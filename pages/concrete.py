#!/usr/bin/env python3
# pages/concrete.py
"""Dash page for managing concrete elements defined by planar nodes + height.

변경 사항
────────
* 프로젝트 목록을 드롭다운 형태로 상단에 배치
* 사용자가 선택한 프로젝트에 해당하는 콘크리트 목록을 DataTable 아래에 표시
* 형상 선택(drop-down) 제거.
* origin, gravity_vec 옵션 삭제.
* ast.literal_eval 로 파싱하여 Python 리터럴 형식의 dims 처리.
* CSV 스키마 변경 → `dims = {"nodes": [[x,y], ...], "h": 높이}`.
* api_concrete.py 시그니처 :
  - add_concrete(project_pk, name, dims)
  - update_concrete(concrete_pk, **kwargs)
* DataTable 열: 이름, 해석 단위(con_unit), 탄성계수(con_e), 베타(con_b), N(con_n)
* DataTable 아래에 “추가/수정/삭제” 버튼 그룹을 배치.
"""
from __future__ import annotations

import ast
import numpy as np
import pandas as pd
import dash  # for no_update
import plotly.graph_objects as go
from dash import (
    html, dcc, Input, Output, State, ctx,
    dash_table, register_page, callback
)
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import api_db

# 프로젝트 메타데이터 로드
projects_df = api_db.get_project_data()

# 페이지 등록
register_page(__name__, path="/concrete", title="콘크리트 관리")

# ────────────────────────────── 3-D 헬퍼 ─────────────────────────────

