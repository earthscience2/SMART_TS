from __future__ import annotations

import os
import glob
import numpy as np
import pandas as pd
import dash
from dash import html, dcc, Input, Output, State, dash_table, register_page, callback
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from datetime import datetime, timedelta

register_page(__name__, path="/strength3d", title="강도/탄성계수 3D 분석")

# ────────────── 레이아웃 ──────────────
layout = dbc.Container(
    fluid=True,
    className="px-4 py-3",
    style={"backgroundColor": "#f7f9fc", "minHeight": "100vh"},
    children=[
        dcc.Location(id="project-url-strength3d", refresh=False),
        dcc.Store(id="project-info-store-strength3d", data=None),
        dcc.Store(id="strength3d-formula-params-store", data={}),
        html.H3("🧱 콘크리트 강도/탄성계수 3D 분석", className="mb-4"),
        dbc.Row([
            # 왼쪽: 콘크리트 목록
            dbc.Col([
                html.Div([
                    dbc.Alert(id="current-project-info-strength3d", color="info", className="mb-3 py-2"),
                    html.Div([
                        html.H6("🧱 콘크리트 목록", className="mb-0 text-secondary fw-bold"),
                        dash_table.DataTable(
                            id="tbl-concrete-strength3d",
                            page_size=5,
                            row_selectable="single",
                            sort_action="native",
                            sort_mode="multi",
                            style_table={"overflowY": "auto", "height": "calc(100vh - 300px)"},
                            style_cell={"whiteSpace": "nowrap", "textAlign": "center", "fontSize": "0.9rem"},
                            style_header={"backgroundColor": "#fafafa", "fontWeight": 600},
                        ),
                        html.Div([
                            dbc.Button("분석 시작", id="btn-concrete-analyze-strength3d", color="success", size="sm", className="px-3", disabled=True),
                        ], className="d-flex justify-content-center gap-2 mt-2"),
                    ], style={"backgroundColor": "white", "padding": "20px", "borderRadius": "12px", "boxShadow": "0 1px 3px rgba(0,0,0,0.1)", "border": "1px solid #e2e8f0", "height": "fit-content"})
                ])
            ], md=4),
            # 오른쪽: 메인
            dbc.Col([
                html.Div([
                    dbc.Tabs([
                        dbc.Tab(label="입력 파라미터", tab_id="tab-strength3d-params"),
                        dbc.Tab(label="3D 강도/탄성계수", tab_id="tab-strength3d-3d"),
                        dbc.Tab(label="노드별 표", tab_id="tab-strength3d-table"),
                    ], id="tabs-main-strength3d", active_tab="tab-strength3d-params", className="mb-0"),
                    html.Div(id="tab-content-strength3d", style={"backgroundColor": "white", "border": "1px solid #e2e8f0", "borderTop": "none", "borderRadius": "0 0 8px 8px", "padding": "20px", "minHeight": "calc(100vh - 200px)"})
                ])
            ], md=8)
        ], className="g-4"),
    ]
)

# 이후 콜백/함수는 TCI 분석 페이지 구조를 참고하여 추가 예정 

# ────────────── 콘크리트 목록 데이터 로딩 콜백 ──────────────
@callback(
    Output("tbl-concrete-strength3d", "data"),
    Output("tbl-concrete-strength3d", "columns"),
    Output("tbl-concrete-strength3d", "selected_rows"),
    Output("project-info-store-strength3d", "data"),
    Input("project-url-strength3d", "search"),
    Input("project-url-strength3d", "pathname"),
    prevent_initial_call=True,
)
def load_concrete_data_strength3d(search, pathname):
    """프로젝트 정보를 로드하고 콘크리트 목록을 표시합니다."""
    if '/strength3d' not in pathname:
        raise dash.exceptions.PreventUpdate
    # (아래는 TCI 분석 페이지의 load_concrete_data_tci 참고, DB 함수는 api_db.get_project_data, api_db.get_concrete_data 사용)
    import api_db
    from utils.encryption import parse_project_key_from_url
    project_pk = None
    if search:
        try:
            project_pk = parse_project_key_from_url(search)
        except Exception:
            pass
    if not project_pk:
        return [], [], [], None
    try:
        df_proj = api_db.get_project_data(project_pk=project_pk)
        if df_proj.empty:
            return [], [], [], None
        proj_row = df_proj.iloc[0]
        proj_name = proj_row["name"]
        df_conc = api_db.get_concrete_data(project_pk=project_pk)
        if df_conc.empty:
            return [], [], [], {"name": proj_name, "pk": project_pk}
    except Exception:
        return [], [], [], None
    table_data = []
    for _, row in df_conc.iterrows():
        table_data.append({
            "concrete_pk": row["concrete_pk"],
            "name": row["name"],
            "pour_date": str(row.get("con_t", "N/A")),
            "activate": "활성" if row["activate"] == 1 else "비활성",
        })
    columns = [
        {"name": "이름", "id": "name", "type": "text"},
        {"name": "타설일", "id": "pour_date", "type": "text"},
        {"name": "상태", "id": "activate", "type": "text"},
    ]
    return table_data, columns, [], {"name": proj_name, "pk": project_pk} 

