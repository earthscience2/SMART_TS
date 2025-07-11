import logging
import os
from api_db import *

# 로그 설정
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

def log_project_operation(operation: str, project_pk: str, details: str):
    """프로젝트 관련 작업을 로그에 기록"""
    logger = setup_logger('project_logger', 'project.log')
    log_message = f"PROJECT_{operation.upper()} | Project: {project_pk} | Details: {details}"
    logger.info(log_message)

def log_concrete_operation(operation: str, concrete_pk: str, project_pk: str, details: str):
    """콘크리트 관련 작업을 로그에 기록"""
    logger = setup_logger('concrete_logger', 'concrete.log')
    log_message = f"CONCRETE_{operation.upper()} | Concrete: {concrete_pk} | Project: {project_pk} | Details: {details}"
    logger.info(log_message)

def log_sensor_operation(operation: str, sensor_pk: str, concrete_pk: str, details: str):
    """센서 관련 작업을 로그에 기록"""
    logger = setup_logger('sensor_logger', 'sensor.log')
    log_message = f"SENSOR_{operation.upper()} | Sensor: {sensor_pk} | Concrete: {concrete_pk} | Details: {details}"
    logger.info(log_message)

# 로그 기능이 추가된 프로젝트 함수들
def add_project_data_with_log(s_code: str, name: str) -> None:
    """로그 기능이 추가된 프로젝트 추가 함수"""
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
    (project_pk, s_code, name, created_at, updated_at) 
    VALUES 
    (:project_pk, :s_code, :name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """
    params = {
        "project_pk": new_pk,
        "s_code": s_code,
        "name": name
    }
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()
    
    # 로그 기록
    log_project_operation("ADD", new_pk, f"프로젝트 추가 - 이름: {name}, 구조코드: {s_code}")
    return new_pk

def update_project_data_with_log(project_pk: str, **kwargs) -> None:
    """로그 기능이 추가된 프로젝트 업데이트 함수"""
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
    
    # 로그 기록
    update_details = ", ".join([f"{k}: {v}" for k, v in update_fields.items()])
    log_project_operation("UPDATE", project_pk, f"프로젝트 수정 - {update_details}")

def delete_project_data_with_log(project_pk: str) -> None:
    """로그 기능이 추가된 프로젝트 삭제 함수"""
    # 먼저 프로젝트 정보 조회 (로그용)
    project_info = get_project_data(project_pk=project_pk)
    project_name = project_info.iloc[0]['name'] if not project_info.empty else "Unknown"
    
    sql = "DELETE FROM project WHERE project_pk = :project_pk"
    params = {"project_pk": project_pk}
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()
    
    # 로그 기록
    log_project_operation("DELETE", project_pk, f"프로젝트 삭제 - 이름: {project_name}")

# 로그 기능이 추가된 콘크리트 함수들
def add_concrete_data_with_log(project_pk: str, name: str, dims: dict, 
                     con_unit: float, con_t: str, con_a: float, con_p: float, con_d: float,
                     activate: int) -> None:
    """로그 기능이 추가된 콘크리트 추가 함수"""
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
    (concrete_pk, project_pk, name, dims, con_unit, con_t, con_a, con_p, con_d, activate, created_at, updated_at) 
    VALUES 
    (:concrete_pk, :project_pk, :name, :dims, :con_unit, :con_t, :con_a, :con_p, :con_d, :activate, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
        "activate": activate
    }
    
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()
    
    # 로그 기록
    log_concrete_operation("ADD", new_pk, project_pk, f"콘크리트 추가 - 이름: {name}, 활성화: {activate}")
    return new_pk

def update_concrete_data_with_log(concrete_pk: str, **kwargs) -> None:
    """로그 기능이 추가된 콘크리트 업데이트 함수"""
    # con_b, con_n, con_e가 kwargs에 있으면 제거 (더 이상 사용하지 않음)
    kwargs.pop('con_b', None)
    kwargs.pop('con_n', None)
    kwargs.pop('con_e', None)
    
    # 업데이트할 필드와 값만 추출
    update_fields = {k: v for k, v in kwargs.items() if v is not None}
    if not update_fields:
        return None  # 업데이트할 필드가 없으면 종료

    # dims가 있다면 JSON 문자열로 변환
    if 'dims' in update_fields:
        update_fields['dims'] = json.dumps(update_fields['dims'])

    # 콘크리트 정보 조회 (project_pk 확인용)
    concrete_info = get_concrete_data(concrete_pk=concrete_pk)
    project_pk = concrete_info.iloc[0]['project_pk'] if not concrete_info.empty else "Unknown"

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
    
    # 로그 기록
    update_details = ", ".join([f"{k}: {v}" for k, v in update_fields.items()])
    log_concrete_operation("UPDATE", concrete_pk, project_pk, f"콘크리트 수정 - {update_details}")

def delete_concrete_data_with_log(concrete_pk: str) -> dict:
    """로그 기능이 추가된 콘크리트 삭제 함수"""
    # 먼저 콘크리트 정보 조회 (로그용)
    concrete_info = get_concrete_data(concrete_pk=concrete_pk)
    concrete_name = concrete_info.iloc[0]['name'] if not concrete_info.empty else "Unknown"
    project_pk = concrete_info.iloc[0]['project_pk'] if not concrete_info.empty else "Unknown"
    
    with engine.connect() as conn:
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
        log_concrete_operation("DELETE", concrete_pk, project_pk, 
                             f"콘크리트 삭제 - 이름: {concrete_name}, 관련 센서 {sensor_count}개도 함께 삭제")
        
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

# 로그 기능이 추가된 센서 함수들
def add_sensors_data_with_log(concrete_pk: str, device_id: str, channel: int, 
                   d_type: int, dims: dict) -> None:
    """로그 기능이 추가된 센서 추가 함수"""
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
    log_sensor_operation("ADD", new_pk, concrete_pk, 
                        f"센서 추가 - 디바이스: {device_id}, 채널: {channel}, 타입: {d_type}")
    return new_pk

def update_sensors_data_with_log(sensor_pk: str, **kwargs) -> None:
    """로그 기능이 추가된 센서 업데이트 함수"""
    # 업데이트할 필드와 값만 추출
    update_fields = {k: v for k, v in kwargs.items() if v is not None}
    if not update_fields:
        return None  # 업데이트할 필드가 없으면 종료

    # dims가 있다면 JSON 문자열로 변환
    if 'dims' in update_fields:
        update_fields['dims'] = json.dumps(update_fields['dims'])

    # 센서 정보 조회 (concrete_pk 확인용)
    sensor_info = get_sensors_data(sensor_pk=sensor_pk)
    concrete_pk = sensor_info.iloc[0]['concrete_pk'] if not sensor_info.empty else "Unknown"

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
    
    # 로그 기록
    update_details = ", ".join([f"{k}: {v}" for k, v in update_fields.items()])
    log_sensor_operation("UPDATE", sensor_pk, concrete_pk, f"센서 수정 - {update_details}")

def delete_sensors_data_with_log(sensor_pk: str) -> None:
    """로그 기능이 추가된 센서 삭제 함수"""
    # 먼저 센서 정보 조회 (로그용)
    sensor_info = get_sensors_data(sensor_pk=sensor_pk)
    device_id = sensor_info.iloc[0]['device_id'] if not sensor_info.empty else "Unknown"
    concrete_pk = sensor_info.iloc[0]['concrete_pk'] if not sensor_info.empty else "Unknown"
    
    sql = "DELETE FROM sensor WHERE sensor_pk = :sensor_pk"
    params = {"sensor_pk": sensor_pk}
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()
    
    # 로그 기록
    log_sensor_operation("DELETE", sensor_pk, concrete_pk, f"센서 삭제 - 디바이스: {device_id}") 