# pages/admin_projects.py
from dash import html, dcc, register_page, callback, Input, Output
import dash_bootstrap_components as dbc
from flask import request as flask_request
import pandas as pd

register_page(__name__, path="/admin_projects", title="프로젝트 관리")

def layout(**kwargs):
    """Admin projects management layout."""
    return html.Div([
        dcc.Location(id="admin-projects-url", refresh=False),
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
                        dbc.NavItem(dcc.Link("📊 프로젝트 관리", href="/admin_projects", className="nav-link active")),
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
                            dbc.Table([
                                html.Thead([
                                    html.Tr([
                                        html.Th("프로젝트 ID"),
                                        html.Th("프로젝트명"),
                                        html.Th("등록일"),
                                        html.Th("종료일"),
                                        html.Th("상태"),
                                        html.Th("작업")
                                    ])
                                ]),
                                html.Tbody([
                                    html.Tr([
                                        html.Td("P_000001"),
                                        html.Td("서울교량 모니터링"),
                                        html.Td("2024-01-15"),
                                        html.Td("2024-12-31"),
                                        html.Td(dbc.Badge("활성", color="success")),
                                        html.Td([
                                            dbc.Button("수정", size="sm", color="primary", className="me-1"),
                                            dbc.Button("삭제", size="sm", color="danger")
                                        ])
                                    ]),
                                    html.Tr([
                                        html.Td("P_000002"),
                                        html.Td("부산항교 모니터링"),
                                        html.Td("2024-02-01"),
                                        html.Td("2024-11-30"),
                                        html.Td(dbc.Badge("활성", color="success")),
                                        html.Td([
                                            dbc.Button("수정", size="sm", color="primary", className="me-1"),
                                            dbc.Button("삭제", size="sm", color="danger")
                                        ])
                                    ]),
                                    html.Tr([
                                        html.Td("P_000003"),
                                        html.Td("대구터널 모니터링"),
                                        html.Td("2023-12-01"),
                                        html.Td("2024-05-31"),
                                        html.Td(dbc.Badge("완료", color="secondary")),
                                        html.Td([
                                            dbc.Button("수정", size="sm", color="primary", className="me-1"),
                                            dbc.Button("삭제", size="sm", color="danger")
                                        ])
                                    ]),
                                ])
                            ], striped=True, bordered=True, hover=True, responsive=True),
                            
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
    [Output("admin-projects-url", "pathname")],
    [Input("admin-projects-url", "pathname")],
    allow_duplicate=True
)
def check_admin_access(pathname):
    """관리자 권한 확인"""
    if not flask_request.cookies.get("admin_user"):
        return ["/admin"]
    return [pathname] 