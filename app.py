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

_PUBLIC_PREFIXES = ("/login", "/do_login", "/admin", "/do_admin_login", "/assets", "/_dash", "/favicon", "/logout")


@server.before_request
def require_login():
    """모든 요청에 대해 로그인 여부 확인. 공용 경로 제외."""
    path = request.path
    
    # 관리자 페이지 접근 체크
    if path.startswith("/admin_dashboard") or path.startswith("/admin_projects") or path.startswith("/admin_logs") or path.startswith("/admin_users"):
        if not request.cookies.get("admin_user"):
            return redirect("/admin")
        return  # 관리자 권한 확인됨
    
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

@server.route("/do_admin_login", methods=["GET", "POST"])
def do_admin_login():
    """관리자 로그인 폼 제출 처리."""
    if request.method == "GET":
        return redirect("/admin")

    user_id = request.form.get("user_id", "").strip()
    user_pw = request.form.get("user_pw", "")
    its = int(request.form.get("its", "1"))  # hidden 필드로 받아오거나 기본 1

    # 입력값 검증
    if not user_id or not user_pw:
        resp = make_response(redirect("/admin?error=" + quote_plus("아이디와 비밀번호를 입력하세요")))
        resp.delete_cookie("admin_user")
        return resp

    auth = authenticate_user(user_id, user_pw, its_num=its)
    if auth["result"] != "Success":
        resp = make_response(redirect(f"/admin?error={quote_plus(auth['msg'])}"))
        # 실패한 로그인 시 기존 쿠키 삭제 (이전 세션 무효화)
        resp.delete_cookie("admin_user")
        return resp
    
    # AD 권한 확인
    if auth["grade"] != "AD":
        resp = make_response(redirect(f"/admin?error={quote_plus('관리자 권한이 필요합니다. AD 권한을 가진 사용자만 접근할 수 있습니다.')}"))
        resp.delete_cookie("admin_user")
        return resp

    # 관리자 로그인 성공: 쿠키 설정 후 관리자 대시보드로 리다이렉트
    resp = make_response(redirect("/admin_dashboard"))
    resp.set_cookie("admin_user", user_id, max_age=60 * 60 * 6, httponly=True)
    return resp

@server.route("/logout")
def logout():
    """쿠키 제거 후 홈으로 리다이렉트"""
    resp = make_response(redirect("/login"))
    resp.delete_cookie("login_user")
    resp.delete_cookie("admin_user")  # 관리자 쿠키도 삭제
    return resp

# ──────────────────────────────────────────────────────────────────────────────
# 이제 Dash 앱 생성
# ──────────────────────────────────────────────────────────────────────────────
from dash import Dash, html, dcc, page_container, no_update
from dash.dependencies import Input, Output
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

# 커스텀 CSS 스타일 추가
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            .admin-navbar .nav-link.active {
                background-color: #ffc107 !important;
                color: #000 !important;
                border-radius: 5px;
                padding: 8px 15px !important;
                margin: 0 5px;
                transition: all 0.3s ease;
            }
            .admin-navbar .nav-link:hover {
                background-color: #ffca2c !important;
                color: #000 !important;
                border-radius: 5px;
                padding: 8px 15px !important;
                margin: 0 5px;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

def _build_navbar():
    """쿠키(login_user) 존재 여부에 따라 Login/Logout 버튼 토글"""
    user_id = flask_request.cookies.get("login_user")
    admin_user = flask_request.cookies.get("admin_user")

    children = [
        # 네비게이션 링크들 (숨김처리하되 주소는 유지)
        dbc.NavItem(dcc.Link("", href="/", className="nav-link d-none", id="nav-home")),
        dbc.NavItem(dcc.Link("", href="/project", className="nav-link d-none", id="nav-project")),
        dbc.NavItem(dcc.Link("", href="/sensor", className="nav-link d-none", id="nav-sensor")),
        dbc.NavItem(dcc.Link("", href="/concrete", className="nav-link d-none", id="nav-concrete")),
        dbc.NavItem(dcc.Link("", href="/download", className="nav-link d-none", id="nav-download")),
        # Login / Logout (보기/숨김 및 정렬)
        dbc.NavItem(dcc.Link("Login", href="/login", className="nav-link", id="nav-login")),
        dbc.NavItem(
            html.A(
                "Logout",
                href="/logout",
                id="nav-logout",
                className="btn btn-danger btn-sm fw-bold mt-1 ms-auto",
                style={"color": "white", "backgroundColor": "#dc3545", "border": "none", "marginLeft": "50px"},
            ),
        ),
    ]

    # 가시성 제어
    if user_id or admin_user:
        # hide login link
        children[-2].style = {"display": "none"}
    else:
        # hide logout button and ensure login link pushed right
        children[-1].style = {"display": "none"}
        children[-2].className += " ms-auto"

    # 브랜드 컴포넌트 설정
    if admin_user:
        brand_component = html.Span([
            html.Span("Concrete MONITORㅤ| ", className="fw-bold"),
            html.Span(f"  🔧 {admin_user} (관리자)", className="ms-2 fw-bold text-warning")
        ])
    elif user_id:
        brand_component = html.Span([
            html.Span("Concrete MONITORㅤ| ", className="fw-bold"),
            html.Span(f"  {user_id}", className="ms-2 fw-bold text-warning")
        ])
    else:
        brand_component = html.Span("Concrete MONITOR", className="fw-bold")

    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand(brand_component, href="/"),
            dbc.Nav(
                children,
                navbar=True,
                className="ms-1"  # 브랜드 옆 여백을 줄여서 왼쪽으로 이동
            ),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-4",
    )

