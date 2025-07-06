#!/usr/bin/env python3
# app.py
import os
from flask import Flask, request, redirect, make_response
from dotenv import load_dotenv
from urllib.parse import quote_plus
from datetime import datetime
import logging

# 사용자 인증 모듈
from api_db import authenticate_user

load_dotenv()

# 로그인 로그 설정
def setup_login_logger():
    """로그인 로그를 위한 로거 설정"""
    log_dir = "log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger('login_logger')
    logger.setLevel(logging.INFO)
    
    # 기존 핸들러 제거 (중복 방지)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 파일 핸들러 설정
    file_handler = logging.FileHandler(os.path.join(log_dir, 'login.log'), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 포맷터 설정
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    return logger

def log_login_attempt(user_id, success, message, ip_address=None, user_agent=None):
    """로그인 시도를 로그에 기록"""
    logger = setup_login_logger()
    
    if ip_address is None:
        ip_address = request.remote_addr if request else "Unknown"
    
    if user_agent is None:
        user_agent = request.headers.get('User-Agent', "Unknown") if request else "Unknown"
    
    status = "SUCCESS" if success else "FAILED"
    log_message = f"LOGIN_{status} | User: {user_id} | IP: {ip_address} | Message: {message} | User-Agent: {user_agent}"
    
    logger.info(log_message)

# 로거 초기화
login_logger = setup_login_logger()

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
    if path.startswith("/admin_dashboard") or path.startswith("/admin_projects") or path.startswith("/admin_logs"):
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
        log_login_attempt(user_id, False, "아이디와 비밀번호를 입력하세요")
        resp = make_response(redirect("/login?error=" + quote_plus("아이디와 비밀번호를 입력하세요")))
        resp.delete_cookie("login_user")
        return resp

    auth = authenticate_user(user_id, user_pw, its_num=its)
    if auth["result"] != "Success":
        log_login_attempt(user_id, False, auth['msg'])
        resp = make_response(redirect(f"/login?error={quote_plus(auth['msg'])}"))
        # 실패한 로그인 시 기존 쿠키 삭제 (이전 세션 무효화)
        resp.delete_cookie("login_user")
        return resp

    # 로그인 성공 로그
    log_login_attempt(user_id, True, "로그인 성공")
    
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
        log_login_attempt(user_id, False, "관리자 로그인: 아이디와 비밀번호를 입력하세요")
        resp = make_response(redirect("/admin?error=" + quote_plus("아이디와 비밀번호를 입력하세요")))
        resp.delete_cookie("admin_user")
        return resp

    auth = authenticate_user(user_id, user_pw, its_num=its)
    if auth["result"] != "Success":
        log_login_attempt(user_id, False, f"관리자 로그인: {auth['msg']}")
        resp = make_response(redirect(f"/admin?error={quote_plus(auth['msg'])}"))
        # 실패한 로그인 시 기존 쿠키 삭제 (이전 세션 무효화)
        resp.delete_cookie("admin_user")
        return resp
    
    # AD 권한 확인
    if auth["grade"] != "AD":
        log_login_attempt(user_id, False, "관리자 로그인: AD 권한이 필요합니다")
        resp = make_response(redirect(f"/admin?error={quote_plus('관리자 권한이 필요합니다. AD 권한을 가진 사용자만 접근할 수 있습니다.')}"))
        resp.delete_cookie("admin_user")
        return resp

    # 관리자 로그인 성공 로그
    log_login_attempt(user_id, True, "관리자 로그인 성공")
    
    # 관리자 로그인 성공: 쿠키 설정 후 관리자 대시보드로 리다이렉트
    resp = make_response(redirect("/admin_dashboard"))
    resp.set_cookie("admin_user", user_id, max_age=60 * 60 * 6, httponly=True)
    return resp

@server.route("/logout")
def logout():
    """쿠키 제거 후 홈으로 리다이렉트"""
    # 로그아웃 로그 기록
    user_id = request.cookies.get("login_user") or request.cookies.get("admin_user") or "Unknown"
    log_login_attempt(user_id, True, "로그아웃")
    
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
from utils.encryption import parse_project_key_from_url, create_project_url

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
            .navbar .container {
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
            }
            
            .navbar .navbar-nav.mx-auto {
                position: absolute !important;
                left: 50% !important;
                transform: translateX(-50%) !important;
                display: flex !important;
                align-items: center !important;
            }
            
            .nav-link {
                padding: 10px 20px !important;
                margin: 0 8px !important;
                border-radius: 6px !important;
                transition: all 0.3s ease !important;
                font-weight: 500 !important;
                color: #ffffff !important;
                position: relative !important;
                text-decoration: none !important;
                border: 2px solid transparent !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                max-width: 120px !important;
                text-align: center !important;
                line-height: 1.2 !important;
            }
            
            .nav-link:hover {
                background-color: #495057 !important;
                color: #ffffff !important;
                transform: translateY(-1px) !important;
                box-shadow: 0 2px 8px rgba(0,0,0,0.2) !important;
            }
            
            .nav-link.active {
                background-color: #ffc107 !important;
                color: #000000 !important;
                font-weight: 700 !important;
                box-shadow: 0 4px 12px rgba(255, 193, 7, 0.4) !important;
                border: 2px solid #ffc107 !important;
                transform: translateY(-2px) !important;
                position: relative !important;
            }
            
            .nav-link.active::before {
                content: '📍' !important;
                margin-right: 4px !important;
                font-size: 12px !important;
            }
            
            .nav-link.active::after {
                content: '' !important;
                position: absolute !important;
                bottom: -4px !important;
                left: 50% !important;
                transform: translateX(-50%) !important;
                width: 30px !important;
                height: 4px !important;
                background-color: #ffc107 !important;
                border-radius: 2px !important;
                box-shadow: 0 2px 4px rgba(255, 193, 7, 0.6) !important;
            }
            
            .navbar-brand {
                font-size: 1.25rem !important;
                z-index: 10 !important;
            }
            
            .navbar-nav.ms-auto {
                z-index: 10 !important;
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

def _build_home_navbar():
    """홈 화면용 네비게이션 바 (로그아웃 버튼만 표시)"""
    user_id = flask_request.cookies.get("login_user")
    admin_user = flask_request.cookies.get("admin_user")

    nav_links = [
        dbc.NavItem(dcc.Link(dbc.Button("Logout", color="danger", size="md", className="text-center"), href="/logout", className="text-decoration-none", id="nav-logout")),
    ]

    # 브랜드(좌측) - 사용자 이름 부분을 강조색으로
    if admin_user:
        brand = html.Span([
            "Concrete MONITOR | ",
            html.Span(admin_user, className="text-warning"),
            " (admin)"
        ])
    elif user_id:
        brand = html.Span([
            "Concrete MONITOR | ",
            html.Span(user_id, className="text-warning")
        ])
    else:
        brand = "Concrete MONITOR"

    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand(brand, href="/", className="fw-bold text-white"),
            dbc.Nav(nav_links, navbar=True, className="ms-auto"),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-4",
        style={
            "backgroundColor": "#2c3e50",
            "borderBottom": "2px solid #34495e",
            "padding": "0.5rem 1rem",
            "position": "relative"
        }
    )

def _build_concrete_sensor_navbar():
    """콘크리트, 센서 페이지용 네비게이션 바"""
    user_id = flask_request.cookies.get("login_user")
    admin_user = flask_request.cookies.get("admin_user")
    
    # 현재 URL에서 프로젝트 키 추출
    from flask import request
    query = request.query_string.decode()
    project_pk = None
    if query:
        project_pk = parse_project_key_from_url(f"?{query}")

    main_nav_links = [
        dbc.NavItem(dcc.Link("대시보드", href="/", className="nav-link", id="nav-dashboard")),
        dbc.NavItem(dcc.Link("콘크리트 모델링", href=create_project_url("/concrete", project_pk), className="nav-link", id="nav-concrete")),
        dbc.NavItem(dcc.Link("센서 위치", href=create_project_url("/sensor", project_pk), className="nav-link", id="nav-sensor")),
    ]
    
    logout_nav = [
        dbc.NavItem(dcc.Link(dbc.Button("Logout", color="danger", size="md", className="text-center"), href="/logout", className="text-decoration-none", id="nav-logout")),
    ]

    if admin_user:
        brand = html.Span([
            "Concrete MONITOR | ",
            html.Span(admin_user, className="text-warning"),
            " (admin)"
        ])
    elif user_id:
        brand = html.Span([
            "Concrete MONITOR | ",
            html.Span(user_id, className="text-warning")
        ])
    else:
        brand = "Concrete MONITOR"

    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand(brand, href="/", className="fw-bold text-white"),
            dbc.Nav(main_nav_links, navbar=True, className="mx-auto"),
            dbc.Nav(logout_nav, navbar=True, className="ms-auto"),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-4",
        style={
            "backgroundColor": "#2c3e50",
            "borderBottom": "2px solid #34495e",
            "padding": "0.5rem 1rem",
            "position": "relative"
        }
    )

