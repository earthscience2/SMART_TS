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
from utils.encryption import parse_project_key_from_url

# 페이지 등록
register_page(__name__, path="/concrete", title="콘크리트 관리")

# 프로젝트 메타데이터 (URL 파라미터 파싱에 사용)
projects_df = api_db.get_project_data()

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
layout = html.Div([
    dcc.Location(id="concrete-url", refresh=False),
    dcc.Store(id="selected-project-store"),
    dbc.Container([
        dbc.Row([
            # 좌측: 상세정보 + 현재 프로젝트 표시 + 콘크리트 목록
            dbc.Col([
                # 프로젝트 정보 카드
                html.Div([
                    dbc.Alert(id="current-project-info", color="info", className="mb-0 py-2"),
                ], className="mb-2"),
                
                # 콘크리트 상세정보 카드
                html.Div(id="concrete-details", className="mb-2"),
                
                # 콘크리트 목록 카드
                html.Div([
                    html.Div([
                        # 제목과 추가 버튼
                        html.Div([
                            html.H6("🧱 콘크리트 목록", className="mb-0 text-secondary fw-bold"),
                            dbc.Button("+ 추가", id="btn-add", color="success", size="sm", className="px-3")
                        ], className="d-flex justify-content-between align-items-center mb-2"),
                        html.Small("💡 컬럼 헤더를 클릭하여 정렬할 수 있습니다", className="text-muted mb-2 d-block"),
                        html.Div([
                            dash_table.DataTable(
                                id="tbl",
                                page_size=5,
                                row_selectable="single",
                                sort_action="native",
                                sort_mode="multi",
                                style_table={"overflowY": "auto", "height": "40vh"},
                                style_cell={
                                    "whiteSpace": "nowrap", 
                                    "textAlign": "center",
                                    "fontSize": "0.9rem",
                                    "padding": "14px 12px",
                                    "border": "none",
                                    "borderBottom": "1px solid #f1f1f0",
                                    "fontFamily": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
                                },
                                style_header={
                                    "backgroundColor": "#fafafa", 
                                    "fontWeight": 600,
                                    "color": "#37352f",
                                    "border": "none",
                                    "borderBottom": "1px solid #e9e9e7",
                                    "fontSize": "0.8rem",
                                    "textTransform": "uppercase",
                                    "letterSpacing": "0.5px"
                                },
                                style_data={
                                    "backgroundColor": "white",
                                    "border": "none",
                                    "color": "#37352f"
                                },
                                style_data_conditional=[
                                    {
                                        'if': {'row_index': 'odd'},
                                        'backgroundColor': '#fbfbfa'
                                    },
                                    {
                                        'if': {'state': 'selected'},
                                        'backgroundColor': '#e8f4fd',
                                        'border': '1px solid #579ddb',
                                        'borderRadius': '6px',
                                        'boxShadow': '0 0 0 1px rgba(87, 157, 219, 0.3)',
                                        'color': '#1d4ed8'
                                    },
                                    {
                                        'if': {
                                            'filter_query': '{status} = 분석중',
                                            'column_id': 'status'
                                        },
                                        'backgroundColor': '#dcfce7',
                                        'color': '#166534',
                                        'fontWeight': '600',
                                        'borderRadius': '4px',
                                        'textAlign': 'center'
                                    },
                                    {
                                        'if': {
                                            'filter_query': '{status} = 설정중',
                                            'column_id': 'status'
                                        },
                                        'backgroundColor': '#f3f4f6',
                                        'color': '#6b7280',
                                        'fontWeight': '600',
                                        'borderRadius': '4px',
                                        'textAlign': 'center'
                                    },
                                    {
                                        'if': {'column_id': 'pour_date'},
                                        'fontSize': '0.85rem',
                                        'color': '#6b7280',
                                        'fontWeight': '500'
                                    },
                                    {
                                        'if': {'column_id': 'name'},
                                        'fontWeight': '600',
                                        'color': '#111827',
                                        'textAlign': 'left',
                                        'paddingLeft': '16px'
                                    }
                                ],
                                css=[
                                    {
                                        'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner table',
                                        'rule': 'border-collapse: separate; border-spacing: 0;'
                                    },
                                    {
                                        'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner tr:hover',
                                        'rule': 'background-color: #f8fafc !important; transition: background-color 0.15s ease;'
                                    },
                                    {
                                        'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner tr.row-selected',
                                        'rule': '''
                                            background-color: #eff6ff !important;
                                            box-shadow: inset 3px 0 0 #3b82f6;
                                            border-left: 3px solid #3b82f6;
                                        '''
                                    },
                                    {
                                        'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner td',
                                        'rule': 'cursor: pointer; transition: all 0.15s ease;'
                                    }
                                ]
                            ),
                        ], style={
                            "borderRadius": "12px", 
                            "overflow": "hidden", 
                            "border": "1px solid #e5e5e4",
                            "boxShadow": "0 1px 3px rgba(0, 0, 0, 0.05)"
                        }),
                        
                        # 선택된 콘크리트 작업 버튼
                        html.Div([
                            dbc.Button("수정", id="btn-edit", color="secondary", size="sm", className="px-3"),
                            dbc.Button("삭제", id="btn-del", color="danger", size="sm", className="px-3"),
                        ], id="concrete-action-buttons", className="d-flex justify-content-center gap-2 mt-2", style={"display": "none"})
                    ], className="p-3")
                ], className="bg-white rounded shadow-sm border"),
            ], md=4),
            
            # 우측: 3D 뷰
            dbc.Col([
                html.Div([
                    html.Div([
                        html.H6("🔍 3D 미리보기", className="mb-2 text-secondary fw-bold"),
                        dcc.Graph(id="viewer", style={"height": "82vh"}, config={'displayModeBar': False}),
                    ], className="p-3")
                ], className="bg-white rounded shadow-sm border"),
            ], md=8),
        ], className="g-3", style={"height": "90vh"}),
    ], className="py-2", style={"maxWidth": "1400px", "height": "100vh"}, fluid=False),
    
    # 알림, 인터벌, 삭제 확인
    dbc.Alert(id="msg", is_open=False, duration=4000),
        dcc.Interval(id="init", interval=500, n_intervals=0, max_intervals=1),
        dcc.ConfirmDialog(
            id="confirm-del", 
            message="선택한 콘크리트를 정말 삭제하시겠습니까?\n\n※ 관련 센서도 함께 삭제됩니다."
        ),

        # 추가 모달
        dbc.Modal(id="modal-add", is_open=False, size="lg", className="modal-notion", children=[
            dbc.ModalHeader([
                html.H5("🧱 콘크리트 추가", className="mb-0 text-secondary fw-bold", style={"fontSize": "1.1rem"})
            ], className="border-0 pb-1"),
            dbc.ModalBody([
                dbc.Row([
                    # 왼쪽 칼럼: 기본 정보 + 3D 미리보기
                    dbc.Col([
                        # 기본 정보 섹션
                        html.Div([
                            html.H6("📝 기본 정보", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("콘크리트 이름", className="form-label fw-semibold", style={"fontSize": "0.85rem"}),
                                    dbc.Input(id="add-name", placeholder="콘크리트 이름을 입력하세요", className="form-control", style={"fontSize": "0.85rem"})
                                ], width=12),
                            ], className="mb-2"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("노드 목록 (예: [[1,0],[1,1],[0,1],[0,0]])", className="form-label fw-semibold", style={"fontSize": "0.85rem"}),
                                    dbc.Textarea(id="add-nodes", rows=2, placeholder="노드 좌표를 입력하세요", className="form-control", style={"fontSize": "0.85rem"})
                                ], width=12),
                            ], className="mb-2"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "높이 [m] ",
                                        html.Small("(0.1~500)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold", style={"fontSize": "0.85rem"}),
                                    dbc.Input(id="add-h", type="number", placeholder="높이를 입력하세요", step=0.1, className="form-control", style={"fontSize": "0.85rem"})
                                ], width=6),
                                dbc.Col([
                                    dbc.Label([
                                        "Solid 요소크기 [m] ",
                                        html.Small("(0.1~10)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold", style={"fontSize": "0.85rem"}),
                                    dbc.Input(id="add-unit", type="number", placeholder="요소크기", 
                                             step=0.1, className="form-control", style={"fontSize": "0.85rem"})
                                ], width=6),
                            ], className="mb-2"),
                        ], className="bg-light p-2 rounded mb-2"),
                        
                        # 미리보기 섹션
                        html.Div([
                            html.H6("👁️ 3D 미리보기", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                            dcc.Graph(id="add-preview", style={"height": "50vh"}, className="rounded", config={'displayModeBar': False}),
                        ], className="bg-light p-2 rounded"),
                    ], md=6),
                    
                    # 오른쪽 칼럼: 콘크리트 물성치
                    dbc.Col([
                        html.Div([
                            html.H6("🔬 타설 콘크리트 탄성계수 (CEB-FIB Model)[Pa]", className="mb-3 text-secondary fw-bold"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "베타 상수 ",
                                        html.Small("(0.1~1.0)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="add-b", type="number", step=0.1, placeholder="베타 상수(con_b)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "N 상수 ",
                                        html.Small("(0.5~0.7)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="add-n", type="number", step=0.1, placeholder="N 상수(con_n)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "E28(재령 28일 압축 탄성계수) [GPa] ",
                                        html.Small("(1~100)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="add-e", type="number", step=0.1, placeholder="탄성계수(con_e)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("타설 날짜", className="form-label fw-semibold"),
                                    dbc.Input(id="add-t-date", type="date", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("타설 시간", className="form-label fw-semibold"),
                                    dbc.Input(id="add-t-time", type="time", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "열팽창계수 [×10⁻⁵/°C] ",
                                        html.Small("(0.1~10.0)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="add-a", type="number", step=0.1, placeholder="열팽창계수(con_a)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "포아송비 ",
                                        html.Small("(0.01~1.00)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="add-p", type="number", step=0.01, placeholder="포아송비(con_p)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "밀도 [kg/m³] ",
                                        html.Small("(500~5000)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="add-d", type="number", step=10, placeholder="밀도(con_d)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                        ], className="bg-light p-3 rounded", style={"height": "fit-content"}),
                    ], md=6),
                ], className="g-3"),
                
                # 경고 메시지 영역 (저장 버튼 근처)
                html.Div([
                    dbc.Alert(id="add-alert", is_open=False, duration=3000, color="danger", className="mb-0"),
                ], className="mt-3"),
            ]),
            dbc.ModalFooter([
                dbc.Button("📥 불러오기", id="add-load-btn", color="outline-primary", className="px-3", size="sm"),
                dbc.Button("3D 미리보기", id="add-build", color="info", className="px-3", size="sm"),
                dbc.Button("재령분석", id="add-age-analysis", color="warning", className="px-3", size="sm"),
                dbc.Button("저장", id="add-save", color="success", className="px-3 fw-semibold ms-auto", size="sm"),
                dbc.Button("닫기", id="add-close", color="secondary", className="px-3", size="sm"),
            ], className="border-0 pt-2"),
        ]),

        # 수정 모달
        dbc.Modal(id="modal-edit", is_open=False, size="lg", className="modal-notion", children=[
            dbc.ModalHeader([
                html.H5("✏️ 콘크리트 수정", className="mb-0 text-secondary fw-bold", style={"fontSize": "1.1rem"})
            ], className="border-0 pb-1"),
            dbc.ModalBody([
                dcc.Store(id="edit-id"),
                dbc.Row([
                    # 왼쪽 칼럼: 기본 정보 + 3D 미리보기
                    dbc.Col([
                        # 기본 정보 섹션
                        html.Div([
                            html.H6("📝 기본 정보", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("콘크리트 이름", className="form-label fw-semibold", style={"fontSize": "0.85rem"}),
                                    dbc.Input(id="edit-name", placeholder="콘크리트 이름을 입력하세요", className="form-control", style={"fontSize": "0.85rem"})
                                ], width=12),
                            ], className="mb-2"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("노드 목록 (예: [[1,0],[1,1],[0,1],[0,0]])", className="form-label fw-semibold", style={"fontSize": "0.85rem"}),
                                    dbc.Textarea(id="edit-nodes", rows=2, placeholder="노드 좌표를 입력하세요", className="form-control", style={"fontSize": "0.85rem"})
                                ], width=12),
                            ], className="mb-2"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "높이 [m] ",
                                        html.Small("(0.1~500)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold", style={"fontSize": "0.85rem"}),
                                    dbc.Input(id="edit-h", type="number", placeholder="높이를 입력하세요", step=0.1, className="form-control", style={"fontSize": "0.85rem"})
                                ], width=6),
                                dbc.Col([
                                    dbc.Label([
                                        "Solid 요소크기 [m] ",
                                        html.Small("(0.1~10)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold", style={"fontSize": "0.85rem"}),
                                    dbc.Input(id="edit-unit", type="number", placeholder="요소크기", 
                                             step=0.1, className="form-control", style={"fontSize": "0.85rem"})
                                ], width=6),
                            ], className="mb-2"),
                        ], className="bg-light p-2 rounded mb-2"),
                        
                        # 미리보기 섹션
                        html.Div([
                            html.H6("👁️ 3D 미리보기", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                            dcc.Graph(id="edit-preview", style={"height": "50vh"}, className="rounded", config={'displayModeBar': False}),
                        ], className="bg-light p-2 rounded"),
                    ], md=6),
                    
                    # 오른쪽 칼럼: 콘크리트 물성치
                    dbc.Col([
                        html.Div([
                            html.H6("🔬 타설 콘크리트 탄성계수 (CEB-FIB Model)[Pa]", className="mb-3 text-secondary fw-bold"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "베타 상수 ",
                                        html.Small("(0.1~1.0)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="edit-b", type="number", step=0.1, placeholder="베타 상수(con_b)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "N 상수 ",
                                        html.Small("(0.5~0.7)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="edit-n", type="number", step=0.1, placeholder="N 상수(con_n)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "E28(재령 28일 압축 탄성계수) [GPa] ",
                                        html.Small("(1~100)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="edit-e", type="number", step=0.1, placeholder="탄성계수(con_e)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("타설 날짜", className="form-label fw-semibold"),
                                    dbc.Input(id="edit-t-date", type="date", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("타설 시간", className="form-label fw-semibold"),
                                    dbc.Input(id="edit-t-time", type="time", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "열팽창계수 [×10⁻⁵/°C] ",
                                        html.Small("(0.1~10.0)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="edit-a", type="number", step=0.1, placeholder="열팽창계수(con_a)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "포아송비 ",
                                        html.Small("(0.01~1.00)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="edit-p", type="number", step=0.01, placeholder="포아송비(con_p)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label([
                                        "밀도 [kg/m³] ",
                                        html.Small("(500~5000)", className="text-muted", style={"fontSize": "0.7rem"})
                                    ], className="form-label fw-semibold"),
                                    dbc.Input(id="edit-d", type="number", step=10, placeholder="밀도(con_d)", className="form-control")
                                ], width=12),
                            ], className="mb-3"),
                        ], className="bg-light p-3 rounded", style={"height": "fit-content"}),
                    ], md=6),
                ], className="g-3"),
                
                # 경고 메시지 영역 (저장 버튼 근처)
                html.Div([
                    dbc.Alert(id="edit-alert", is_open=False, duration=3000, color="danger", className="mb-0"),
                ], className="mt-3"),
            ]),
            dbc.ModalFooter([
                dbc.Button("3D 미리보기", id="edit-build", color="info", className="px-3", size="sm"),
                dbc.Button("재령분석", id="edit-age-analysis", color="warning", className="px-3", size="sm"),
                dbc.Button("저장", id="edit-save", color="success", className="px-3 fw-semibold ms-auto", size="sm"),
                dbc.Button("닫기", id="edit-close", color="secondary", className="px-3", size="sm"),
            ], className="border-0 pt-2"),
        ]),

        # 콘크리트 불러오기 모달
        dbc.Modal(id="modal-load-concrete", is_open=False, size="md", className="modal-notion", children=[
            dbc.ModalHeader([
                html.H5("📥 기존 콘크리트 불러오기", className="mb-0 text-secondary fw-bold", style={"fontSize": "1.1rem"})
            ], className="border-0 pb-1"),
            dbc.ModalBody([
                html.P("복사할 콘크리트를 선택하세요. 선택한 콘크리트의 설정값이 입력창에 복사됩니다.", 
                       className="text-muted mb-3", style={"fontSize": "0.9rem"}),
                html.Div([
                    dash_table.DataTable(
                        id="load-concrete-table",
                        page_size=5,
                        row_selectable="single",
                        style_table={"overflowY": "auto", "height": "40vh"},
                        style_cell={
                            "whiteSpace": "nowrap", 
                            "textAlign": "center",
                            "fontSize": "0.85rem",
                            "padding": "12px 8px",
                            "border": "none",
                            "borderBottom": "1px solid #f1f1f0",
                        },
                        style_header={
                            "backgroundColor": "#fafafa", 
                            "fontWeight": 600,
                            "color": "#37352f",
                            "border": "none",
                            "borderBottom": "1px solid #e9e9e7",
                            "fontSize": "0.8rem",
                        },
                        style_data={
                            "backgroundColor": "white",
                            "border": "none",
                            "color": "#37352f"
                        },
                        style_data_conditional=[
                            {
                                'if': {'row_index': 'odd'},
                                'backgroundColor': '#fbfbfa'
                            },
                            {
                                'if': {'state': 'selected'},
                                'backgroundColor': '#e8f4fd',
                                'border': '1px solid #579ddb',
                                'borderRadius': '6px',
                                'color': '#1d4ed8'
                            }
                        ]
                    )
                ], className="rounded border")
            ]),
            dbc.ModalFooter([
                dbc.Button("불러오기", id="load-concrete-apply", color="primary", className="px-3", size="sm", disabled=True),
                dbc.Button("취소", id="load-concrete-cancel", color="secondary", className="px-3", size="sm"),
            ], className="border-0 pt-2"),
        ]),

        # 재령분석 모달
        dbc.Modal(id="modal-age-analysis", is_open=False, size="xl", className="modal-notion", children=[
            dcc.Store(id="age-analysis-source"),  # 어느 모달에서 호출되었는지 저장
            dbc.ModalHeader([
                html.H5("📊 재령일별 탄성계수 분석 (CEB-FIB Model)", className="mb-0 text-secondary fw-bold", style={"fontSize": "1.1rem"})
            ], className="border-0 pb-1"),
            dbc.ModalBody([
                # 상단: 수식과 매개변수 섹션
                html.Div([
                    dbc.Row([
                        # 왼쪽: 수식 + 매개변수 설정
                        dbc.Col([
                            # 수식 영역
                            html.Div([
                                html.H6("🔬 CEB-FIB Model", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                                html.Div([
                                    html.P("E(t) = E₂₈ × (t/(t+β))ⁿ", 
                                          className="text-center mb-0", 
                                          style={
                                              "fontSize": "1.0rem", 
                                              "fontWeight": "bold", 
                                              "color": "#495057", 
                                              "backgroundColor": "#f8f9fa", 
                                              "padding": "8px", 
                                              "borderRadius": "6px", 
                                              "fontFamily": "monospace"
                                          }),
                                ], className="border rounded p-1 mb-2"),
                            ]),
                            
                            # 매개변수 설정 영역
                            html.Div([
                                html.H6("⚙️ 매개변수 설정", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label([
                                            "E₂₈ (재령 28일 압축 탄성계수) [GPa] ", 
                                            html.Small("(1~100)", className="text-muted", style={"fontSize": "0.7rem"})
                                        ], className="form-label fw-semibold", style={"fontSize": "0.85rem"}),
                                        dbc.Input(id="analysis-e28", type="number", step=0.1, className="form-control-sm")
                                    ], md=4),
                                    dbc.Col([
                                        dbc.Label([
                                            "β (베타 상수) ", 
                                            html.Small("(0.1~1.0)", className="text-muted", style={"fontSize": "0.7rem"})
                                        ], className="form-label fw-semibold", style={"fontSize": "0.85rem"}),
                                        dbc.Input(id="analysis-beta", type="number", step=0.1, className="form-control-sm")
                                    ], md=4),
                                    dbc.Col([
                                        dbc.Label([
                                            "n (N 상수) ", 
                                            html.Small("(0.5~0.7)", className="text-muted", style={"fontSize": "0.7rem"})
                                        ], className="form-label fw-semibold", style={"fontSize": "0.85rem"}),
                                        dbc.Input(id="analysis-n", type="number", step=0.01, className="form-control-sm")
                                    ], md=4),
                                ], className="g-2 mb-2"),

                            ], className="bg-light p-2 rounded"),
                        ], md=12),  # 전체 너비로 변경
                    ], className="g-2"),
                ], className="bg-white p-2 rounded shadow-sm border mb-2"),
                

                
                # 하단: 결과 섹션
                html.Div([
                    dbc.Row([
                        # 수치 결과 테이블
                        dbc.Col([
                            html.Div([
                                html.H6("📋 수치 결과", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                                html.Div(id="age-analysis-table", style={"height": "45vh", "overflowY": "auto"}),
                            ]),
                        ], md=5),
                        
                        # 그래프
                        dbc.Col([
                            html.Div([
                                html.H6("📊 재령일별 탄성계수 변화", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                                dcc.Graph(id="age-analysis-graph", style={"height": "45vh"}, config={'displayModeBar': False}),
                            ]),
                        ], md=7),
                    ], className="g-2"),
                ], className="bg-white p-2 rounded shadow-sm border mb-2"),
                
                # 경고 메시지 영역 (저장 버튼 근처)
                html.Div([
                    dbc.Alert(id="age-analysis-alert", is_open=False, duration=3000, color="warning", className="mb-0"),
                ]),
            ]),
            dbc.ModalFooter([
                dbc.Button("적용", id="age-analysis-apply", color="success", className="px-3 fw-semibold", size="sm"),
                dbc.Button("닫기", id="age-analysis-close", color="secondary", className="px-3", size="sm"),
            ], className="border-0 pt-2"),
        ]),
], style={"backgroundColor": "#f8f9fa", "minHeight": "100vh"})

# ───────────────────── ① URL에서 프로젝트 정보 읽기
@callback(
    Output("selected-project-store", "data", allow_duplicate=True),
    Output("current-project-info", "children", allow_duplicate=True),
    Input("concrete-url", "search"),
    prevent_initial_call=True
)
def parse_url_project(search):
    if not search:
        return None, [
            "프로젝트가 선택되지 않았습니다. ",
            html.A("홈으로 돌아가기", href="/", className="alert-link")
        ]
    
    try:
        # 암호화된 프로젝트 키 파싱
        project_pk = parse_project_key_from_url(search)
        
        if not project_pk:
            return None, [
                "프로젝트가 선택되지 않았습니다. ",
                html.A("홈으로 돌아가기", href="/", className="alert-link")
            ]
        
        # 프로젝트 정보 조회 (project_pk가 문자열일 수 있음)
        project_info = projects_df[projects_df["project_pk"] == project_pk]
        if project_info.empty:
            return None, [
                f"프로젝트 ID {project_pk}를 찾을 수 없습니다. ",
                html.A("홈으로 돌아가기", href="/", className="alert-link")
            ]
        
        project_name = project_info.iloc[0]["name"]
        return project_pk, f"📁 현재 프로젝트: {project_name}"
        
    except Exception as e:
        return None, [
            f"프로젝트 정보를 읽는 중 오류가 발생했습니다: {str(e)} ",
            html.A("홈으로 돌아가기", href="/", className="alert-link")
        ]

# ───────────────────── ② 테이블 로드 및 필터링
@callback(
    Output("tbl", "data"),
    Output("tbl", "columns"),
    Output("tbl", "selected_rows"),
    Input("init", "n_intervals"),
    Input("selected-project-store", "data"),
    Input("tbl", "data_timestamp"),   # ← 추가
    prevent_initial_call=False
)
def refresh_table(n, project_pk, _data_ts):
    df_all = api_db.get_concrete_data()
    if project_pk:
        df = df_all[df_all["project_pk"] == project_pk]
    else:
        df = pd.DataFrame(columns=df_all.columns if not df_all.empty else [])
    
    # 상태 정보와 타설 날짜 추가
    if not df.empty:
        df["status"] = df["activate"].apply(lambda x: "분석중" if x == 0 else "설정중")
        
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
        
        # 최신 업데이트 순으로 정렬 (updated_at이 있으면 사용, 없으면 concrete_pk 역순)
        if 'updated_at' in df.columns:
            df = df.sort_values('updated_at', ascending=False)
        elif 'created_at' in df.columns:
            df = df.sort_values('created_at', ascending=False)
        else:
            # concrete_pk를 역순으로 정렬 (최신 생성 순)
            df = df.sort_values('concrete_pk', ascending=False)
        
        # 인덱스 재설정
        df = df.reset_index(drop=True)
    
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
    Output("concrete-action-buttons", "style"),
    Output("btn-edit",         "disabled"),
    Output("btn-del",          "disabled"),
    Input("tbl",               "selected_rows"),
    State("tbl",               "data"),
    prevent_initial_call=True
)
def show_selected(sel, data):
    # 아무 것도 선택 안 됐으면 모두 비활성
    if not sel:
        return go.Figure(), "", {"display": "none"}, True, True

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
    status_text = "분석중" if not is_active else "설정중"
    status_color = "success" if not is_active else "secondary"
    
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
            html.Div(con_t_formatted, className="fw-bold", style={"fontSize": "0.8rem", "lineHeight": "1.2"}),
            # 분석중일 때 수정 불가 안내 메시지 추가
            html.Div([
                html.Hr(className="my-2"),
                                 dbc.Alert([
                     html.I(className="fas fa-exclamation-triangle me-2"),
                     "분석중인 콘크리트는 수정할 수 없습니다."
                 ], color="danger", className="py-2 mb-0", style={"fontSize": "0.75rem"})
            ] if not is_active else [], style={"marginTop": "8px"})
        ], className="py-2")
    ], className="shadow-sm")

    if not is_active:
        # 분석중인 경우: 버튼 숨김 및 비활성화
        return fig, details, {"display": "none"}, True, True
    else:
        # 설정중인 경우: 버튼 표시 및 활성화
        return fig, details, {"display": "flex"}, False, False



