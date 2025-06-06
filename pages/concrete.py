#!/usr/bin/env python3
# pages/concrete.py
"""Dash page for managing concrete elements defined by planar nodes + height.

변경 사항
────────
* 형상 선택(drop-down) 제거.
* 사용자가 평면상의 노드 목록과 높이(H)를 직접 입력하도록 UI 전면 개편.
* origin, gravity_vec 옵션 삭제.
* JSON 대신 `ast.literal_eval` 로 파싱하여 Python 리터럴 형식의 dims 처리.
* CSV 스키마 변경 → `dims = {"nodes": [[x,y], ...], "h": 높이}` (Python dict 문자열).
* `make_fig` : 임의 다각형을 높이 H 만큼 압출(extrude)하여 3-D 메쉬·Edge 생성.
* API 시그니처 : `api.add_concrete(name, dims)` / `api.update_concrete(cid, name, dims, {})`.
* 왼쪽 DataTable 아래에 “추가/수정/삭제” 버튼 그룹을 배치(센서 페이지와 동일한 형태).
"""
from __future__ import annotations

import ast
import numpy as np
import pandas as pd
import dash  # no_update 등을 사용하기 위해 dash 모듈을 추가합니다
import plotly.graph_objects as go
from dash import (
    html, dcc, Input, Output, State, ctx,
    dash_table, register_page, callback
)
import dash_bootstrap_components as dbc
import api_concrete as api          # CSV CRUD
from dash.exceptions import PreventUpdate

register_page(__name__, path="/concrete")

# ────────────────────────────── 3-D 헬퍼 ─────────────────────────────

