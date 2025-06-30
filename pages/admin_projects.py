# pages/admin_projects.py
from dash import html, dcc, register_page, callback, Input, Output, State, ALL
import dash_bootstrap_components as dbc
from flask import request as flask_request
import pandas as pd
from api_db import get_project_data, update_project_data, delete_project_data, add_project_data, get_all_sensor_structures
import json
import dash

register_page(__name__, path="/admin_projects", title="프로젝트 관리")

def layout(**kwargs):
    """Admin projects management layout."""
    return html.Div([
        dcc.Location(id="admin-projects-url", refresh=False),
        dcc.Store(id="projects-data-store"),
        dcc.Store(id="current-page", data=1),
        dcc.Store(id="sensor-structures-store"),
        dbc.Container([
            # 메인 콘텐츠
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H4("📊 프로젝트 관리", className="mb-0 text-primary"),
                            html.Small("프로젝트 생성, 수정, 삭제 및 권한 관리", className="text-muted")
                        ]),
                        dbc.CardBody([
                            # 프로젝트 추가 버튼
                            dbc.Row([
                                dbc.Col([
                                    dbc.Button([
                                        html.Span("➕", className="me-2"),
                                        "새 프로젝트 추가"
                                    ], color="success", className="mb-3", id="add-project-btn")
                                ], width=12)
                            ]),
                            
                            # 프로젝트 목록 테이블
                            html.Div(id="projects-table-container"),
                            
                            # 페이지네이션
                            dbc.Row([
                                dbc.Col([
                                    html.Div(id="pagination-container", className="d-flex justify-content-center mt-3")
                                ])
                            ])
                        ])
                    ], className="shadow")
                ])
            ])
        ], fluid=True),
        
        # 새 프로젝트 추가 모달
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("새 프로젝트 추가")),
            dbc.ModalBody([
                dbc.Form([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("프로젝트명", className="fw-bold"),
                            dbc.Input(id="new-project-name", type="text", placeholder="프로젝트명을 입력하세요", className="mb-3")
                        ], width=12)
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("센서 구조 목록", className="fw-bold"),
                            html.Div(id="sensor-structures-table-container", className="mt-2")
                        ], width=12)
                    ])
                ])
            ]),
            dbc.ModalFooter([
                dbc.Button("취소", id="add-cancel", className="ms-auto"),
                dbc.Button("생성", id="add-save", color="primary")
            ])
        ], id="add-modal", is_open=False, size="lg"),
        
        # 수정 모달
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("프로젝트 수정")),
            dbc.ModalBody([
                dbc.Form([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("프로젝트 ID", className="fw-bold"),
                            dbc.Input(id="edit-project-id", type="text", disabled=True, className="mb-3")
                        ], width=6),
                        dbc.Col([
                            dbc.Label("프로젝트명", className="fw-bold"),
                            dbc.Input(id="edit-project-name", type="text", placeholder="프로젝트명을 입력하세요", className="mb-3")
                        ], width=6)
                    ])
                ])
            ]),
            dbc.ModalFooter([
                dbc.Button("취소", id="edit-cancel", className="ms-auto"),
                dbc.Button("저장", id="edit-save", color="primary")
            ])
        ], id="edit-modal", is_open=False),
        
        # 삭제 확인 모달
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("프로젝트 삭제 확인")),
            dbc.ModalBody([
                html.P("정말로 이 프로젝트를 삭제하시겠습니까?"),
                html.P(id="delete-project-info", className="text-danger fw-bold")
            ]),
            dbc.ModalFooter([
                dbc.Button("취소", id="delete-cancel", className="ms-auto"),
                dbc.Button("삭제", id="delete-confirm", color="danger")
            ])
        ], id="delete-modal", is_open=False),
        
        # 알림 토스트
        dbc.Toast([
            html.P(id="toast-message")
        ], id="toast", header="알림", is_open=False, dismissable=True, icon="primary", style={"position": "fixed", "top": 66, "right": 10, "width": 350})
    ])