def make_fig(nodes: list[list[float]], h: float) -> go.Figure:
    fig = go.Figure()
    poly = np.array(nodes)
    x0, y0 = poly[:, 0], poly[:, 1]
    z0 = [0] * len(nodes)
    x1, y1 = x0, y0
    z1 = [h] * len(nodes)
    verts_x = list(x0) + list(x1)
    verts_y = list(y0) + list(y1)
    verts_z = z0 + z1
    n = len(nodes)
    faces = []
    # 바닥면
    for i in range(1, n - 1): faces.append((0, i, i + 1))
    # 상단면
    for i in range(1, n - 1): faces.append((n, n + i + 1, n + i))
    # 측면
    for i in range(n):
        nxt = (i + 1) % n
        faces.append((i, n + i, n + nxt))
        faces.append((i, n + nxt, nxt))
    i0, i1, i2 = zip(*faces)
    fig.add_trace(go.Mesh3d(
        x=verts_x, y=verts_y, z=verts_z,
        i=i0, j=i1, k=i2,
        color="lightgray", opacity=0.35
    ))
    # 에지선
    edges = []
    for xs, ys, zs in [(x0, y0, 0), (x1, y1, h)]:
        for i in range(n):
            edges.extend([(xs[i], ys[i], zs), (xs[(i + 1) % n], ys[(i + 1) % n], zs)])
    # 세로 엣지
    for i in range(n): edges.extend([(x0[i], y0[i], 0), (x1[i], y1[i], h)])
    fig.add_trace(go.Scatter3d(
        x=[e[0] for e in edges], y=[e[1] for e in edges], z=[e[2] for e in edges],
        mode="lines", line=dict(width=4, color="dimgray"), hoverinfo="skip"
    ))
    fig.update_layout(margin=dict(l=0, r=0, b=0, t=0), scene_aspectmode="data")
    return fig

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    children=[
        dbc.Row([
            # 좌측: 프로젝트 드롭다운 + 콘크리트 목록
            dbc.Col([
                dcc.Dropdown(
                    id="project-dropdown",
                    options=[{"label": row["name"], "value": row["project_pk"]} for _, row in projects_df.iterrows()],
                    value=projects_df["project_pk"].iloc[0] if not projects_df.empty else None,
                    clearable=False,
                    className="mb-3"
                ),
                dash_table.DataTable(
                    id="tbl",
                    page_size=20,
                    row_selectable="single",
                    style_table={"overflowY": "auto", "height": "60vh"},
                    style_cell={"whiteSpace": "nowrap", "textAlign": "center"},
                    style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
                ),
                dbc.ButtonGroup([
                    dbc.Button("+ 추가", id="btn-add", color="success", className="mt-2"),
                    dbc.Button("수정", id="btn-edit", color="secondary", className="mt-2", disabled=True),
                    dbc.Button("삭제", id="btn-del",  color="danger", className="mt-2", disabled=True),
                ], size="sm", vertical=True, className="w-100 mt-2"),
            ], md=3),
            # 우측: 3D 뷰
            dbc.Col([
                dbc.Row([dbc.Col(html.H5(id="sel-title"), align="center")], className="mb-1 g-2"),
                dcc.Graph(id="viewer", style={"height": "80vh"}),
            ], md=9),
        ], className="g-3"),

        # 알림, 인터벌, 삭제 확인
        dbc.Alert(id="msg", is_open=False, duration=4000),
        dcc.Interval(id="init", interval=500, n_intervals=0, max_intervals=1),
        dcc.ConfirmDialog(id="confirm-del", message="선택한 콘크리트를 정말 삭제하시겠습니까?"),

        # 추가 모달
        dbc.Modal(id="modal-add", is_open=False, size="lg", children=[
        dbc.ModalHeader("콘크리트 추가"),
            dbc.ModalBody([
                dbc.Input(id="add-name", placeholder="이름", className="mb-2"),
                dbc.Alert(id="add-alert", is_open=False, duration=3000, color="danger"),
                dbc.Textarea(id="add-nodes",
                            placeholder="노드 목록 (예: [(1,0),(1,1),(0,1),(0,0)])",
                            rows=3, className="mb-2"),
                dbc.Input(id="add-h", placeholder="높이 H", type="number", className="mb-2"),
                # ▼ 추가된 필드
                dbc.Input(id="add-unit", placeholder="해석 단위(con_unit, m)", type="number", className="mb-2"),
                dbc.Input(id="add-e",    placeholder="탄성계수(con_e)",    type="number", className="mb-2"),
                dbc.Input(id="add-b",    placeholder="베타 상수(con_b)",     type="number", className="mb-2"),
                dbc.Input(id="add-n",    placeholder="N 상수(con_n)",       type="number", className="mb-2"),
                dcc.Graph(id="add-preview", style={"height": "45vh"}, className="border"),
            ]),
            dbc.ModalFooter([
                dbc.Button("미리보기", id="add-build", color="info", className="me-auto"),
                dbc.Button("저장",     id="add-save",  color="primary"),
                dbc.Button("닫기",     id="add-close", color="secondary"),
            ]),
        ]),

        # 수정 모달
        dbc.Modal(id="modal-edit", is_open=False, size="lg", children=[
            dbc.ModalHeader("콘크리트 수정"),
            dbc.ModalBody([
                dcc.Store(id="edit-id"),
                dbc.Input(id="edit-name", className="mb-2"),
                dbc.Alert(id="edit-alert", is_open=False, duration=3000, color="danger"),
                dbc.Textarea(id="edit-nodes", rows=3, className="mb-2"),
                dbc.Input(id="edit-h", type="number", className="mb-2"),
                dcc.Graph(id="edit-preview", style={"height": "45vh"}, className="border"),
            ]),
            dbc.ModalFooter([
                dbc.Button("미리보기", id="edit-build", color="info", className="me-auto"),
                dbc.Button("저장", id="edit-save", color="primary"),
                dbc.Button("닫기", id="edit-close", color="secondary"),
            ]),
        ]),
    ]
)

# ───────────────────── ① 테이블 로드 및 필터링
@callback(
    Output("tbl", "data"),
    Output("tbl", "columns"),
    Output("tbl", "selected_rows"),
    Input("init", "n_intervals"),
    Input("project-dropdown", "value"),
    prevent_initial_call=False
)
def refresh_table(n, project_pk):
    df_all = api_db.get_concrete_data()
    if project_pk:
        df = df_all[df_all["project_pk"] == project_pk]
    else:
        df = pd.DataFrame(columns=df_all.columns)
    cols = [
        {"name": "이름", "id": "name"},
        {"name": "해석 단위(m)", "id": "con_unit"},
        {"name": "탄성계수", "id": "con_e"},
        {"name": "베타", "id": "con_b"},
        {"name": "N", "id": "con_n"},
    ]
    sel = [0] if not df.empty else []
    return df.to_dict("records"), cols, sel

