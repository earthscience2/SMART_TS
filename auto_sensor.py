import sys
import os

import pymysql
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import pandas as pd
import threading
import time
import logging
from ITS_CLI import config, tcp_client

# 0) 로거 설정
LOG_PATH = 'log/auto_sensor.log'
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 센서 데이터 조회 및 추출
def export_sensor_data(deviceid, channel, sd_start=None):
    # --- 1) ITS 설정 로드 ---
    try:
        config.config_load()
        if not hasattr(config, 'SERVER_IP') or not config.SERVER_IP:
            logger.error("ITS 서버 설정이 누락되었습니다")
            return None
    except Exception as e:
        logger.error(f"ITS 설정 로드 실패: {e}")
        # config.ini 파일 존재 확인
        config_path = 'config.ini'
        logger.error(f"config.ini 경로: {config_path}, 존재: {os.path.exists(config_path)}")
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                logger.error(f"config.ini 내용:\n{f.read()}")
        return None
    
    # --- 2) ITS 클라이언트 연결 ---
    user_id = 'cbk4689'
    user_pass = 'qudrhks7460!@'
    
    ITS_CLIENT = tcp_client.TCPClient(
        config.SERVER_IP, config.SERVER_PORT, config.ITS_NUM, config.certfile
    )
    
    if not ITS_CLIENT:
        logger.error("ITS 클라이언트 생성 실패")
        return None
    
    t = threading.Thread(target=ITS_CLIENT.receive_messages)
    t.daemon = True
    t.start()
    time.sleep(1)
    
    # --- 3) ITS 로그인 ---
    ITS_CLIENT.set_user_password(user_id, user_pass)
    res = ITS_CLIENT.message('login')
    
    if not res:
        logger.error("ITS 로그인 응답이 없습니다")
        return None
        
    if res.get('result') != 'Success':
        login_msg = res.get('msg', '알 수 없는 오류')
        logger.error(f"ITS 로그인 실패: {login_msg}")
        return None
        
    logger.info("ITS 로그인 성공")

    # --- 4) 센서 데이터 조회 ---
    result = ITS_CLIENT.message_getdata(
        'query_device_channel_data',
        start_date=sd_start,
        end_date=None,
        projectid=None,
        structureid=None,
        deviceid=deviceid,
        channel=channel
    )

    if not result:
        logger.warning(f"{deviceid}/{channel} 조회 결과가 없습니다")
        return pd.DataFrame()  # 빈 DataFrame 반환
    
    if not isinstance(result, list):
        logger.error(f"{deviceid}/{channel} 조회 결과 형식 오류: {type(result)}")
        return None

    # --- 5) 데이터 프레임 생성 및 검증 ---
    df = pd.DataFrame(result)
    if df.empty:
        logger.info(f"{deviceid}/{channel} 신규 데이터 없음.")
        return pd.DataFrame()  # 명시적으로 빈 DataFrame 반환

    # 필수 컬럼 확인
    required_columns = ['time', 'temperature', 'humidity', 'sv']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        logger.error(f"{deviceid}/{channel} 필수 컬럼 누락: {missing_columns}")
        return None

    # --- 6) 시간 데이터 처리 ---
    if df['time'].dtype == 'object':
        df['time'] = pd.to_datetime(df['time'])
    
    original_count = len(df)
    
    # --- 7) 온도 필터링 ---
    df = df[(df['temperature'] > -20) & (df['temperature'] < 80)]
    filtered_count = len(df)
    
    if filtered_count < original_count:
        logger.info(f"{deviceid}/{channel} 온도 필터링: {original_count} → {filtered_count}")
    
    if df.empty:
        logger.info(f"{deviceid}/{channel} 필터 후 데이터 없음.")
        return pd.DataFrame()  # 명시적으로 빈 DataFrame 반환

    # --- 8) 시간별 집계 ---
    df['hour'] = df['time'].dt.floor('h')
    numeric_cols = df.select_dtypes(include='number').columns.tolist()
    
    if not numeric_cols:
        logger.error(f"{deviceid}/{channel} 집계할 수치 데이터가 없습니다")
        return None
    
    agg = (
        df
        .groupby('hour', as_index=False)[numeric_cols]
        .mean()
        .rename(columns={'hour': 'time'})
    )

    logger.info(f"{deviceid}/{channel} 데이터 {len(agg)}개 집계 완료")
    return agg

