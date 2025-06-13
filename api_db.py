# app.py
from sqlalchemy import create_engine, text
import pandas as pd
from datetime import datetime, timedelta

# --------------------------------------------------
# 1) SQLAlchemy Engine 생성
DB_URL = (
    f"mysql+pymysql://root:smart001!@localhost:3306/ITS_TS"
    "?charset=utf8mb4"
)
engine = create_engine(DB_URL, pool_pre_ping=True)


# 유틸리티 함수
def parse_ymdh(ts: str) -> datetime:
    return datetime.strptime(ts, '%Y%m%d%H')

def format_sql_datetime(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


# 2) 프로젝트 조회
def get_project_data(project_pk: str = None,
                     user_company_pk: str = None) -> pd.DataFrame:
    sql = "SELECT * FROM project"
    conditions = []
    params = {}

    if project_pk:
        conditions.append("project_pk = :project_pk")
        params["project_pk"] = project_pk
    if user_company_pk:
        conditions.append("user_company_pk = :user_company_pk")
        params["user_company_pk"] = user_company_pk
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    stmt = text(sql)
    return pd.read_sql(stmt, con=engine, params=params)


# 3) 콘크리트 조회
def get_concrete_data(concrete_pk: str = None,
                      project_pk: str = None) -> pd.DataFrame:
    sql = "SELECT * FROM concrete"
    conditions = []
    params = {}

    if concrete_pk:
        conditions.append("concrete_pk = :concrete_pk")
        params["concrete_pk"] = concrete_pk
    if project_pk:
        conditions.append("project_pk = :project_pk")
        params["project_pk"] = project_pk
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    stmt = text(sql)
    return pd.read_sql(stmt, con=engine, params=params)


# 4) 센서 조회
def get_sensors_data(sensor_pk: str = None,
                     concrete_pk: str = None,
                     device_id: str = None,
                     channel: str = None,
                     d_type: str = None) -> pd.DataFrame:
    sql = "SELECT * FROM sensor"
    conditions = []
    params = {}

    if sensor_pk:
        conditions.append("sensor_pk = :sensor_pk")
        params["sensor_pk"] = sensor_pk
    if concrete_pk:
        conditions.append("concrete_pk = :concrete_pk")
        params["concrete_pk"] = concrete_pk
    if device_id:
        conditions.append("device_id = :device_id")
        params["device_id"] = device_id
    if channel:
        conditions.append("channel = :channel")
        params["channel"] = channel
    if d_type:
        conditions.append("d_type = :d_type")
        params["d_type"] = d_type
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    stmt = text(sql)
    return pd.read_sql(stmt, con=engine, params=params)


# 5) 센서 데이터 조회 (시간 범위)
def get_sensor_data(sensor_pk: str = None,
                    start: str  = None,
                    end: str    = None) -> pd.DataFrame:
    # 1) 날짜 계산
    if start:
        dt_start = parse_ymdh(start)
    if end:
        dt_end = parse_ymdh(end)

    if not (start or end):
        df_max = pd.read_sql(text("SELECT MAX(`time`) AS max_time FROM sensor_data"),
                             con=engine)
        latest = df_max.loc[0, "max_time"]
        dt_end = latest if isinstance(latest, datetime) else pd.to_datetime(latest)
        dt_start = dt_end - timedelta(days=30)
    elif not start:
        dt_start = dt_end - timedelta(days=30)
    elif not end:
        dt_end = dt_start + timedelta(days=30)

    # 2) 쿼리 조합
    sql = """
    SELECT *
      FROM sensor_data
     WHERE time BETWEEN :start_time AND :end_time
    """
    params = {
        "start_time": format_sql_datetime(dt_start),
        "end_time":   format_sql_datetime(dt_end),
    }

    if sensor_pk:
        sql += " AND sensor_pk = :sensor_pk"
        params["sensor_pk"] = sensor_pk

    sql += " ORDER BY time ASC"
    stmt = text(sql)

    return pd.read_sql(stmt, con=engine, params=params)


# 테스트
if __name__ == "__main__":
    print(get_project_data())
    print(get_project_data(project_pk="P000001"))
    print(get_concrete_data(concrete_pk="C000001"))
    print(get_sensors_data())
    print(get_sensor_data(sensor_pk="S000001", start="2025061220", end="2025061310"))