# ───────────────────── ③ 버튼 활성화 제어
@callback(
    Output("btn-add", "disabled"),
    Input("selected-project-store", "data"),
    prevent_initial_call=False
)
def control_add_button(project_pk):
    return project_pk is None

# ───────────────────── ④ 추가 모달 토글
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

# ───────────────────── ④-1 불러오기 모달 토글
@callback(
    Output("modal-load-concrete", "is_open"),
    Input("add-load-btn", "n_clicks"),
    Input("load-concrete-cancel", "n_clicks"),
    Input("load-concrete-apply", "n_clicks"),
    State("modal-load-concrete", "is_open"),
    prevent_initial_call=True
)
def toggle_load_modal(open_btn, cancel_btn, apply_btn, is_open):
    trig = ctx.triggered_id
    if trig == "add-load-btn":
        return True
    if trig in ("load-concrete-cancel", "load-concrete-apply"):
        return False
    return is_open

# ───────────────────── ④-2 불러오기 모달 열릴 때 테이블 데이터 로드
@callback(
    Output("load-concrete-table", "data"),
    Output("load-concrete-table", "columns"),
    Output("load-concrete-table", "selected_rows"),
    Input("modal-load-concrete", "is_open"),
    State("selected-project-store", "data"),
    prevent_initial_call=True
)
def load_concrete_table_data(is_open, project_pk):
    if not is_open or not project_pk:
        return [], [], []
    
    try:
        df_all = api_db.get_concrete_data()
        df = df_all[df_all["project_pk"] == project_pk]
        
        if df.empty:
            return [], [], []
        
        # 필요한 컬럼만 선택하여 표시
        display_df = df[["concrete_pk", "name", "con_unit", "con_e"]].copy()
        
        cols = [
            {"name": "이름", "id": "name", "type": "text"},
            {"name": "해석단위(m)", "id": "con_unit", "type": "numeric"},
            {"name": "탄성계수(GPa)", "id": "con_e", "type": "numeric"},
        ]
        
        return display_df.to_dict("records"), cols, []
        
    except Exception:
        return [], [], []

