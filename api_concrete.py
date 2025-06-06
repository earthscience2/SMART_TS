# api_concrete.py
import pandas as pd
import os
import csv
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
    컬럼: ["concrete_id","name","dims","created"]
    파일이 없으면 빈 DataFrame 반환.
    """
    if not os.path.isfile(CONCRETE_CSV):
        # 파일이 없으면 빈 DataFrame with columns 반환
        return pd.DataFrame(columns=["concrete_id", "name", "dims", "created"])

    df = pd.read_csv(CONCRETE_CSV, dtype=str)
    # 기존 CSV가 column 순서가 다를 수 있으니 항상 통일
    expected_cols = ["concrete_id", "name", "dims", "created"]
    df = df[expected_cols]
    return df

# ──────────────────────────────────────────────────────────────────────────────
# 2) add_concrete(name, dims): 새로운 콘크리트 추가
# ──────────────────────────────────────────────────────────────────────────────
def add_concrete(name: str, dims: dict):
    """
    새로운 concrete_id를 자동 생성(예: C001 → C002 → ...)
    - name: 콘크리트 이름 (문자열)
    - dims: Python dict, 예: {"nodes": [[1,1],[1,2],[2,2],[2,1]], "h":0.5}
    CSV에 한 줄 추가 후 저장.
    """
    df = load_all()
    # 새로운 ID 생성: 기존에 가장 큰 숫자 + 1
    if df.empty:
        new_id = "C001"
    else:
        # "C" 제거한 뒤 숫자로 변환 → 최대값 + 1
        existing = df["concrete_id"].apply(lambda x: int(x.strip().lstrip("C")))
        max_num = existing.max()
        new_id = f"C{max_num+1:03d}"

    now_iso = datetime.utcnow().isoformat() + "Z"
    dims_str = str(dims).replace("'", '"')  # JSON처럼 double quote로 맞추기
    new_row = {"concrete_id": new_id, "name": name, "dims": dims_str, "created": now_iso}

    df = df.append(new_row, ignore_index=True)
    df.to_csv(CONCRETE_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)

# ──────────────────────────────────────────────────────────────────────────────
# 3) update_concrete(concrete_id, name, dims): 기존 콘크리트 수정
# ──────────────────────────────────────────────────────────────────────────────
def update_concrete(concrete_id: str, name: str, dims: dict):
    """
    주어진 concrete_id 행을 찾아 name, dims를 수정 후 저장.
    created 컬럼은 변경하지 않음.
    """
    df = load_all()
    if df.empty or concrete_id not in df["concrete_id"].values:
        raise ValueError(f"존재하지 않는 Concrete ID: {concrete_id}")

    # dims를 문자열로 변경
    dims_str = str(dims).replace("'", '"')
    # 해당 행의 name, dims 값 바꿈
    df.loc[df["concrete_id"] == concrete_id, "name"] = name
    df.loc[df["concrete_id"] == concrete_id, "dims"] = dims_str

    # 저장
    df.to_csv(CONCRETE_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)

# ──────────────────────────────────────────────────────────────────────────────
# 4) delete_concrete(concrete_id): 콘크리트 삭제 (행 하나 삭제)
# ──────────────────────────────────────────────────────────────────────────────
def delete_concrete(concrete_id: str):
    """
    주어진 concrete_id 행을 삭제 후 CSV 저장.
    """
    df = load_all()
    if df.empty or concrete_id not in df["concrete_id"].values:
        raise ValueError(f"존재하지 않는 Concrete ID: {concrete_id}")

    df = df[df["concrete_id"] != concrete_id]
    df.to_csv(CONCRETE_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)
