#!/usr/bin/env python3
# app.py
import os
from flask import Flask, request, redirect, make_response
from dotenv import load_dotenv
import api_user

load_dotenv()

# 1) Flask 서버만 먼저 생성
server = Flask(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# 로그인 처리 라우트 (GET/POST)
# 로그아웃 처리 라우트 (GET)
# 반드시 Dash(app) 생성 전에 정의
# ──────────────────────────────────────────────────────────────────────────────
@server.route("/do_login", methods=["GET", "POST"])
def do_login():
    if request.method == "GET":
        return redirect("/login")
    user_id = request.form.get("user_id", "")
    user_pw = request.form.get("user_pw", "")
    success, token_or_msg = api_user.authenticate(user_id, user_pw)
    if not success:
        return redirect(f"/login?error={token_or_msg}")
    resp = make_response(redirect("/"))
    resp.set_cookie("login_token", token_or_msg, max_age=api_user.TOKEN_EXPIRATION, httponly=True)
    return resp

@server.route("/logout")
def logout():
    resp = make_response(redirect("/"))
    resp.delete_cookie("login_token")
    return resp

# ──────────────────────────────────────────────────────────────────────────────
# 이제 Dash 앱 생성
# ──────────────────────────────────────────────────────────────────────────────
from dash import Dash, html, dcc, page_container
import dash_bootstrap_components as dbc

app = Dash(
    __name__,
    server=server,
    use_pages=True,
    suppress_callback_exceptions=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)
app.title = "Concrete Dashboard"

# 네비게이션 바 정의 (Logout 버튼은 href="/logout" 유지)
navbar = dbc.NavbarSimple(
    brand="Concrete MONITOR", color="dark", dark=True, className="mb-4",
    children=[
        dbc.NavItem(dcc.Link("Home", href="/", className="nav-link")),
        dbc.NavItem(dcc.Link("Project", href="/project", className="nav-link")),
        dbc.NavItem(dcc.Link("Concrete", href="/concrete", className="nav-link")),
        dbc.NavItem(dcc.Link("Sensor", href="/sensor", className="nav-link")),
        # Logout: dcc.Link + refresh=True 로 강제 풀 리프레시
        dbc.NavItem(
            dcc.Link(
                "Logout",
                href="/logout",
                refresh=True,                            # 중요!
                className="btn btn-outline-danger px-3"
            ),
            className="ms-auto"
        ),
    ],
)

app.layout = dbc.Container(
    fluid=True,
    children=[
        navbar,
        dbc.Card(className="shadow-sm p-4", children=[ page_container ]),
    ],
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(debug=True, host="0.0.0.0", port=port)
