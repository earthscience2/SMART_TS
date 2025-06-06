# api_sensor.py
import pandas as pd
import os
import csv
from datetime import datetime
import ast

# ──────────────────────────────────────────────────────────────────────────────
# 설정: CSV 파일 경로
# ──────────────────────────────────────────────────────────────────────────────
DATA_DIR = "data"
SENSOR_CSV = os.path.join(DATA_DIR, "sensor.csv")

os.makedirs(DATA_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# 1) load_all_sensors(): 센서 메타데이터 전체 로드
# ──────────────────────────────────────────────────────────────────────────────
def load_all_sensors() -> pd.DataFrame:
    """
    sensor.csv 파일을 읽어 DataFrame으로 반환.
    컬럼: ["concrete_id","sensor_id","dims","created"]
    파일이 없으면 빈 DataFrame 반환.
    """
    if not os.path.isfile(SENSOR_CSV):
        return pd.DataFrame(columns=["concrete_id", "sensor_id", "dims", "created"])

    df = pd.read_csv(SENSOR_CSV, dtype=str)
    expected_cols = ["concrete_id", "sensor_id", "dims", "created"]
    df = df[expected_cols]
    return df

# ──────────────────────────────────────────────────────────────────────────────
# 2) add_sensor(concrete_id, sensor_id, dims): 센서 추가
# ──────────────────────────────────────────────────────────────────────────────
def add_sensor(concrete_id: str, sensor_id: str, dims: dict):
    """
    새로운 sensor_id를 주어진 concrete_id에 추가.
    - 기존에 동일한 sensor_id가 같은 concrete_id에 존재하면 에러
    - dims: Python dict, 예: {"nodes": [1.2,1.2,0.4]}
    """
    df = load_all_sensors()

    # 중복 체크: 같은 concrete_id, 같은 sensor_id 존재 여부
    duplicate = df[
        (df["concrete_id"] == concrete_id) & (df["sensor_id"] == sensor_id)
    ]
    if not duplicate.empty:
        raise ValueError(f"{concrete_id}에 이미 Sensor ID {sensor_id}가 존재합니다.")

    now_iso = datetime.utcnow().isoformat() + "Z"
    dims_str = str(dims).replace("'", '"')
    new_row = {
        "concrete_id": concrete_id,
        "sensor_id": sensor_id,
        "dims": dims_str,
        "created": now_iso,
    }
    df = df.append(new_row, ignore_index=True)
    df.to_csv(SENSOR_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)

# ──────────────────────────────────────────────────────────────────────────────
# 3) update_sensor(concrete_id, sensor_id, dims): 센서 위치(dims) 수정
# ──────────────────────────────────────────────────────────────────────────────
def update_sensor(concrete_id: str, sensor_id: str, dims: dict):
    """
    주어진 concrete_id와 sensor_id 조합이 존재하면 dims만 수정.
    created 컬럼은 수정하지 않음.
    """
    df = load_all_sensors()
    mask = (df["concrete_id"] == concrete_id) & (df["sensor_id"] == sensor_id)
    if not mask.any():
        raise ValueError(f"{concrete_id}에 Sensor ID {sensor_id}가 존재하지 않습니다.")

    dims_str = str(dims).replace("'", '"')
    df.loc[mask, "dims"] = dims_str
    df.to_csv(SENSOR_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)

# ──────────────────────────────────────────────────────────────────────────────
# 4) delete_sensor(concrete_id, sensor_id): 센서 삭제
# ──────────────────────────────────────────────────────────────────────────────
def delete_sensor(concrete_id: str, sensor_id: str):
    """
    주어진 concrete_id와 sensor_id 조합을 삭제.
    """
    df = load_all_sensors()
    mask = (df["concrete_id"] == concrete_id) & (df["sensor_id"] == sensor_id)
    if not mask.any():
        raise ValueError(f"{concrete_id}에 Sensor ID {sensor_id}가 존재하지 않습니다.")

    df = df[~mask]
    df.to_csv(SENSOR_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)
