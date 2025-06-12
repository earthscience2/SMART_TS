# api_user.py

import os
import pandas as pd
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from dotenv import load_dotenv

load_dotenv()  # .env 파일 자동 로드

SECRET_KEY = os.getenv("SECRET_KEY")
TOKEN_EXPIRATION = 86400  # 1일

serializer = URLSafeTimedSerializer(SECRET_KEY, salt="login-token")

def load_users() -> pd.DataFrame:
    df = pd.read_csv("data/user.csv", dtype=str)
    # "true"/"false" 문자열을 올바르게 불리언으로 변환
    df["active"] = df["active"].str.lower() == "true"
    return df

def authenticate(user_id: str, user_pw: str) -> tuple[bool, str]:
    df = load_users()
    row = df[(df.user_id == user_id) & (df.user_pw == user_pw)]
    if row.empty:
        return False, "아이디 또는 비밀번호가 일치하지 않습니다."
    if not row.iloc[0].active:
        return False, "비활성화된 계정입니다."
    token = serializer.dumps({"user_id": user_id})
    return True, token

def validate_token(token: str) -> bool:
    try:
        data = serializer.loads(token, max_age=TOKEN_EXPIRATION)
        df = load_users()
        return not df[df.user_id == data["user_id"]].empty
    except (SignatureExpired, BadSignature, Exception):
        return False

def get_user_info(token: str) -> dict | None:
    """
    토큰이 유효하고, 활성화된 사용자가 존재하면
    해당 사용자의 모든 필드를 dict로 반환.
    그렇지 않으면 None을 반환.
    """
    try:
        data = serializer.loads(token, max_age=TOKEN_EXPIRATION)
    except (SignatureExpired, BadSignature):
        return None

    df = load_users()
    user_row = df[df.user_id == data["user_id"]]
    if user_row.empty or not user_row.iloc[0].active:
        return None

    u = user_row.iloc[0]
    return {
        "user_id": u.user_id,
        "user_name": u.user_name,
        "user_email": u.user_email,
        "user_phone": u.user_phone,
        "user_role": u.user_role,
        "user_company": u.user_company,
        "active": u.active,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
    }