# ───────────────────── ② 선택된 행 → 3-D 뷰
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
    title = f"{row['concrete_pk']} · {row['name']}"
    return make_fig(dims['nodes'], dims['h']), title, False, False

# 이하 모달, 추가/수정/삭제 콜백은 기존과 동일
# (생략 가능하지만 편의를 위해 기존 코드를 그대로 유지)


# ───────────────────── ③ 추가 모달 토글
@callback(
    Output("modal-add", "is_open"),
    Input("btn-add", "n_clicks"),
    Input("add-close", "n_clicks"),
    Input("add-save", "n_clicks"),
    State("modal-add", "is_open"),
    prevent_initial_call=True
)
def toggle_add(b1, b2, b3, is_open):
    trig = ctx.triggered_id
    if trig == "btn-add":
        return True
    if trig in ("add-close", "add-save"):
        return False
    return is_open

# ───────────────────── ④ 추가 미리보기
@callback(
    Output("add-preview", "figure"),
    Output("add-alert",   "children", allow_duplicate=True),
    Output("add-alert",   "is_open",   allow_duplicate=True),
    Input("add-build", "n_clicks"),
    State("add-nodes", "value"),
    State("add-h", "value"),
    prevent_initial_call=True
)
def add_preview(_, nodes_txt, h):
    if not nodes_txt:
        return dash.no_update, "노드 목록 입력요", True
    try:
        nodes = ast.literal_eval(nodes_txt)
        assert isinstance(nodes, list)
    except Exception:
        return dash.no_update, "노드 형식 오류", True
    if h is None:
        return dash.no_update, "높이 입력요", True
    return make_fig(nodes, float(h)), "", False

# ───────────────────── ⑤ 추가 저장
@callback(
    Output("add-alert",  "children",        allow_duplicate=True),
    Output("add-alert",  "is_open",          allow_duplicate=True),
    Output("tbl",        "data_timestamp",   allow_duplicate=True),
    Output("modal-add",  "is_open",          allow_duplicate=True),
    Input("add-save",    "n_clicks"),
    State("project-dropdown", "value"),
    State("add-name",    "value"),
    State("add-nodes",   "value"),
    State("add-h",       "value"),
    State("add-unit",    "value"),
    State("add-e",       "value"),
    State("add-b",       "value"),
    State("add-n",       "value"),
    prevent_initial_call=True
)
def add_save(n_clicks, project_pk, name, nodes_txt, h, unit, e, b, n):
    # 클릭이 없으면 무시
    if not n_clicks:
        raise PreventUpdate

    # 빈 값 체크
    missing = []
    if not project_pk: missing.append("프로젝트")
    if not name:       missing.append("이름")
    if not nodes_txt:  missing.append("노드 목록")
    if h    is None:   missing.append("높이 H")
    if unit is None:   missing.append("해석 단위")
    if e    is None:   missing.append("탄성계수")
    if b    is None:   missing.append("베타 상수")
    if n    is None:   missing.append("N 상수")

    if missing:
        return f"{', '.join(missing)}을(를) 입력해주세요.", True, dash.no_update, True

    # 노드 파싱
    try:
        nodes = ast.literal_eval(nodes_txt)
        assert isinstance(nodes, list)
    except Exception:
        return "노드 형식이 잘못되었습니다.", True, dash.no_update, True

    # DB 저장 (activate를 0으로 고정)
    dims = {"nodes": nodes, "h": float(h)}
    api_db.add_concrete_data(
        project_pk=project_pk,
        name=name.strip(),
        dims=dims,
        con_unit=float(unit),
        con_e=float(e),
        con_b=float(b),
        con_n=float(n),
        activate=0
    )

    # 성공 시: 모달 닫기, Alert 숨기기, 테이블 갱신
    return "", False, pd.Timestamp.utcnow().value, False

# ───────────────────── ⑥ 삭제 수행
@callback(
    Output("confirm-del", "displayed"),
    Input("btn-del", "n_clicks"),
    State("tbl", "selected_rows"),
    prevent_initial_call=True
)
def ask_delete(n, sel):
    return bool(n and sel)