# ────────────── 입력 파라미터 탭 콘텐츠 함수 ──────────────
def create_strength3d_params_tab_content():
    return html.Div([
        html.H5("강도/탄성계수 공식 및 입력값", style={"fontWeight": "700", "marginBottom": "18px", "color": "#1e293b"}),
        html.Hr(style={"margin": "8px 0 20px 0", "borderColor": "#e5e7eb"}),
        dbc.Row([
            dbc.Col([
                html.Label("강도 공식", style={"fontWeight": "600"}),
                dcc.Dropdown(
                    id="strength3d-fc-formula",
                    options=[
                        {"label": "CEB-FIP Model Code 1990", "value": "ceb"},
                        {"label": "ACI 318", "value": "aci"},
                        {"label": "Eurocode2", "value": "ec2"},
                    ],
                    value="ceb", clearable=False
                ),
                html.Br(),
                html.Label("28일 압축강도 fcm28 (MPa)", style={"fontWeight": "600"}),
                dbc.Input(id="strength3d-fcm28", type="number", value=30, min=10, max=100),
                html.Br(),
                html.Label("(선택) 강도 공식 계수", style={"fontWeight": "600"}),
                dbc.Input(id="strength3d-fc-coef-a", type="number", value=1, min=0.1, max=2, step=0.01),
                dbc.Input(id="strength3d-fc-coef-b", type="number", value=1, min=0.1, max=2, step=0.01),
            ], md=6),
            dbc.Col([
                html.Label("탄성계수 공식", style={"fontWeight": "600"}),
                dcc.Dropdown(
                    id="strength3d-ec-formula",
                    options=[
                        {"label": "CEB-FIP Model Code 1990", "value": "ceb"},
                        {"label": "ACI 318", "value": "aci"},
                        {"label": "Eurocode2", "value": "ec2"},
                    ],
                    value="ceb", clearable=False
                ),
                html.Br(),
                html.Label("28일 탄성계수 Ec28 (MPa)", style={"fontWeight": "600"}),
                dbc.Input(id="strength3d-ec28", type="number", value=30000, min=10000, max=50000),
                html.Br(),
                html.Label("(CEB-FIP) s계수", style={"fontWeight": "600"}),
                dbc.Input(id="strength3d-ec-s", type="number", value=0.2, min=0.1, max=1, step=0.01),
            ], md=6),
        ]),
        html.Div(id="strength3d-formula-preview", className="mt-4"),
    ], style={"maxWidth": "900px", "margin": "0 auto"})

# ────────────── 탭 콘텐츠 스위치 콜백 ──────────────
@callback(
    Output("tab-content-strength3d", "children"),
    Input("tabs-main-strength3d", "active_tab"),
    prevent_initial_call=False
)
def switch_tab_strength3d(active_tab):
    if active_tab == "tab-strength3d-params":
        return create_strength3d_params_tab_content()
    elif active_tab == "tab-strength3d-3d":
        return html.Div("3D 강도/탄성계수 그래프 영역 (추후 구현)")
    elif active_tab == "tab-strength3d-table":
        return html.Div("노드별 표 영역 (추후 구현)")
    else:
        return html.Div("알 수 없는 탭입니다.")

# ────────────── 입력값 Store 저장 콜백 ──────────────
@callback(
    Output("strength3d-formula-params-store", "data"),
    Output("strength3d-formula-preview", "children"),
    Input("strength3d-fc-formula", "value"),
    Input("strength3d-fcm28", "value"),
    Input("strength3d-fc-coef-a", "value"),
    Input("strength3d-fc-coef-b", "value"),
    Input("strength3d-ec-formula", "value"),
    Input("strength3d-ec28", "value"),
    Input("strength3d-ec-s", "value"),
    prevent_initial_call=False
)
def update_strength3d_formula_params(fc_formula, fcm28, fc_a, fc_b, ec_formula, ec28, ec_s):
    params = {
        "fc_formula": fc_formula,
        "fcm28": fcm28,
        "fc_a": fc_a,
        "fc_b": fc_b,
        "ec_formula": ec_formula,
        "ec28": ec28,
        "ec_s": ec_s
    }
    # 미리보기 텍스트
    fc_formula_txt = f"강도 공식: {fc_formula}, fcm28={fcm28}, a={fc_a}, b={fc_b}"
    ec_formula_txt = f"탄성계수 공식: {ec_formula}, Ec28={ec28}, s={ec_s}"
    preview = html.Div([
        html.Div(fc_formula_txt),
        html.Div(ec_formula_txt)
    ], style={"color": "#64748b", "fontSize": "15px"})
    return params, preview 

