# app.py
import pymysql
from pymysql.cursors import DictCursor
from typing import List, Dict
import os
import pandas as pd
from datetime import datetime, timedelta

# --------------------------------------------------
# 전역으로 DB 연결 설정
DB_CONFIG = {
    'host':     'localhost',
    'port':     3306,
    'user':     'root',
    'password': 'smart001!',
    'database': 'ITS_TS',
    'charset':  'utf8mb4',
}

def get_connection():
    return pymysql.connect(**DB_CONFIG)

def get_project_data(project_pk=None, user_company_pk=None):
    sql = "SELECT * FROM project"
    conditions = []
    params = []

    if project_pk:
        conditions.append("project_pk = %s")
        params.append(project_pk)
    if user_company_pk:
        conditions.append("user_company_pk = %s")
        params.append(user_company_pk)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    conn = get_connection()
    try:
        df = pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()

    return df

def get_concrete_data(concrete_pk=None, project_pk=None):
    sql = "SELECT * FROM concrete"
    conditions = []
    params = []
    if concrete_pk:
        conditions.append("concrete_pk = %s")
        params.append(concrete_pk)
    if project_pk:
        conditions.append("project_pk = %s")
        params.append(project_pk)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    conn = get_connection()
    try:
        df = pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()

    return df

def get_sensors_data(sensor_pk=None, concrete_pk=None, device_id=None, channel=None, d_type=None):
    sql = "SELECT * FROM sensor"
    conditions = []
    params = []
    if sensor_pk:
        conditions.append("sensor_pk = %s")
        params.append(sensor_pk)
    if concrete_pk:
        conditions.append("concrete_pk = %s")
        params.append(concrete_pk)
    if device_id:
        conditions.append("device_id = %s")
        params.append(device_id)
    if channel:
        conditions.append("channel = %s")
        params.append(channel)
    if d_type:
        conditions.append("d_type = %s")
        params.append(d_type)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    conn = get_connection()
    try:
        df = pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()

    return df

def parse_ymdh(ts: str) -> datetime:
    """'YYYYMMDDHH' 문자열을 datetime 객체로 변환."""
    return datetime.strptime(ts, '%Y%m%d%H')

def format_sql_datetime(dt: datetime) -> str:
    """SQL DATETIME 문자열 포맷."""
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def get_sensor_data(sensor_pk=None, start=None, end=None):
    """
    sensor_pk, start, end 값이 주어지면 그에 맞는 행을
    """
    sql = "SELECT * FROM sensor_data"
    conditions = []
    params = []
    if sensor_pk:
        conditions.append("sensor_pk = %s")
        params.append(sensor_pk)
    if start:
        conditions.append("time >= %s")
        params.append(start)
    if end:
        conditions.append("time <= %s")
        params.append(end)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY time ASC"

def get_sensor_data(sensor_pk: str = None,
                    start: str  = None,
                    end: str    = None) -> pd.DataFrame:
    """
    sensor_pk, start, end를 입력받아 sensor_data를 반환.
    - start/end: 'YYYYMMDDHH' 형식
    - start=None, end 주어지면 → end로부터 30일 이전부터 end
    - end=None, start 주어지면 → start부터 30일 이후까지
    - 둘 다 None → 테이블에서 최신 time 기준 30일 이전부터 최신까지
    - sensor_pk=None이면 모든 센서 포함
    """
    conn = get_connection()
    try:
        # 1) 시작/끝날짜 계산
        if start:
            dt_start = parse_ymdh(start)
        if end:
            dt_end = parse_ymdh(end)
        # 둘 다 없으면, 테이블에서 최신 시각 조회
        if not (start or end):
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(`time`) FROM sensor_data;")
                latest = cur.fetchone()[0]
            dt_end = latest if isinstance(latest, datetime) else pd.to_datetime(latest)
            dt_start = dt_end - timedelta(days=30)
        # start만 없고 end만 있을 때
        elif not start and end:
            dt_end = dt_end
            dt_start = dt_end - timedelta(days=30)
        # end만 없고 start만 있을 때
        elif start and not end:
            dt_start = dt_start
            dt_end = dt_start + timedelta(days=30)
        # 둘 다 있을 때는 그대로

        sql = """
        SELECT *
          FROM sensor_data
         WHERE time BETWEEN %s AND %s
        """
        params = [ format_sql_datetime(dt_start), format_sql_datetime(dt_end) ]

        if sensor_pk:
            sql += " AND sensor_pk = %s"
            params.append(sensor_pk)

        sql += " ORDER BY time ASC"

        df = pd.read_sql(sql, conn, params=params)
        return df

    finally:
        conn.close()

