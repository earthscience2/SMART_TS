from dash import html, dcc, register_page, callback, Input, Output
import dash_bootstrap_components as dbc
from flask import request as flask_request
import urllib.parse

register_page(__name__, path="/admin", title="관리자 페이지")

def layout(error: str | None = None, **kwargs):
    """Admin page layout.

    Dash pages 모드에서는 /admin?error=... 형태의 쿼리 파라미터가 함수
    인자로 전달되므로 이를 받아 오류 메시지로 사용한다.
    """
    return html.Div([
        dcc.Location(id="admin-url", refresh=False),
        dbc.Container(
            fluid=True,
            className="d-flex justify-content-center align-items-center",
            style={"height": "80vh"},
            children=dbc.Card(
                style={"width": "400px", "padding": "20px"},
                children=[
                    html.H3("Concrete MONITOR", className="mb-2 text-center text-primary fw-bold"),
                    html.H4("관리자 로그인", className="mb-4 text-center text-danger"),
                    html.Hr(className="mb-4"),
                    html.Form(
                        action="/do_admin_login",
                        method="post",
                        children=[
                            dbc.Input(name="user_id", placeholder="관리자 아이디", className="mb-3"),
                            dbc.Input(name="user_pw", placeholder="관리자 비밀번호", type="password", className="mb-4"),
                            dbc.Button("관리자 로그인", type="submit", color="danger", className="w-100"),
                        ],
                    ),
                    html.Div(id="error-alert"),
                    html.Hr(className="mt-4 mb-3"),
                    html.Div([
                        html.Small("일반 사용자는 ", className="text-muted"),
                        dcc.Link("여기", href="/login", className="text-primary"),
                        html.Small("를 클릭하세요", className="text-muted")
                    ], className="text-center")
                ],
            ),
        ),
    ])

@callback(
    Output("error-alert", "children"),
    Input("admin-url", "search")
)
def update_error_message(search):
    """URL 파라미터에서 error 메시지를 추출하여 Alert 표시"""
    if not search:
        return None
    
    # ?error=... 형태에서 error 값 추출
    try:
        params = urllib.parse.parse_qs(search[1:])  # ? 제거
        error_encoded = params.get("error", [None])[0]
        if error_encoded:
            error_msg = urllib.parse.unquote_plus(error_encoded)
            return dbc.Alert(error_msg, color="danger", is_open=True, className="mt-3")
    except Exception as e:
        print(f"Error parsing URL params: {e}")
    
    return None 