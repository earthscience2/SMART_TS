# pages/login.py
from dash import html, dcc, register_page
import dash_bootstrap_components as dbc
from flask import request

register_page(__name__, path="/login", title="로그인")

def layout():
    error_msg = request.args.get("error", "")
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
                            dbc.Button("로그인", type="submit", color="primary", className="me-2"),
                            dbc.Button("회원가입", href="/signup", color="secondary"),
                        ],
                    ),
                    html.Div(error_msg, className="mt-3 text-danger text-center"),
                ],
            ),
        ),
    ])
