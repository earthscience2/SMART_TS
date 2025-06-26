#!/usr/bin/env python3
# app.py
import os
from flask import Flask, request, redirect, make_response
from dotenv import load_dotenv
from urllib.parse import quote_plus

# 사용자 인증 모듈
from api_db import authenticate_user

load_dotenv()

# 1) Flask 서버만 먼저 생성
server = Flask(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# 로그인 처리 라우트 (GET/POST)
# 로그아웃 처리 라우트 (GET)
# 반드시 Dash(app) 생성 전에 정의
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────
#  인증 체크: 로그인 안 했으면 /login 으로 리다이렉트
# ──────────────────────────────────────────────────

_PUBLIC_PREFIXES = ("/login", "/do_login", "/assets", "/_dash", "/favicon", "/logout")


@server.before_request
def require_login():
    """모든 요청에 대해 로그인 여부 확인. 공용 경로 제외."""
    path = request.path
    if path.startswith(_PUBLIC_PREFIXES):
        return  # allow

    # 쿠키가 있는 상태로 /login 접근 시 홈으로 리다이렉트
    if flask_request.cookies.get("login_user") and flask_request.path.startswith("/login"):
        return dcc.Location(href="/", id="redirect-home")

    # 쿠키에 login_user 가 없으면 로그인 페이지로
    if not request.cookies.get("login_user"):
        # Ajax 요청 등은 401 처리 가능, 여기서는 단순 리다이렉트
        return redirect("/login")

@server.route("/do_login", methods=["GET", "POST"])
def do_login():
    """로그인 폼 제출 처리."""
    if request.method == "GET":
        return redirect("/login")

    user_id = request.form.get("user_id", "").strip()
    user_pw = request.form.get("user_pw", "")
    its = int(request.form.get("its", "1"))  # hidden 필드로 받아오거나 기본 1

    # 입력값 검증
    if not user_id or not user_pw:
        resp = make_response(redirect("/login?error=" + quote_plus("아이디와 비밀번호를 입력하세요")))
        resp.delete_cookie("login_user")
        return resp

    auth = authenticate_user(user_id, user_pw, its_num=its)
    if auth["result"] != "Success":
        resp = make_response(redirect(f"/login?error={quote_plus(auth['msg'])}"))
        # 실패한 로그인 시 기존 쿠키 삭제 (이전 세션 무효화)
        resp.delete_cookie("login_user")
        return resp

    # 간단하게 쿠키에 user_id 저장 (실 서비스라면 JWT 등 사용)
    resp = make_response(redirect("/"))
    resp.set_cookie("login_user", user_id, max_age=60 * 60 * 6, httponly=True)
    return resp

@server.route("/logout")
def logout():
    """쿠키 제거 후 홈으로 리다이렉트"""
    resp = make_response(redirect("/login"))
    resp.delete_cookie("login_user")
    return resp

# ──────────────────────────────────────────────────────────────────────────────
# 이제 Dash 앱 생성
# ──────────────────────────────────────────────────────────────────────────────
from dash import Dash, html, dcc, page_container
import dash_bootstrap_components as dbc
from flask import request as flask_request

app = Dash(
    __name__,
    server=server,
    use_pages=True,
    suppress_callback_exceptions=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)
app.title = "Concrete Dashboard"

def _build_navbar():
    """쿠키(login_user) 존재 여부에 따라 Login/Logout 버튼 토글"""
    user_id = flask_request.cookies.get("login_user")

    children = [
        dbc.NavItem(dcc.Link("Home", href="/", className="nav-link", id="nav-home")),
        dbc.NavItem(dcc.Link("Project", href="/project", className="nav-link", id="nav-project")),
        dbc.NavItem(dcc.Link("Sensor", href="/sensor", className="nav-link", id="nav-sensor")),
        dbc.NavItem(dcc.Link("Concrete", href="/concrete", className="nav-link", id="nav-concrete")),
        dbc.NavItem(dcc.Link("Download", href="/download", className="nav-link", id="nav-download")),
        # Login / Logout (보기/숨김 및 정렬)
        dbc.NavItem(dcc.Link("Login", href="/login", className="nav-link", id="nav-login")),
        dbc.NavItem(
            html.A(
                "Logout",
                href="/logout",
                id="nav-logout",
                className="btn btn-danger btn-sm fw-bold mt-1 ms-auto",
                style={"color": "white", "backgroundColor": "#dc3545", "border": "none"},
            ),
        ),
    ]

    # 가시성 제어
    if user_id:
        # hide login link
        children[-2].style = {"display": "none"}
    else:
        # hide logout button and ensure login link pushed right
        children[-1].style = {"display": "none"}
        children[-2].className += " ms-auto"

    brand_component = html.Span([
        html.Span("Concrete MONITOR", className="fw-bold"),
        html.Span(f" | {user_id}", className="ms-2 fw-bold text-warning") if user_id else None
    ])

    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand(brand_component, href="/"),
            dbc.Nav(
                children,
                navbar=True,
                className="ms-3"  # 브랜드 옆에 여백을 두고 배치
            ),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-4",
    )

def serve_layout():
    """Dash Serve layout function, evaluated per request.

    쿠키(login_user)가 없으면 로그인 페이지 레이아웃을 직접 반환해 SPA 내부 이동까지 차단한다.
    """

    if not flask_request.cookies.get("login_user"):
        from pages import login as login_page  # 지역 임포트로 순환참조 방지
        error_param = flask_request.args.get("error")
        return login_page.layout(error=error_param)

    navbar = _build_navbar()
    return dbc.Container(
        fluid=True,
        children=[
            dcc.Location(id="url"),
            navbar,
            dbc.Card(className="shadow-sm p-4", children=[page_container]),
        ],
    )

app.layout = serve_layout

# 네비게이션 바 active 클래스 동적 적용 콜백
from dash.dependencies import Input, Output

@app.callback(
    [Output("nav-home", "className"),
     Output("nav-project", "className"),
     Output("nav-sensor", "className"),
     Output("nav-concrete", "className"),
     Output("nav-download", "className"),
     Output("nav-login", "className"),
     Output("nav-logout", "className")],
    Input("url", "pathname")
)
def update_nav_active(pathname):
    classes = ["nav-link"] * 7
    if pathname == "/":
        classes[0] += " active"
    elif pathname.startswith("/project"):
        classes[1] += " active"
    elif pathname.startswith("/sensor"):
        classes[2] += " active"
    elif pathname.startswith("/concrete"):
        classes[3] += " active"
    elif pathname.startswith("/download"):
        classes[4] += " active"
    elif pathname.startswith("/login"):
        classes[5] += " active"
    return classes

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=23022)
