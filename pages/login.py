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
    # 디버깅: 모든 파라미터 확인
    print(f"DEBUG - layout() called with error={error}, kwargs={kwargs}")
    
    raw_msg = error or flask_request.args.get("error", "")
    print(f"DEBUG - raw_msg: '{raw_msg}'")
    
    error_msg = urllib.parse.unquote_plus(raw_msg)
    print(f"DEBUG - error_msg after unquote_plus: '{error_msg}'")
    
    # flask_request.args 직접 확인
    print(f"DEBUG - flask_request.args: {dict(flask_request.args)}")
    print(f"DEBUG - flask_request.url: {flask_request.url}")
    
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
                            dbc.Input(name="user_pw", placeholder="비밀번호", type="password", className="mb-4"),
                            dbc.Button("로그인", type="submit", color="primary", className="w-100"),
                        ],
                    ),
                    html.Div(id="error-alert"),
                    # 디버깅용 - 제거 가능
                    html.Div([
                        html.P(f"Debug - error param: '{error}'", style={"fontSize": "10px", "color": "red"}),
                        html.P(f"Debug - raw_msg: '{raw_msg}'", style={"fontSize": "10px", "color": "blue"}),
                        html.P(f"Debug - error_msg: '{error_msg}'", style={"fontSize": "10px", "color": "green"}),
                        html.P(f"Debug - flask_request.args: {dict(flask_request.args)}", style={"fontSize": "10px", "color": "purple"}),
                    ], className="mt-2"),
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
