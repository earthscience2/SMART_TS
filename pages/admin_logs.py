from dash import html, dcc, register_page, callback, Input, Output
import dash_bootstrap_components as dbc
from flask import request as flask_request
import pandas as pd

register_page(__name__, path="/admin_logs", title="로그 확인")

def layout(**kwargs):
    """Admin logs management layout."""
    return html.Div([
        dcc.Location(id="admin-logs-url", refresh=False),
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
                        dbc.NavItem(dcc.Link("📋 로그 확인", href="/admin_logs", className="nav-link active")),
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
                            html.H4("📋 로그 확인", className="mb-0 text-success"),
                            html.Small("시스템 로그 및 사용자 활동 로그 확인", className="text-muted")
                        ]),
                        dbc.CardBody([
                            # 로그 필터링 옵션
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("로그 유형", className="fw-bold"),
                                    dcc.Dropdown(
                                        id="log-type-dropdown",
                                        options=[
                                            {"label": "전체", "value": "all"},
                                            {"label": "로그인/로그아웃", "value": "auth"},
                                            {"label": "프로젝트 접근", "value": "project"},
                                            {"label": "센서 데이터", "value": "sensor"},
                                            {"label": "시스템 오류", "value": "error"}
                                        ],
                                        value="all",
                                        className="mb-3"
                                    )
                                ], width=3),
                                dbc.Col([
                                    dbc.Label("날짜 범위", className="fw-bold"),
                                    dcc.DatePickerRange(
                                        id="log-date-range",
                                        className="mb-3"
                                    )
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("사용자", className="fw-bold"),
                                    dcc.Dropdown(
                                        id="log-user-dropdown",
                                        options=[
                                            {"label": "전체 사용자", "value": "all"},
                                            {"label": "admin", "value": "admin"},
                                            {"label": "user1", "value": "user1"},
                                            {"label": "user2", "value": "user2"}
                                        ],
                                        value="all",
                                        className="mb-3"
                                    )
                                ], width=3),
                                dbc.Col([
                                    dbc.Label("", className="fw-bold"),
                                    dbc.Button("🔍 검색", color="primary", className="w-100")
                                ], width=2)
                            ], className="mb-4"),
                            
                            # 로그 테이블
                            dbc.Table([
                                html.Thead([
                                    html.Tr([
                                        html.Th("시간"),
                                        html.Th("사용자"),
                                        html.Th("로그 유형"),
                                        html.Th("내용"),
                                        html.Th("IP 주소"),
                                        html.Th("상태")
                                    ])
                                ]),
                                html.Tbody([
                                    html.Tr([
                                        html.Td("2024-01-15 14:30:25"),
                                        html.Td("admin"),
                                        html.Td(dbc.Badge("로그인", color="success")),
                                        html.Td("관리자 로그인 성공"),
                                        html.Td("192.168.1.100"),
                                        html.Td(dbc.Badge("성공", color="success"))
                                    ]),
                                    html.Tr([
                                        html.Td("2024-01-15 14:25:10"),
                                        html.Td("user1"),
                                        html.Td(dbc.Badge("프로젝트", color="info")),
                                        html.Td("P_000001 프로젝트 접근"),
                                        html.Td("192.168.1.101"),
                                        html.Td(dbc.Badge("성공", color="success"))
                                    ]),
                                    html.Tr([
                                        html.Td("2024-01-15 14:20:15"),
                                        html.Td("user2"),
                                        html.Td(dbc.Badge("센서", color="warning")),
                                        html.Td("센서 데이터 조회"),
                                        html.Td("192.168.1.102"),
                                        html.Td(dbc.Badge("성공", color="success"))
                                    ]),
                                    html.Tr([
                                        html.Td("2024-01-15 14:15:30"),
                                        html.Td("unknown"),
                                        html.Td(dbc.Badge("오류", color="danger")),
                                        html.Td("권한 없는 접근 시도"),
                                        html.Td("192.168.1.103"),
                                        html.Td(dbc.Badge("실패", color="danger"))
                                    ]),
                                    html.Tr([
                                        html.Td("2024-01-15 14:10:45"),
                                        html.Td("admin"),
                                        html.Td(dbc.Badge("시스템", color="secondary")),
                                        html.Td("시스템 백업 완료"),
                                        html.Td("192.168.1.100"),
                                        html.Td(dbc.Badge("성공", color="success"))
                                    ]),
                                ])
                            ], striped=True, bordered=True, hover=True, responsive=True),
                            
                            # 로그 내보내기 버튼
                            dbc.Row([
                                dbc.Col([
                                    dbc.Button([
                                        html.Span("📥", className="me-2"),
                                        "로그 내보내기 (CSV)"
                                    ], color="info", className="mt-3")
                                ], width=12)
                            ]),
                            
                            # 페이지네이션
                            dbc.Row([
                                dbc.Col([
                                    dbc.Pagination(
                                        id="log-pagination",
                                        max_value=10,
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
    [Output("admin-logs-url", "pathname")],
    [Input("admin-logs-url", "pathname")],
    allow_duplicate=True
)
def check_admin_access(pathname):
    """관리자 권한 확인"""
    if not flask_request.cookies.get("admin_user"):
        return ["/admin"]
    return [pathname] 