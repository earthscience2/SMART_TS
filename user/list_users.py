"""tb_user 전체 조회 스크립트 (민감 정보는 secret.ini 로 분리)

1. user 디렉터리에 secret.ini 파일을 두고, .gitignore 로 추적되지 않도록 한다.
2. secret.ini 구조는 secret_example.ini 를 참고.
3. 해당 정보로 두 ITS DB 에 접속해 사용자 목록을 출력한다.
4. 권한이 AD가 아닌 사용자의 경우 접근 가능한 프로젝트 ID와 구조ID를 표시한다.
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


USER_QUERY = (
    "SELECT userid, grade, authstartdate, authenddate "
    "FROM tb_user ORDER BY userid;"
)

AUTH_QUERY = (
    "SELECT userid, satype, id, auth "
    "FROM tb_sensor_auth_mapping WHERE userid = %s;"
)

PROJECT_STRUCTURE_QUERY = (
    "SELECT tp.projectid, tp.projectname, s.stid, s.stname, s.staddr "
    "FROM tb_structure s "
    "JOIN tb_group g ON s.groupid = g.groupid "
    "JOIN tb_project tp ON g.projectid = tp.projectid "
    "WHERE tp.projectid IN (%s) "
    "ORDER BY tp.projectid, s.stid;"
)


def fetch_users(cfg: Dict[str, str]) -> pd.DataFrame:
    """사용자 목록 조회"""
    uri = (
        f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['db']}"
    )
    try:
        engine = create_engine(uri, pool_pre_ping=True)
        with engine.begin() as conn:
            df = pd.read_sql(USER_QUERY, conn)
        return df
    except Exception as exc:
        print(f"[오류] {cfg['name']} 접속 실패: {exc}")
        return pd.DataFrame()


def fetch_user_permissions(cfg: Dict[str, str], userid: str) -> pd.DataFrame:
    """특정 사용자의 권한 정보 조회"""
    uri = (
        f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['db']}"
    )
    try:
        engine = create_engine(uri, pool_pre_ping=True)
        with engine.begin() as conn:
            df = pd.read_sql(AUTH_QUERY, conn, params=[userid])
        return df
    except Exception as exc:
        print(f"[오류] {cfg['name']} 권한 조회 실패: {exc}")
        return pd.DataFrame()


def fetch_project_structures(cfg: Dict[str, str], project_ids: List[str]) -> pd.DataFrame:
    """프로젝트 ID 목록에 해당하는 프로젝트 및 구조 정보 조회"""
    if not project_ids:
        return pd.DataFrame()
    
    uri = (
        f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['db']}"
    )
    try:
        engine = create_engine(uri, pool_pre_ping=True)
        # 플레이스홀더 생성
        placeholders = ', '.join(['%s'] * len(project_ids))
        query = PROJECT_STRUCTURE_QUERY % placeholders
        
        with engine.begin() as conn:
            df = pd.read_sql(query, conn, params=project_ids)
        return df
    except Exception as exc:
        print(f"[오류] {cfg['name']} 프로젝트-구조 조회 실패: {exc}")
        return pd.DataFrame()


def display_user_permissions(cfg: Dict[str, str], userid: str, grade: str):
    """사용자의 권한 정보 표시"""
    if grade == "AD":
        print(f"    → 권한: 관리자 (모든 프로젝트/구조 접근 가능)")
        return
    
    # 권한 정보 조회
    auth_df = fetch_user_permissions(cfg, userid)
    if auth_df.empty:
        print(f"    → 권한: 접근 권한 없음")
        return
    
    # 프로젝트 ID와 구조 ID 분류
    project_ids = []
    structure_ids = []
    
    for _, row in auth_df.iterrows():
        auth_id = row['id']
        if auth_id.startswith('P_'):
            project_ids.append(auth_id)
        elif auth_id.startswith('S_'):
            structure_ids.append(auth_id)
    
    print(f"    → 접근 가능한 프로젝트 ID: {', '.join(project_ids) if project_ids else '없음'}")
    print(f"    → 접근 가능한 구조 ID: {', '.join(structure_ids) if structure_ids else '없음'}")
    
    # 프로젝트가 있으면 해당 프로젝트의 구조 목록도 표시
    if project_ids:
        project_structure_df = fetch_project_structures(cfg, project_ids)
        if not project_structure_df.empty:
            print(f"    → 프로젝트 상세 정보:")
            for _, row in project_structure_df.iterrows():
                print(f"        • {row['projectid']} ({row['projectname']}) - 구조: {row['stid']} ({row['stname']})")


def main():
    db_configs = load_configs()
    for cfg in db_configs:
        print(f"\n=== {cfg['name']} 사용자 목록 ===")
        df = fetch_users(cfg)
        if df.empty:
            print("(데이터 없음/조회 실패)")
            continue
        
        print(f"\n{'사용자ID':<15} {'권한':<10} {'권한시작일':<12} {'권한종료일':<12}")
        print("-" * 55)
        
        for _, row in df.iterrows():
            userid = row['userid']
            grade = row['grade']
            start_date = row['authstartdate'].strftime('%Y-%m-%d') if pd.notna(row['authstartdate']) else '미설정'
            end_date = row['authenddate'].strftime('%Y-%m-%d') if pd.notna(row['authenddate']) else '미설정'
            
            print(f"{userid:<15} {grade:<10} {start_date:<12} {end_date:<12}")
            
            # AD가 아닌 사용자의 경우 권한 상세 정보 표시
            if grade != "AD":
                display_user_permissions(cfg, userid, grade)
            
            print()  # 사용자 간 구분을 위한 빈 줄


if __name__ == "__main__":
    main() 