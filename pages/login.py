# pages/login.py
from dash import html, dcc, register_page
import dash_bootstrap_components as dbc
from flask import request as flask_request
import urllib.parse

register_page(__name__, path="/login", title="로그인")

def layout(error: str | None = None, **kwargs):
    """Login page layout.

    Dash pages 모드에서는 /login?error=... 형태의 쿼리 파라미터가 함수
    인자로 전달되므로 이를 받아 오류 메시지로 사용한다.
    """
    raw_msg = error or flask_request.args.get("error", "")
    error_msg = urllib.parse.unquote_plus(raw_msg)
    return html.Div([
        dbc.Container(
            fluid=True,
            className="d-flex justify-content-center align-items-center",
            style={"height": "80vh"},
            children=dbc.Card(
                style={"width": "360px", "padding": "20px"},
                children=[
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
                    dbc.Alert(error_msg or "아이디와 비밀번호를 입력하세요.", color="danger" if error_msg else "info", is_open=True, className="mt-3"),
                ],
            ),
        ),
    ])
