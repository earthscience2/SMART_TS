from dash import html, dcc, register_page, callback, Input, Output
import dash_bootstrap_components as dbc
from flask import request as flask_request
import pandas as pd

register_page(__name__, path="/admin_users", title="사용자 관리")

def layout(**kwargs):
    """Admin users management layout."""
    return html.Div([
        dcc.Location(id="admin-users-url", refresh=False),
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
                        dbc.NavItem(dcc.Link("👥 사용자 관리", href="/admin_users", className="nav-link active")),
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
                            html.H4("👥 사용자 관리", className="mb-0 text-info"),
                            html.Small("사용자 계정 및 권한 관리", className="text-muted")
                        ]),
                        dbc.CardBody([
                            # 사용자 추가 버튼
                            dbc.Row([
                                dbc.Col([
                                    dbc.Button([
                                        html.Span("➕", className="me-2"),
                                        "새 사용자 추가"
                                    ], color="success", className="mb-3")
                                ], width=12)
                            ]),
                            
                            # 사용자 목록 테이블
                            dbc.Table([
                                html.Thead([
                                    html.Tr([
                                        html.Th("사용자 ID"),
                                        html.Th("권한 등급"),
                                        html.Th("권한 시작일"),
                                        html.Th("권한 종료일"),
                                        html.Th("상태"),
                                        html.Th("작업")
                                    ])
                                ]),
                                html.Tbody([
                                    html.Tr([
                                        html.Td("admin"),
                                        html.Td(dbc.Badge("AD", color="danger")),
                                        html.Td("2024-01-01"),
                                        html.Td("2024-12-31"),
                                        html.Td(dbc.Badge("활성", color="success")),
                                        html.Td([
                                            dbc.Button("수정", size="sm", color="primary", className="me-1"),
                                            dbc.Button("권한", size="sm", color="warning", className="me-1"),
                                            dbc.Button("삭제", size="sm", color="danger")
                                        ])
                                    ]),
                                    html.Tr([
                                        html.Td("user1"),
                                        html.Td(dbc.Badge("CM", color="warning")),
                                        html.Td("2024-01-15"),
                                        html.Td("2024-06-30"),
                                        html.Td(dbc.Badge("활성", color="success")),
                                        html.Td([
                                            dbc.Button("수정", size="sm", color="primary", className="me-1"),
                                            dbc.Button("권한", size="sm", color="warning", className="me-1"),
                                            dbc.Button("삭제", size="sm", color="danger")
                                        ])
                                    ]),
                                    html.Tr([
                                        html.Td("user2"),
                                        html.Td(dbc.Badge("CT", color="info")),
                                        html.Td("2024-02-01"),
                                        html.Td("2024-05-31"),
                                        html.Td(dbc.Badge("활성", color="success")),
                                        html.Td([
                                            dbc.Button("수정", size="sm", color="primary", className="me-1"),
                                            dbc.Button("권한", size="sm", color="warning", className="me-1"),
                                            dbc.Button("삭제", size="sm", color="danger")
                                        ])
                                    ]),
                                    html.Tr([
                                        html.Td("user3"),
                                        html.Td(dbc.Badge("US", color="secondary")),
                                        html.Td("2024-01-10"),
                                        html.Td("2024-03-31"),
                                        html.Td(dbc.Badge("만료", color="secondary")),
                                        html.Td([
                                            dbc.Button("수정", size="sm", color="primary", className="me-1"),
                                            dbc.Button("권한", size="sm", color="warning", className="me-1"),
                                            dbc.Button("삭제", size="sm", color="danger")
                                        ])
                                    ]),
                                ])
                            ], striped=True, bordered=True, hover=True, responsive=True),
                            
                            # 권한 등급 설명
                            dbc.Row([
                                dbc.Col([
                                    html.H6("권한 등급 설명", className="mt-4 mb-2"),
                                    dbc.Alert([
                                        html.Strong("AD (Administrator): "),
                                        "관리자 - 모든 기능 접근 가능",
                                        html.Br(),
                                        html.Strong("CM (Contract Manager): "),
                                        "계약 관리자 - 프로젝트 관리 권한",
                                        html.Br(),
                                        html.Strong("CT (Contractor): "),
                                        "계약자 - 제한된 프로젝트 접근",
                                        html.Br(),
                                        html.Strong("US (User): "),
                                        "일반 사용자 - 기본 기능만 접근"
                                    ], color="light", className="mb-3")
                                ])
                            ]),
                            
                            # 페이지네이션
                            dbc.Row([
                                dbc.Col([
                                    dbc.Pagination(
                                        id="user-pagination",
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
    [Output("admin-users-url", "pathname")],
    [Input("admin-users-url", "pathname")],
    allow_duplicate=True
)
def check_admin_access(pathname):
    """관리자 권한 확인"""
    if not flask_request.cookies.get("admin_user"):
        return ["/admin"]
    return [pathname] 