def make_fig(nodes: list[list[float]], h: float) -> go.Figure:
    """nodes: [[x,y], ...], h: 높이 ⇒ plotly 3-D Figure"""
    fig = go.Figure()
    poly = np.array(nodes)
    x0, y0 = poly[:,0], poly[:,1]
    z0 = np.zeros(len(nodes))
    x1, y1 = x0, y0
    z1 = np.full(len(nodes), h)
    verts_x = np.concatenate([x0, x1])
    verts_y = np.concatenate([y0, y1])
    verts_z = np.concatenate([z0, z1])
    n = len(nodes)
    faces = []
    # 바닥면
    for i in range(1, n-1):
        faces.append((0, i, i+1))
    # 상단면 (반대 순서)
    for i in range(1, n-1):
        faces.append((n, n+i+1, n+i))
    # 측면면
    for i in range(n):
        nxt = (i+1) % n
        faces.append((i, nxt, n+nxt))
        faces.append((i, n+nxt, n+i))
    i0, i1, i2 = zip(*faces)
    fig.add_trace(go.Mesh3d(
        x=verts_x, y=verts_y, z=verts_z,
        i=i0, j=i1, k=i2,
        color="lightgray", opacity=0.35
    ))
    edges = []
    # 바닥
    for i in range(n):
        edges.append((x0[i], y0[i], 0))
        edges.append((x0[(i+1)%n], y0[(i+1)%n], 0))
    # 상단
    for i in range(n):
        edges.append((x1[i], y1[i], h))
        edges.append((x1[(i+1)%n], y1[(i+1)%n], h))
    # 세로 모서리
    for i in range(n):
        edges.append((x0[i], y0[i], 0))
        edges.append((x1[i], y1[i], h))
    fig.add_trace(go.Scatter3d(
        x=[p[0] for p in edges], y=[p[1] for p in edges], z=[p[2] for p in edges],
        mode="lines", line=dict(width=4, color="dimgray"), hoverinfo="skip"
    ))
    fig.update_layout(margin=dict(l=0, r=0, b=0, t=0), scene_aspectmode="data")
    return fig

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True, 
    children=[
    # 좌측 목록 + 우측 3-D 뷰
    dbc.Row([
        dbc.Col([
            dash_table.DataTable(
                id="tbl",
                page_size=20,
                row_selectable="single",
                style_table={"overflowY": "auto", "height": "65vh"},
                style_cell={"whiteSpace": "nowrap", "textAlign": "center"},
                style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
            ),
            dbc.ButtonGroup(
                [
                    dbc.Button("+ 추가", id="btn-add", color="success", className="mt-2"),
                    dbc.Button("수정", id="btn-edit", color="secondary", className="mt-2", disabled=True),
                    dbc.Button("삭제", id="btn-del",  color="danger", className="mt-2", disabled=True),
                ],
                size="sm",
                vertical=True,
                className="w-100",
            )
        ], md=3),

        dbc.Col([
            dbc.Row([
                dbc.Col(html.H5(id="sel-title"), align="center"),
                # 오른쪽 상단 버튼 그룹 제거(이 부분이 삭제됨)
            ], className="mb-1 g-2"),
            dcc.Graph(id="viewer", style={"height": "80vh"}),
        ], md=9),
    ], className="g-3"),

    dbc.Alert(id="msg", is_open=False, duration=4000),
    dcc.Interval(id="init", interval=500, n_intervals=0, max_intervals=1),
    dcc.ConfirmDialog(id="confirm-del", message="선택한 콘크리트를 정말 삭제하시겠습니까?"),

    # ── 추가 모달 ──────────────────────────────────────────
    dbc.Modal(id="modal-add", is_open=False, size="lg", children=[
        dbc.ModalHeader("콘크리트 추가"),
        dbc.ModalBody([
            dbc.Input(id="add-name", placeholder="이름", className="mb-2"),
            dbc.Alert(id="add-alert", is_open=False, duration=3000, color="danger"),
            dbc.Row([
                dbc.Col(
                    dbc.Textarea(
                        id="add-nodes",
                        placeholder="노드 목록 (예: [(1,0),(1,1),(0,1),(0,0)])",
                        rows=3
                    ),
                    width=12
                ),
                dbc.Col(
                    dbc.Input(id="add-h", placeholder="높이 H", type="number"),
                    width=12
                )
            ], className="mb-2"),
            dcc.Graph(id="add-preview", style={"height": "45vh"}, className="border"),
        ]),
        dbc.ModalFooter([
            dbc.Button("미리보기", id="add-build", color="info", className="me-auto"),
            dbc.Button("저장",     id="add-save",  color="primary"),
            dbc.Button("닫기",     id="add-close", color="secondary"),
        ]),
    ]),

    # ── 수정 모달 ──────────────────────────────────────────
    dbc.Modal(id="modal-edit", is_open=False, size="lg", children=[
        dbc.ModalHeader("콘크리트 수정"),
        dbc.ModalBody([
            dcc.Store(id="edit-id"),
            dbc.Input(id="edit-name", className="mb-2"),
            dbc.Alert(id="edit-alert", is_open=False, duration=3000, color="danger"),
            dbc.Row([
                dbc.Col(
                    dbc.Textarea(id="edit-nodes", rows=3),
                    width=12
                ),
                dbc.Col(
                    dbc.Input(id="edit-h", type="number"),
                    width=12
                )
            ], className="mb-2"),
            dcc.Graph(id="edit-preview", style={"height": "45vh"}, className="border"),
        ]),
        dbc.ModalFooter([
            dbc.Button("미리보기", id="edit-build", color="info", className="me-auto"),
            dbc.Button("저장",     id="edit-save",  color="primary"),
            dbc.Button("닫기",     id="edit-close", color="secondary"),
        ]),
    ]),
])

# ───────────────────── ① 테이블 로드 ──────────────────────
@callback(
    Output("tbl", "data"),
    Output("tbl", "columns"),
    Output("tbl", "selected_rows"),
    Input("init", "n_intervals"),
    Input("tbl", "data_timestamp"),
    prevent_initial_call=False
)
def refresh_table(_, __):
    df = api.load_all()
    cols = [
        {"name": "ID",   "id": "concrete_id"},
        {"name": "이름", "id": "name"}
    ]
    # 테이블이 비어있지 않으면 첫 번째 행을 기본 선택
    sel = [0] if not df.empty else []
    return df.to_dict("records"), cols, sel

