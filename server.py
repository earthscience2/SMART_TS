# server.py
import os
from flask import Flask, request, redirect, make_response
from dash import Dash
import dash_bootstrap_components as dbc
import api_user  # 앞서 만든 api_user.py

# --------------------------------------------------
# Flask & Dash 앱 초기화
# --------------------------------------------------
server = Flask(__name__)
app = Dash(
    __name__,
    server=server,
    use_pages=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)

# --------------------------------------------------
# 로그인 처리 라우트 (GET/POST 모두 허용)
# --------------------------------------------------
@server.route("/do_login", methods=["GET", "POST"])
def do_login():
    # GET 요청일 때는 /login 페이지로 리다이렉트
    if request.method == "GET":
        return redirect("/login")

    # POST 요청일 때만 실제 로그인 로직 실행
    user_id = request.form.get("user_id", "")
    user_pw = request.form.get("user_pw", "")
    success, token_or_msg = api_user.authenticate(user_id, user_pw)

    if not success:
        # 로그인 실패 시 /login?error=... 로 리다이렉트
        return redirect(f"/login?error={token_or_msg}")

    # 로그인 성공: 쿠키 설정 후 홈으로 리다이렉트
    resp = make_response(redirect("/"))
    resp.set_cookie(
        "login_token",
        token_or_msg,
        max_age=api_user.TOKEN_EXPIRATION,
        httponly=True,
        secure=False,  # HTTPS 환경이라면 True로 변경
    )
    return resp

# --------------------------------------------------
# Dash가 pages 디렉토리 아래의 페이지들을 자동으로 로드
# --------------------------------------------------
# pages/login.py, pages/home.py가 각각 /login, / 에 매핑됩니다.

if __name__ == "__main__":
    # 서버 재시작
    app.run_server(debug=True, host="0.0.0.0", port=8050)
