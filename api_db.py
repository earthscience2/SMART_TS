# app.py
from sqlalchemy import create_engine, text
import pandas as pd
from datetime import datetime, timedelta
import json

# --------------------------------------------------
# SQLAlchemy Engine 생성
# --------------------------------------------------
DB_URL = (
    f"mysql+pymysql://root:smart001!@localhost:3306/ITS_TS"
    "?charset=utf8mb4"
)
engine = create_engine(DB_URL, pool_pre_ping=True)

# --------------------------------------------------
# 프로젝트 DB
# --------------------------------------------------

# 프로젝트 조회
def get_project_data(project_pk: str = None,
                     user_company_pk: str = None,
                     activate: int = None) -> pd.DataFrame:
    sql = "SELECT * FROM project"
    conditions = []
    params = {}

    if project_pk:
        conditions.append("project_pk = :project_pk")
        params["project_pk"] = project_pk
    if user_company_pk:
        conditions.append("user_company_pk = :user_company_pk")
        params["user_company_pk"] = user_company_pk
    if activate is not None:
        conditions.append("activate = :activate")
        params["activate"] = activate
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    stmt = text(sql)
    return pd.read_sql(stmt, con=engine, params=params)

# 프로젝트 추가 
def add_project_data(user_company_pk: str, name: str, activate: int = 0) -> None:
    # 1) 현재 가장 큰 project_pk 가져오기
    max_pk_sql = "SELECT MAX(project_pk) as max_pk FROM project"
    max_pk_df = pd.read_sql(text(max_pk_sql), con=engine)
    max_pk = max_pk_df.iloc[0]['max_pk']
    
    # 2) 새로운 project_pk 생성 (P000001 형식)
    if max_pk is None:
        new_pk = 'P000001'
    else:
        num = int(max_pk[1:]) + 1
        new_pk = f'P{num:06d}'
    
    # 3) INSERT 쿼리 실행
    sql = """
    INSERT INTO project 
    (project_pk, user_company_pk, name, activate, created_at, updated_at) 
    VALUES 
    (:project_pk, :user_company_pk, :name, :activate, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """
    params = {
        "project_pk": new_pk,
        "user_company_pk": user_company_pk,
        "name": name,
        "activate": activate
    }
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()

# 프로젝트 업데이트
def update_project_data(project_pk: str, **kwargs) -> None:
    # 업데이트할 필드와 값만 추출
    update_fields = {k: v for k, v in kwargs.items() if v is not None}
    if not update_fields:
        return None  # 업데이트할 필드가 없으면 종료

    # SQL 쿼리 동적 생성
    set_clause = ", ".join([f"{k} = :{k}" for k in update_fields.keys()])
    sql = f"""
    UPDATE project 
    SET {set_clause}, updated_at = CURRENT_TIMESTAMP 
    WHERE project_pk = :project_pk
    """
    
    # 파라미터 설정
    params = {"project_pk": project_pk, **update_fields}

    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()

# 프로젝트 삭제
def delete_project_data(project_pk: str):
    sql = "DELETE FROM project WHERE project_pk = :project_pk"
    params = {"project_pk": project_pk}
    return pd.read_sql(text(sql), con=engine, params=params)


# --------------------------------------------------
# 콘크리트 DB
# --------------------------------------------------

# 콘크리트 조회
def get_concrete_data(concrete_pk: str = None,
                      project_pk: str = None,
                      activate: int = None) -> pd.DataFrame:
    sql = "SELECT * FROM concrete"
    conditions = []
    params = {}

    if concrete_pk:
        conditions.append("concrete_pk = :concrete_pk")
        params["concrete_pk"] = concrete_pk
    if project_pk:
        conditions.append("project_pk = :project_pk")
        params["project_pk"] = project_pk
    if activate is not None:
        conditions.append("activate = :activate")
        params["activate"] = activate
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    stmt = text(sql)
    return pd.read_sql(stmt, con=engine, params=params)

# 콘크리트 추가
def add_concrete_data(project_pk: str, name: str, dims: dict, 
                     con_unit: float, con_e: float, 
                     con_b: float, con_n: float,
                     activate: int) -> None:
    # 1) 현재 가장 큰 concrete_pk 가져오기
    max_pk_sql = "SELECT MAX(concrete_pk) as max_pk FROM concrete"
    max_pk_df = pd.read_sql(text(max_pk_sql), con=engine)
    max_pk = max_pk_df.iloc[0]['max_pk']
    
    # 2) 새로운 concrete_pk 생성 (C000001 형식)
    if max_pk is None:
        new_pk = 'C000001'
    else:
        num = int(max_pk[1:]) + 1
        new_pk = f'C{num:06d}'
    
    # 3) INSERT 쿼리 실행
    sql = """
    INSERT INTO concrete 
    (concrete_pk, project_pk, name, dims, con_unit, con_e, con_b, con_n, activate, created_at, updated_at) 
    VALUES 
    (:concrete_pk, :project_pk, :name, :dims, :con_unit, :con_e, :con_b, :con_n, :activate, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """
    
    params = {
        "concrete_pk": new_pk,
        "project_pk": project_pk,
        "name": name,
        "dims": json.dumps(dims),
        "con_unit": con_unit,
        "con_e": con_e,
        "con_b": con_b,
        "con_n": con_n,
        "activate": activate
    }
    
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()