# ───────────────────── ② 행 선택 → 3-D ────────────────────
@callback(
    Output("viewer", "figure"),
    Output("sel-title", "children"),
    Output("btn-edit", "disabled"),
    Output("btn-del", "disabled"),
    Input("tbl", "selected_rows"),
    State("tbl", "data"),
    prevent_initial_call=True
)
def show_selected(sel, data):
    if not sel:
        return go.Figure(), "", True, True

    row = pd.DataFrame(data).iloc[sel[0]]
    try:
        dims = ast.literal_eval(row["dims"])
    except Exception:
        raise PreventUpdate

    nodes, h = dims.get("nodes"), dims.get("h")
    title = f"{row['concrete_id']} · {row['name']}"
    return make_fig(nodes, h), title, False, False

# ───────────────────── ③ 추가-모달 토글 ─────────────────────
@callback(
    Output("modal-add", "is_open"),
    Input("btn-add",   "n_clicks"),
    Input("add-close", "n_clicks"),
    Input("add-save",  "n_clicks"),
    State("modal-add","is_open"),
    prevent_initial_call=True,
)
def toggle_add_modal(b_add, b_close, b_save, is_open):
    trig = ctx.triggered_id
    if trig == "btn-add":
        return True
    if trig in ("add-close", "add-save"):
        return False
    return is_open

# ───────────────────── ④ 추가-미리보기 ─────────────────────
@callback(
    Output("add-preview", "figure"),
    Output("add-alert",   "children"),
    Output("add-alert",   "is_open"),
    Input("add-build", "n_clicks"),
    State("add-nodes","value"),
    State("add-h","value"),
    prevent_initial_call=True,
)
def add_preview(_, nodes_txt, h):
    if not nodes_txt:
        return dash.no_update, "노드 목록을 입력하세요", True
    try:
        nodes = ast.literal_eval(nodes_txt)
        if not isinstance(nodes, list) or not all(
            isinstance(pt, (list, tuple)) and len(pt)==2 for pt in nodes
        ):
            raise ValueError
    except Exception:
        return dash.no_update, "노드 형식이 잘못되었습니다", True
    if h is None:
        return dash.no_update, "높이를 입력하세요", True

    return make_fig(nodes, float(h)), "", False

# ───────────────────── ⑤ 추가-저장 ────────────────────────
@callback(
    Output("msg","children",           allow_duplicate=True),
    Output("msg","color",              allow_duplicate=True),
    Output("msg","is_open",            allow_duplicate=True),
    Output("tbl","data_timestamp",     allow_duplicate=True),
    Input("add-save","n_clicks"),
    State("add-name","value"),
    State("add-nodes","value"),
    State("add-h","value"),
    prevent_initial_call=True,
)
def add_save(_, name, nodes_txt, h):
    if not (name and nodes_txt):
        return "이름과 노드 목록을 입력하세요", "danger", True, dash.no_update
    try:
        nodes = ast.literal_eval(nodes_txt)
    except Exception:
        return "노드 형식이 잘못되었습니다", "danger", True, dash.no_update

    if not isinstance(nodes, list) or not all(
        isinstance(pt, (list, tuple)) and len(pt)==2 for pt in nodes
    ):
        return "노드 형식이 잘못되었습니다", "danger", True, dash.no_update
    if h is None:
        return "높이를 입력하세요", "danger", True, dash.no_update

    dims = {"nodes": nodes, "h": float(h)}
    api.add_concrete(name, dims)
    return "추가 완료", "success", True, pd.Timestamp.utcnow().value

# ───────────────────── ⑥ 삭제 (확인→실행) ───────────────────
@callback(
    Output("confirm-del", "displayed"),
    Input("btn-del", "n_clicks"),
    State("tbl","selected_rows"),
    prevent_initial_call=True
)
def ask_delete(n, sel):
    return bool(n and sel)