# ───────────────────── ④-3 테이블 선택 시 불러오기 버튼 활성화
@callback(
    Output("load-concrete-apply", "disabled"),
    Input("load-concrete-table", "selected_rows"),
    prevent_initial_call=True
)
def enable_load_button(selected_rows):
    return len(selected_rows) == 0  # 선택된 행이 없으면 비활성화

# ───────────────────── ④-4 불러오기 적용 시 값들 복사
@callback(
    Output("add-name", "value", allow_duplicate=True),
    Output("add-nodes", "value", allow_duplicate=True),
    Output("add-h", "value", allow_duplicate=True),
    Output("add-unit", "value", allow_duplicate=True),
    Output("add-b", "value", allow_duplicate=True),
    Output("add-n", "value", allow_duplicate=True),
    Output("add-t-date", "value", allow_duplicate=True),
    Output("add-t-time", "value", allow_duplicate=True),
    Output("add-a", "value", allow_duplicate=True),
    Output("add-p", "value", allow_duplicate=True),
    Output("add-d", "value", allow_duplicate=True),
    Output("add-e", "value", allow_duplicate=True),
    Output("add-preview", "figure", allow_duplicate=True),
    Input("load-concrete-apply", "n_clicks"),
    State("load-concrete-table", "selected_rows"),
    State("load-concrete-table", "data"),
    prevent_initial_call=True
)
def apply_concrete_load(n_clicks, selected_rows, table_data):
    if not n_clicks or not selected_rows:
        raise PreventUpdate
    
    try:
        # 선택된 행의 concrete_pk 가져오기
        selected_concrete_pk = table_data[selected_rows[0]]["concrete_pk"]
        
        # 선택된 콘크리트 데이터 조회
        df = api_db.get_concrete_data(selected_concrete_pk)
        
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            raise PreventUpdate
        
        # DataFrame이면 첫 행을 꺼내 dict로, 아니면 이미 dict라고 가정
        if isinstance(df, pd.DataFrame):
            row = df.iloc[0].to_dict()
        else:
            row = df
        
        # dims 필드가 문자열이면 파싱
        dims_field = row.get("dims", {})
        if isinstance(dims_field, str):
            try:
                dims = ast.literal_eval(dims_field)
            except Exception:
                dims = {}
        else:
            dims = dims_field or {}
        
        # 각 값 추출 (이름은 복사하지 않고 빈 값으로)
        name = ""  # 이름은 복사하지 않음
        nodes = str(dims.get("nodes", []))
        h_value = dims.get("h", 0)
        
        # 콘크리트 속성들
        con_unit = row.get("con_unit", "")
        con_b = row.get("con_b", "")
        con_n = row.get("con_n", "")
        con_a = row.get("con_a", "")
        con_p = row.get("con_p", "")
        con_d = row.get("con_d", "")
        con_e = row.get("con_e", "")
        
        # 타설 시간 포맷팅 (현재 시간으로 설정)
        from datetime import datetime
        dt = datetime.now()
        con_t_date = dt.strftime('%Y-%m-%d')
        con_t_time = dt.strftime('%H:%M')
        
        # 3D 미리보기 생성
        fig = make_fig(dims.get("nodes", []), dims.get("h", 0)) if dims.get("nodes") else go.Figure()
        
        return name, nodes, h_value, con_unit, con_b, con_n, con_t_date, con_t_time, con_a, con_p, con_d, con_e, fig
        
    except Exception:
        raise PreventUpdate