# 콘크리트 업데이트
def update_concrete_data(concrete_pk: str, **kwargs) -> None:
    # 업데이트할 필드와 값만 추출
    update_fields = {k: v for k, v in kwargs.items() if v is not None}
    if not update_fields:
        return None  # 업데이트할 필드가 없으면 종료

    # dims가 있다면 JSON 문자열로 변환
    if 'dims' in update_fields:
        update_fields['dims'] = json.dumps(update_fields['dims'])

    # SQL 쿼리 동적 생성
    set_clause = ", ".join([f"{k} = :{k}" for k in update_fields.keys()])
    sql = f"""
    UPDATE concrete 
    SET {set_clause}, updated_at = CURRENT_TIMESTAMP 
    WHERE concrete_pk = :concrete_pk
    """
    
    # 파라미터 설정
    params = {"concrete_pk": concrete_pk, **update_fields}
    
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()

# 콘크리트 삭제
def delete_concrete_data(concrete_pk: str):
    sql = "DELETE FROM concrete WHERE concrete_pk = :concrete_pk"
    params = {"concrete_pk": concrete_pk}
    return pd.read_sql(text(sql), con=engine, params=params)


# --------------------------------------------------
# 센서 DB

# 센서 조회
def get_sensors_data(sensor_pk: str = None,
                     concrete_pk: str = None,
                     device_id: str = None,
                     channel: int = None,
                     d_type: int = None) -> pd.DataFrame:
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
    if channel is not None:
        conditions.append("channel = :channel")
        params["channel"] = channel
    if d_type is not None:
        conditions.append("d_type = :d_type")
        params["d_type"] = d_type
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    stmt = text(sql)
    return pd.read_sql(stmt, con=engine, params=params)

# 센서 추가
def add_sensor_data(concrete_pk: str, device_id: str, channel: int, 
                   d_type: int, dims: dict) -> None:
    # 1) 현재 가장 큰 sensor_pk 가져오기
    max_pk_sql = "SELECT MAX(sensor_pk) as max_pk FROM sensor"
    max_pk_df = pd.read_sql(text(max_pk_sql), con=engine)
    max_pk = max_pk_df.iloc[0]['max_pk']
    
    # 2) 새로운 sensor_pk 생성 (S000001 형식)
    if max_pk is None:
        new_pk = 'S000001'
    else:
        num = int(max_pk[1:]) + 1
        new_pk = f'S{num:06d}'
    
    # 3) INSERT 쿼리 실행
    sql = """
    INSERT INTO sensor 
    (sensor_pk, concrete_pk, device_id, channel, d_type, dims, created_at, updated_at) 
    VALUES 
    (:sensor_pk, :concrete_pk, :device_id, :channel, :d_type, :dims, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """
    
    params = {
        "sensor_pk": new_pk,
        "concrete_pk": concrete_pk,
        "device_id": device_id,
        "channel": channel,
        "d_type": d_type,
        "dims": json.dumps(dims)
    }
    
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()

# 센서 업데이트
def update_sensor_data(sensor_pk: str, **kwargs) -> None:
    # 업데이트할 필드와 값만 추출
    update_fields = {k: v for k, v in kwargs.items() if v is not None}
    if not update_fields:
        return None  # 업데이트할 필드가 없으면 종료

    # dims가 있다면 JSON 문자열로 변환
    if 'dims' in update_fields:
        update_fields['dims'] = json.dumps(update_fields['dims'])

    # SQL 쿼리 동적 생성
    set_clause = ", ".join([f"{k} = :{k}" for k in update_fields.keys()])
    sql = f"""
    UPDATE sensor 
    SET {set_clause}, updated_at = CURRENT_TIMESTAMP 
    WHERE sensor_pk = :sensor_pk
    """
    
    # 파라미터 설정
    params = {"sensor_pk": sensor_pk, **update_fields}
    
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()