def _build_admin_navbar():
    """관리자 페이지용 네비게이션 바"""
    admin_user = flask_request.cookies.get("admin_user")
    
    children = [
        # 관리자 네비게이션 링크들
        dbc.NavItem(dcc.Link("📊 프로젝트", href="/admin_projects", className="nav-link fw-bold", id="admin-nav-projects")),
        dbc.NavItem(dcc.Link("📋 로그", href="/admin_logs", className="nav-link fw-bold", id="admin-nav-logs")),
        dbc.NavItem(dcc.Link("⚙️ 자동화", href="/admin_automation", className="nav-link fw-bold", id="admin-nav-automation")),
        # Logout 버튼
        dbc.NavItem(
            html.A(
                "Logout",
                href="/logout",
                id="admin-nav-logout",
                className="btn btn-danger btn-sm fw-bold mt-1 ms-auto",
                style={"color": "white", "backgroundColor": "#dc3545", "border": "none", "marginLeft": "50px"},
            ),
        ),
    ]

    # 브랜드 컴포넌트 설정
    brand_component = html.Span([
        html.Span("Concrete MONITORㅤ| ", className="fw-bold"),
        html.Span(f"  🔧 {admin_user} (관리자)", className="ms-2 fw-bold text-warning")
    ])

    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand(brand_component, href="/admin_dashboard", id="admin-brand"),
            dbc.Nav(
                children,
                navbar=True,
                className="ms-1"
            ),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-4 admin-navbar",
        style={"borderBottom": "2px solid #ffc107"}
    )

# 정적 레이아웃 설정
app.layout = dbc.Container(
    fluid=True,
    children=[
        dcc.Location(id="url"),
        html.Div(id="navbar-container"),
        dbc.Card(className="shadow-sm p-4", children=[page_container]),
    ],
)

# 통합된 URL 리다이렉트 콜백
@app.callback(
    Output("url", "pathname"),
    [Input("url", "pathname"),
     Input("admin-brand", "n_clicks")],
    prevent_initial_call=True
)
def handle_url_redirects(pathname, admin_brand_clicks):
    """모든 URL 리다이렉트 로직을 처리합니다."""
    
    # 관리자 브랜드 클릭 처리
    if admin_brand_clicks:
        return "/admin_dashboard"
    
    # 관리자 페이지에서 일반 페이지 접근 차단
    admin_user = flask_request.cookies.get("admin_user")
    if admin_user and pathname in ["/", "/project", "/sensor", "/concrete", "/download", "/tci_analysis"]:
        return "/admin_dashboard"
    
    # 로그인 페이지 리다이렉트
    # 관리자 페이지 접근 체크
    if pathname.startswith("/admin_dashboard") or pathname.startswith("/admin_projects") or pathname.startswith("/admin_logs") or pathname.startswith("/admin_users") or pathname.startswith("/admin_automation"):
        if not flask_request.cookies.get("admin_user"):
            return "/admin"
    
    # 일반 페이지 접근 체크
    if not pathname.startswith(("/login", "/admin", "/do_login", "/do_admin_login", "/assets", "/_dash", "/favicon", "/logout")):
        if not flask_request.cookies.get("login_user"):
            return "/login"
    
    return no_update

# 네비게이션 바 동적 생성 콜백
@app.callback(
    Output("navbar-container", "children"),
    Input("url", "pathname")
)
def update_navbar(pathname):
    """URL에 따라 적절한 네비게이션 바를 반환합니다."""
    # 관리자 페이지 접근 체크
    if pathname.startswith("/admin_dashboard") or pathname.startswith("/admin_projects") or pathname.startswith("/admin_logs") or pathname.startswith("/admin_users") or pathname.startswith("/admin_automation"):
        if not flask_request.cookies.get("admin_user"):
            return html.Div()  # 빈 div 반환
        return _build_admin_navbar()
    
    if not flask_request.cookies.get("login_user"):
        return html.Div()  # 빈 div 반환
    
    return _build_navbar()