# ───────────────────── ⑤ 추가 미리보기
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

# ───────────────────── ⑥ 추가 저장
@callback(
    Output("add-alert",  "children",      allow_duplicate=True),
    Output("add-alert",  "is_open",       allow_duplicate=True),
    Output("tbl",        "data_timestamp",allow_duplicate=True),
    Output("modal-add",  "is_open",       allow_duplicate=True),
    Output("msg",        "children",      allow_duplicate=True),
    Output("msg",        "color",         allow_duplicate=True),
    Output("msg",        "is_open",       allow_duplicate=True),
    Input("add-save",    "n_clicks"),
    State("selected-project-store", "data"),
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

    # 1) 빈값 및 범위 체크
    missing = []
    range_errors = []
    
    # 기본 정보 체크
    if not project_pk: missing.append("프로젝트 선택")
    if not name:       missing.append("이름")
    if not nodes_txt:  missing.append("노드 목록")
    if not t:          missing.append("타설 시간")
    
    # 수치 입력 필드들 - 빈값과 범위를 함께 체크
    if unit is None:
        missing.append("해석 단위")
    elif unit < 0.1 or unit > 10.0:
        range_errors.append("해석 단위(0.1~10.0)")
        
    if h is None:
        missing.append("높이 H")
    elif h < 0.1 or h > 500:
        range_errors.append("높이(0.1~500)")
        
    if b is None:
        missing.append("베타 상수")
    elif b < 0.1 or b > 1.0:
        range_errors.append("베타 상수(0.1~1.0)")
        
    if n is None:
        missing.append("N 상수")
    elif n < 0.5 or n > 0.7:
        range_errors.append("N 상수(0.5~0.7)")
        
    if a is None:
        missing.append("열팽창계수")
    elif a < 0.1 or a > 10.0:
        range_errors.append("열팽창계수(0.1~10.0)")
        
    if p is None:
        missing.append("포아송비")
    elif p < 0.01 or p > 1.0:
        range_errors.append("포아송비(0.01~1.0)")
        
    if d is None:
        missing.append("밀도")
    elif d < 500 or d > 5000:
        range_errors.append("밀도(500~5000)")
        
    if e is None:
        missing.append("탄성계수")
    elif e < 1 or e > 100:
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
            f"다음 항목의 수치를 입력범위 안으로 조절해주세요: {', '.join(range_errors)}",
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

# ───────────────────── ⑦ 삭제 수행
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

# ───────────────────── ⑧ 수정 모달 열기
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

# ───────────────────── ⑨ 수정 필드 채우기
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


# ───────────────────── ⑩ 수정 미리보기
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

# ───────────────────── ⑪ 수정 저장
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

    # 1) 빈값 및 범위 체크
    missing = []
    range_errors = []
    
    # 기본 정보 체크
    if not cid:        missing.append("항목 선택")
    if not name:       missing.append("이름")
    if not nodes_txt:  missing.append("노드 목록")
    if not t:          missing.append("타설 시간")
    
    # 수치 입력 필드들 - 빈값과 범위를 함께 체크
    if unit is None:
        missing.append("해석 단위")
    elif unit < 0.1 or unit > 10.0:
        range_errors.append("해석 단위(0.1~10.0)")
        
    if h is None:
        missing.append("높이 H")
    elif h < 0.1 or h > 500:
        range_errors.append("높이(0.1~500)")
        
    if b is None:
        missing.append("베타 상수")
    elif b < 0.1 or b > 1.0:
        range_errors.append("베타 상수(0.1~1.0)")
        
    if n is None:
        missing.append("N 상수")
    elif n < 0.5 or n > 0.7:
        range_errors.append("N 상수(0.5~0.7)")
        
    if a is None:
        missing.append("열팽창계수")
    elif a < 0.1 or a > 10.0:
        range_errors.append("열팽창계수(0.1~10.0)")
        
    if p is None:
        missing.append("포아송비")
    elif p < 0.01 or p > 1.0:
        range_errors.append("포아송비(0.01~1.0)")
        
    if d is None:
        missing.append("밀도")
    elif d < 500 or d > 5000:
        range_errors.append("밀도(500~5000)")
        
    if e is None:
        missing.append("탄성계수")
    elif e < 1 or e > 100:
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
            f"다음 항목의 수치를 입력범위 안으로 조절해주세요: {', '.join(range_errors)}",
            True,                                       # edit-alert.is_open
            dash.no_update,                             # tbl.data_timestamp
            True,                                       # modal-edit.is_open
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

# ───────────────────── ⑫ 재령분석 모달 토글 및 소스 추적
@callback(
    Output("modal-age-analysis", "is_open"),
    Output("age-analysis-source", "data"),
    Input("add-age-analysis", "n_clicks"),
    Input("edit-age-analysis", "n_clicks"),
    Input("age-analysis-close", "n_clicks"),
    Input("age-analysis-apply", "n_clicks"),
    State("modal-age-analysis", "is_open"),
    prevent_initial_call=True
)
def toggle_age_analysis(add_btn, edit_btn, close_btn, apply_btn, is_open):
    trig = ctx.triggered_id
    if trig == "add-age-analysis":
        return True, "add"
    elif trig == "edit-age-analysis":
        return True, "edit"
    elif trig in ("age-analysis-close", "age-analysis-apply"):
        return False, dash.no_update
    return is_open, dash.no_update

# ───────────────────── ⑬ 모달 열릴 때 입력창에 기존 값 채우기
@callback(
    Output("analysis-e28", "value"),
    Output("analysis-beta", "value"),
    Output("analysis-n", "value"),
    Input("modal-age-analysis", "is_open"),
    State("age-analysis-source", "data"),
    State("add-e", "value"),
    State("add-b", "value"),
    State("add-n", "value"),
    State("edit-e", "value"),
    State("edit-b", "value"),
    State("edit-n", "value"),
    prevent_initial_call=True
)
def fill_analysis_inputs(is_open, source, add_e, add_b, add_n, edit_e, edit_b, edit_n):
    if not is_open:
        raise PreventUpdate
    
    # 소스에 따라 적절한 값 사용
    if source == "add":
        return add_e, add_b, add_n
    elif source == "edit":
        return edit_e, edit_b, edit_n
    else:
        # 기본값으로 add 사용
        return add_e, add_b, add_n

# ───────────────────── ⑭ 재령분석 계산 및 표시
@callback(
    Output("age-analysis-table", "children"),
    Output("age-analysis-graph", "figure"),
    Output("age-analysis-alert", "children"),
    Output("age-analysis-alert", "is_open"),
    Input("analysis-e28", "value"),
    Input("analysis-beta", "value"),
    Input("analysis-n", "value"),
    State("modal-age-analysis", "is_open"),
    prevent_initial_call=True
)
def calculate_age_analysis(e28, beta, n, is_open):
    if not is_open:
        raise PreventUpdate
    
    # 값 유효성 검사
    if e28 is None or beta is None or n is None:
        missing_params = []
        if e28 is None: missing_params.append("E₂₈")
        if beta is None: missing_params.append("β")
        if n is None: missing_params.append("n")
        
        empty_table = dbc.Alert("매개변수를 입력하면 결과가 표시됩니다.", color="info", className="text-center")
        empty_fig = go.Figure()
        empty_fig.update_layout(
            title="매개변수 입력 후 그래프가 표시됩니다",
            xaxis_title="재령일 [day]",
            yaxis_title="탄성계수 E(t) [GPa]",
            margin=dict(l=40, r=40, t=60, b=40)
        )
        
        alert_msg = f"다음 값들을 먼저 입력해주세요: {', '.join(missing_params)}"
        return empty_table, empty_fig, alert_msg, True
    
    # 범위 자동 조정 (범위를 벗어나면 자동으로 제한)
    e28 = max(1, min(100, e28))
    beta = max(0.1, min(1.0, beta))
    n = max(0.5, min(0.7, n))
    
    # CEB-FIB 모델 계산: E(t) = E28 * (t/(t+β))^n
    days = list(range(1, 29))  # 1일부터 28일까지
    elasticity_values = []
    
    for t in days:
        e_t = e28 * ((t / (t + beta)) ** n)
        elasticity_values.append(e_t)
    

    
    # 테이블 생성 (1일부터 28일까지, 4주간 데이터)
    table_data = []
    highlight_days = [1, 7, 14, 21, 28]
    
    for i, (day, e_val) in enumerate(zip(days, elasticity_values)):
        is_highlight = day in highlight_days
        table_data.append({
            "day": f"{day}일",
            "elasticity": f"{e_val:.2f} GPa",
            "ratio": f"{e_val/e28*100:.1f}%",
            "highlight": is_highlight  # 강조 여부 플래그
        })
    
    # 조건부 스타일링을 위한 스타일 리스트 생성
    style_data_conditional = []
    for i, row in enumerate(table_data):
        if row["highlight"]:
            style_data_conditional.append({
                'if': {'row_index': i},
                'backgroundColor': '#fff3cd',
                'fontWeight': 'bold'
            })
    
    table = dash_table.DataTable(
        data=table_data,
        columns=[
            {"name": "재령", "id": "day", "type": "text"},
            {"name": "E(t) (GPa)", "id": "elasticity", "type": "text"},
            {"name": "E28 대비", "id": "ratio", "type": "text"},
        ],
        style_table={"height": "45vh", "overflowY": "auto"},
        style_cell={
            "textAlign": "center",
            "fontSize": "0.8rem",
            "padding": "6px",
            "border": "1px solid #ddd"
        },
        style_header={
            "backgroundColor": "#f8f9fa",
            "fontWeight": "bold",
            "fontSize": "0.8rem"
        },
        style_data_conditional=style_data_conditional
    )
    
    # 그래프 생성
    fig = go.Figure()
    
    # 메인 곡선
    fig.add_trace(go.Scatter(
        x=days,
        y=elasticity_values,
        mode='lines+markers',
        name='E(t)',
        line=dict(color='#1f77b4', width=3),
        marker=dict(size=6)
    ))
    
    # 주요 포인트 강조
    highlight_indices = [d-1 for d in highlight_days]
    fig.add_trace(go.Scatter(
        x=[days[i] for i in highlight_indices],
        y=[elasticity_values[i] for i in highlight_indices],
        mode='markers',
        name='주요 시점',
        marker=dict(
            size=10,
            color='red',
            symbol='diamond'
        )
    ))
    
    # E28 기준선
    fig.add_hline(
        y=e28,
        line_dash="dash",
        line_color="green",
        annotation_text=f"E28 = {e28} GPa",
        annotation_position="top right"
    )
    
    fig.update_layout(
        title="재령일별 탄성계수 변화 (CEB-FIB Model)",
        xaxis_title="재령일 [day]",
        yaxis_title="탄성계수 E(t) [GPa]",
        margin=dict(l=40, r=40, t=60, b=40),
        showlegend=False,
        hovermode='x unified'
    )
    
    # x축 설정 (주요 시점들만 표시)
    fig.update_xaxes(
        tickmode='array',
        tickvals=highlight_days,
        ticktext=[f'{d}일' for d in highlight_days]
    )
    
    return table, fig, "", False

# ───────────────────── ⑮ 재령분석 결과 적용
@callback(
    Output("add-e", "value", allow_duplicate=True),
    Output("add-b", "value", allow_duplicate=True),
    Output("add-n", "value", allow_duplicate=True),
    Output("edit-e", "value", allow_duplicate=True),
    Output("edit-b", "value", allow_duplicate=True),
    Output("edit-n", "value", allow_duplicate=True),
    Input("age-analysis-apply", "n_clicks"),
    State("age-analysis-source", "data"),
    State("analysis-e28", "value"),
    State("analysis-beta", "value"),
    State("analysis-n", "value"),
    prevent_initial_call=True
)
def apply_age_analysis_values(apply_clicks, source, e28, beta, n):
    if not apply_clicks:
        raise PreventUpdate
    
    # 소스에 따라 적절한 모달에 값 적용
    if source == "add":
        # add 모달에만 적용
        return e28, beta, n, dash.no_update, dash.no_update, dash.no_update
    elif source == "edit":
        # edit 모달에만 적용
        return dash.no_update, dash.no_update, dash.no_update, e28, beta, n
    else:
        # 소스가 명확하지 않으면 아무것도 하지 않음
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update



