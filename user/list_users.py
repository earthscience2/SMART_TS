"""tb_user 전체 조회 스크립트 (민감 정보는 secret.ini 로 분리)

1. user 디렉터리에 secret.ini 파일을 두고, .gitignore 로 추적되지 않도록 한다.
2. secret.ini 구조는 secret_example.ini 를 참고.
3. 해당 정보로 두 ITS DB 에 접속해 사용자 목록을 출력한다.
"""

from pathlib import Path
from typing import List, Dict
import sys
import configparser

import pandas as pd
from sqlalchemy import create_engine


def load_configs() -> List[Dict[str, str]]:
    """secret.ini 를 읽어 DB 설정 딕셔너리 리스트 반환."""
    ini_path = Path(__file__).resolve().parent / "secret.ini"
    if not ini_path.exists():
        print("[오류] user/secret.ini 가 없습니다. secret_example.ini 를 복사해 작성하세요.")
        sys.exit(1)

    parser = configparser.ConfigParser()
    parser.read(ini_path, encoding="utf-8")

    dbs: List[Dict[str, str]] = []
    for section in parser.sections():
        cfg = parser[section]
        dbs.append(
            {
                "name": section.replace("_DB", ""),
                "host": cfg.get("host"),
                "port": cfg.getint("port", 3306),
                "user": cfg.get("user"),
                "password": cfg.get("password"),
                "db": cfg.get("db_name"),
            }
        )
    return dbs


QUERY = (
    "SELECT userid, grade, authstartdate, authenddate "
    "FROM tb_user ORDER BY userid;"
)


def fetch_users(cfg: Dict[str, str]) -> pd.DataFrame:
    uri = (
        f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['db']}"
    )
    try:
        engine = create_engine(uri, pool_pre_ping=True)
        with engine.begin() as conn:
            df = pd.read_sql(QUERY, conn)
        return df
    except Exception as exc:
        print(f"[오류] {cfg['name']} 접속 실패: {exc}")
        return pd.DataFrame()


def main():
    db_configs = load_configs()
    for cfg in db_configs:
        print(f"\n=== {cfg['name']} 사용자 목록 ===")
        df = fetch_users(cfg)
        if df.empty:
            print("(데이터 없음/조회 실패)")
        else:
            with pd.option_context("display.max_columns", None, "display.width", 160):
                print(df.to_string(index=False))


if __name__ == "__main__":
    main() 