def _build_analysis_navbar():
    """분석 페이지용 네비게이션 바"""
    user_id = flask_request.cookies.get("login_user")
    admin_user = flask_request.cookies.get("admin_user")
    
    from flask import request
    query = request.query_string.decode()
    project_pk = None
    if query:
        project_pk = parse_project_key_from_url(f"?{query}")

    main_nav_links = [
        dbc.NavItem(dcc.Link("대시보드", href="/", className="nav-link", id="nav-dashboard")),
        dbc.NavItem(dcc.Link("온도", href=create_project_url("/temp", project_pk), className="nav-link", id="nav-temp")),
        dbc.NavItem(dcc.Link("응력", href=create_project_url("/stress", project_pk), className="nav-link", id="nav-stress")),
        dbc.NavItem(dcc.Link("TCI", href=create_project_url("/tci", project_pk), className="nav-link", id="nav-tci")),
        dbc.NavItem(dcc.Link("강도", href=create_project_url("/strength", project_pk), className="nav-link", id="nav-strength")),
        dbc.NavItem(dcc.Link("다운로드", href=create_project_url("/download", project_pk), className="nav-link", id="nav-download")),
    ]
    
    logout_nav = [
        dbc.NavItem(dcc.Link(dbc.Button("Logout", color="danger", size="md", className="text-center"), href="/logout", className="text-decoration-none", id="nav-logout")),
    ]

    if admin_user:
        brand = html.Span([
            "Concrete MONITOR | ",
            html.Span(admin_user, className="text-warning"),
            " (admin)"
        ])
    elif user_id:
        brand = html.Span([
            "Concrete MONITOR | ",
            html.Span(user_id, className="text-warning")
        ])
    else:
        brand = "Concrete MONITOR"

    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand(brand, href="/", className="fw-bold text-white"),
            dbc.Nav(main_nav_links, navbar=True, className="mx-auto"),
            dbc.Nav(logout_nav, navbar=True, className="ms-auto"),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-4",
        style={
            "backgroundColor": "#2c3e50",
            "borderBottom": "2px solid #34495e",
            "padding": "0.5rem 1rem",
            "position": "relative"
        }
    )

