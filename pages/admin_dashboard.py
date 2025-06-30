from dash import html, dcc, register_page, callback, Input, Output
import dash_bootstrap_components as dbc
from flask import request as flask_request
import pandas as pd

register_page(__name__, path="/admin_dashboard", title="관리자 대시보드")

def layout(**kwargs):
    """Admin dashboard layout."""
    return html.Div([
        dcc.Location(id="admin-dashboard-url", refresh=False),
        dbc.Container([
            # 관리자 전용 네비게이션 바
            dbc.Navbar(
                dbc.Container([
                    dbc.NavbarBrand([
                        html.Span("🔧 관리자 대시보드", className="fw-bold text-warning"),
                        html.Span(" | ", className="mx-2"),
                        html.Span("Concrete MONITOR", className="fw-bold")
                    ], href="/admin_dashboard"),
                    dbc.Nav([
                        dbc.NavItem(dcc.Link("📊 프로젝트 관리", href="/admin_projects", className="nav-link")),
                        dbc.NavItem(dcc.Link("📋 로그 확인", href="/admin_logs", className="nav-link")),
                        dbc.NavItem(dcc.Link("👥 사용자 관리", href="/admin_users", className="nav-link")),
                        dbc.NavItem(
                            html.A(
                                "🏠 일반 페이지",
                                href="/",
                                className="btn btn-outline-light btn-sm me-2"
                            )
                        ),
                        dbc.NavItem(
                            html.A(
                                "🚪 로그아웃",
                                href="/logout",
                                className="btn btn-outline-light btn-sm"
                            )
                        ),
                    ], navbar=True, className="ms-auto"),
                ], fluid=True),
                color="dark",
                dark=True,
                className="mb-4",
            ),
            
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
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.H5("📊 프로젝트 관리", className="card-title text-primary"),
                                            html.P("프로젝트 생성, 수정, 삭제 및 권한 관리", className="card-text"),
                                            dcc.Link(
                                                dbc.Button("프로젝트 관리", color="primary", className="w-100"),
                                                href="/admin_projects"
                                            )
                                        ])
                                    ], className="mb-3")
                                ], width=4),
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.H5("📋 로그 확인", className="card-title text-success"),
                                            html.P("시스템 로그 및 사용자 활동 로그 확인", className="card-text"),
                                            dcc.Link(
                                                dbc.Button("로그 확인", color="success", className="w-100"),
                                                href="/admin_logs"
                                            )
                                        ])
                                    ], className="mb-3")
                                ], width=4),
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.H5("👥 사용자 관리", className="card-title text-info"),
                                            html.P("사용자 계정 및 권한 관리", className="card-text"),
                                            dcc.Link(
                                                dbc.Button("사용자 관리", color="info", className="w-100"),
                                                href="/admin_users"
                                            )
                                        ])
                                    ], className="mb-3")
                                ], width=4),
                            ]),
                            
                            html.Hr(className="my-4"),
                            
                            # 시스템 상태 요약
                            dbc.Row([
                                dbc.Col([
                                    html.H5("📈 시스템 상태", className="text-dark mb-3"),
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Card([
                                                dbc.CardBody([
                                                    html.H6("활성 프로젝트", className="text-primary"),
                                                    html.H3("12", className="fw-bold text-primary")
                                                ])
                                            ])
                                        ], width=3),
                                        dbc.Col([
                                            dbc.Card([
                                                dbc.CardBody([
                                                    html.H6("등록된 사용자", className="text-success"),
                                                    html.H3("45", className="fw-bold text-success")
                                                ])
                                            ])
                                        ], width=3),
                                        dbc.Col([
                                            dbc.Card([
                                                dbc.CardBody([
                                                    html.H6("활성 센서", className="text-info"),
                                                    html.H3("156", className="fw-bold text-info")
                                                ])
                                            ])
                                        ], width=3),
                                        dbc.Col([
                                            dbc.Card([
                                                dbc.CardBody([
                                                    html.H6("시스템 상태", className="text-warning"),
                                                    html.H3("정상", className="fw-bold text-warning")
                                                ])
                                            ])
                                        ], width=3),
                                    ])
                                ])
                            ])
                        ])
                    ], className="shadow")
                ])
            ])
        ], fluid=True)
    ])

@callback(
    [Output("admin-dashboard-url", "pathname")],
    [Input("admin-dashboard-url", "pathname")]
)
def check_admin_access(pathname):
    """관리자 권한 확인"""
    if not flask_request.cookies.get("admin_user"):
        return ["/admin"]
    return [pathname] 