@callback(
    Output("projects-data-store", "data"),
    Input("admin-projects-url", "pathname")
)
def load_projects_data(pathname):
    """프로젝트 데이터를 로드합니다."""
    try:
        # get_project_data 함수를 사용하여 모든 프로젝트 조회
        df = get_project_data()
        
        if not df.empty:
            # 날짜 형식 변환
            df_copy = df.copy()
            if 'created_at' in df_copy.columns:
                df_copy['created_at'] = df_copy['created_at'].astype(str).str[:10]  # YYYY-MM-DD 형식
            if 'updated_at' in df_copy.columns:
                df_copy['updated_at'] = df_copy['updated_at'].astype(str).str[:10]  # YYYY-MM-DD 형식
            
            return df_copy.to_dict('records')
        else:
            return []
    except Exception as e:
        print(f"Error loading projects: {e}")
        return []

@callback(
    Output("sensor-structures-store", "data"),
    Input("admin-projects-url", "pathname")
)
def load_sensor_structures_data(pathname):
    """센서 구조 데이터를 로드합니다."""
    try:
        # get_all_sensor_structures 함수를 사용하여 모든 센서 구조 조회
        df = get_all_sensor_structures(its_num=1)
        
        if not df.empty:
            return df.to_dict('records')
        else:
            return []
    except Exception as e:
        print(f"Error loading sensor structures: {e}")
        return []

