# pages/login.py
from dash import html, dcc, register_page, callback, Input, Output
import dash_bootstrap_components as dbc
from flask import request as flask_request
import urllib.parse

register_page(__name__, path="/login", title="로그인")

def layout(error: str | None = None, **kwargs):
    """Login page layout.

    Dash pages 모드에서는 /login?error=... 형태의 쿼리 파라미터가 함수
    인자로 전달되므로 이를 받아 오류 메시지로 사용한다.
    """
    return html.Div([
        dcc.Location(id="login-url", refresh=False),
        dbc.Container(
            fluid=True,
            className="d-flex justify-content-center align-items-center",
            style={"height": "80vh"},
            children=dbc.Card(
                style={"width": "360px", "padding": "20px"},
                children=[
                    html.H3("Concrete MONITOR", className="mb-2 text-center text-primary fw-bold"),
                    html.H4("로그인", className="mb-4 text-center"),
                    html.Form(
                        action="/do_login",
                        method="post",
                        children=[
                            dbc.Input(name="user_id", placeholder="아이디", className="mb-3"),
                            dbc.Input(name="user_pw", placeholder="비밀번호", type="password", className="mb-3"),
                            dbc.Select(
                                id="its-select",
                                name="its",
                                options=[
                                    {"label": "ITS1", "value": "1"},
                                    {"label": "ITS2", "value": "2"}
                                ],
                                value="1",
                                className="mb-4"
                            ),
                            dbc.Button("로그인", type="submit", color="primary", className="w-100"),
                        ],
                    ),
                    html.Div(id="error-alert")
                ],
            ),
        ),
    ])

@callback(
    Output("error-alert", "children"),
    Input("login-url", "search")
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
