#!/usr/bin/env python3
# pages/concrete.py
from __future__ import annotations

import json, numpy as np, pandas as pd
import plotly.graph_objects as go
from dash import (
    html, dcc, Input, Output, State, ctx,
    dash_table, register_page, callback, dash
)
import dash_bootstrap_components as dbc
import api                     # CSV CRUD
from dash.exceptions import PreventUpdate

register_page(__name__, path="/concrete")

# ─── 공통 상수 ──────────────────────────────────────────────
REQ_DIM = {
    "rect":     ("w", "l", "h"),
    "cylinder": ("r", "h"),
    "sphere":   ("r",),
    "arch":     ("span", "rise", "thk"),
}
SHAPES = [
    {"label": "직사각형", "value": "rect"},
    {"label": "원기둥",   "value": "cylinder"},
    {"label": "구",      "value": "sphere"},
    {"label": "아치",    "value": "arch"},
]
show = lambda f: {"display": "block"} if f else {"display": "none"}

# ────────────────────────────── 3-D 헬퍼 ─────────────────────────────
def make_fig(shape: str, dims: dict, aux: dict | str | None = None) -> go.Figure:
    """shape·dims(필수) + aux(origin·gravity_vec) ⇒ plotly 3-D Figure"""
    fig = go.Figure()

    # ── 본체 ----------------------------------------------------------
    if shape == "rect":
        w, l, h = dims["w"], dims["l"], dims["h"]
        x, y, z = np.meshgrid([0, w], [0, l], [0, h])
        fig.add_trace(go.Mesh3d(
            x=x.flatten(), y=y.flatten(), z=z.flatten(),
            color="lightgray", opacity=0.35, alphahull=0
        ))
        # 모서리
        edges = [(0,0,0),(w,0,0),(w,l,0),(0,l,0),(0,0,0),
                 (0,0,h),(w,0,h),(w,l,h),(0,l,h),(0,0,h),
                 (w,0,h),(w,0,0),(w,l,0),(w,l,h),(0,l,h),(0,l,0)]
        fig.add_trace(go.Scatter3d(
            x=[p[0] for p in edges], y=[p[1] for p in edges], z=[p[2] for p in edges],
            mode="lines", line=dict(width=4, color="dimgray"), hoverinfo="skip"
        ))

    elif shape == "cylinder":
        r, h = dims["r"], dims["h"]
        th, zz = np.linspace(0, 2*np.pi, 60), np.linspace(0, h, 2)
        th, zz = np.meshgrid(th, zz)
        fig.add_trace(go.Surface(
            x=r*np.cos(th), y=r*np.sin(th), z=zz,
            showscale=False, opacity=0.35,
            colorscale=[[0, 'lightgray'], [1, 'lightgray']]
        ))
        circ = np.linspace(0, 2*np.pi, 60)
        for z0 in (0, h):
            fig.add_trace(go.Scatter3d(
                x=r*np.cos(circ), y=r*np.sin(circ), z=[z0]*len(circ),
                mode="lines", line=dict(width=4, color="dimgray"), hoverinfo="skip"
            ))
        for a in (0, np.pi/2, np.pi, np.pi*3/2):
            fig.add_trace(go.Scatter3d(
                x=[r*np.cos(a)]*2, y=[r*np.sin(a)]*2, z=[0, h],
                mode="lines", line=dict(width=4, color="dimgray"), hoverinfo="skip"
            ))

    elif shape == "sphere":
        r = dims["r"]
        u, v = np.mgrid[0:2*np.pi:60j, 0:np.pi:30j]
        fig.add_trace(go.Surface(
            x=r*np.cos(u)*np.sin(v), y=r*np.sin(u)*np.sin(v), z=r*np.cos(v),
            showscale=False, opacity=0.35,
            colorscale=[[0, 'lightgray'], [1, 'lightgray']]
        ))
        circ = np.linspace(0, 2*np.pi, 120)
        fig.add_trace(go.Scatter3d(
            x=r*np.cos(circ), y=r*np.sin(circ), z=[0]*len(circ),
            mode="lines", line=dict(width=4, color="dimgray"), hoverinfo="skip"
        ))
        fig.add_trace(go.Scatter3d(
            x=r*np.cos(circ), y=[0]*len(circ), z=r*np.sin(circ),
            mode="lines", line=dict(width=4, color="dimgray"), hoverinfo="skip"
        ))
        fig.add_trace(go.Scatter3d(
            x=[0]*len(circ), y=r*np.cos(circ), z=r*np.sin(circ),
            mode="lines", line=dict(width=4, color="dimgray"), hoverinfo="skip"
        ))

    elif shape == "arch":
        span, rise, thk = dims["span"], dims["rise"], dims["thk"]
        x = np.linspace(-span/2, span/2, 120)
        y = rise * (1 - (2*x/span)**2)
        fig.add_trace(go.Surface(
            x=np.tile(x, (2,1)), y=np.tile(y, (2,1)),
            z=np.array([[0]*len(x), [thk]*len(x)]),
            showscale=False, opacity=0.35,
            colorscale=[[0, 'lightgray'], [1, 'lightgray']]
        ))
        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=[0]*len(x), mode="lines",
            line=dict(width=4, color="dimgray"), hoverinfo="skip"
        ))
        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=[thk]*len(x), mode="lines",
            line=dict(width=4, color="dimgray"), hoverinfo="skip"
        ))
        for xi, yi in ((x[0], y[0]), (x[-1], y[-1])):
            fig.add_trace(go.Scatter3d(
                x=[xi]*2, y=[yi]*2, z=[0, thk],
                mode="lines", line=dict(width=4, color="dimgray"), hoverinfo="skip"
            ))

    # ── origin & gravity ------------------------------------------------
    if isinstance(aux, str):
        try:
            aux = json.loads(aux)
        except Exception:
            aux = None
    if aux:
        ox, oy, oz = map(float, aux.get("origin", "0,0,0").split(","))
        fig.add_trace(go.Scatter3d(
            x=[ox], y=[oy], z=[oz], mode="markers+text",
            marker=dict(size=5, color="red"),
            text=["기준점"], textposition="bottom center", showlegend=False
        ))
        L  = max(dims.values()) * 0.25
        gv = aux.get("gravity_vec", "0,0,-1")
        gx, gy, gz = map(float, gv.split(","))
        if (gx, gy, gz) != (0, 0, 0):
            norm = (gx**2 + gy**2 + gz**2)**0.5
            dx, dy, dz = np.array([gx, gy, gz]) / norm * L
            fig.add_trace(go.Scatter3d(
                x=[ox, ox+dx*0.9], y=[oy, oy+dy*0.9], z=[oz, oz+dz*0.9],
                mode="lines", line=dict(width=4, color="firebrick"), hoverinfo="skip"
            ))
            fig.add_trace(go.Cone(
                x=[ox+dx*0.9], y=[oy+dy*0.9], z=[oz+dz*0.9],
                u=[dx*0.1], v=[dy*0.1], w=[dz*0.1],
                showscale=False, anchor="tail",
                colorscale=[[0, "firebrick"], [1, "firebrick"]],
                sizemode="absolute", sizeref=L*0.1
            ))

    fig.update_layout(margin=dict(l=0, r=0, b=0, t=0), scene_aspectmode="data")
    return fig