@callback(
    [Output("projects-table-container", "children"),
     Output("pagination-container", "children")],
    [Input("projects-data-store", "data"),
     Input("current-page", "data")]
)
def update_projects_table(projects_data, current_page):
    """프로젝트 테이블을 업데이트합니다."""
    if not projects_data:
        return dbc.Alert("프로젝트 데이터를 불러올 수 없습니다.", color="warning"), ""
    
    # 페이지네이션 설정
    items_per_page = 10
    total_items = len(projects_data)
    total_pages = (total_items + items_per_page - 1) // items_per_page
    
    # 현재 페이지의 데이터만 선택
    start_idx = (current_page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    current_data = projects_data[start_idx:end_idx]
    
    # 테이블 헤더
    table_header = [
        html.Thead([
            html.Tr([
                html.Th("프로젝트 ID"),
                html.Th("프로젝트명"),
                html.Th("생성일"),
                html.Th("수정일"),
                html.Th("작업")
            ])
        ])
    ]
    
    # 테이블 바디
    table_rows = []
    for project in current_data:
        row = html.Tr([
            html.Td(project.get('project_pk', '')),
            html.Td(project.get('name', '')),
            html.Td(project.get('created_at', '')),
            html.Td(project.get('updated_at', '')),
            html.Td([
                dbc.Button("수정", size="sm", color="primary", className="me-1", 
                          id={"type": "edit-btn", "index": project.get('project_pk', '')}),
                dbc.Button("삭제", size="sm", color="danger",
                          id={"type": "delete-btn", "index": project.get('project_pk', '')})
            ])
        ])
        table_rows.append(row)
    
    table_body = [html.Tbody(table_rows)]
    
    # 페이지네이션 컴포넌트
    if total_pages > 1:
        pagination = dbc.Pagination(
            id="project-pagination",
            max_value=total_pages,
            value=current_page,
            fully_expanded=False,
            first_last=True,
            previous_next=True,
            className="justify-content-center"
        )
    else:
        pagination = ""
    
    return dbc.Table(
        table_header + table_body,
        striped=True,
        bordered=True,
        hover=True,
        responsive=True
    ), pagination

# 수정 모달 관련 콜백
@callback(
    [Output("edit-modal", "is_open"),
     Output("edit-project-id", "value"),
     Output("edit-project-name", "value")],
    [Input({"type": "edit-btn", "index": ALL}, "n_clicks")],
    [State("projects-data-store", "data")],
    prevent_initial_call=True
)
def open_edit_modal(n_clicks, projects_data):
    """수정 모달을 엽니다."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return False, "", ""
    
    # n_clicks가 None이거나 모든 값이 None이면 초기 로드이므로 모달을 열지 않음
    if not n_clicks or all(click is None for click in n_clicks):
        return False, "", ""
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    project_id = json.loads(button_id)['index']
    
    # 프로젝트 데이터 찾기
    project = next((p for p in projects_data if p.get('project_pk') == project_id), None)
    if project:
        return True, project.get('project_pk', ''), project.get('name', '')
    
    return False, "", ""

@callback(
    [Output("edit-modal", "is_open", allow_duplicate=True),
     Output("toast", "is_open"),
     Output("toast-message", "children"),
     Output("projects-data-store", "data", allow_duplicate=True)],
    [Input("edit-save", "n_clicks"),
     Input("edit-cancel", "n_clicks")],
    [State("edit-project-id", "value"),
     State("edit-project-name", "value"),
     State("projects-data-store", "data")],
    prevent_initial_call=True
)
def handle_edit_modal(save_clicks, cancel_clicks, project_id, project_name, projects_data):
    """수정 모달을 처리합니다."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return False, False, "", dash.no_update
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == "edit-cancel":
        return False, False, "", dash.no_update
    
    if button_id == "edit-save" and project_id and project_name:
        try:
            # 프로젝트 업데이트
            update_project_data(
                project_pk=project_id,
                name=project_name
            )
            
            # 데이터 다시 로드
            df = get_project_data()
            if not df.empty:
                df_copy = df.copy()
                if 'created_at' in df_copy.columns:
                    df_copy['created_at'] = df_copy['created_at'].astype(str).str[:10]
                if 'updated_at' in df_copy.columns:
                    df_copy['updated_at'] = df_copy['updated_at'].astype(str).str[:10]
                new_data = df_copy.to_dict('records')
            else:
                new_data = []
            
            return False, True, "프로젝트가 성공적으로 수정되었습니다.", new_data
        except Exception as e:
            return False, True, f"프로젝트 수정 중 오류가 발생했습니다: {str(e)}", dash.no_update
    
    return False, False, "", dash.no_update

# 삭제 모달 관련 콜백
@callback(
    [Output("delete-modal", "is_open"),
     Output("delete-project-info", "children")],
    [Input({"type": "delete-btn", "index": ALL}, "n_clicks")],
    [State("projects-data-store", "data")],
    prevent_initial_call=True
)
def open_delete_modal(n_clicks, projects_data):
    """삭제 모달을 엽니다."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return False, ""
    
    # n_clicks가 None이거나 모든 값이 None이면 초기 로드이므로 모달을 열지 않음
    if not n_clicks or all(click is None for click in n_clicks):
        return False, ""
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    project_id = json.loads(button_id)['index']
    
    # 프로젝트 데이터 찾기
    project = next((p for p in projects_data if p.get('project_pk') == project_id), None)
    if project:
        project_info = f"프로젝트 ID: {project.get('project_pk', '')} | 프로젝트명: {project.get('name', '')}"
        return True, project_info
    
    return False, ""

@callback(
    [Output("delete-modal", "is_open", allow_duplicate=True),
     Output("toast", "is_open", allow_duplicate=True),
     Output("toast-message", "children", allow_duplicate=True),
     Output("projects-data-store", "data", allow_duplicate=True)],
    [Input("delete-confirm", "n_clicks"),
     Input("delete-cancel", "n_clicks")],
    [State("delete-project-info", "children"),
     State("projects-data-store", "data")],
    prevent_initial_call=True
)
def handle_delete_modal(confirm_clicks, cancel_clicks, project_info, projects_data):
    """삭제 모달을 처리합니다."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return False, False, "", dash.no_update
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == "delete-cancel":
        return False, False, "", dash.no_update
    
    if button_id == "delete-confirm" and project_info:
        try:
            # 프로젝트 ID 추출
            project_id = project_info.split(" | ")[0].split(": ")[1]
            
            # 프로젝트 삭제
            delete_project_data(project_pk=project_id)
            
            # 데이터 다시 로드
            df = get_project_data()
            if not df.empty:
                df_copy = df.copy()
                if 'created_at' in df_copy.columns:
                    df_copy['created_at'] = df_copy['created_at'].astype(str).str[:10]
                if 'updated_at' in df_copy.columns:
                    df_copy['updated_at'] = df_copy['updated_at'].astype(str).str[:10]
                new_data = df_copy.to_dict('records')
            else:
                new_data = []
            
            return False, True, "프로젝트가 성공적으로 삭제되었습니다.", new_data
        except Exception as e:
            return False, True, f"프로젝트 삭제 중 오류가 발생했습니다: {str(e)}", dash.no_update
    
    return False, False, "", dash.no_update

# 페이지네이션 콜백
@callback(
    Output("current-page", "data"),
    Input("project-pagination", "value"),
    prevent_initial_call=True
)
def update_current_page(page):
    """현재 페이지를 업데이트합니다."""
    return page if page else 1

@callback(
    [Output("admin-projects-url", "pathname")],
    [Input("admin-projects-url", "pathname")],
    allow_duplicate=True
)
def check_admin_access(pathname):
    """관리자 권한 확인"""
    if not flask_request.cookies.get("admin_user"):
        return ["/admin"]
    return [pathname]

# 새 프로젝트 추가 모달 관련 콜백
@callback(
    [Output("add-modal", "is_open"),
     Output("new-project-name", "value")],
    [Input("add-project-btn", "n_clicks")],
    prevent_initial_call=True
)
def open_add_modal(n_clicks):
    """새 프로젝트 추가 모달을 엽니다."""
    if not n_clicks:
        return False, ""
    
    return True, ""

@callback(
    Output("sensor-structures-table-container", "children"),
    [Input("add-modal", "is_open"),
     Input("sensor-structures-store", "data")]
)
def update_sensor_structures_table(is_open, structures_data):
    """센서 구조 테이블을 업데이트합니다."""
    if not is_open or not structures_data:
        return ""
    
    # 테이블 헤더
    table_header = [
        html.Thead([
            html.Tr([
                html.Th("선택"),
                html.Th("구조 ID"),
                html.Th("구조명"),
                html.Th("디바이스 수"),
                html.Th("센서 수")
            ])
        ])
    ]
    
    # 테이블 바디
    table_rows = []
    for i, structure in enumerate(structures_data):
        row = html.Tr([
            html.Td([
                dbc.RadioButton(
                    id={"type": "structure-select", "index": i},
                    name="structure-selection",
                    value=structure.get('structure_id', '')
                )
            ]),
            html.Td(structure.get('structure_id', '')),
            html.Td(structure.get('structure_name', '')),
            html.Td(structure.get('device_count', 0)),
            html.Td(structure.get('sensor_count', 0))
        ])
        table_rows.append(row)
    
    table_body = [html.Tbody(table_rows)]
    
    return dbc.Table(
        table_header + table_body,
        striped=True,
        bordered=True,
        hover=True,
        responsive=True,
        size="sm"
    )

@callback(
    [Output("add-modal", "is_open", allow_duplicate=True),
     Output("toast", "is_open", allow_duplicate=True),
     Output("toast-message", "children", allow_duplicate=True),
     Output("projects-data-store", "data", allow_duplicate=True)],
    [Input("add-save", "n_clicks"),
     Input("add-cancel", "n_clicks")],
    [State("new-project-name", "value"),
     State({"type": "structure-select", "index": ALL}, "value"),
     State("sensor-structures-store", "data")],
    prevent_initial_call=True
)
def handle_add_modal(save_clicks, cancel_clicks, project_name, selected_structures, structures_data):
    """새 프로젝트 추가 모달을 처리합니다."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return False, False, "", dash.no_update
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == "add-cancel":
        return False, False, "", dash.no_update
    
    if button_id == "add-save" and project_name and selected_structures:
        try:
            # 선택된 구조 찾기
            selected_structure = None
            for i, value in enumerate(selected_structures):
                if value:
                    selected_structure = structures_data[i]
                    break
            
            if not selected_structure:
                return False, True, "구조를 선택해주세요.", dash.no_update
            
            # 프로젝트 생성
            add_project_data(
                user_company_pk="UC000001",  # 기본값 사용
                name=project_name
            )
            
            # 데이터 다시 로드
            df = get_project_data()
            if not df.empty:
                df_copy = df.copy()
                if 'created_at' in df_copy.columns:
                    df_copy['created_at'] = df_copy['created_at'].astype(str).str[:10]
                if 'updated_at' in df_copy.columns:
                    df_copy['updated_at'] = df_copy['updated_at'].astype(str).str[:10]
                new_data = df_copy.to_dict('records')
            else:
                new_data = []
            
            structure_info = f"구조 ID: {selected_structure.get('structure_id', '')}, 구조명: {selected_structure.get('structure_name', '')}"
            return False, True, f"프로젝트 '{project_name}'이(가) 성공적으로 생성되었습니다. ({structure_info})", new_data
        except Exception as e:
            return False, True, f"프로젝트 생성 중 오류가 발생했습니다: {str(e)}", dash.no_update
    
    return False, False, "", dash.no_update 