# 센서 삭제
def delete_sensor_data(sensor_pk: str):
    sql = "DELETE FROM sensor WHERE sensor_pk = :sensor_pk"
    params = {"sensor_pk": sensor_pk}
    return pd.read_sql(text(sql), con=engine, params=params)

# --------------------------------------------------
# 센서 데이터 DB
# --------------------------------------------------

# 센서 데이터 조회
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

# 센서 데이터 조회 (시간 범위)
def get_sensor_data_by_time(sensor_pk: str = None,
                            time: str    = None) -> pd.DataFrame:
    # 1) 날짜 계산
    if not (time):
        return None

    # 2) 쿼리 조합
    sql = """
    SELECT *
      FROM sensor_data
     WHERE time = :time
    """
    params = {
        "time": time,
    }

    if sensor_pk:
        sql += " AND sensor_pk = :sensor_pk"
        params["sensor_pk"] = sensor_pk

    stmt = text(sql)

    return pd.read_sql(stmt, con=engine, params=params)

# --------------------------------------------------
# 유틸리티 함수
# --------------------------------------------------
def parse_ymdh(ts: str) -> datetime:
    return datetime.strptime(ts, '%Y%m%d%H')

def format_sql_datetime(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')



# 테스트
if __name__ == "__main__":
    """
    # 1. 프로젝트 테스트
    print("\n=== 프로젝트 테스트 ===")
    # 프로젝트 추가
    add_project_data(
        user_company_pk="UC000001",
        name="테스트 프로젝트",
        activate=1
    )
    # 프로젝트 조회
    projects = get_project_data(activate=1)
    print("\n활성화된 프로젝트 목록:")
    print(projects)
    
    # 프로젝트 업데이트
    if not projects.empty:
        project_pk = projects.iloc[0]['project_pk']
        update_project_data(
            project_pk=project_pk,
            name="수정된 프로젝트명"
        )
    
    # 2. 콘크리트 테스트
    print("\n=== 콘크리트 테스트 ===")
    # 콘크리트 추가
    add_concrete_data(
        project_pk="P000001",
        name="테스트 콘크리트",
        dims={"nodes": [[0,0,0], [1,0,0], [1,1,0], [0,1,0]], "h": 0.5},
        con_unit=0.1,
        con_e=30000,
        con_b=0.2,
        con_n=1.0e-5,
        activate=1
    )
    
    # 콘크리트 조회
    concretes = get_concrete_data(project_pk="P000001", activate=1)
    print("\n프로젝트의 콘크리트 목록:")
    print(concretes)
    
    # 콘크리트 업데이트
    if not concretes.empty:
        concrete_pk = concretes.iloc[0]['concrete_pk']
        update_concrete_data(
            concrete_pk=concrete_pk,
            name="수정된 콘크리트명",
            con_unit=0.2
        )
    
    # 3. 센서 테스트
    print("\n=== 센서 테스트 ===")
    # 센서 추가
    add_sensor_data(
        concrete_pk="C000001",
        device_id="test_device",
        channel=1,
        d_type=2,
        dims={"nodes": [0.5, 0.5, 0.0]}
    )
    
    # 센서 조회
    sensors = get_sensors_data(concrete_pk="C000001")
    print("\n콘크리트의 센서 목록:")
    print(sensors)
    
    # 센서 업데이트
    if not sensors.empty:
        sensor_pk = sensors.iloc[0]['sensor_pk']
        update_sensor_data(
            sensor_pk=sensor_pk,
            channel=2,
            dims={"nodes": [0.6, 0.6, 0.0]}
        )
    
    # 4. 센서 데이터 테스트
    print("\n=== 센서 데이터 테스트 ===")
    # 센서 데이터 조회 (시간 범위)
    sensor_data = get_sensor_data(
        sensor_pk="S000001",
        start="2025061300",
        end="2025061400"
    )
    print("\n센서 데이터 (시간 범위):")
    print(sensor_data)
    
    # 센서 데이터 조회 (특정 시간)
    sensor_data_time = get_sensor_data_by_time(
        sensor_pk="S000001",
        time="2025-06-13 12:00:00"
    )
    print("\n센서 데이터 (특정 시간):")
    print(sensor_data_time)
    
    # 5. 삭제 테스트 (실제 삭제는 주석 처리)
    """
    print("\n=== 삭제 테스트 ===")
    projects = get_project_data()
    print(projects)

    concretes = get_concrete_data()
    print(concretes)

    sensors = get_sensors_data()
    print(sensors)
    
    """
    # 프로젝트 삭제
    delete_project_data("P000001")
    
    # 콘크리트 삭제
    delete_concrete_data("C000001")
    
    # 센서 삭제
    delete_sensor_data("S000001")
    """