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

# ─── CSV 경로 (콘크리트 DB) ────────────────────────────────
CSV_PATH = Path("concrete.csv")

# ─── secret.ini → (USER, PW) ──────────────────────────────
def _load_secret(path: Path = SECRET_DEFAULT) -> tuple[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"secret.ini not found: {path}")
    user = pw = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _RE_KV.match(line)
        if not m:
            continue
        k, v = m[1].upper(), m[2].strip()
        if k == "USER":
            user = v
        elif k in ("PW", "PASSWORD"):
            pw = v
    if not user or not pw:
        raise RuntimeError("secret.ini must contain USER and PW")
    return user, pw

# ─── ITS TCP 연결 헬퍼 ─────────────────────────────────────
def _connect() -> tcp_client.TCPClient:
    config.config_load()
    c = tcp_client.TCPClient(config.SERVER_IP, config.SERVER_PORT,
                             config.ITS_NUM, config.certfile)
    threading.Thread(target=c.receive_messages, daemon=True).start()
    time.sleep(1)
    return c

# ─── (예시) ITS 프로젝트 리스트 가져오기 ──────────────────
def get_project_list(secret_path: Path | str = SECRET_DEFAULT,
                     as_dataframe: bool = True):
    uid, pw = _load_secret(Path(secret_path))
    cli = _connect()
    try:
        cli.set_user_password(uid, pw)
        if cli.message(CMD_LOGIN).get("result") != "Success":
            raise RuntimeError("login failed")
        res = cli.message(CMD_GET_PROJECTS)
        if res.get("result") != "Success":
            raise RuntimeError("get_project_list failed")
        data = res["data"]
        return pd.DataFrame(data) if as_dataframe else data
    finally:
        cli.close()

# ─── CSV 기반 콘크리트 DB CRUD ────────────────────────────
_cols = ["concrete_id", "name", "shape", "dims", "aux", "created"]

def _load_df() -> pd.DataFrame:
    if CSV_PATH.exists():
        return pd.read_csv(CSV_PATH, dtype=str)
    return pd.DataFrame(columns=_cols)

def _save_df(df: pd.DataFrame) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False, encoding="utf-8")

def load_all() -> pd.DataFrame:
    return _load_df()

def add_concrete(name: str, shape: str, dims: Dict) -> None:
    df = _load_df()
    new_row = {
        "concrete_id": f"C{len(df)+1:03d}",
        "name": name,
        "shape": shape,
        "dims": json.dumps(dims, ensure_ascii=False),
        "aux": json.dumps({"origin": "0,0,0", "dir": "+X+Y"}, ensure_ascii=False),
        "created": pd.Timestamp.utcnow().isoformat(timespec="seconds") + "Z"
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    _save_df(df)

def update_dims(concrete_id: str, new_dims: Dict) -> None:
    df = _load_df()
    mask = df["concrete_id"] == concrete_id
    if not mask.any():
        raise ValueError("ID not found")
    df.loc[mask, "dims"] = json.dumps(new_dims, ensure_ascii=False)
    _save_df(df)
