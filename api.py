# its_project_api.py
from __future__ import annotations
import threading, time, re, json
from pathlib import Path
from typing import List, Dict, Optional
import pandas as pd
from ITS_CLI import config, tcp_client

# ─── ITS 관련 상수 ─────────────────────────────────────────
CMD_LOGIN, CMD_GET_PROJECTS = "login", "get_project_list"
SECRET_DEFAULT = Path("secret.ini")                # USER / PW=...
_RE_KV = re.compile(r"^\s*([A-Za-z_]+)\s*=\s*(.+?)\s*$")

# ─── CSV 기반 콘크리트 DB ──────────────────────────────────────────────
CSV_PATH   = Path("concrete.csv")
_COLS      = ["concrete_id", "name", "shape", "dims", "aux", "created"]


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
    """CSV 전체 덮어쓰기 저장(외부에서 직접 수정 후 호출)"""
    _save_df(df)


def add_concrete(name: str, shape: str, dims: Dict,
                 aux: Dict | None = None) -> str:
    """새 콘크리트 행 추가 → ID 반환"""
    df = _load_df()
    cid = f"C{len(df) + 1:03d}"
    row = {
        "concrete_id": cid,
        "name": name,
        "shape": shape,
        "dims": json.dumps(dims, ensure_ascii=False),
        "aux":  json.dumps(aux or {"origin": "0,0,0",
                                   "gravity_vec": "0,0,-1"}, ensure_ascii=False),
        "created": pd.Timestamp.utcnow().isoformat(timespec="seconds") + "Z",
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save_df(df)
    return cid


def update_concrete(cid: str, name: str, shape: str,
                    dims: Dict, aux: Dict) -> None:
    """ID 행을 찾아 모든 필드 업데이트"""
    df = _load_df()
    m  = df["concrete_id"] == cid
    if not m.any():
        raise ValueError("concrete_id not found")
    df.loc[m, ["name", "shape"]] = name, shape
    df.loc[m, "dims"] = json.dumps(dims, ensure_ascii=False)
    df.loc[m, "aux"]  = json.dumps(aux,  ensure_ascii=False)
    _save_df(df)


def delete_concrete(cid: str) -> None:
    """ID 행 삭제"""
    df = _load_df()
    df = df[df["concrete_id"] != cid].reset_index(drop=True)
    _save_df(df)
    
def update_concrete(concrete_id, name, shape, dims, aux):
    df = _load_df()
    m  = df["concrete_id"] == concrete_id
    if not m.any():
        raise ValueError("ID not found")
    df.loc[m, ["name","shape"]] = [name, shape]
    df.loc[m, "dims"] = json.dumps(dims, ensure_ascii=False)
    df.loc[m, "aux"]  = json.dumps(aux,  ensure_ascii=False)
    _save_df(df)