# ────────────── INP 파일 파서: 노드 좌표 추출 ──────────────
def read_inp_nodes(inp_path):
    """INP 파일에서 노드 좌표를 추출합니다."""
    nodes = []
    try:
        with open(inp_path, 'r') as f:
            lines = f.readlines()
        node_section = False
        for line in lines:
            if line.strip().startswith('*NODE'):
                node_section = True
                continue
            if node_section:
                if line.strip().startswith('*') or line.strip() == '':
                    break
                parts = line.strip().split(',')
                if len(parts) >= 4:
                    node_id = int(parts[0])
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                    nodes.append({"id": node_id, "x": x, "y": y, "z": z})
    except Exception as e:
        print(f"INP 파싱 오류: {e}")
    return nodes 

# ────────────── 강도/탄성계수 계산 함수 ──────────────
def calc_strength_over_age(age_days, fcm28, formula="ceb", a=1, b=1):
    """
    재령(age_days)에 따른 압축강도(MPa) 계산
    formula: 'ceb', 'aci', 'ec2'
    """
    if age_days <= 0:
        return 0
    if formula == "ceb":
        # CEB-FIP: fcm(t) = fcm28 * ( t / (a + b*t) )^0.5
        return fcm28 * (age_days / (a + b * age_days)) ** 0.5
    elif formula == "aci":
        # ACI: fcm(t) = fcm28 * (age_days/28)^0.5 (t<=28), 이후는 fcm28
        return fcm28 * (age_days/28) ** 0.5 if age_days <= 28 else fcm28
    elif formula == "ec2":
        # EC2: fcm(t) = fcm28 * exp[s*(1-(28/t))], s=0.2(보통강도)
        s = 0.2
        return fcm28 * np.exp(s * (1 - 28/age_days))
    else:
        return fcm28

def calc_elastic_modulus_over_age(age_days, fc_t, ec28, formula="ceb", s=0.2):
    """
    재령(age_days)에 따른 탄성계수(MPa) 계산
    fc_t: 해당 시점 강도(MPa)
    formula: 'ceb', 'aci', 'ec2'
    """
    if formula == "ceb":
        # CEB-FIP: Ec(t) = Ec28 * exp[s*(1-28/t)]
        return ec28 * np.exp(s * (1 - 28/age_days))
    elif formula == "aci":
        # ACI: Ec = 4700 * sqrt(fc)
        return 4700 * np.sqrt(fc_t)
    elif formula == "ec2":
        # EC2: Ec = 22000 * (fc/10)^0.3
        return 22000 * (fc_t/10) ** 0.3
    else:
        return ec28 

