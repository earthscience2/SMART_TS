# 로그인 검증용 테스트 스크립트
# 콘솔에서 아이디(ID)와 비밀번호를 입력받아 MySQL DB에 저장된 값과 비교한다.
# itsdb1.py 의 user_regist 함수를 활용하며, 비밀번호 비교는 bcrypt.checkpw 로 수행한다.

import getpass
import bcrypt
import sys

import itsdb1


def init_db():
    """DB 접속 정보를 받아 itsdb1 모듈을 초기화한다."""
    print("[DB 접속 정보 입력] (Enter 키를 누르면 기본값 적용)")
    host = input("호스트 (기본: 127.0.0.1): ") or "127.0.0.1"
    user = input("DB 사용자 (기본: root): ") or "root"
    pwd = getpass.getpass("DB 비밀번호 (기본: smart001): ") or "smart001"
    dbname = input("DB 이름 (기본: itsdb): ") or "itsdb"

    try:
        itsdb1.itsdb_init(host, user, pwd, dbname)
        print("DB 연결 성공 ✅")
    except Exception as e:
        print(f"DB 연결 실패 ❌: {e}")
        sys.exit(1)


def verify_user():
    """사용자 ID/비밀번호를 입력받아 존재 여부 및 비밀번호 일치 여부를 확인한다."""
    user_id = input("아이디 입력: ").strip()
    password = getpass.getpass("비밀번호 입력: ")

    df = itsdb1.user_regist(user_id)
    if df is None or df.empty:
        print("[실패] 존재하지 않는 사용자입니다.")
        return

    stored_hash = df.iloc[0]["userpw"].encode("utf-8")
    if bcrypt.checkpw(password.encode("utf-8"), stored_hash):
        grade = df.iloc[0]["grade"]
        print(f"[성공] 로그인 완료! 등급: {grade}")
    else:
        print("[실패] 비밀번호가 올바르지 않습니다.")


if __name__ == "__main__":
    init_db()
    verify_user()