# 네비게이션 바 active 클래스 동적 적용 콜백
@app.callback(
    [Output("nav-home", "className"),
     Output("nav-project", "className"),
     Output("nav-sensor", "className"),
     Output("nav-concrete", "className"),
     Output("nav-download", "className"),
     Output("nav-login", "className"),
     Output("nav-logout", "className"),
     Output("nav-home", "children"),
     Output("nav-project", "children"),
     Output("nav-sensor", "children"),
     Output("nav-concrete", "children"),
     Output("nav-download", "children")],
    [Input("url", "pathname"),
     Input("url", "search")]
)
def update_nav_active(pathname, search):
    # 프로젝트 ID 추출
    project_pk = None
    if search:
        try:
            from urllib.parse import parse_qs
            params = parse_qs(search.lstrip('?'))
            project_pk = params.get('page', [None])[0]
        except Exception:
            pass
    
    # 홈 페이지인지 확인
    is_home = pathname == "/"
    
    # 기본 클래스 설정
    if is_home:
        # 홈에서는 모든 네비게이션 링크 숨김
        base_classes = ["nav-link d-none"] * 5
    else:
        # 다른 페이지에서는 네비게이션 링크 표시
        base_classes = ["nav-link"] * 5
    
    login_logout_classes = ["nav-link"] * 2
    
    # Active 클래스 추가
    if pathname == "/":
        base_classes[0] += " active"
    elif pathname.startswith("/project"):
        base_classes[1] += " active"
    elif pathname.startswith("/sensor"):
        base_classes[2] += " active"
    elif pathname.startswith("/concrete"):
        base_classes[3] += " active"
    elif pathname.startswith("/download"):
        base_classes[4] += " active"
    elif pathname.startswith("/login"):
        login_logout_classes[0] += " active"
    
    # 네비게이션 링크 텍스트 및 아이콘 설정
    if project_pk and not is_home:
        nav_texts = [
            [html.Span("🏠", className="me-2"), "홈"],
            [html.Span("📊", className="me-2"), "분석"],
            [html.Span("📡", className="me-2"), "센서"],
            [html.Span("🧱", className="me-2"), "콘크리트"],
            [html.Span("💾", className="me-2"), "다운로드"]
        ]
    else:
        nav_texts = [""] * 5
    
    return (
        base_classes[0], base_classes[1], base_classes[2], base_classes[3], base_classes[4],
        login_logout_classes[0], login_logout_classes[1],
        nav_texts[0], nav_texts[1], nav_texts[2], nav_texts[3], nav_texts[4]
    )

# 관리자 네비게이션 바 active 클래스 동적 적용 콜백
@app.callback(
    [Output("admin-nav-projects", "className"),
     Output("admin-nav-logs", "className"),
     Output("admin-nav-automation", "className")],
    [Input("url", "pathname")]
)
def update_admin_nav_active(pathname):
    """관리자 네비게이션 바의 active 상태를 업데이트합니다."""
    # 기본 클래스 설정
    base_classes = ["nav-link fw-bold"] * 3
    
    # Active 클래스 추가
    if pathname.startswith("/admin_projects"):
        base_classes[0] += " active"
    elif pathname.startswith("/admin_logs"):
        base_classes[1] += " active"
    elif pathname.startswith("/admin_automation"):
        base_classes[2] += " active"
    
    return base_classes[0], base_classes[1], base_classes[2]

# 네비게이션 링크 href 동적 업데이트
@app.callback(
    [Output("nav-home", "href"),
     Output("nav-project", "href"),
     Output("nav-sensor", "href"),
     Output("nav-concrete", "href"),
     Output("nav-download", "href")],
    [Input("url", "pathname"),
     Input("url", "search")]
)
def update_nav_links(pathname, search):
    # 프로젝트 ID 추출
    project_pk = None
    if search:
        try:
            from urllib.parse import parse_qs
            params = parse_qs(search.lstrip('?'))
            project_pk = params.get('page', [None])[0]
        except Exception:
            pass
    
    # 기본 링크
    if project_pk and pathname != "/":
        return (
            "/",
            f"/project?page={project_pk}",
            f"/sensor?page={project_pk}",
            f"/concrete?page={project_pk}",
            f"/download?page={project_pk}"
        )
    else:
        return "/", "/project", "/sensor", "/concrete", "/download"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=23022)
