# pages/admin_projects.py
from dash import html, dcc, register_page, callback, Input, Output
import dash_bootstrap_components as dbc
from flask import request as flask_request
import pandas as pd
from api_db import get_accessible_projects

register_page(__name__, path="/admin_projects", title="프로젝트 관리")

def layout(**kwargs):
    """Admin projects management layout."""
    return html.Div([
        dcc.Location(id="admin-projects-url", refresh=False),
        dcc.Store(id="projects-data-store"),
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
                                    ], color="success", className="mb-3")
                                ], width=12)
                            ]),
                            
                            # 프로젝트 목록 테이블
                            html.Div(id="projects-table-container"),
                            
                            # 페이지네이션
                            dbc.Row([
                                dbc.Col([
                                    dbc.Pagination(
                                        id="project-pagination",
                                        max_value=5,
                                        fully_expanded=False,
                                        first_last=True,
                                        previous_next=True,
                                        className="justify-content-center mt-3"
                                    )
                                ])
                            ])
                        ])
                    ], className="shadow")
                ])
            ])
        ], fluid=True)
    ])

@callback(
    Output("projects-data-store", "data"),
    Input("admin-projects-url", "pathname")
)
def load_projects_data(pathname):
    """프로젝트 데이터를 로드합니다."""
    try:
        # 관리자 권한으로 모든 프로젝트 조회
        result = get_accessible_projects("admin", its_num=1)
        
        if result["result"] == "Success" and result["projects"] is not None:
            # 날짜 형식 변환
            df = result["projects"].copy()
            if not df.empty:
                # regdate와 closedate를 문자열로 변환
                if 'regdate' in df.columns:
                    df['regdate'] = df['regdate'].astype(str).str[:10]  # YYYY-MM-DD 형식
                if 'closedate' in df.columns:
                    df['closedate'] = df['closedate'].astype(str).str[:10]  # YYYY-MM-DD 형식
            
            return df.to_dict('records')
        else:
            return []
    except Exception as e:
        print(f"Error loading projects: {e}")
        return []

@callback(
    Output("projects-table-container", "children"),
    Input("projects-data-store", "data")
)
def update_projects_table(projects_data):
    """프로젝트 테이블을 업데이트합니다."""
    if not projects_data:
        return dbc.Alert("프로젝트 데이터를 불러올 수 없습니다.", color="warning")
    
    # 테이블 헤더
    table_header = [
        html.Thead([
            html.Tr([
                html.Th("프로젝트 ID"),
                html.Th("프로젝트명"),
                html.Th("등록일"),
                html.Th("종료일"),
                html.Th("작업")
            ])
        ])
    ]
    
    # 테이블 바디
    table_rows = []
    for project in projects_data:
        row = html.Tr([
            html.Td(project.get('projectid', '')),
            html.Td(project.get('projectname', '')),
            html.Td(project.get('regdate', '')),
            html.Td(project.get('closedate', '')),
            html.Td([
                dbc.Button("수정", size="sm", color="primary", className="me-1"),
                dbc.Button("삭제", size="sm", color="danger")
            ])
        ])
        table_rows.append(row)
    
    table_body = [html.Tbody(table_rows)]
    
    return dbc.Table(
        table_header + table_body,
        striped=True,
        bordered=True,
        hover=True,
        responsive=True
    )

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