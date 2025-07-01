from dash import html, dcc, register_page, callback, Input, Output
import dash_bootstrap_components as dbc
from flask import request as flask_request
from api_db import get_project_data_with_stats

register_page(__name__, path="/admin_dashboard", title="관리자 대시보드")

def get_system_stats():
    """시스템 통계 데이터를 가져옵니다"""
    try:
        # 프로젝트 데이터 조회
        projects_df = get_project_data_with_stats()
        active_projects = len(projects_df) if not projects_df.empty else 0
        
        # 센서 수는 프로젝트 데이터에서 집계
        total_sensors = projects_df['sensor_count'].sum() if not projects_df.empty else 0
        
        return {
            'active_projects': active_projects,
            'active_sensors': total_sensors,
            'system_status': '정상'
        }
    except Exception as e:
        print(f"시스템 통계 조회 오류: {e}")
        return {
            'active_projects': 0,
            'active_sensors': 0,
            'system_status': '오류'
        }

def create_feature_card(title, description, href, color):
    """기능 카드 컴포넌트 생성"""
    return dbc.Card([
        dbc.CardBody([
            html.H5(title, className=f"card-title text-{color}"),
            html.P(description, className="card-text"),
            dcc.Link(
                dbc.Button(title.split(" ")[-1], color=color, className="w-100"),
                href=href
            )
        ])
    ], className="mb-3")

def create_status_card(title, value, color):
    """상태 카드 컴포넌트 생성"""
    return dbc.Card([
        dbc.CardBody([
            html.H6(title, className=f"text-{color}"),
            html.H3(str(value), className=f"fw-bold text-{color}")
        ])
    ])

def layout(**kwargs):
    """Admin dashboard layout."""
    return html.Div([
        dcc.Location(id="admin-dashboard-url", refresh=False),
        dbc.Container([
            # 메인 콘텐츠
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H4("🔧 관리자 기능", className="mb-0 text-primary")
                        ]),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    create_feature_card(
                                        "📊 프로젝트 관리",
                                        "프로젝트 생성, 수정, 삭제 및 권한 관리",
                                        "/admin_projects",
                                        "primary"
                                    )
                                ], width=3),
                                dbc.Col([
                                    create_feature_card(
                                        "📋 일반 로그",
                                        "로그인, 센서, 프로젝트, 콘크리트 로그 확인",
                                        "/admin_logs",
                                        "success"
                                    )
                                ], width=3),
                                dbc.Col([
                                    create_feature_card(
                                        "⚙️ 자동화 로그",
                                        "자동화 작업 로그 및 모니터링",
                                        "/admin_automation",
                                        "warning"
                                    )
                                ], width=3),
                            ]),
                            
                            html.Hr(className="my-4"),
                            
                            # 시스템 상태 요약
                            dbc.Row([
                                dbc.Col([
                                    html.H5("📈 시스템 상태", className="text-dark mb-3"),
                                    html.Div(id="system-status-cards")
                                ])
                            ])
                        ])
                    ], className="shadow")
                ])
            ])
        ], fluid=True)
    ])

@callback(
    Output("system-status-cards", "children"),
    Input("admin-dashboard-url", "pathname")
)
def update_system_status(pathname):
    """시스템 상태 카드 업데이트"""
    stats = get_system_stats()
    
    status_color = "success" if stats['system_status'] == '정상' else "danger"
    
    cards = dbc.Row([
        dbc.Col([
            create_status_card("활성 프로젝트", stats['active_projects'], "primary")
        ], width=4),
        dbc.Col([
            create_status_card("활성 센서", stats['active_sensors'], "info")
        ], width=4),
        dbc.Col([
            create_status_card("시스템 상태", stats['system_status'], status_color)
        ], width=4),
    ])
    
    return cards

@callback(
    [Output("admin-dashboard-url", "pathname")],
    [Input("admin-dashboard-url", "pathname")],
    allow_duplicate=True
)
def check_admin_access(pathname):
    """관리자 권한 확인"""
    if not flask_request.cookies.get("admin_user"):
        return ["/admin"]
    return [pathname] 