# 센서 데이터 자동 저장 및 업데이트
def auto_sensor_data():
    # SQLAlchemy 엔진 생성
    engine = create_engine('mysql+pymysql://root:smart001!@localhost:3306/ITS_TS?charset=utf8mb4')
    
    # PyMySQL 연결 (cursor 작업용)
    conn = pymysql.connect(
        host='localhost', port=3306,
        user='root', password='smart001!',
        database='ITS_TS', charset='utf8mb4'
    )

    try:
        # device_id, channel 기준으로 중복 제거 (최신 센서만 선택)
        sql_query = """
        SELECT s1.device_id, s1.channel, s1.d_type 
        FROM sensor s1
        INNER JOIN (
            SELECT device_id, channel, MAX(created_at) as max_created_at
            FROM sensor 
            GROUP BY device_id, channel
        ) s2 ON s1.device_id = s2.device_id 
              AND s1.channel = s2.channel 
              AND s1.created_at = s2.max_created_at
        ORDER BY s1.device_id, s1.channel;
        """
        df_sensors = pd.read_sql(sql_query, engine)
        
        # 중복 제거 결과 로깅
        total_sensors = pd.read_sql("SELECT COUNT(*) as cnt FROM sensor;", engine).iloc[0]['cnt']
        unique_sensors = len(df_sensors)
        if total_sensors != unique_sensors:
            logger.info(f"센서 중복 제거: 전체 {total_sensors}개 → 유니크 {unique_sensors}개")
            print(f"📊 센서 중복 제거: 전체 {total_sensors}개 → 유니크 {unique_sensors}개")
        records = df_sensors.to_dict(orient='records')
        
        # 진행도 추적 변수들
        total_sensors = len(records)
        processed_count = 0
        success_count = 0
        fail_count = 0
        start_time = datetime.now()
        
        print(f"🚀 센서 데이터 수집 시작 - 총 {total_sensors}개 센서 (중복 제거 후)")
        print("=" * 60)
        
        # 선택된 센서 목록 표시
        print("📋 처리할 센서 목록:")
        for idx, record in enumerate(records, 1):
            print(f"  {idx:2d}. {record['device_id']}/{record['channel']} (타입: {record['d_type']})")
        print("=" * 60)

        with conn.cursor() as cursor:
            for idx, rec in enumerate(records, 1):
                device_id = rec['device_id']
                channel = rec['channel']
                cursor.execute(
                    "SELECT MAX(`time`) FROM `sensor_data` WHERE `device_id` = %s AND `channel` = %s",
                    (device_id, channel)
                )
                last_time = cursor.fetchone()[0]

                if last_time:
                    if isinstance(last_time, str):
                        last_time = datetime.strptime(last_time, '%Y-%m-%d %H:%M:%S')
                    prev_hour = last_time - timedelta(hours=1)
                    sd_start = prev_hour.strftime('%Y%m%d%H')
                else:
                    sd_start = None

                # 진행도 표시
                progress = (idx / total_sensors) * 100
                print(f"[{idx:3d}/{total_sensors}] ({progress:5.1f}%) 처리 중: {device_id}/{channel}", end=" ")
                
                logger.info(f"{device_id}/{channel} 기준 start_date={sd_start}")

                # 1단계: 센서 데이터 수집
                print("📡 데이터 수집 중...", end=" ")
                agg = export_sensor_data(device_id, channel, sd_start)
                
                if agg is None:
                    print("❌ ITS 시스템 연결 실패 또는 데이터 조회 오류")
                    fail_count += 1
                    processed_count += 1
                    continue
                
                # DataFrame인지 확인 후 empty 체크
                if isinstance(agg, pd.DataFrame) and agg.empty:
                    print("⚠️  신규 데이터 없음")
                    processed_count += 1
                    continue
                
                # None이 아니고 DataFrame도 아닌 경우 처리
                if not isinstance(agg, pd.DataFrame):
                    print("❌ 데이터 형식 오류")
                    fail_count += 1
                    processed_count += 1
                    continue

                # 2단계: 데이터 검증
                print(f"📊 {len(agg)}건 수집 →", end=" ")
                
                # 필수 컬럼 존재 확인
                required_cols = ['time', 'humidity', 'sv', 'temperature']
                missing_cols = [col for col in required_cols if col not in agg.columns]
                if missing_cols:
                    print(f"❌ 필수 컬럼 누락: {missing_cols}")
                    fail_count += 1
                    processed_count += 1
                    continue

                # 3단계: 데이터베이스 저장
                print("💾 DB 저장 중...", end=" ")
                insert_count = 0
                update_count = 0
                
                for row_idx, row in enumerate(agg.to_dict(orient='records')):
                    # 데이터 유효성 검증
                    if pd.isna(row['time']):
                        print(f"❌ {row_idx+1}번째 행: 시간 정보 누락")
                        fail_count += 1
                        processed_count += 1
                        continue
                        
                    ts = row['time'].strftime('%Y-%m-%d %H:%M:%S')
                    hmd, sv, tmp = row['humidity'], row['sv'], row['temperature']
                    
                    # NULL 값 검증
                    if pd.isna(hmd) or pd.isna(sv) or pd.isna(tmp):
                        print(f"❌ {row_idx+1}번째 행 ({ts}): 센서값 누락 (hmd:{hmd}, sv:{sv}, tmp:{tmp})")
                        continue

                    # 중복 확인
                    cursor.execute(
                        "SELECT COUNT(*) FROM sensor_data WHERE device_id=%s AND channel=%s AND time=%s",
                        (device_id, channel, ts)
                    )
                    exists = cursor.fetchone()[0] > 0

                    if exists:
                        cursor.execute("""
                            UPDATE sensor_data
                            SET humidity=%s, sv=%s, temperature=%s, updated_at=NOW()
                            WHERE device_id=%s AND channel=%s AND time=%s
                        """, (hmd, sv, tmp, device_id, channel, ts))
                        update_count += 1
                        logger.info(f"UPDATED {device_id}/{channel} @ {ts}: hmd={hmd}, sv={sv}, tmp={tmp}")
                    else:
                        cursor.execute("""
                            INSERT INTO sensor_data
                              (device_id, channel, time, humidity, sv, temperature, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                        """, (device_id, channel, ts, hmd, sv, tmp))
                        insert_count += 1
                        logger.info(f"INSERTED {device_id}/{channel} @ {ts}: hmd={hmd}, sv={sv}, tmp={tmp}")

                # 4단계: 커밋
                print("🔄 커밋 중...", end=" ")
                conn.commit()
                print(f"✅ 완료 (신규:{insert_count}, 갱신:{update_count})")
                success_count += 1
                processed_count += 1
                
        # 작업 완료 통계 표시
        elapsed_time = datetime.now() - start_time
        print("\n" + "=" * 60)
        print(f"🏁 센서 데이터 수집 완료!")
        print(f"📊 처리 결과: 총 {processed_count}개 / 성공 {success_count}개 / 실패 {fail_count}개")
        print(f"⏱️  소요 시간: {elapsed_time}")
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"auto_sensor_data 오류: {e}")
        print(f"\n❌ 전체 작업 실패: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    auto_sensor_data()