@callback(
    Output("tbl", "data_timestamp", allow_duplicate=True),
    Output("msg", "children",         allow_duplicate=True),
    Output("msg", "color",            allow_duplicate=True),
    Output("msg", "is_open",          allow_duplicate=True),
    Input("confirm-del", "submit_n_clicks"),
    State("tbl", "selected_rows"),
    State("tbl", "data"),
    prevent_initial_call=True,
)
def delete_row(_, sel, data):
    if not sel:
        raise PreventUpdate

    cid = data[sel[0]]["concrete_id"]
    api.delete_concrete(cid)
    return pd.Timestamp.utcnow().value, f"{cid} 삭제 완료", "warning", True

# ───────────────────── ⑦ 수정-모달 열기 ─────────────────────
@callback(
    Output("modal-edit", "is_open"),
    Output("edit-id",    "data"),
    Input("btn-edit", "n_clicks"),
    Input("edit-close", "n_clicks"),
    Input("edit-save",  "n_clicks"),
    State("tbl", "selected_rows"),
    State("tbl", "data"),
    prevent_initial_call=True,
)
def open_edit(b_open, b_close, b_save, sel, data):
    trig = ctx.triggered_id
    if trig == "btn-edit" and sel:
        return True, data[sel[0]]["concrete_id"]
    return False, dash.no_update

# ───────────────────── ⑧ 수정-모달 필드 채우기 ───────────────
@callback(
    Output("edit-name",  "value"),
    Output("edit-nodes","value"),
    Output("edit-h","value"),
    Output("edit-preview","figure"),
    Input("modal-edit","is_open"),
    State("edit-id","data"),
    prevent_initial_call=True,
)
def fill_edit(opened, cid):
    if not opened or not cid:
        raise PreventUpdate

    row   = api.load_all().query("concrete_id == @cid").iloc[0]
    dims  = ast.literal_eval(row["dims"])
    nodes, h = dims.get("nodes"), dims.get("h")
    fig   = make_fig(nodes, h)
    return row["name"], str(nodes), h, fig

# ───────────────────── ⑨ 수정-미리보기 ─────────────────────
@callback(
    Output("edit-preview","figure", allow_duplicate=True),
    Output("edit-alert",  "children"),
    Output("edit-alert","is_open"),
    Input("edit-build","n_clicks"),
    State("edit-nodes","value"),
    State("edit-h","value"),
    prevent_initial_call=True,
)
def edit_preview(_, nodes_txt, h):
    if not nodes_txt:
        return dash.no_update, "노드 목록을 입력하세요", True
    try:
        nodes = ast.literal_eval(nodes_txt)
    except Exception:
        return dash.no_update, "노드 형식이 잘못되었습니다", True

    if not isinstance(nodes, list) or not all(
        isinstance(pt, (list, tuple)) and len(pt)==2 for pt in nodes
    ):
        return dash.no_update, "노드 형식이 잘못되었습니다", True
    if h is None:
        return dash.no_update, "높이를 입력하세요", True

    return make_fig(nodes, float(h)), "", False

# ───────────────────── ⑩ 수정-저장 ────────────────────────
@callback(
    Output("tbl","data_timestamp",     allow_duplicate=True),
    Output("msg","children",           allow_duplicate=True),
    Output("msg","color",              allow_duplicate=True),
    Output("msg","is_open",            allow_duplicate=True),
    Input("edit-save","n_clicks"),
    State("edit-id","data"),
    State("edit-name","value"),
    State("edit-nodes","value"),
    State("edit-h","value"),
    prevent_initial_call=True,
)
def save_edit(_, cid, name, nodes_txt, h):
    if not cid or not (name and nodes_txt):
        return dash.no_update, "입력 누락!", "danger", True

    try:
        nodes = ast.literal_eval(nodes_txt)
    except Exception:
        return dash.no_update, "노드 형식이 잘못되었습니다", "danger", True

    if not isinstance(nodes, list) or not all(
        isinstance(pt, (list, tuple)) and len(pt)==2 for pt in nodes
    ):
        return dash.no_update, "노드 형식이 잘못되었습니다", "danger", True
    if h is None:
        return dash.no_update, "높이를 입력하세요", "danger", True

    dims = {"nodes": nodes, "h": float(h)}
    api.update_concrete(cid, name, dims)
    return pd.Timestamp.utcnow().value, f"{cid} 수정 완료", "success", True
