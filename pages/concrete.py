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
* DataTable 아래에 "추가/수정/삭제" 버튼 그룹을 배치.
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
            # 좌측: 상세정보 + 프로젝트 드롭다운 + 콘크리트 목록
            dbc.Col([
                html.Div(id="concrete-details", className="mb-3"),
                dcc.Dropdown(
                    id="project-dropdown",
                    options=[{"label": row["name"], "value": row["project_pk"]} for _, row in projects_df.iterrows()],
                    value=projects_df["project_pk"].iloc[0] if not projects_df.empty else None,
                    clearable=False,
                    className="mb-3"
                ),
                html.Hr(className="my-2"),
                html.Small("💡 컬럼 헤더를 클릭하여 정렬할 수 있습니다", className="text-muted mb-2 d-block"),
                dash_table.DataTable(
                    id="tbl",
                    page_size=5,
                    row_selectable="single",
                    sort_action="native",
                    sort_mode="multi",
                    style_table={"overflowY": "auto", "height": "30vh"},
                    style_cell={"whiteSpace": "nowrap", "textAlign": "center"},
                    style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
                    style_data_conditional=[
                        {
                            'if': {
                                'filter_query': '{status} = 분석중',
                                'column_id': 'status'
                            },
                            'backgroundColor': '#fff3cd',
                            'color': '#856404',
                            'fontWeight': 'bold'
                        },
                        {
                            'if': {
                                'filter_query': '{status} = 수정가능',
                                'column_id': 'status'
                            },
                            'backgroundColor': '#d1ecf1',
                            'color': '#0c5460',
                            'fontWeight': 'bold'
                        },
                        {
                            'if': {'column_id': 'pour_date'},
                            'fontSize': '0.85rem',
                            'color': '#6c757d'
                        }
                    ],
                ),
                dbc.ButtonGroup([
                    dbc.Button("+ 추가", id="btn-add", color="success", className="mt-2"),
                    dbc.Button("수정", id="btn-edit", color="secondary", className="mt-2", disabled=True),
                    dbc.Button("삭제", id="btn-del",  color="danger", className="mt-2", disabled=True),
                ], size="sm", vertical=True, className="w-100 mt-2"),
            ], md=4),
            # 우측: 3D 뷰
            dbc.Col([
                dcc.Graph(id="viewer", style={"height": "85vh"}),
            ], md=8),
        ], className="g-3"),

        # 알림, 인터벌, 삭제 확인
        dbc.Alert(id="msg", is_open=False, duration=4000),
        dcc.Interval(id="init", interval=500, n_intervals=0, max_intervals=1),
        dcc.ConfirmDialog(
            id="confirm-del", 
            message="선택한 콘크리트를 정말 삭제하시겠습니까?\n\n※ 관련 센서도 함께 삭제됩니다."
        ),

        # 추가 모달
        dbc.Modal(id="modal-add", is_open=False, size="lg", children=[
            dbc.ModalHeader("콘크리트 추가"),
            dbc.ModalBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("콘크리트 이름"),
                        dbc.Input(id="add-name", placeholder="콘크리트 이름을 입력하세요")
                    ], width=12),
                ], className="mb-2"),
                dbc.Alert(id="add-alert", is_open=False, duration=3000, color="danger"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("노드 목록 (예: [[1,0],[1,1],[0,1],[0,0]])"),
                        dbc.Textarea(id="add-nodes", rows=3, placeholder="노드 좌표를 입력하세요")
                    ], width=12),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("높이 (m)"),
                        dbc.Input(id="add-h", type="number", placeholder="높이를 입력하세요", step=0.1)
                    ], width=6),
                    dbc.Col([
                        dbc.Label("해석 단위 (0.1 ~ 1.0) [m]"),
                        dbc.Input(id="add-unit", type="number", placeholder="해석 단위", 
                                 min=0.1, max=1.0, step=0.1)
                    ], width=6),
                ], className="mb-2"),
                html.Hr(),
                html.H6("콘크리트 물성치", className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("베타 상수 (0.1 ~ 1.0)"),
                        dbc.Input(id="add-b", type="number", min=0.1, max=1.0, step=0.1, placeholder="베타 상수(con_b)")
                    ], width=6),
                    dbc.Col([
                        dbc.Label("N 상수 (0.5 ~ 0.7)"),
                        dbc.Input(id="add-n", type="number", min=0.5, max=0.7, step=0.1, placeholder="N 상수(con_n)")
                    ], width=6),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("28일 후 탄성계수 (1 ~ 100) [GPa]"),
                        dbc.Input(id="add-e", type="number", min=1, max=100, step=0.1, placeholder="탄성계수(con_e)")
                    ], width=12),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("타설 날짜"),
                        dbc.Input(id="add-t-date", type="date", className="mb-1")
                    ], width=6),
                    dbc.Col([
                        dbc.Label("타설 시간"),
                        dbc.Input(id="add-t-time", type="time", className="mb-1")
                    ], width=6),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("열팽창계수 (0.1 ~ 10.0) [×10⁻⁵/°C]"),
                        dbc.Input(id="add-a", type="number", min=0.1, max=10.0, step=0.1, placeholder="열팽창계수(con_a)")
                    ], width=6),
                    dbc.Col([
                        dbc.Label("포아송비 (0.01 ~ 1.00)"),
                        dbc.Input(id="add-p", type="number", min=0.01, max=1.00, step=0.01, placeholder="포아송비(con_p)")
                    ], width=6),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("밀도 (500 ~ 5000) [kg/m³]"),
                        dbc.Input(id="add-d", type="number", min=500, max=5000, step=10, placeholder="밀도(con_d)")
                    ], width=12),
                ], className="mb-2"),
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
                dbc.Row([
                    dbc.Col([
                        dbc.Label("콘크리트 이름"),
                        dbc.Input(id="edit-name", placeholder="콘크리트 이름을 입력하세요")
                    ], width=12),
                ], className="mb-2"),
                dbc.Alert(id="edit-alert", is_open=False, duration=3000, color="danger"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("노드 목록 (예: [(1,0),(1,1),(0,1),(0,0)])"),
                        dbc.Textarea(id="edit-nodes", rows=3, placeholder="노드 좌표를 입력하세요")
                    ], width=12),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("높이 (m)"),
                        dbc.Input(id="edit-h", type="number", placeholder="높이를 입력하세요", step=0.1)
                    ], width=6),
                    dbc.Col([
                        dbc.Label("해석 단위 (0.1 ~ 1.0) [m]"),
                        dbc.Input(id="edit-unit", type="number", placeholder="해석 단위", 
                                 min=0.1, max=1.0, step=0.1)
                    ], width=6),
                ], className="mb-2"),
                html.Hr(),
                html.H6("콘크리트 물성치", className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("베타 상수 (0.1 ~ 1.0)"),
                        dbc.Input(id="edit-b", type="number", min=0.1, max=1.0, step=0.1, placeholder="베타 상수(con_b)")
                    ], width=6),
                    dbc.Col([
                        dbc.Label("N 상수 (0.5 ~ 0.7)"),
                        dbc.Input(id="edit-n", type="number", min=0.5, max=0.7, step=0.1, placeholder="N 상수(con_n)")
                    ], width=6),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("28일 후 탄성계수 (1 ~ 100) [GPa]"),
                        dbc.Input(id="edit-e", type="number", min=1, max=100, step=0.1, placeholder="탄성계수(con_e)")
                    ], width=12),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("타설 날짜"),
                        dbc.Input(id="edit-t-date", type="date", className="mb-1")
                    ], width=6),
                    dbc.Col([
                        dbc.Label("타설 시간"),
                        dbc.Input(id="edit-t-time", type="time", className="mb-1")
                    ], width=6),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("열팽창계수 (0.1 ~ 10.0) [×10⁻⁵/°C]"),
                        dbc.Input(id="edit-a", type="number", min=0.1, max=10.0, step=0.1, placeholder="열팽창계수(con_a)")
                    ], width=6),
                    dbc.Col([
                        dbc.Label("포아송비 (0.01 ~ 1.00)"),
                        dbc.Input(id="edit-p", type="number", min=0.01, max=1.00, step=0.01, placeholder="포아송비(con_p)")
                    ], width=6),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("밀도 (500 ~ 5000) [kg/m³]"),
                        dbc.Input(id="edit-d", type="number", min=500, max=5000, step=10, placeholder="밀도(con_d)")
                    ], width=12),
                ], className="mb-2"),
                dcc.Graph(id="edit-preview", style={"height": "45vh"}, className="border"),
            ]),
            dbc.ModalFooter([
                dbc.Button("미리보기", id="edit-build", color="info", className="me-auto"),
                dbc.Button("저장",     id="edit-save",  color="primary"),
                dbc.Button("닫기",     id="edit-close", color="secondary"),
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
    Input("tbl", "data_timestamp"),   # ← 추가
    prevent_initial_call=False
)
def refresh_table(n, project_pk, _data_ts):
    df_all = api_db.get_concrete_data()
    if project_pk:
        df = df_all[df_all["project_pk"] == project_pk]
    else:
        df = pd.DataFrame(columns=df_all.columns)
    
    # 상태 정보와 타설 날짜 추가
    if not df.empty:
        df["status"] = df["activate"].apply(lambda x: "수정가능" if x == 1 else "분석중")
        
        # 타설 날짜를 YY.MM.DD 형식으로 변환 및 정렬용 데이터 생성
        def format_date_display(con_t):
            if con_t and con_t not in ["", "N/A", None]:
                try:
                    from datetime import datetime
                    # datetime 객체인 경우
                    if hasattr(con_t, 'strftime'):
                        dt = con_t
                    # 문자열인 경우 파싱
                    elif isinstance(con_t, str):
                        if 'T' in con_t:
                            # ISO 형식 (2024-01-01T10:00 또는 2024-01-01T10:00:00)
                            dt = datetime.fromisoformat(con_t.replace('Z', ''))
                        else:
                            # 다른 형식 시도
                            dt = datetime.strptime(str(con_t), '%Y-%m-%d %H:%M:%S')
                    else:
                        return 'N/A'
                    
                    return dt.strftime('%y.%m.%d')
                except Exception:
                    return 'N/A'
            else:
                return 'N/A'
        

        
        df["pour_date"] = df["con_t"].apply(format_date_display)
    
    cols = [
        {"name": "이름", "id": "name", "type": "text"},
        {"name": "타설일", "id": "pour_date", "type": "text"},
        {"name": "상태", "id": "status", "type": "text"},
    ]
    sel = [0] if not df.empty else []
    return df.to_dict("records"), cols, sel

# ───────────────────── ② 선택된 행 → 3-D 뷰
@callback(
    Output("viewer",           "figure"),
    Output("concrete-details", "children"),
    Output("btn-edit",         "disabled"),
    Output("btn-del",          "disabled"),
    Input("tbl",               "selected_rows"),
    State("tbl",               "data"),
    prevent_initial_call=True
)
def show_selected(sel, data):
    # 아무 것도 선택 안 됐으면 모두 비활성
    if not sel:
        return go.Figure(), "", True, True

    # 선택된 레코드 가져오기
    row = pd.DataFrame(data).iloc[sel[0]]
    # dims 파싱
    try:
        dims = ast.literal_eval(row["dims"])
    except Exception:
        raise PreventUpdate

    # 3D 뷰 준비
    fig = make_fig(dims["nodes"], dims["h"])
    
    # 타설 시간 포맷팅
    con_t_raw = row.get('con_t', 'N/A')
    if con_t_raw and con_t_raw != 'N/A':
        try:
            from datetime import datetime
            dt = None
            
            # datetime 객체인 경우
            if hasattr(con_t_raw, 'strftime'):
                dt = con_t_raw
            # 문자열인 경우 파싱
            elif isinstance(con_t_raw, str):
                if 'T' in con_t_raw:
                    # ISO 형식 (2024-01-01T10:00 또는 2024-01-01T10:00:00)
                    dt = datetime.fromisoformat(con_t_raw.replace('Z', ''))
                else:
                    # 다른 형식 시도
                    dt = datetime.strptime(str(con_t_raw), '%Y-%m-%d %H:%M:%S')
            
            if dt:
                # 기본 날짜/시간 포맷
                con_t_formatted = dt.strftime('%Y년 %m월 %d일 %H:%M')
                
                # 경과 시간 계산
                now = datetime.now()
                time_diff = now - dt
                
                # 경과 시간 포맷팅
                total_seconds = int(time_diff.total_seconds())
                days = total_seconds // 86400
                hours = (total_seconds % 86400) // 3600
                minutes = (total_seconds % 3600) // 60
                
                if days > 0:
                    if hours > 0:
                        con_t_formatted += f" ({days}일 {hours}시간 경과)"
                    else:
                        con_t_formatted += f" ({days}일 경과)"
                elif hours > 0:
                    if minutes > 30:  # 30분 이상이면 분도 표시
                        con_t_formatted += f" ({hours}시간 {minutes}분 경과)"
                    else:
                        con_t_formatted += f" ({hours}시간 경과)"
                elif minutes > 0:
                    con_t_formatted += f" ({minutes}분 경과)"
                else:
                    con_t_formatted += " (방금 전)"
            else:
                con_t_formatted = str(con_t_raw)
                
        except Exception:
            con_t_formatted = str(con_t_raw)
    else:
        con_t_formatted = 'N/A'
    
    # activate 체크 (없으면 1로 간주)
    is_active = row.get("activate", 1) == 1
    
    # 상태 정보 준비
    status_text = "수정가능" if is_active else "분석중"
    status_color = "success" if is_active else "warning"
    
    # 상세 정보 카드 생성
    details = dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.Span(f"{row['name']}", className="text-primary", style={"fontSize": "1rem", "fontWeight": "600"}),
                html.Span(f" [해석단위: {row.get('con_unit', 'N/A')}m]", className="text-muted", style={"fontSize": "0.85rem", "marginLeft": "8px"}),
                dbc.Badge(status_text, color=status_color, className="ms-2", style={"fontSize": "0.7rem"})
            ])
        ], className="py-2"),
        dbc.CardBody([
            # 2x3 물성치 레이아웃
            dbc.Row([
                dbc.Col([
                    html.Small("베타", className="text-muted", style={"fontSize": "0.7rem"}),
                    html.Div(f"{row.get('con_b', 'N/A')}", className="fw-bold", style={"fontSize": "0.8rem"})
                ], width=4, className="mb-1"),
                dbc.Col([
                    html.Small("N", className="text-muted", style={"fontSize": "0.7rem"}),
                    html.Div(f"{row.get('con_n', 'N/A')}", className="fw-bold", style={"fontSize": "0.8rem"})
                ], width=4, className="mb-1"),
                dbc.Col([
                    html.Small("탄성계수", className="text-muted", style={"fontSize": "0.7rem"}),
                    html.Div(f"{row.get('con_e', 'N/A')}GPa", className="fw-bold", style={"fontSize": "0.8rem"})
                ], width=4, className="mb-1"),
            ]),
            dbc.Row([
                dbc.Col([
                    html.Small("포아송비", className="text-muted", style={"fontSize": "0.7rem"}),
                    html.Div(f"{row.get('con_p', 'N/A')}", className="fw-bold", style={"fontSize": "0.8rem"})
                ], width=4, className="mb-1"),
                dbc.Col([
                    html.Small("밀도", className="text-muted", style={"fontSize": "0.7rem"}),
                    html.Div(f"{row.get('con_d', 'N/A')}kg/m³", className="fw-bold", style={"fontSize": "0.8rem"})
                ], width=4, className="mb-1"),
                dbc.Col([
                    html.Small("열팽창계수", className="text-muted", style={"fontSize": "0.7rem"}),
                    html.Div(f"{row.get('con_a', 'N/A')}×10⁻⁵/°C", className="fw-bold", style={"fontSize": "0.8rem"})
                ], width=4, className="mb-1"),
            ]),
            html.Hr(className="my-2"),
            html.Small("타설시간", className="text-muted", style={"fontSize": "0.7rem"}),
            html.Div(con_t_formatted, className="fw-bold", style={"fontSize": "0.8rem", "lineHeight": "1.2"})
        ], className="py-2")
    ], className="shadow-sm")

    if not is_active:
        # 비활성화된 경우: 수정/삭제 비활성화
        return fig, details, True, True
    else:
        # 활성화된 경우: 수정/삭제 활성화
        return fig, details, False, False

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
    Output("add-alert",  "children",      allow_duplicate=True),
    Output("add-alert",  "is_open",       allow_duplicate=True),
    Output("tbl",        "data_timestamp",allow_duplicate=True),
    Output("modal-add",  "is_open",       allow_duplicate=True),
    Output("msg",        "children",      allow_duplicate=True),
    Output("msg",        "color",         allow_duplicate=True),
    Output("msg",        "is_open",       allow_duplicate=True),
    Input("add-save",    "n_clicks"),
    State("project-dropdown", "value"),
    State("add-name",    "value"),
    State("add-nodes",   "value"),
    State("add-h",       "value"),
    State("add-unit",    "value"),
    State("add-b",       "value"),
    State("add-n",       "value"),
    State("add-t-date",  "value"),
    State("add-t-time",  "value"),
    State("add-a",       "value"),
    State("add-p",       "value"),
    State("add-d",       "value"),
    State("add-e",       "value"),
    prevent_initial_call=True
)
def add_save(n_clicks, project_pk, name, nodes_txt, h, unit, b, n, t_date, t_time, a, p, d, e):
    if not n_clicks:
        raise PreventUpdate

    # 날짜와 시간 합치기
    t = None
    if t_date and t_time:
        t = f"{t_date}T{t_time}"
    elif t_date:
        t = f"{t_date}T00:00"
    elif t_time:
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        t = f"{today}T{t_time}"

    # 1) 빈값 체크
    missing = []
    if not project_pk: missing.append("프로젝트")
    if not name:       missing.append("이름")
    if not nodes_txt:  missing.append("노드 목록")
    if h    is None:   missing.append("높이 H")
    if unit is None:   missing.append("해석 단위")
    if b    is None:   missing.append("베타 상수")
    if n    is None:   missing.append("N 상수")
    if not t:          missing.append("타설 시간")
    if a    is None:   missing.append("열팽창계수")
    if p    is None:   missing.append("포아송비")
    if d    is None:   missing.append("밀도")
    if e    is None:   missing.append("탄성계수")
    
    # 2) 범위 체크
    range_errors = []
    if unit is not None and (unit < 0.1 or unit > 1.0):
        range_errors.append("해석 단위(0.1~1.0)")
    if b is not None and (b < 0.1 or b > 1.0):
        range_errors.append("베타 상수(0.1~1.0)")
    if n is not None and (n < 0.5 or n > 0.7):
        range_errors.append("N 상수(0.5~0.7)")
    if a is not None and (a < 0.1 or a > 10.0):
        range_errors.append("열팽창계수(0.1~10.0)")
    if p is not None and (p < 0.01 or p > 1.0):
        range_errors.append("포아송비(0.01~1.0)")
    if d is not None and (d < 500 or d > 5000):
        range_errors.append("밀도(500~5000)")
    if e is not None and (e < 1 or e > 100):
        range_errors.append("탄성계수(1~100)")

    if missing:
        return (
            f"{', '.join(missing)}을(를) 입력해주세요.",  # add-alert.children
            True,                                       # add-alert.is_open
            dash.no_update,                             # tbl.data_timestamp
            True,                                       # modal-add.is_open
            "",                                         # msg.children
            "",                                         # msg.color
            False                                       # msg.is_open
        )
    
    if range_errors:
        return (
            f"다음 항목에 올바른 범위값을 입력해주세요: {', '.join(range_errors)}",
            True,                                       # add-alert.is_open
            dash.no_update,                             # tbl.data_timestamp
            True,                                       # modal-add.is_open
            "",                                         # msg.children
            "",                                         # msg.color
            False                                       # msg.is_open
        )

    # 2) 노드 파싱
    try:
        nodes = ast.literal_eval(nodes_txt)
        assert isinstance(nodes, list)
    except Exception:
        return (
            "노드 형식이 잘못되었습니다.",
            True,
            dash.no_update,
            True,
            "",
            "",
            False
        )

    # 3) DB 저장 (activate=1 고정)
    dims = {"nodes": nodes, "h": float(h)}
    api_db.add_concrete_data(
        project_pk=project_pk,
        name=name.strip(),
        dims=dims,
        con_unit=float(unit),
        con_b=float(b),
        con_n=float(n),
        con_t=t,  # datetime 값 전달
        con_a=float(a),
        con_p=float(p),
        con_d=float(d),
        con_e=float(e),
        activate=1
    )

    # 4) 성공 처리: 모달 닫기, 내부 Alert 숨기기, 테이블 갱신, 전역 알림
    return (
        "",                             # add-alert.children
        False,                          # add-alert.is_open
        pd.Timestamp.utcnow().value,   # tbl.data_timestamp
        False,                          # modal-add.is_open
        "저장했습니다.",                # msg.children
        "success",                      # msg.color
        True                            # msg.is_open
    )

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
    concrete_name = data[sel[0]].get("name", cid)
    
    try:
        result = api_db.delete_concrete_data(cid)
        
        if result["success"]:
            if result["deleted_sensors"] > 0:
                # 관련 센서도 함께 삭제된 경우
                msg_color = "warning"
                msg_text = f"'{concrete_name}' {result['message']}"
            else:
                # 콘크리트만 삭제된 경우
                msg_color = "success"
                msg_text = f"'{concrete_name}' {result['message']}"
            
            return pd.Timestamp.utcnow().value, msg_text, msg_color, True
        else:
            return dash.no_update, f"'{concrete_name}' 삭제 실패", "danger", True
            
    except Exception as e:
        return dash.no_update, f"'{concrete_name}' 삭제 중 오류 발생: {str(e)}", "danger", True

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
    Output("edit-name",     "value"),
    Output("edit-nodes",    "value"),
    Output("edit-h",        "value"),
    Output("edit-unit",     "value"),
    Output("edit-b",        "value"),
    Output("edit-n",        "value"),
    Output("edit-t-date",   "value"),
    Output("edit-t-time",   "value"),
    Output("edit-a",        "value"),
    Output("edit-p",        "value"),
    Output("edit-d",        "value"),
    Output("edit-e",        "value"),
    Output("edit-preview",  "figure"),
    Input("modal-edit",     "is_open"),
    State("edit-id",        "data"),
    prevent_initial_call=True
)
def fill_edit(opened: bool, cid):
    if not opened or not cid:
        raise PreventUpdate

    # 1) 데이터 조회
    df = api_db.get_concrete_data(cid)

    # 2) 유효성 검사: None 또는 빈 DataFrame이면 무시
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        raise PreventUpdate

    # 3) DataFrame이면 첫 행을 꺼내 dict로, 아니면 이미 dict라고 가정
    if isinstance(df, pd.DataFrame):
        row = df.iloc[0].to_dict()
    else:
        row = df

    # 4) dims 필드가 문자열이면 파싱
    dims_field = row.get("dims", {})
    if isinstance(dims_field, str):
        try:
            dims = ast.literal_eval(dims_field)
        except Exception:
            dims = {}
    else:
        dims = dims_field or {}

    # 5) 각 값 추출
    name     = row.get("name", "")
    nodes    = str(dims.get("nodes", []))
    h_value  = dims.get("h", 0)

    # 6) 수정된 콘크리트의 속성들
    con_unit = row.get("con_unit", "")
    con_b    = row.get("con_b", "")
    con_n    = row.get("con_n", "")
    con_a    = row.get("con_a", "")
    con_p    = row.get("con_p", "")
    con_d    = row.get("con_d", "")
    con_e    = row.get("con_e", "")
    
    # 타설 시간 포맷팅 (날짜와 시간 분리)
    con_t_raw = row.get("con_t", "")
    con_t_date = ""
    con_t_time = ""
    
    if con_t_raw and con_t_raw not in ["", "N/A", None]:
        try:
            from datetime import datetime
            # datetime 객체인 경우
            if hasattr(con_t_raw, 'strftime'):
                dt = con_t_raw
            # 문자열인 경우 파싱
            elif isinstance(con_t_raw, str):
                if 'T' in con_t_raw:
                    # ISO 형식 (2024-01-01T10:00 또는 2024-01-01T10:00:00)
                    dt = datetime.fromisoformat(con_t_raw.replace('Z', ''))
                else:
                    # 다른 형식 시도
                    dt = datetime.strptime(str(con_t_raw), '%Y-%m-%d %H:%M:%S')
            else:
                # 기타 형식 - 현재 시간으로 기본값 설정
                dt = datetime.now()
            
            con_t_date = dt.strftime('%Y-%m-%d')
            con_t_time = dt.strftime('%H:%M')
            
        except Exception as e:
            # 파싱 실패 시 현재 시간으로 설정
            from datetime import datetime
            dt = datetime.now()
            con_t_date = dt.strftime('%Y-%m-%d')
            con_t_time = dt.strftime('%H:%M')
    else:
        # 값이 없으면 현재 시간으로 설정
        from datetime import datetime
        dt = datetime.now()
        con_t_date = dt.strftime('%Y-%m-%d')
        con_t_time = dt.strftime('%H:%M')

    # 7) 3D 미리보기 생성
    fig = make_fig(dims.get("nodes", []), dims.get("h", 0))

    return name, nodes, h_value, con_unit, con_b, con_n, con_t_date, con_t_time, con_a, con_p, con_d, con_e, fig


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
    Output("edit-alert",  "children",      allow_duplicate=True),
    Output("edit-alert",  "is_open",       allow_duplicate=True),
    Output("tbl",         "data_timestamp",allow_duplicate=True),
    Output("modal-edit",  "is_open",       allow_duplicate=True),
    Output("msg",         "children",      allow_duplicate=True),
    Output("msg",         "color",         allow_duplicate=True),
    Output("msg",         "is_open",       allow_duplicate=True),
    Input("edit-save",    "n_clicks"),
    State("edit-id",      "data"),
    State("edit-name",    "value"),
    State("edit-nodes",   "value"),
    State("edit-h",       "value"),
    State("edit-unit",    "value"),
    State("edit-b",       "value"),
    State("edit-n",       "value"),
    State("edit-t-date",  "value"),
    State("edit-t-time",  "value"),
    State("edit-a",       "value"),
    State("edit-p",       "value"),
    State("edit-d",       "value"),
    State("edit-e",       "value"),
    prevent_initial_call=True
)
def save_edit(n_clicks, cid, name, nodes_txt, h, unit, b, n, t_date, t_time, a, p, d, e):
    if not n_clicks:
        raise PreventUpdate

    # 날짜와 시간 합치기
    t = None
    if t_date and t_time:
        t = f"{t_date}T{t_time}"
    elif t_date:
        t = f"{t_date}T00:00"
    elif t_time:
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        t = f"{today}T{t_time}"

    # 1) 빈값 체크
    missing = []
    if not cid:        missing.append("항목 선택")
    if not name:       missing.append("이름")
    if not nodes_txt:  missing.append("노드 목록")
    if h    is None:   missing.append("높이 H")
    if unit is None:   missing.append("해석 단위")
    if b    is None:   missing.append("베타 상수")
    if n    is None:   missing.append("N 상수")
    if not t:          missing.append("타설 시간")
    if a    is None:   missing.append("열팽창계수")
    if p    is None:   missing.append("포아송비")
    if d    is None:   missing.append("밀도")
    if e    is None:   missing.append("탄성계수")
    
    # 2) 범위 체크
    range_errors = []
    if unit is not None and (unit < 0.1 or unit > 1.0):
        range_errors.append("해석 단위(0.1~1.0)")
    if b is not None and (b < 0.1 or b > 1.0):
        range_errors.append("베타 상수(0.1~1.0)")
    if n is not None and (n < 0.5 or n > 0.7):
        range_errors.append("N 상수(0.5~0.7)")
    if a is not None and (a < 0.1 or a > 10.0):
        range_errors.append("열팽창계수(0.1~10.0)")
    if p is not None and (p < 0.01 or p > 1.0):
        range_errors.append("포아송비(0.01~1.0)")
    if d is not None and (d < 500 or d > 5000):
        range_errors.append("밀도(500~5000)")
    if e is not None and (e < 1 or e > 100):
        range_errors.append("탄성계수(1~100)")

    if missing:
        return (
            f"{', '.join(missing)}을(를) 입력해주세요.",
            True,                  # edit-alert 열기
            dash.no_update,        # 테이블 미갱신
            True,                  # 모달 닫지 않음
            "", "", False          # 전역 msg 없음
        )
    
    if range_errors:
        return (
            f"다음 항목에 올바른 범위값을 입력해주세요: {', '.join(range_errors)}",
            True,                  # edit-alert 열기
            dash.no_update,        # 테이블 미갱신
            True,                  # 모달 닫지 않음
            "", "", False          # 전역 msg 없음
        )

    # 2) 노드 파싱
    try:
        nodes = ast.literal_eval(nodes_txt)
        assert isinstance(nodes, list)
    except Exception:
        return (
            "노드 형식이 잘못되었습니다.",
            True,
            dash.no_update,
            True,
            "", "", False
        )

    # 3) DB 업데이트
    dims = {"nodes": nodes, "h": float(h)}
    api_db.update_concrete_data(
        cid,
        name=name.strip(),
        dims=dims,
        con_unit=float(unit),
        con_b=float(b),
        con_n=float(n),
        con_t=t,  # datetime 값 전달
        con_a=float(a),
        con_p=float(p),
        con_d=float(d),
        con_e=float(e),
        activate=1
    )

    # 4) 성공 처리
    return (
        "",                             # edit-alert 비우기
        False,                          # edit-alert 닫기
        pd.Timestamp.utcnow().value,   # 테이블 갱신
        False,                          # 모달 닫기
        "수정했습니다.",                 # 전역 msg
        "success",                      # 전역 msg 색상
        True                            # 전역 msg 열기
    )