def _build_sensor_data_navbar():
    """센서 데이터 확인 페이지용 네비게이션 바"""
    user_id = flask_request.cookies.get("login_user")
    admin_user = flask_request.cookies.get("admin_user")
    
    from flask import request
    query = request.query_string.decode()
    page_param = None
    if query:
        from urllib.parse import parse_qs
        params = parse_qs(query)
        page_param = params.get('page', [None])[0]
        query_str = f"?{query}" if page_param else ""
    else:
        query_str = ""

    main_nav_links = [
        dbc.NavItem(dcc.Link("대시보드", href="/", className="nav-link", id="nav-dashboard")),
        dbc.NavItem(dcc.Link("센서 데이터", href=f"/sensor_data{query_str}" if page_param else "/sensor_data", className="nav-link", id="nav-sensor-data")),
    ]
    
    logout_nav = [
        dbc.NavItem(dcc.Link(dbc.Button("Logout", color="danger", size="md", className="text-center"), href="/logout", className="text-decoration-none", id="nav-logout")),
    ]

    if admin_user:
        brand = html.Span([
            "Concrete MONITOR | ",
            html.Span(admin_user, className="text-warning"),
            " (admin)"
        ])
    elif user_id:
        brand = html.Span([
            "Concrete MONITOR | ",
            html.Span(user_id, className="text-warning")
        ])
    else:
        brand = "Concrete MONITOR"

    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand(brand, href="/", className="fw-bold text-white"),
            dbc.Nav(main_nav_links, navbar=True, className="mx-auto"),
            dbc.Nav(logout_nav, navbar=True, className="ms-auto"),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-4",
        style={
            "backgroundColor": "#2c3e50",
            "borderBottom": "2px solid #34495e",
            "padding": "0.5rem 1rem",
            "position": "relative"
        }
    )