# ─── 공통 입력 Row ─────────────────────────────────────────
def dim_input_row(prefix: str, hidden=True):
    style = {"display": "none"} if hidden else {}
    num   = lambda sid, ph: dbc.Input(id=f"{prefix}-{sid}", placeholder=ph,
                                      type="number", style=style)
    return dbc.Row([
        dbc.Col(num("w",   "W")),  dbc.Col(num("l", "L")),   dbc.Col(num("h",   "H")),
        dbc.Col(num("r",   "R")),
        dbc.Col(num("span","Span")), dbc.Col(num("rise","Rise")), dbc.Col(num("thk","Thk")),
    ], className="g-2 mb-2")

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(fluid=True, children=[
    # 좌측 목록 + 우측 3-D 뷰
    dbc.Row([
        dbc.Col([
            dash_table.DataTable(
                id="tbl", page_size=20, row_selectable="single",
                style_table={"overflowY": "auto", "height": "75vh"},
                style_cell={"whiteSpace": "nowrap", "textAlign": "center"},
                style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
            ),
            dbc.Button("+ 추가", id="btn-add", color="success", className="mt-2 w-100"),
        ], md=3),
        dbc.Col([
            dbc.Row([
                dbc.Col(html.H5(id="sel-title"), align="center"),
                dbc.Col(dbc.ButtonGroup([
                    dbc.Button("수정", id="btn-edit", color="secondary", disabled=True),
                    dbc.Button("삭제", id="btn-del",  color="danger",    disabled=True),
                ], size="sm"), width="auto"),
            ], className="mb-1 g-2"),
            dcc.Graph(id="viewer", style={"height": "70vh"}),
        ], md=9),
    ], className="g-3"),

    dbc.Alert(id="msg", is_open=False, duration=4000),
    dcc.Interval(id="init", interval=500, n_intervals=0, max_intervals=1),
    dcc.ConfirmDialog(id="confirm-del",
                      message="선택한 콘크리트를 정말 삭제하시겠습니까?"),

    # ── 추가 모달 ──────────────────────────────────────────
    dbc.Modal(id="modal-add", is_open=False, size="lg", children=[
        dbc.ModalHeader("콘크리트 추가"),
        dbc.ModalBody([
            dbc.Input(id="add-name", placeholder="이름", className="mb-2"),
            dcc.Dropdown(SHAPES, id="add-shape", placeholder="형상", className="mb-3"),
            dbc.Alert(id="add-alert", is_open=False, duration=3000, color="danger"),
            dim_input_row("add"),
            dbc.Row([
                dbc.Col(dbc.Input(id="add-origin", value="0,0,0",
                                  placeholder="origin (x,y,z)"), md=6),
                dbc.Col(dbc.Input(id="add-gvec", value="0,0,-1",
                                  placeholder="gravity (x,y,z)"), md=6),
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
            dcc.Dropdown(SHAPES, id="edit-shape", className="mb-3"),
            dbc.Alert(id="edit-alert", is_open=False, duration=3000, color="danger"),
            dim_input_row("edit"),
            dbc.Row([
                dbc.Col(dbc.Input(id="edit-origin"), md=6),
                dbc.Col(dbc.Input(id="edit-gvec"),   md=6),
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
    Output("tbl", "data"), Output("tbl", "columns"), Output("tbl", "selected_rows"),
    Input("init", "n_intervals"), Input("tbl", "data_timestamp"),
    prevent_initial_call=False
)
def refresh_table(_, __):
    df = api.load_all()
    cols = [{"name": "ID", "id": "concrete_id"},
            {"name": "이름", "id": "name"},
            {"name": "형상", "id": "shape"}]
    return df.to_dict("records"), cols, ([0] if not df.empty else [])

# ───────────────────── ② 행 선택 → 3-D ────────────────────
@callback(
    Output("viewer", "figure"), Output("sel-title", "children"),
    Output("btn-edit", "disabled"), Output("btn-del", "disabled"),
    Input("tbl", "selected_rows"), State("tbl", "data")
)
def show_selected(sel, data):
    if not sel:
        return go.Figure(), "", True, True
    row = pd.DataFrame(data).iloc[sel[0]]
    dims, aux = json.loads(row["dims"]), json.loads(row["aux"])
    title = f"{row['concrete_id']} · {row['name']} ({row['shape']})"
    return make_fig(row["shape"], dims, aux), title, False, False

# ───────────────────── ③ 추가-모달 토글 ───────────────────
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

# ───────────────────── ④ 형상 변경 → 입력칸 토글 ──────────
@callback(
    Output("add-w","style"), Output("add-l","style"), Output("add-h","style"),
    Output("add-r","style"),
    Output("add-span","style"), Output("add-rise","style"), Output("add-thk","style"),
    Input("add-shape","value"), prevent_initial_call=True
)
def add_toggle(shape):
    vis = REQ_DIM.get(shape, ())
    return (show("w" in vis), show("l" in vis), show("h" in vis),
            show("r" in vis), show("span" in vis),
            show("rise" in vis), show("thk" in vis))

# ───────────────────── ⑤ 추가-미리보기 ─────────────────────
@callback(
    Output("add-preview", "figure"),
    Output("add-alert",   "children"), Output("add-alert", "is_open"),
    Input("add-build", "n_clicks"),
    State("add-shape","value"),
    State("add-w","value"),  State("add-l","value"),  State("add-h","value"),
    State("add-r","value"),  State("add-span","value"),
    State("add-rise","value"),State("add-thk","value"),
    State("add-origin","value"), State("add-gvec","value"),
    prevent_initial_call=True,
)
def add_preview(_, shape, w,l,h,r,span,rise,thk, origin, gvec):
    if not shape:
        return dash.no_update, "형상을 먼저 선택하세요", True
    need = REQ_DIM[shape]
    vals = dict(w=w,l=l,h=h,r=r,span=span,rise=rise,thk=thk)
    if any(vals[k] is None for k in need):
        return dash.no_update, "모든 값을 입력하세요", True
    dims = {k: vals[k] for k in need}
    aux  = {"origin": origin or "0,0,0", "gravity_vec": gvec or "0,0,-1"}
    return make_fig(shape, dims, aux), "", False

# ───────────────────── ⑥ 추가-저장 ────────────────────────
@callback(
    Output("msg","children"), Output("msg","color"),
    Output("msg","is_open"),  Output("tbl","data_timestamp"),
    Input("add-save","n_clicks"),
    State("add-name","value"),  State("add-shape","value"),
    State("add-w","value"),     State("add-l","value"),  State("add-h","value"),
    State("add-r","value"),     State("add-span","value"),
    State("add-rise","value"),  State("add-thk","value"),
    State("add-origin","value"),State("add-gvec","value"),
    prevent_initial_call=True,
)
def add_save(_, name, shape, w,l,h,r,span,rise,thk, origin, gvec):
    if not (name and shape):
        return "이름과 형상을 입력하세요", "danger", True, dash.no_update
    need = REQ_DIM[shape]
    vals = dict(w=w,l=l,h=h,r=r,span=span,rise=rise,thk=thk)
    if any(vals[k] is None for k in need):
        return "치수를 모두 입력하세요", "danger", True, dash.no_update
    dims = {k: vals[k] for k in need}
    aux  = {"origin": origin or "0,0,0", "gravity_vec": gvec or "0,0,-1"}
    api.add_concrete(name, shape, dims)
    df = api.load_all()
    df.iloc[-1, df.columns.get_loc("aux")] = json.dumps(aux, ensure_ascii=False)
    api.save_all(df)
    return "추가 완료", "success", True, pd.Timestamp.utcnow().value

# ───────────────────── ⑦ 삭제 (확인→실행) ───────────────────
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
    Output("msg", "children",       allow_duplicate=True),
    Output("msg", "color",          allow_duplicate=True),
    Output("msg", "is_open",        allow_duplicate=True),
    Input("confirm-del", "submit_n_clicks"),
    State("tbl", "selected_rows"), State("tbl", "data"),
    prevent_initial_call=True,
)
def delete_row(_, sel, data):
    if not sel:
        raise PreventUpdate
    cid = data[sel[0]]["concrete_id"]
    api.delete_concrete(cid)
    return pd.Timestamp.utcnow().value, f"{cid} 삭제 완료", "warning", True

# ───────────────────── ⑧ 수정-모달 열기 ─────────────────────
@callback(
    Output("modal-edit", "is_open"),
    Output("edit-id",    "data"),
    Input("btn-edit", "n_clicks"),
    Input("edit-close", "n_clicks"),
    Input("edit-save",  "n_clicks"),
    State("tbl", "selected_rows"), State("tbl", "data"),
    prevent_initial_call=True,
)
def open_edit(b_open, b_close, b_save, sel, data):
    trig = ctx.triggered_id
    if trig == "btn-edit" and sel:
        return True, data[sel[0]]["concrete_id"]
    return False, dash.no_update

# ───────────────────── ⑨ 수정-모달 필드 채우기 ───────────────
@callback(
    Output("edit-name",  "value"),  Output("edit-shape", "value"),
    Output("edit-w",     "value"),  Output("edit-l",    "value"),
    Output("edit-h",     "value"),  Output("edit-r",    "value"),
    Output("edit-span",  "value"),  Output("edit-rise", "value"),
    Output("edit-thk",   "value"),
    Output("edit-origin","value"),  Output("edit-gvec", "value"),
    Output("edit-preview","figure"),   
    Output("edit-w","style"),Output("edit-l","style"),Output("edit-h","style"),
    Output("edit-r","style"),
    Output("edit-span","style"),Output("edit-rise","style"),Output("edit-thk","style"),
    Input("modal-edit","is_open"),
    State("edit-id","data"),
)
def fill_edit(opened, cid):
    if not opened or not cid:
        raise PreventUpdate
    row   = api.load_all().query("concrete_id == @cid").iloc[0]
    dims  = json.loads(row["dims"])
    aux   = json.loads(row["aux"])
    shape = row["shape"]
    vis   = REQ_DIM[shape]
    show_ = lambda k: show(k in vis)
    fig   = make_fig(shape, dims, aux)
    return (
        row["name"], shape,
        dims.get("w"), dims.get("l"), dims.get("h"),
        dims.get("r"), dims.get("span"), dims.get("rise"), dims.get("thk"),
        aux.get("origin","0,0,0"), aux.get("gravity_vec","0,0,-1"),
        fig,
        show_("w"), show_("l"), show_("h"), show_("r"),
        show_("span"), show_("rise"), show_("thk"),
    )

# ───────────────────── ⑩ shape 변경 → 칸 토글 ───────────────
@callback(
    Output("edit-w","style",   allow_duplicate=True),
    Output("edit-l","style",   allow_duplicate=True),
    Output("edit-h","style",   allow_duplicate=True),
    Output("edit-r","style",   allow_duplicate=True),
    Output("edit-span","style",allow_duplicate=True),
    Output("edit-rise","style",allow_duplicate=True),
    Output("edit-thk","style", allow_duplicate=True),
    Input("edit-shape","value"),
    prevent_initial_call=True, 
)
def edit_toggle(shape):
    vis = REQ_DIM.get(shape, ())
    return (show("w" in vis), show("l" in vis), show("h" in vis),
            show("r" in vis), show("span" in vis),
            show("rise" in vis), show("thk" in vis))

# ───────────────────── ⑪ 수정-미리보기 ─────────────────────
@callback(
    Output("edit-preview","figure", allow_duplicate=True),
    Output("edit-alert",  "children"), Output("edit-alert","is_open"),
    Input("edit-build","n_clicks"),
    State("edit-shape","value"),
    State("edit-w","value"),State("edit-l","value"),State("edit-h","value"),
    State("edit-r","value"),State("edit-span","value"),
    State("edit-rise","value"),State("edit-thk","value"),
    State("edit-origin","value"),State("edit-gvec","value"),
    prevent_initial_call=True,
)
def edit_preview(_, shape, w,l,h,r,span,rise,thk, origin, gvec):
    if not shape:
        return dash.no_update, "형상 선택!", True
    need = REQ_DIM[shape]
    vals = dict(w=w,l=l,h=h,r=r,span=span,rise=rise,thk=thk)
    if any(vals[k] is None for k in need):
        return dash.no_update, "치수 입력!", True
    dims = {k: vals[k] for k in need}
    aux  = {"origin": origin or "0,0,0", "gravity_vec": gvec or "0,0,-1"}
    return make_fig(shape, dims, aux), "", False

# ───────────────────── ⑫ 수정-저장 ────────────────────────
@callback(
    Output("tbl","data_timestamp", allow_duplicate=True),
    Output("msg","children",       allow_duplicate=True),
    Output("msg","color",          allow_duplicate=True),
    Output("msg","is_open",        allow_duplicate=True),
    Input("edit-save","n_clicks"), State("edit-id","data"),
    State("edit-name","value"),  State("edit-shape","value"),
    State("edit-w","value"),     State("edit-l","value"),   State("edit-h","value"),
    State("edit-r","value"),     State("edit-span","value"),
    State("edit-rise","value"),  State("edit-thk","value"),
    State("edit-origin","value"),State("edit-gvec","value"),
    prevent_initial_call=True,
)
def save_edit(_, cid, name, shape, w,l,h,r,span,rise,thk, org, gvec):
    if not cid or not (name and shape):
        return dash.no_update, "입력 누락!", "danger", True
    need = REQ_DIM[shape]
    vals = dict(w=w,l=l,h=h,r=r,span=span,rise=rise,thk=thk)
    if any(vals[k] is None for k in need):
        return dash.no_update, "치수 입력!", "danger", True
    dims = {k: vals[k] for k in need}
    aux  = {"origin": org or "0,0,0", "gravity_vec": gvec or "0,0,-1"}
    api.update_concrete(cid, name, shape, dims, aux)
    return pd.Timestamp.utcnow().value, f"{cid} 수정 완료", "success", True
