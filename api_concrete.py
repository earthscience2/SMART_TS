import pandas as pd
import os
import csv
import json
from datetime import datetime

# ──────────────────────────────────────────────────────────────────────────────
# 설정: CSV 파일 경로
# ──────────────────────────────────────────────────────────────────────────────
DATA_DIR = "data"
CONCRETE_CSV = os.path.join(DATA_DIR, "concrete.csv")
# 필요한 폴더가 없으면 생성
os.makedirs(DATA_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# 1) load_all(): 콘크리트 메타데이터 전체 로드
# ──────────────────────────────────────────────────────────────────────────────
def load_all() -> pd.DataFrame:
    """
    concrete.csv 파일을 읽어 DataFrame으로 반환.
    컬럼: ["concrete_pk","project_pk","name","dims","con_unit","con_e","con_b","con_n","created_at","updated_at"]
    파일이 없으면 빈 DataFrame 반환.
    """
    if not os.path.isfile(CONCRETE_CSV):
        return pd.DataFrame(columns=["concrete_pk","project_pk","name","dims","con_unit","con_e","con_b","con_n","created_at","updated_at"])

    df = pd.read_csv(CONCRETE_CSV, dtype=str)
    # 컬럼 순서 통일
    expected = ["concrete_pk","project_pk","name","dims","con_unit","con_e","con_b","con_n","created_at","updated_at"]
    df = df.reindex(columns=expected)
    return df

# ──────────────────────────────────────────────────────────────────────────────
# 2) load_by_project(project_pk): 특정 프로젝트의 콘크리트 목록 반환
# ──────────────────────────────────────────────────────────────────────────────
def load_by_project(project_pk: str) -> pd.DataFrame:
    """
    주어진 project_pk에 해당하는 콘크리트만 필터링해 반환.
    """
    df = load_all()
    if df.empty:
        return df
    return df[df["project_pk"] == project_pk]

# ──────────────────────────────────────────────────────────────────────────────
# 3) add_concrete(project_pk, name, dims, con_unit, con_e, con_b, con_n): 새로운 콘크리트 추가
# ──────────────────────────────────────────────────────────────────────────────
def add_concrete(
    project_pk: str,
    name: str,
    dims: dict,
    con_unit: str = None,
    con_e: str = None,
    con_b: str = None,
    con_n: str = None,
):
    """
    새로운 concrete_pk를 자동 생성(예: C001 → C002 → ...)
    - project_pk: 연결된 프로젝트 PK
    - name: 콘크리트 이름
    - dims: dict (예: {"nodes": [...], "h":0.5})
    - con_unit, con_e, con_b, con_n: 센서 유닛/염도 등 선택적 속성
    CSV에 한 줄 추가 후 저장.
    """
    df = load_all()
    # ID 생성
    if df.empty:
        new_id = "C001"
    else:
        nums = df["concrete_pk"].str.lstrip("C").astype(int)
        new_id = f"C{nums.max()+1:03d}"

    now = datetime.utcnow().isoformat() + "Z"
    dims_str = json.dumps(dims, ensure_ascii=False)
    row = {
        "concrete_pk": new_id,
        "project_pk": project_pk,
        "name": name,
        "dims": dims_str,
        "con_unit": con_unit or "",
        "con_e": con_e or "",
        "con_b": con_b or "",
        "con_n": con_n or "",
        "created_at": now,
        "updated_at": now,
    }
    print(row)
    # 또는 방법2: loc로 직접 추가
    df.loc[len(df)] = row
    df.to_csv(CONCRETE_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)
    return new_id

# ──────────────────────────────────────────────────────────────────────────────
# 4) update_concrete(concrete_pk, **kwargs): 기존 콘크리트 수정
# ──────────────────────────────────────────────────────────────────────────────
def update_concrete(concrete_pk: str, **kwargs):
    """
    주어진 concrete_pk 행을 찾아 주어진 필드만 수정 후 저장.
    허용 필드: project_pk, name, dims, con_unit, con_e, con_b, con_n
    """
    df = load_all()
    if df.empty or concrete_pk not in df["concrete_pk"].values:
        raise ValueError(f"존재하지 않는 Concrete PK: {concrete_pk}")

    idx = df.index[df["concrete_pk"] == concrete_pk][0]
    # 각 키별 처리
    for key in ["project_pk","name","dims","con_unit","con_e","con_b","con_n"]:
        if key in kwargs and kwargs[key] is not None:
            if key == "dims":
                df.at[idx, "dims"] = json.dumps(kwargs["dims"], ensure_ascii=False)
            else:
                df.at[idx, key] = kwargs[key]
    # updated_at 갱신
    df.at[idx, "updated_at"] = datetime.utcnow().isoformat() + "Z"

    df.to_csv(CONCRETE_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)

# ──────────────────────────────────────────────────────────────────────────────
# 5) delete_concrete(concrete_pk): 콘크리트 삭제
# ──────────────────────────────────────────────────────────────────────────────
def delete_concrete(concrete_pk: str):
    """
    주어진 concrete_pk 행을 삭제 후 CSV 저장.
    """
    df = load_all()
    if df.empty or concrete_pk not in df["concrete_pk"].values:
        raise ValueError(f"존재하지 않는 Concrete PK: {concrete_pk}")

    df = df[df["concrete_pk"] != concrete_pk]
    df.to_csv(CONCRETE_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)

# ──────────────────────────────────────────────────────────────────────────────
# 6) get_concrete(concrete_pk): 단일 콘크리트 조회
# ──────────────────────────────────────────────────────────────────────────────
def get_concrete(concrete_pk: str) -> dict:
    """
    주어진 concrete_pk에 해당하는 콘크리트 정보를 dict로 반환.
    존재하지 않으면 None.
    """
    df = load_all()
    row = df[df["concrete_pk"] == concrete_pk]
    if row.empty:
        return None
    data = row.iloc[0].to_dict()
    # dims를 dict로 변환
    try:
        data["dims"] = json.loads(data["dims"])
    except Exception:
        pass
    return data