def _build_admin_navbar():
    admin_user = flask_request.cookies.get("admin_user")

    # 관리자 네비게이션 바: 브랜드 + 관리자 메뉴
    admin_nav_links = [
        dbc.NavItem(dcc.Link("Dashboard", href="/admin_dashboard", className="nav-link", id="admin-nav-dashboard")),
        dbc.NavItem(dcc.Link("Projects", href="/admin_projects", className="nav-link", id="admin-nav-projects")),
        dbc.NavItem(dcc.Link("Logs", href="/admin_logs", className="nav-link", id="admin-nav-logs")),
        dbc.NavItem(dcc.Link("Automation", href="/admin_automation", className="nav-link", id="admin-nav-automation")),
        dbc.NavItem(dcc.Link(dbc.Button("Logout", color="danger", size="md", className="text-center"), href="/logout", className="text-decoration-none")),
    ]

    # 브랜드(좌측) - 관리자 이름 부분을 강조색으로
    brand = html.Span([
        "Concrete MONITOR | ",
        html.Span(admin_user, className="text-warning"),
        " (admin)"
    ])

    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand(brand, href="/admin_dashboard", className="fw-bold text-white"),
            dbc.Nav(admin_nav_links, navbar=True, className="admin-navbar ms-auto"),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-4",
        style={
            "backgroundColor": "#34495e",
            "borderBottom": "2px solid #2c3e50",
            "padding": "0.5rem 1rem"
        }
    )

def serve_layout():
    return dbc.Container(
        fluid=True,
        children=[
            dcc.Location(id="url"),
            html.Div(id="navbar-container"),
            dbc.Card(className="shadow-sm p-4", children=[page_container]),
        ],
    )
app.layout = serve_layout

# 통합된 URL 리다이렉트 콜백
@app.callback(
    Output("url", "pathname"),
    [Input("url", "pathname")],
    prevent_initial_call=True
)
def handle_url_redirects(pathname):
    """모든 URL 리다이렉트 로직을 처리합니다."""
    
    # 관리자 페이지에서 일반 페이지 접근 차단
    admin_user = flask_request.cookies.get("admin_user")
    if admin_user and pathname in ["/", "/project", "/sensor", "/concrete", "/download", "/tci_analysis"]:
        return "/admin_dashboard"
    
    # 로그인 페이지 리다이렉트
    # 관리자 페이지 접근 체크
    if pathname.startswith("/admin_dashboard") or pathname.startswith("/admin_projects") or pathname.startswith("/admin_logs") or pathname.startswith("/admin_automation"):
        if not flask_request.cookies.get("admin_user"):
            return "/admin"
    
    # 일반 페이지 접근 체크
    if not pathname.startswith(("/login", "/admin", "/do_login", "/do_admin_login", "/assets", "/_dash", "/favicon", "/logout")):
        if not flask_request.cookies.get("login_user"):
            return "/login"
    
    return no_update

# 통합된 네비게이션 바 콜백
@app.callback(
    Output("navbar-container", "children"),
    Input("url", "pathname")
)
def update_navbar(pathname):
    """URL에 따라 적절한 네비게이션 바를 반환합니다."""
    # 로그인 페이지에서는 네비게이션 바 숨김
    if pathname and pathname.startswith("/login"):
        return None
    
    # 관리자 페이지 접근 체크
    if pathname.startswith("/admin_dashboard") or pathname.startswith("/admin_projects") or pathname.startswith("/admin_logs") or pathname.startswith("/admin_automation"):
        if not flask_request.cookies.get("admin_user"):
            return html.Div()  # 빈 div 반환
        return _build_admin_navbar()
    
    # 일반 사용자 페이지 접근 체크
    if not flask_request.cookies.get("login_user"):
        return html.Div()  # 빈 div 반환
    
    # 페이지별 네비게이션 바 선택
    if pathname == "/":
        # 홈 화면: 로그아웃 버튼만
        return _build_home_navbar()
    elif pathname.startswith("/concrete") or pathname.startswith("/sensor"):
        # 콘크리트, 센서 페이지: 대시보드, 콘크리트 모델링, 센서 위치
        return _build_concrete_sensor_navbar()
    elif pathname.startswith("/temp") or pathname.startswith("/stress") or pathname.startswith("/tci") or pathname.startswith("/strength") or pathname.startswith("/download"):
        # 분석 페이지: 대시보드, 온도분석, 응력분석, TCI분석, 강도분석, 파일 다운로드
        return _build_analysis_navbar()
    elif pathname.startswith("/sensor_data"):
        # 센서 데이터 확인 페이지: 대시보드, 센서 데이터
        return _build_sensor_data_navbar()
    else:
        # 기본값: 홈 네비게이션 바
        return _build_home_navbar()



