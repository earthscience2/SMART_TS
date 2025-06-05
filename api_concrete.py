from __future__ import annotations
import json
from pathlib import Path
from typing import Dict
import pandas as pd

# ─── CSV 기반 콘크리트 DB ──────────────────────────────────────────────
CSV_PATH   = Path("concrete.csv")
_COLS      = ["concrete_id", "name", "dims", "created"]


def _load_df() -> pd.DataFrame:
    if CSV_PATH.exists():
        return pd.read_csv(CSV_PATH, dtype=str)
    return pd.DataFrame(columns=_COLS)


def _save_df(df: pd.DataFrame) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False, encoding="utf-8")


# ─── public CRUD API ──────────────────────────────────────────────────

def load_all() -> pd.DataFrame:
    """CSV 전체 로드"""
    return _load_df()


def save_all(df: pd.DataFrame) -> None:
    """CSV 전체 덮어쓰기 저장 (외부에서 직접 수정 후 호출)"""
    _save_df(df)


def add_concrete(name: str, dims: Dict) -> str:
    """
    새 콘크리트 행 추가 → 생성된 ID 반환
    dims: {"nodes": [[x,y], ...], "h": 높이}
    """
    df = _load_df()
    cid = f"C{len(df) + 1:03d}"
    row = {
        "concrete_id": cid,
        "name": name,
        "dims": json.dumps(dims, ensure_ascii=False),
        "created": pd.Timestamp.utcnow().isoformat(timespec="seconds") + "Z",
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save_df(df)
    return cid


def update_concrete(concrete_id: str, name: str, dims: Dict) -> None:
    """
    기존 ID 행을 찾아 name + dims 필드만 업데이트
    dims: {"nodes": [[x,y], ...], "h": 높이}
    """
    df = _load_df()
    m  = df["concrete_id"] == concrete_id
    if not m.any():
        raise ValueError(f"콘크리트 ID '{concrete_id}'를 찾을 수 없습니다.")
    df.loc[m, ["name"]] = name
    df.loc[m, "dims"]   = json.dumps(dims, ensure_ascii=False)
    _save_df(df)


def delete_concrete(concrete_id: str) -> None:
    """해당 콘크리트 ID 행을 삭제"""
    df = _load_df()
    df = df[df["concrete_id"] != concrete_id].reset_index(drop=True)
    _save_df(df)
