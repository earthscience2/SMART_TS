from __future__ import annotations
import json
from pathlib import Path
from typing import Dict
import pandas as pd

# ─── CSV 기반 센서 DB ──────────────────────────────────────────────
CSV_PATH_SENSOR = Path("sensor.csv")
_COLS_SENSOR    = ["concrete_id", "sensor_id", "dims", "created"]


def _load_df_sensor() -> pd.DataFrame:
    if CSV_PATH_SENSOR.exists():
        return pd.read_csv(CSV_PATH_SENSOR, dtype=str)
    return pd.DataFrame(columns=_COLS_SENSOR)


def _save_df_sensor(df: pd.DataFrame) -> None:
    CSV_PATH_SENSOR.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH_SENSOR, index=False, encoding="utf-8")


# ─── public CRUD API ──────────────────────────────────────────────────

def load_all_sensors() -> pd.DataFrame:
    """
    CSV 전체 로드
    반환 DataFrame 컬럼: ["concrete_id", "sensor_id", "dims", "created"]
    """
    return _load_df_sensor()


def add_sensor(concrete_id: str, sensor_id: str, dims: Dict) -> None:
    """
    새 센서 행 추가
    dims: {"nodes": [x, y, z]}
    """
    df = _load_df_sensor()
    row = {
        "concrete_id": concrete_id,
        "sensor_id": sensor_id,
        "dims": json.dumps(dims, ensure_ascii=False),
        "created": pd.Timestamp.utcnow().isoformat(timespec="seconds") + "Z",
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save_df_sensor(df)


def update_sensor(concrete_id: str, sensor_id: str, dims: Dict) -> None:
    """
    기존 센서 행을 찾아 dims만 업데이트
    (concrete_id + sensor_id 조합으로 고유 행을 식별)
    dims: {"nodes": [x, y, z]}
    """
    df = _load_df_sensor()
    m = (df["concrete_id"] == concrete_id) & (df["sensor_id"] == sensor_id)
    if not m.any():
        raise ValueError(f"콘크리트 '{concrete_id}' + 센서 '{sensor_id}' 조합을 찾을 수 없습니다.")
    df.loc[m, "dims"] = json.dumps(dims, ensure_ascii=False)
    _save_df_sensor(df)


def delete_sensor(concrete_id: str, sensor_id: str) -> None:
    """
    해당 concrete_id + sensor_id 조합을 삭제
    """
    df = _load_df_sensor()
    df = df[~((df["concrete_id"] == concrete_id) & (df["sensor_id"] == sensor_id))].reset_index(drop=True)
    _save_df_sensor(df)
