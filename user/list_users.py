"""ITS1, ITS2 MySQL 데이터베이스의 tb_user 테이블 전체 레코드를 조회해
콘솔에 출력하는 스크립트.

사용: python user/list_users.py
의존: PyMySQL, pandas
"""

import sys
from typing import List, Dict

import pandas as pd
from sqlalchemy import create_engine


DB_CONFIGS: List[Dict[str, str]] = [
    {
        "name": "ITS1",
        "host": "210.105.85.3",
        "port": 3306,
        "user": "smart",
        "password": "smart001",
        "db": "itsdb",
    },
    {
        "name": "ITS2",
        "host": "220.89.167.217",
        "port": 3306,
        "user": "smart",
        "password": "smart001",
        "db": "itsdb",
    },
]


QUERY = (
    "SELECT userid, grade, authstartdate, authenddate "
    "FROM tb_user ORDER BY userid;"
)


def fetch_users(cfg: Dict[str, str]) -> pd.DataFrame:
    """주어진 DB 설정으로 tb_user 전체 목록을 조회해 DataFrame 반환."""

    uri = (
        f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['db']}"
    )

    try:
        engine = create_engine(uri, echo=False, pool_pre_ping=True)
        with engine.begin() as conn:
            df = pd.read_sql(QUERY, conn)
        return df
    except Exception as exc:
        print(f"[오류] {cfg['name']} DB 접속 실패: {exc}")
        return pd.DataFrame()


def main() -> None:
    for cfg in DB_CONFIGS:
        print(f"\n=== {cfg['name']} 사용자 목록 ===")
        df = fetch_users(cfg)
        if df.empty:
            print("(데이터 없음 또는 조회 실패)")
        else:
            # 컬럼 너비가 길어지는 경우를 대비해 최대 폭 설정
            with pd.option_context("display.max_columns", None, "display.width", 160):
                print(df.to_string(index=False))


if __name__ == "__main__":
    if "pymysql" not in sys.modules:
        print("PyMySQL 모듈이 필요합니다. requirements.txt 를 설치하세요.")
    main() 