# its_project_api.py
from __future__ import annotations
import threading, time, re, json
from pathlib import Path
from typing import List, Dict, Optional
import pandas as pd
from ITS_CLI import config, tcp_client
from pathlib import Path
import csv
import json
from typing import Tuple, Dict

# ─── ITS 관련 상수 ─────────────────────────────────────────
CMD_LOGIN, CMD_GET_PROJECTS = "login", "get_project_list"
SECRET_DEFAULT = Path("secret.ini")                # USER / PW=...
_RE_KV = re.compile(r"^\s*([A-Za-z_]+)\s*=\s*(.+?)\s*$")


def make_inp(sensor_id: str,
             sensor_csv: Path = Path("data/sensor.csv"),
             concrete_csv: Path = Path("data/concrete.csv")
             ) -> Tuple[Dict[int, Tuple[float, float]], float]:
    """
    sensor_id에 대응하는 concrete_id를 찾아,
    해당 concrete의 dims.nodes를 plan_points 딕셔너리로,
    dims.h를 thickness로 반환한다.
    """
    # 1) sensor.csv에서 concrete_id 찾기
    concrete_id = None
    with sensor_csv.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['sensor_id'] == sensor_id:
                concrete_id = row['concrete_id']
                break
    if concrete_id is None:
        raise ValueError(f"sensor_id '{sensor_id}'를 sensor.csv에서 찾을 수 없습니다.")

    # 2) concrete.csv에서 dims 파싱
    dims = None
    with concrete_csv.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['concrete_id'] == concrete_id:
                dims = json.loads(row['dims'])
                break
    if dims is None:
        raise ValueError(f"concrete_id '{concrete_id}'를 concrete.csv에서 찾을 수 없습니다.")

    # 3) plan_points 생성 (1-based index)
    nodes = dims.get('nodes', [])
    plan_points = {idx + 1: (float(x), float(y))
                   for idx, (x, y) in enumerate(nodes)}

    # 4) thickness를 dims['h'] 값으로 설정
    thickness = float(dims.get('h', 0.0))

    return plan_points, thickness

# 센서 데이터 조회
# 센서 폴더에 일 단위로 폴더 이름으로 저장
#def get_sensor_data(sensor_id, str_time, end_time):