@callback(
    Output("tbl", "data_timestamp", allow_duplicate=True),
    Output("msg", "children", allow_duplicate=True),
    Output("msg", "color", allow_duplicate=True),
    Output("msg", "is_open", allow_duplicate=True),
    Input("confirm-del", "submit_n_clicks"),
    State("tbl", "selected_rows"),
    State("tbl", "data"),
    prevent_initial_call=True
)
def delete_row(_, sel, data):
    if not sel:
        raise PreventUpdate
    cid = data[sel[0]]["concrete_pk"]
    api_db.delete_concrete_data(cid)
    return pd.Timestamp.utcnow().value, f"{cid} 삭제 완료", "warning", True

# ───────────────────── ⑦ 수정 모달 열기
@callback(
    Output("modal-edit", "is_open"),
    Output("edit-id", "data"),
    Input("btn-edit", "n_clicks"),
    Input("edit-close", "n_clicks"),
    State("tbl", "selected_rows"),
    State("tbl", "data"),
    prevent_initial_call=True
)
def open_edit(b1, b2, sel, data):
    if ctx.triggered_id == "btn-edit" and sel:
        return True, data[sel[0]]["concrete_pk"]
    return False, dash.no_update

# ───────────────────── ⑧ 수정 필드 채우기
@callback(
    Output("edit-name", "value"),
    Output("edit-nodes", "value"),
    Output("edit-h", "value"),
    Output("edit-preview", "figure"),
    Input("modal-edit", "is_open"),
    State("edit-id", "data"),
    prevent_initial_call=True
)
def fill_edit(opened, cid):
    if not opened or not cid:
        raise PreventUpdate

    # 1) 데이터 조회
    df = api_db.get_concrete_data(cid)

    # 2) 유효성 검사: None 또는 빈 DataFrame이면 취소
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        raise PreventUpdate

    # 3) DataFrame이면 첫 행을 꺼내 dict로, 아니면 그대로 dict로 가정
    if isinstance(df, pd.DataFrame):
        row = df.iloc[0].to_dict()
    else:
        row = df  # 이미 dict일 때

    # 4) dims는 dict 형태로 저장되어 있다고 가정
    dims = row.get("dims", {})

    return (
        # 수정 모달의 각 필드에 값을 채워줌
        row.get("name", ""),
        str(dims.get("nodes", [])),
        dims.get("h", 0),
        make_fig(dims.get("nodes", []), dims.get("h", 0))
    )

# ───────────────────── ⑨ 수정 미리보기
@callback(
    Output("edit-preview", "figure", allow_duplicate=True),
    Output("edit-alert", "children"),
    Output("edit-alert", "is_open"),
    Input("edit-build", "n_clicks"),
    State("edit-nodes", "value"),
    State("edit-h", "value"),
    prevent_initial_call=True
)
def edit_preview(_, nodes_txt, h):
    if not nodes_txt:
        return dash.no_update, "노드 입력", True
    try:
        nodes = ast.literal_eval(nodes_txt)
    except Exception:
        return dash.no_update, "노드 형식 오류", True
    if not isinstance(nodes, list):
        return dash.no_update, "노드 형식 오류", True
    if h is None:
        return dash.no_update, "높이 입력", True
    return make_fig(nodes, float(h)), "", False

# ───────────────────── ⑩ 수정 저장
@callback(
    Output("tbl", "data_timestamp", allow_duplicate=True),
    Output("msg", "children", allow_duplicate=True),
    Output("msg", "color", allow_duplicate=True),
    Output("msg", "is_open", allow_duplicate=True),
    Input("edit-save", "n_clicks"),
    State("edit-id", "data"),
    State("edit-name", "value"),
    State("edit-nodes", "value"),
    State("edit-h", "value"),
    prevent_initial_call=True
)
def save_edit(_, cid, name, nodes_txt, h):
    if not (cid and name and nodes_txt):
        return dash.no_update, "입력 누락", "danger", True
    try:
        nodes = ast.literal_eval(nodes_txt)
    except Exception:
        return dash.no_update, "노드 형식 오류", "danger", True
    if not isinstance(nodes, list):
        return dash.no_update, "노드 형식 오류", "danger", True
    if h is None:
        return dash.no_update, "높이 입력", "danger", True
    dims = {"nodes": nodes, "h": float(h)}
    api_db.update_concrete_data(cid, name=name, dims=dims)
    return pd.Timestamp.utcnow().value, f"{cid} 수정 완료", "success", True