# 네비게이션 바 링크 URL 동적 업데이트 콜백 (분석 페이지용)
@app.callback(
    [Output("nav-temp", "href"),
     Output("nav-stress", "href"),
     Output("nav-tci", "href"),
     Output("nav-strength", "href"),
     Output("nav-download", "href")],
    [Input("url", "pathname"),
     Input("url", "search")],
    prevent_initial_call=True
)
def update_analysis_nav_links(pathname, search):
    """분석 페이지용 네비게이션 바 링크들이 현재 URL의 쿼리 파라미터를 유지하도록 업데이트합니다."""
    
    # 분석 페이지가 아닌 경우 업데이트하지 않음
    if not (pathname.startswith("/temp") or pathname.startswith("/stress") or 
            pathname.startswith("/tci") or pathname.startswith("/strength") or 
            pathname.startswith("/download")):
        raise dash.exceptions.PreventUpdate
    
    # 프로젝트 키 추출
    project_pk = parse_project_key_from_url(search) if search else None
    
    # 암호화된 URL 생성
    temp_url = create_project_url("/temp", project_pk)
    stress_url = create_project_url("/stress", project_pk)
    tci_url = create_project_url("/tci", project_pk)
    strength_url = create_project_url("/strength", project_pk)
    download_url = create_project_url("/download", project_pk)
    
    return temp_url, stress_url, tci_url, strength_url, download_url



# 분석 페이지용 네비게이션 바 active 클래스 동적 적용 콜백
@app.callback(
    [Output("nav-dashboard", "className", allow_duplicate=True),
     Output("nav-temp", "className"),
     Output("nav-stress", "className"),
     Output("nav-tci", "className"),
     Output("nav-strength", "className"),
     Output("nav-download", "className")],
    [Input("url", "pathname")],
    prevent_initial_call=True
)
def update_analysis_nav_active(pathname):
    """분석 페이지용 네비게이션 링크의 active 상태를 업데이트합니다."""
    
    # 분석 페이지가 아닌 경우 업데이트하지 않음
    if not (pathname.startswith("/temp") or pathname.startswith("/stress") or 
            pathname.startswith("/tci") or pathname.startswith("/strength") or 
            pathname.startswith("/download")):
        raise dash.exceptions.PreventUpdate
    
    # 기본 클래스 설정
    base_classes = ["nav-link"] * 6
    
    # Active 클래스 추가
    if pathname == "/":
        base_classes[0] += " active"  # 대시보드
    elif pathname.startswith("/temp"):
        base_classes[1] += " active"  # 온도
    elif pathname.startswith("/stress"):
        base_classes[2] += " active"  # 응력
    elif pathname.startswith("/tci"):
        base_classes[3] += " active"  # TCI
    elif pathname.startswith("/strength"):
        base_classes[4] += " active"  # 강도
    elif pathname.startswith("/download"):
        base_classes[5] += " active"  # 다운로드
    
    return tuple(base_classes)

# 관리자 네비게이션 바 active 클래스 동적 적용 콜백
@app.callback(
    [Output("admin-nav-dashboard", "className"),
     Output("admin-nav-projects", "className"),
     Output("admin-nav-logs", "className"),
     Output("admin-nav-automation", "className")],
    [Input("url", "pathname")]
)
def update_admin_nav_active(pathname):
    """관리자 네비게이션 바의 active 상태를 업데이트합니다."""
    # 기본 클래스 설정
    base_classes = ["nav-link fw-bold"] * 4
    
    # Active 클래스 추가
    if pathname.startswith("/admin_dashboard"):
        base_classes[0] += " active"
    elif pathname.startswith("/admin_projects"):
        base_classes[1] += " active"
    elif pathname.startswith("/admin_logs"):
        base_classes[2] += " active"
    elif pathname.startswith("/admin_automation"):
        base_classes[3] += " active"
    
    return base_classes[0], base_classes[1], base_classes[2], base_classes[3]



if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=23022)
