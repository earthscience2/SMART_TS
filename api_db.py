# app.py
from sqlalchemy import create_engine, text
import pandas as pd
from datetime import datetime, timedelta
import json
from pathlib import Path
import configparser
import bcrypt
import logging
import os

# --------------------------------------------------
# 로그 설정
# --------------------------------------------------

def setup_logger(log_name: str, log_file: str):
    """로그를 위한 로거 설정"""
    log_dir = "log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger(log_name)
    logger.setLevel(logging.INFO)
    
    # 기존 핸들러 제거 (중복 방지)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 파일 핸들러 설정
    file_handler = logging.FileHandler(os.path.join(log_dir, log_file), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 포맷터 설정
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    return logger



def log_concrete_operation(operation: str, concrete_pk: str, structure_id: str, details: str):
    """콘크리트 관련 작업을 로그에 기록"""
    logger = setup_logger('concrete_logger', 'concrete.log')
    log_message = f"CONCRETE_{operation.upper()} | Concrete: {concrete_pk} | Structure: {structure_id} | Details: {details}"
    logger.info(log_message)

def log_sensor_operation(operation: str, sensor_pk: str, concrete_pk: str, details: str):
    """센서 관련 작업을 로그에 기록"""
    logger = setup_logger('sensor_logger', 'sensor.log')
    log_message = f"SENSOR_{operation.upper()} | Sensor: {sensor_pk} | Concrete: {concrete_pk} | Details: {details}"
    logger.info(log_message)

# --------------------------------------------------
# SQLAlchemy Engine 생성
# --------------------------------------------------
DB_URL = (
    f"mysql+pymysql://root:smart001!@localhost:3306/ITS_TS"
    "?charset=utf8mb4"
)
engine = create_engine(DB_URL, pool_pre_ping=True)

# --------------------------------------------------
# ITS1/ITS2 접속 설정 로딩 (user/secret.ini)
# --------------------------------------------------

_SECRET_INI = Path(__file__).resolve().parent / "user" / "secret.ini"
_its_configs = {}
if _SECRET_INI.exists():
    _parser = configparser.ConfigParser()
    _parser.read(_SECRET_INI, encoding="utf-8")
    for sec in _parser.sections():
        if sec.endswith("_DB"):
            _its_configs[sec.replace("_DB", "")] = {
                "host": _parser[sec].get("host"),
                "port": _parser[sec].getint("port", 3306),
                "db": _parser[sec].get("db_name"),
                "user": _parser[sec].get("user"),
                "pwd": _parser[sec].get("password"),
            }


def _get_its_engine(its_num: int):
    """ITS 번호(1/2)에 해당하는 SQLAlchemy Engine 반환."""
    key = f"ITS{its_num}"
    cfg = _its_configs.get(key)
    if not cfg:
        raise ValueError(f"secret.ini 에 {key}_DB 설정이 없습니다.")
    uri = (
        f"mysql+pymysql://{cfg['user']}:{cfg['pwd']}@{cfg['host']}:{cfg['port']}/{cfg['db']}"
        "?charset=utf8mb4"
    )
    return create_engine(uri, pool_pre_ping=True)


# --------------------------------------------------
# 사용자 인증 & 프로젝트/구조 접근 목록
# --------------------------------------------------


def authenticate_user(user_id: str, password: str, its_num: int = 1):
    """주어진 ITS DB 에서 사용자 인증 후 (grade, 허용 프로젝트/구조) 반환.

    Returns
    -------
    dict with keys:
        result: "Success" | "Fail"
        grade: str | None
        auth: list[str]  # 허용 projectid / stid 리스트 (grade==AD 면 [])
        msg:   str  (Fail 시 이유)
    """
    try:
        eng = _get_its_engine(its_num)
    except Exception as exc:
        return {"result": "Fail", "msg": f"DB 연결 실패: {exc}", "grade": None, "auth": []}

    try:
        query = text("SELECT userid, userpw, grade FROM tb_user WHERE userid = :uid LIMIT 1")
        df_user = pd.read_sql(query, eng, params={"uid": user_id})
        if df_user.empty:
            return {"result": "Fail", "msg": "존재하지 않는 아이디", "grade": None, "auth": []}

        stored_hash = df_user.iloc[0]["userpw"].encode("utf-8")
        if not bcrypt.checkpw(password.encode("utf-8"), stored_hash):
            return {"result": "Fail", "msg": "비밀번호 불일치", "grade": None, "auth": []}

        grade = df_user.iloc[0]["grade"]

        # grade 가 AD 면 전체 권한
        if grade == "AD":
            auth_list: list[str] = []
        else:
            df_auth = pd.read_sql(
                text("SELECT id FROM tb_sensor_auth_mapping WHERE userid = :uid"),
                eng,
                params={"uid": user_id},
            )
            auth_list = df_auth["id"].tolist()

        return {"result": "Success", "msg": "", "grade": grade, "auth": auth_list}
    except Exception as exc:
        return {"result": "Fail", "msg": str(exc), "grade": None, "auth": []}


def get_project_structure_list(its_num: int, allow_list: list[str] | None, grade: str):
    """tb_project, tb_structure 조인해 접근 가능한 프로젝트/구조 목록 반환."""
    try:
        eng = _get_its_engine(its_num)
    except Exception as exc:
        raise RuntimeError(f"DB 연결 실패: {exc}") from exc

    if grade == "AD" or not allow_list:
        condition = ""
        params = {}
    else:
        placeholders = ", ".join([":p" + str(i) for i, _ in enumerate(allow_list)])
        condition = f"WHERE tp.projectid IN ({placeholders})"
        params = {f"p{i}": v for i, v in enumerate(allow_list)}

    sql = f"""
        SELECT tp.projectid, tp.projectname, s.stid, s.stname, s.staddr, tp.regdate, tp.closedate
        FROM tb_structure s
        JOIN tb_group g ON s.groupid = g.groupid
        JOIN tb_project tp ON g.projectid = tp.projectid
        {condition}
        ORDER BY tp.projectid, s.stid
    """

    df = pd.read_sql(text(sql), _get_its_engine(its_num), params=params)
    return df




# --------------------------------------------------
# 콘크리트 DB
# --------------------------------------------------

# 콘크리트 조회
def get_concrete_data(concrete_pk: str = None,
                      structure_id: str = None,
                      activate: int = None) -> pd.DataFrame:
    sql = "SELECT * FROM concrete"
    conditions = []
    params = {}

    if concrete_pk:
        conditions.append("concrete_pk = :concrete_pk")
        params["concrete_pk"] = concrete_pk
    if structure_id:
        conditions.append("structure_id = :structure_id")
        params["structure_id"] = structure_id
    if activate is not None:
        conditions.append("activate = :activate")
        params["activate"] = activate
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    stmt = text(sql)
    return pd.read_sql(stmt, con=engine, params=params)

# 콘크리트 추가
def add_concrete_data(project_pk: str, name: str, dims: dict, 
                     con_unit: float, con_t: str, con_a: float, con_p: float, con_d: float,
                     activate: int, ceb_fib: list = None) -> None:
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
    (concrete_pk, project_pk, name, dims, con_unit, con_t, con_a, con_p, con_d, `CEB-FIB`, activate, created_at, updated_at) 
    VALUES 
    (:concrete_pk, :project_pk, :name, :dims, :con_unit, :con_t, :con_a, :con_p, :con_d, :ceb_fib, :activate, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """
    
    params = {
        "concrete_pk": new_pk,
        "project_pk": project_pk,
        "name": name,
        "dims": json.dumps(dims),
        "con_unit": con_unit,
        "con_t": con_t,
        "con_a": con_a,
        "con_p": con_p,
        "con_d": con_d,
        "ceb_fib": json.dumps(ceb_fib) if ceb_fib else None,
        "activate": activate
    }
    
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()
        
    # 로그 기록
    log_concrete_operation("CREATE", new_pk, project_pk, f"name: {name}, con_unit: {con_unit}, activate: {activate}")

# 콘크리트 업데이트
def update_concrete_data(concrete_pk: str, **kwargs) -> None:
    # con_b, con_n, con_e가 kwargs에 있으면 제거 (더 이상 사용하지 않음)
    kwargs.pop('con_b', None)
    kwargs.pop('con_n', None)
    kwargs.pop('con_e', None)
    
    # con_ceb_fib를 CEB-FIB로 변경
    if 'con_ceb_fib' in kwargs:
        kwargs['CEB-FIB'] = kwargs.pop('con_ceb_fib')
    
    # 업데이트할 필드와 값만 추출
    update_fields = {k: v for k, v in kwargs.items() if v is not None}
    if not update_fields:
        return None  # 업데이트할 필드가 없으면 종료

    # dims가 있다면 JSON 문자열로 변환
    if 'dims' in update_fields:
        update_fields['dims'] = json.dumps(update_fields['dims'])
    
    # CEB-FIB가 있다면 JSON 문자열로 변환
    if 'CEB-FIB' in update_fields:
        update_fields['CEB-FIB'] = json.dumps(update_fields['CEB-FIB'])

    # 하이픈이 포함된 컬럼명을 백틱으로 감싸기
    set_clause_parts = []
    for k in update_fields.keys():
        if '-' in k:
            set_clause_parts.append(f"`{k}` = :{k}")
        else:
            set_clause_parts.append(f"{k} = :{k}")
    
    set_clause = ", ".join(set_clause_parts)
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
        
    # 로그 기록 - 구조 ID를 찾기 위해 추가 조회
    structure_query = "SELECT structure_id FROM concrete WHERE concrete_pk = :concrete_pk"
    structure_df = pd.read_sql(text(structure_query), con=engine, params={"concrete_pk": concrete_pk})
    structure_id = structure_df.iloc[0]['structure_id'] if not structure_df.empty else "Unknown"
    update_details = ", ".join([f"{k}: {v}" for k, v in update_fields.items()])
    log_concrete_operation("UPDATE", concrete_pk, structure_id, f"Updated fields: {update_details}")

# 콘크리트 삭제 (관련 센서도 함께 삭제)
def delete_concrete_data(concrete_pk: str) -> dict:
    """
    콘크리트 삭제 함수 - 관련 센서도 함께 삭제
    Returns:
        dict: {"success": bool, "message": str, "deleted_sensors": int}
    """
    with engine.connect() as conn:
        # 0) 삭제 전에 구조 ID 조회
        structure_query = "SELECT structure_id FROM concrete WHERE concrete_pk = :concrete_pk"
        result = conn.execute(text(structure_query), {"concrete_pk": concrete_pk})
        structure_row = result.fetchone()
        structure_id = structure_row[0] if structure_row else "Unknown"
        
        # 1) 관련된 센서 개수 확인
        sensor_check_sql = "SELECT COUNT(*) as count FROM sensor WHERE concrete_pk = :concrete_pk"
        result = conn.execute(text(sensor_check_sql), {"concrete_pk": concrete_pk})
        sensor_count = result.fetchone()[0]
        
        # 2) 관련 센서 먼저 삭제
        if sensor_count > 0:
            delete_sensors_sql = "DELETE FROM sensor WHERE concrete_pk = :concrete_pk"
            conn.execute(text(delete_sensors_sql), {"concrete_pk": concrete_pk})
        
        # 3) 콘크리트 삭제
        delete_concrete_sql = "DELETE FROM concrete WHERE concrete_pk = :concrete_pk"
        conn.execute(text(delete_concrete_sql), {"concrete_pk": concrete_pk})
        
        conn.commit()
        
        # 로그 기록
        log_concrete_operation("DELETE", concrete_pk, structure_id, f"Concrete deleted with {sensor_count} related sensors")
        
        if sensor_count > 0:
            return {
                "success": True,
                "message": f"콘크리트와 관련 센서 {sensor_count}개가 삭제되었습니다.",
                "deleted_sensors": sensor_count
            }
        else:
            return {
                "success": True,
                "message": "콘크리트가 삭제되었습니다.",
                "deleted_sensors": 0
            }




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
def add_sensors_data(concrete_pk: str, device_id: str, channel: int, 
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
        
    # 로그 기록
    log_sensor_operation("CREATE", new_pk, concrete_pk, f"device_id: {device_id}, channel: {channel}, d_type: {d_type}")

# 센서 업데이트
def update_sensors_data(sensor_pk: str, **kwargs) -> None:
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
        
    # 로그 기록 - 콘크리트 PK를 찾기 위해 추가 조회
    concrete_query = "SELECT concrete_pk FROM sensor WHERE sensor_pk = :sensor_pk"
    concrete_df = pd.read_sql(text(concrete_query), con=engine, params={"sensor_pk": sensor_pk})
    concrete_pk = concrete_df.iloc[0]['concrete_pk'] if not concrete_df.empty else "Unknown"
    update_details = ", ".join([f"{k}: {v}" for k, v in update_fields.items()])
    log_sensor_operation("UPDATE", sensor_pk, concrete_pk, f"Updated fields: {update_details}")

# 센서 삭제
def delete_sensors_data(sensor_pk: str) -> None:
    # 삭제 전에 콘크리트 PK 조회
    concrete_query = "SELECT concrete_pk FROM sensor WHERE sensor_pk = :sensor_pk"
    concrete_df = pd.read_sql(text(concrete_query), con=engine, params={"sensor_pk": sensor_pk})
    concrete_pk = concrete_df.iloc[0]['concrete_pk'] if not concrete_df.empty else "Unknown"
    
    sql = "DELETE FROM sensor WHERE sensor_pk = :sensor_pk"
    params = {"sensor_pk": sensor_pk}
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()
        
    # 로그 기록
    log_sensor_operation("DELETE", sensor_pk, concrete_pk, "Sensor deleted")

# --------------------------------------------------
# 센서 데이터 DB
# --------------------------------------------------

# 센서 데이터 조회
def get_sensor_data(device_id: str = None,
                   channel: str = None,
                   start: str = None,
                   end: str = None,
                   use_its: bool = False,
                   its_num: int = 1) -> pd.DataFrame:
    """센서 데이터를 조회합니다. ITS 데이터베이스 또는 로컬 데이터베이스에서 선택 가능합니다.
    
    Args:
        device_id: 디바이스 ID
        channel: 채널 번호
        start: 시작 시간 (YYYYMMDDHH 형식)
        end: 종료 시간 (YYYYMMDDHH 형식)
        use_its: ITS 데이터베이스에서 직접 조회할지 여부
        its_num: ITS 번호 (1 또는 2)
    
    Returns:
        센서 데이터 DataFrame
    """
    if use_its:
        # ITS 데이터베이스에서 직접 조회
        if start and end:
            start_dt = parse_ymdh(start)
            end_dt = parse_ymdh(end)
            hours = int((end_dt - start_dt).total_seconds() / 3600)
        else:
            hours = 24  # 기본 24시간
        
        return get_its_sensor_data(device_id, channel, its_num, hours)
    else:
        # 로컬 데이터베이스에서 조회 (기존 방식)
        # 1) 날짜 계산
        if start:
            start_dt = parse_ymdh(start)
        else:
            start_dt = datetime.now() - timedelta(days=30)
        
        if end:
            end_dt = parse_ymdh(end)
        else:
            end_dt = datetime.now()

        # 2) SQL 쿼리 생성
        sql = "SELECT * FROM sensor_data"
        conditions = []
        params = {}

        if device_id:
            conditions.append("device_id = :device_id")
            params["device_id"] = device_id
        if channel:
            conditions.append("channel = :channel")
            params["channel"] = channel

        # 날짜 조건 추가
        conditions.append("time >= :start_dt")
        conditions.append("time <= :end_dt")
        params["start_dt"] = format_sql_datetime(start_dt)
        params["end_dt"] = format_sql_datetime(end_dt)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY time ASC"

        stmt = text(sql)
        return pd.read_sql(stmt, con=engine, params=params)

# 특정 시간의 센서 데이터 조회
def get_sensor_data_by_time(device_id: str = None,
                          channel: str = None,
                          time: str = None) -> pd.DataFrame:
    # 1) 날짜 계산
    if time:
        time_dt = datetime.strptime(time, '%Y-%m-%d %H:%M:%S')
    else:
        time_dt = datetime.now()

    # 2) SQL 쿼리 생성
    sql = "SELECT * FROM sensor_data"
    conditions = []
    params = {}

    if device_id:
        conditions.append("device_id = :device_id")
        params["device_id"] = device_id
    if channel:
        conditions.append("channel = :channel")
        params["channel"] = channel

    # 시간 조건 추가
    conditions.append("time = :time_dt")
    params["time_dt"] = format_sql_datetime(time_dt)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    stmt = text(sql)
    return pd.read_sql(stmt, con=engine, params=params)

# --------------------------------------------------
# 유틸리티 함수
# --------------------------------------------------
def parse_ymdh(ts: str) -> datetime:
    return datetime.strptime(ts, '%Y%m%d%H')

def format_sql_datetime(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def get_latest_sensor_data_time(device_id: str, channel: str) -> dict:
    """센서의 가장 최근 데이터 시간을 조회합니다.
    
    Args:
        device_id: 디바이스 ID
        channel: 채널 번호
    
    Returns:
        dict: {'status': 'success'|'fail', 'time': datetime|None, 'msg': str}
    """
    try:
        # 로컬 센서 데이터 DB에서 조회 (SQLite)
        query = text("""
            SELECT time 
            FROM sensor_data 
            WHERE device_id = :device_id AND channel = :channel 
            ORDER BY time DESC 
            LIMIT 1
        """)
        
        df = pd.read_sql(query, engine, params={"device_id": device_id, "channel": channel})
        
        if df.empty:
            return {"status": "fail", "time": None, "msg": "데이터 없음"}
        
        latest_time = pd.to_datetime(df.iloc[0]['time'])
        return {"status": "success", "time": latest_time, "msg": ""}
        
    except Exception as e:
        print(f"Error getting latest sensor data time for {device_id}/{channel}: {e}")
        return {"status": "fail", "time": None, "msg": str(e)}


def get_all_sensor_structures(its_num: int = 1) -> pd.DataFrame:
    """P_000078 프로젝트에서 모든 센서 구조 리스트를 조회합니다.
    
    Args:
        its_num: ITS 번호 (1 또는 2)
    
    Returns:
        센서 구조 리스트 DataFrame (구조 단위로 그룹화)
    """
    try:
        eng = _get_its_engine(its_num)
        
        # P_000078 프로젝트에서 모든 구조 리스트 조회 (구조 단위로 그룹화)
        structure_query = text("""
            SELECT DISTINCT st.stid AS structure_id, st.stname AS structure_name,
                   COUNT(DISTINCT s.deviceid) AS device_count,
                   COUNT(s.channel) AS sensor_count
            FROM tb_structure st
            JOIN tb_group g ON g.groupid = st.groupid 
            JOIN tb_project p ON p.projectid = g.projectid 
            JOIN tb_device d ON d.stid = st.stid
            JOIN tb_sensor s ON s.deviceid = d.deviceid
            WHERE p.projectid = 'P_000078'
                AND d.manageyn = 'Y' AND s.manageyn = 'Y' 
            GROUP BY st.stid, st.stname
            ORDER BY st.stid
        """)
        
        df_structures = pd.read_sql(structure_query, eng)
        return df_structures
        
    except Exception as e:
        print(f"Error getting all sensor structures: {e}")
        return pd.DataFrame()


def get_sensor_list_for_structure(s_code: str, its_num: int = 1) -> pd.DataFrame:
    """P_000078 프로젝트에서 특정 구조ID의 센서 리스트를 조회합니다.
    
    Args:
        s_code: 구조 ID (S_000xxx 형식)
        its_num: ITS 번호 (1 또는 2)
    
    Returns:
        센서 리스트 DataFrame
    """
    try:
        eng = _get_its_engine(its_num)
        
        # P_000078 프로젝트에서 해당 구조의 센서 리스트 조회
        sensor_query = text("""
            SELECT s.deviceid, CAST(IFNULL(s.channel,1) AS CHAR) AS channel,
                   d.devicetype AS device_type, tddt.data_type,
                   IF(tdc.modelname IS NOT NULL,'Y','N') AS is3axis
            FROM tb_sensor s 
            JOIN tb_device d ON d.deviceid = s.deviceid 
            JOIN tb_structure st ON st.stid = d.stid 
            JOIN tb_group g ON g.groupid = st.groupid 
            JOIN tb_project p ON p.projectid = g.projectid 
            LEFT JOIN tb_device_data_type tddt ON d.devicetype = tddt.device_type 
            LEFT JOIN tb_device_catalog tdc ON tdc.idx = d.modelidx 
                AND tdc.modelname IN ('SSC-320HR(2.0g)','SSC-320HR(5.0g)','SSC-320(3.0g)') 
            WHERE p.projectid = 'P_000078' AND st.stid = :s_code
                AND d.manageyn = 'Y' AND s.manageyn = 'Y' 
            ORDER BY s.deviceid, s.channel
        """)
        
        df_sensors = pd.read_sql(sensor_query, eng, params={"s_code": s_code})
        return df_sensors
        
    except Exception as e:
        print(f"Error getting sensor list for {s_code}: {e}")
        return pd.DataFrame()


def get_sensor_list_for_project(project_id: str, its_num: int = 1) -> pd.DataFrame:
    """특정 프로젝트의 모든 센서 리스트를 조회합니다.
    
    Args:
        project_id: 프로젝트 ID (P_000xxx 형식)
        its_num: ITS 번호 (1 또는 2)
    
    Returns:
        센서 리스트 DataFrame
    """
    try:
        eng = _get_its_engine(its_num)
        
        # 해당 프로젝트의 모든 센서 리스트 조회
        sensor_query = text("""
            SELECT s.deviceid, CAST(IFNULL(s.channel,1) AS CHAR) AS channel,
                   d.devicetype AS device_type, tddt.data_type,
                   IF(tdc.modelname IS NOT NULL,'Y','N') AS is3axis,
                   st.stid AS structure_id, st.stname AS structure_name
            FROM tb_sensor s 
            JOIN tb_device d ON d.deviceid = s.deviceid 
            JOIN tb_structure st ON st.stid = d.stid 
            JOIN tb_group g ON g.groupid = st.groupid 
            JOIN tb_project p ON p.projectid = g.projectid 
            LEFT JOIN tb_device_data_type tddt ON d.devicetype = tddt.device_type 
            LEFT JOIN tb_device_catalog tdc ON tdc.idx = d.modelidx 
                AND tdc.modelname IN ('SSC-320HR(2.0g)','SSC-320HR(5.0g)','SSC-320(3.0g)') 
            WHERE p.projectid = :project_id
                AND d.manageyn = 'Y' AND s.manageyn = 'Y' 
            ORDER BY st.stid, s.deviceid, s.channel
        """)
        
        df_sensors = pd.read_sql(sensor_query, eng, params={"project_id": project_id})
        return df_sensors
        
    except Exception as e:
        print(f"Error getting sensor list for project {project_id}: {e}")
        return pd.DataFrame()


def get_accessible_projects(user_id: str, its_num: int = 1):
    """사용자가 접근 가능한 프로젝트 목록을 반환합니다.
    
    Args:
        user_id: 사용자 ID
        its_num: ITS 번호 (1 또는 2)
    
    Returns:
        dict: {
            'result': 'Success' | 'Fail',
            'projects': DataFrame 또는 None,
            'msg': 오류 메시지
        }
    """
    try:
        eng = _get_its_engine(its_num)
    except Exception as exc:
        return {"result": "Fail", "projects": None, "msg": f"DB 연결 실패: {exc}"}

    try:
        # 사용자 정보 조회
        user_query = text("SELECT userid, grade FROM tb_user WHERE userid = :uid LIMIT 1")
        df_user = pd.read_sql(user_query, eng, params={"uid": user_id})
        
        if df_user.empty:
            return {"result": "Fail", "projects": None, "msg": "존재하지 않는 사용자"}

        grade = df_user.iloc[0]["grade"]
        
        # 관리자(AD)인 경우 모든 프로젝트 반환
        if grade == "AD":
            project_query = text("""
                SELECT DISTINCT tp.projectid, tp.projectname, tp.regdate, tp.closedate
                FROM tb_project tp
                ORDER BY tp.projectid
            """)
            df_projects = pd.read_sql(project_query, eng)
        else:
            # 일반 사용자의 경우 권한이 있는 프로젝트만 반환
            auth_query = text("SELECT id FROM tb_sensor_auth_mapping WHERE userid = :uid")
            df_auth = pd.read_sql(auth_query, eng, params={"uid": user_id})
            
            if df_auth.empty:
                return {"result": "Fail", "projects": None, "msg": "접근 권한이 없습니다"}
            
            auth_list = df_auth["id"].tolist()
            
            # 프로젝트 ID 추출 (권한 목록에서)
            project_ids = [auth_id for auth_id in auth_list if auth_id.startswith('P_')]
            
            if not project_ids:
                return {"result": "Fail", "projects": None, "msg": "접근 가능한 프로젝트가 없습니다"}
            
            # 권한이 있는 프로젝트만 조회
            placeholders = ", ".join([f":p{i}" for i in range(len(project_ids))])
            project_query = text(f"""
                SELECT DISTINCT tp.projectid, tp.projectname, tp.regdate, tp.closedate
                FROM tb_project tp
                WHERE tp.projectid IN ({placeholders})
                ORDER BY tp.projectid
            """)
            params = {f"p{i}": pid for i, pid in enumerate(project_ids)}
            df_projects = pd.read_sql(project_query, eng, params=params)

        return {"result": "Success", "projects": df_projects, "msg": ""}
        
    except Exception as exc:
        return {"result": "Fail", "projects": None, "msg": f"오류 발생: {str(exc)}"}




def get_user_data(its_num: int = 1) -> pd.DataFrame:
    """ITS 데이터베이스에서 사용자 정보를 조회합니다.
    
    Args:
        its_num: ITS 번호 (기본값: 1)
    
    Returns:
        사용자 정보 DataFrame
    """
    try:
        eng = _get_its_engine(its_num)
        query = text("""
            SELECT 
                userid as user_id,
                grade as authority,
                authstartdate as authority_start_date,
                authenddate as authority_end_date
            FROM tb_user 
            ORDER BY userid
        """)
        df = pd.read_sql(query, eng)
        
        # 날짜 컬럼을 문자열로 변환
        for col in ['authority_start_date', 'authority_end_date']:
            if col in df.columns:
                df[col] = df[col].astype(str)
                df[col] = df[col].replace('NaT', None)
                df[col] = df[col].replace('nan', None)
        
        return df
    except Exception as e:
        print(f"사용자 데이터 조회 오류: {e}")
        return pd.DataFrame()

# ITS 센서 데이터 수집 및 조회 함수들
def collect_its_sensor_data(device_id: str, channel: str, its_num: int = 1, hours: int = 24) -> dict:
    """ITS 데이터베이스에서 센서 데이터를 수집하여 로컬 DB에 저장합니다.
    
    Args:
        device_id: 디바이스 ID
        channel: 채널 번호
        its_num: ITS 번호 (1 또는 2)
        hours: 수집할 시간 범위 (시간 단위)
    
    Returns:
        dict: {'status': 'success'|'fail', 'count': int, 'msg': str}
    """
    try:
        # ITS 데이터베이스 연결
        eng = _get_its_engine(its_num)
        
        # 수집할 시간 범위 계산
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        # ITS 센서 데이터 조회 쿼리
        query = text("""
            SELECT 
                :device_id AS device_id,
                :channel AS channel,
                timestamp AS time,
                temperature,
                humidity,
                sv,
                x_accel, y_accel, z_accel,
                x_gyro, y_gyro, z_gyro
            FROM tb_sensor_data 
            WHERE deviceid = :device_id 
                AND channel = :channel 
                AND timestamp BETWEEN :start_time AND :end_time
            ORDER BY timestamp ASC
        """)
        
        params = {
            "device_id": device_id,
            "channel": channel,
            "start_time": start_time,
            "end_time": end_time
        }
        
        df = pd.read_sql(query, eng, params=params)
        
        if df.empty:
            return {"status": "fail", "count": 0, "msg": "수집할 데이터가 없습니다"}
        
        # 기존 데이터 삭제 (중복 방지)
        delete_query = text("""
            DELETE FROM sensor_data 
            WHERE device_id = :device_id 
                AND channel = :channel 
                AND time BETWEEN :start_time AND :end_time
        """)
        
        engine.execute(delete_query, params=params)
        
        # 새 데이터 삽입
        df.to_sql('sensor_data', engine, if_exists='append', index=False)
        
        return {
            "status": "success", 
            "count": len(df), 
            "msg": f"{len(df)}개의 데이터를 수집했습니다"
        }
        
    except Exception as e:
        print(f"Error collecting ITS sensor data for {device_id}/{channel}: {e}")
        return {"status": "fail", "count": 0, "msg": str(e)}

def get_its_sensor_data(device_id: str, channel: str, its_num: int = 1, hours: int = 24) -> pd.DataFrame:
    """ITS 데이터베이스에서 직접 센서 데이터를 조회합니다.
    
    Args:
        device_id: 디바이스 ID
        channel: 채널 번호
        its_num: ITS 번호 (1 또는 2)
        hours: 조회할 시간 범위 (시간 단위)
    
    Returns:
        센서 데이터 DataFrame
    """
    try:
        # ITS 데이터베이스 연결
        eng = _get_its_engine(its_num)
        
        # 조회할 시간 범위 계산
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        # ITS 센서 데이터 조회 쿼리
        query = text("""
            SELECT 
                deviceid AS device_id,
                channel,
                timestamp AS time,
                temperature,
                humidity,
                sv,
                x_accel, y_accel, z_accel,
                x_gyro, y_gyro, z_gyro
            FROM tb_sensor_data 
            WHERE deviceid = :device_id 
                AND channel = :channel 
                AND timestamp BETWEEN :start_time AND :end_time
            ORDER BY timestamp ASC
        """)
        
        params = {
            "device_id": device_id,
            "channel": channel,
            "start_time": start_time,
            "end_time": end_time
        }
        
        df = pd.read_sql(query, eng, params=params)
        
        if not df.empty:
            # 시간 컬럼을 datetime으로 변환
            df['time'] = pd.to_datetime(df['time'])
        
        return df
        
    except Exception as e:
        print(f"Error getting ITS sensor data for {device_id}/{channel}: {e}")
        return pd.DataFrame()

def collect_all_sensors_data(its_num: int = 1, hours: int = 24) -> dict:
    """모든 센서의 데이터를 일괄 수집합니다.
    
    Args:
        its_num: ITS 번호 (1 또는 2)
        hours: 수집할 시간 범위 (시간 단위)
    
    Returns:
        dict: {'status': 'success'|'fail', 'total_count': int, 'sensors': list, 'msg': str}
    """
    try:
        # 모든 구조의 센서 목록 가져오기
        structures_df = get_all_sensor_structures(its_num)
        
        if structures_df.empty:
            return {"status": "fail", "total_count": 0, "sensors": [], "msg": "센서 구조를 찾을 수 없습니다"}
        
        total_count = 0
        collected_sensors = []
        
        for _, structure in structures_df.iterrows():
            structure_id = structure['structure_id']
            
            # 해당 구조의 센서 목록 가져오기
            sensors_df = get_sensor_list_for_structure(structure_id, its_num)
            
            for _, sensor in sensors_df.iterrows():
                device_id = sensor["deviceid"]
                channel = sensor["channel"]
                
                # 센서 데이터 수집
                result = collect_its_sensor_data(device_id, channel, its_num, hours)
                
                if result["status"] == "success":
                    total_count += result["count"]
                    collected_sensors.append({
                        "device_id": device_id,
                        "channel": channel,
                        "structure_id": structure_id,
                        "count": result["count"]
                    })
        
        return {
            "status": "success",
            "total_count": total_count,
            "sensors": collected_sensors,
            "msg": f"총 {total_count}개의 데이터를 {len(collected_sensors)}개 센서에서 수집했습니다"
        }
        
    except Exception as e:
        print(f"Error collecting all sensors data: {e}")
        return {"status": "fail", "total_count": 0, "sensors": [], "msg": str(e)}

 
    