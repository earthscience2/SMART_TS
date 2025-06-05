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