# ────────────── 3D 그래프 및 표 콜백 ──────────────
@callback(
    Output("tab-content-strength3d", "children", allow_duplicate=True),
    Input("tbl-concrete-strength3d", "selected_rows"),
    Input("strength3d-formula-params-store", "data"),
    State("tbl-concrete-strength3d", "data"),
    prevent_initial_call=True
)
def update_strength3d_analysis(selected_rows, formula_params, tbl_data):
    """콘크리트 선택 시 3D 강도/탄성계수 분석을 수행합니다."""
    if not selected_rows or not tbl_data or not formula_params:
        return html.Div("콘크리트를 선택하고 입력 파라미터를 설정하세요.")
    
    try:
        row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
        concrete_pk = row["concrete_pk"]
        concrete_name = row["name"]
        
        # INP 파일 찾기
        inp_dir = f"inp/{concrete_pk}"
        if not os.path.exists(inp_dir):
            return html.Div("INP 파일이 없습니다.")
        
        inp_files = glob.glob(f"{inp_dir}/*.inp")
        if not inp_files:
            return html.Div("INP 파일이 없습니다.")
        
        # 첫 번째 INP 파일 사용
        inp_file = inp_files[0]
        nodes = read_inp_nodes(inp_file)
        if not nodes:
            return html.Div("노드 정보를 읽을 수 없습니다.")
        
        # 재령 계산 (예시: 7일)
        age_days = 7.0
        
        # 강도/탄성계수 계산
        fc_t = calc_strength_over_age(
            age_days, 
            formula_params["fcm28"], 
            formula_params["fc_formula"],
            formula_params["fc_a"],
            formula_params["fc_b"]
        )
        
        ec_t = calc_elastic_modulus_over_age(
            age_days,
            fc_t,
            formula_params["ec28"],
            formula_params["ec_formula"],
            formula_params["ec_s"]
        )
        
        # 3D 그래프 생성
        x_coords = [node["x"] for node in nodes]
        y_coords = [node["y"] for node in nodes]
        z_coords = [node["z"] for node in nodes]
        
        # 모든 노드에 동일한 값 적용 (실제로는 위치별로 다를 수 있음)
        strength_values = [fc_t] * len(nodes)
        elastic_values = [ec_t] * len(nodes)
        
        # 3D 강도 그래프
        strength_fig = go.Figure(data=go.Volume(
            x=x_coords, y=y_coords, z=z_coords, value=strength_values,
            opacity=0.1, surface_count=15, colorscale='Viridis',
            colorbar=dict(title='강도 (MPa)', thickness=10),
            showscale=True
        ))
        strength_fig.update_layout(
            title=f"{concrete_name} - 3D 강도 분포 (재령: {age_days}일)",
            scene=dict(aspectmode='data', bgcolor='white'),
            margin=dict(l=0, r=0, t=30, b=0)
        )
        
        # 3D 탄성계수 그래프
        elastic_fig = go.Figure(data=go.Volume(
            x=x_coords, y=y_coords, z=z_coords, value=elastic_values,
            opacity=0.1, surface_count=15, colorscale='Plasma',
            colorbar=dict(title='탄성계수 (MPa)', thickness=10),
            showscale=True
        ))
        elastic_fig.update_layout(
            title=f"{concrete_name} - 3D 탄성계수 분포 (재령: {age_days}일)",
            scene=dict(aspectmode='data', bgcolor='white'),
            margin=dict(l=0, r=0, t=30, b=0)
        )
        
        # 노드별 표 데이터
        table_data = []
        for i, node in enumerate(nodes[:20]):  # 처음 20개 노드만 표시
            table_data.append({
                "노드ID": node["id"],
                "X (m)": round(node["x"], 3),
                "Y (m)": round(node["y"], 3),
                "Z (m)": round(node["z"], 3),
                "강도 (MPa)": round(strength_values[i], 2),
                "탄성계수 (MPa)": round(elastic_values[i], 0)
            })
        
        # 3D 탭 콘텐츠
        if dash.callback_context.triggered[0]['prop_id'] == 'tbl-concrete-strength3d.selected_rows':
            active_tab = "tab-strength3d-3d"
        else:
            active_tab = dash.callback_context.inputs.get('tabs-main-strength3d.active_tab', 'tab-strength3d-params')
        
        if active_tab == "tab-strength3d-3d":
            return html.Div([
                html.H5(f"3D 강도/탄성계수 분석 - {concrete_name}", style={"fontWeight": "700", "marginBottom": "18px"}),
                dbc.Row([
                    dbc.Col([
                        dcc.Graph(figure=strength_fig, style={"height": "400px"})
                    ], md=6),
                    dbc.Col([
                        dcc.Graph(figure=elastic_fig, style={"height": "400px"})
                    ], md=6)
                ]),
                html.Div([
                    html.H6("분석 정보", style={"fontWeight": "600", "marginTop": "20px"}),
                    html.P(f"재령: {age_days}일"),
                    html.P(f"평균 강도: {fc_t:.2f} MPa"),
                    html.P(f"평균 탄성계수: {ec_t:.0f} MPa")
                ])
            ])
        elif active_tab == "tab-strength3d-table":
            return html.Div([
                html.H5(f"노드별 강도/탄성계수 표 - {concrete_name}", style={"fontWeight": "700", "marginBottom": "18px"}),
                dash_table.DataTable(
                    columns=[{"name": k, "id": k} for k in table_data[0].keys()],
                    data=table_data,
                    page_size=10,
                    style_table={"overflowY": "auto", "height": "400px"},
                    style_cell={"textAlign": "center", "fontSize": "14px"},
                    style_header={"backgroundColor": "#f8fafc", "fontWeight": "600"}
                )
            ])
        else:
            return create_strength3d_params_tab_content()
            
    except Exception as e:
        return html.Div(f"분석 중 오류 발생: {str(e)}") 