import pymysql
from datetime import datetime, timedelta
import pandas as pd
import threading
import time
import logging
from ITS_CLI import config, tcp_client

# 0) 로거 설정
def setup_auto_sensor_logger():
    """auto_sensor 전용 로거 설정"""
    log_dir = "log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger('auto_sensor_logger')
    logger.setLevel(logging.INFO)
    
    # 기존 핸들러 제거 (중복 방지)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 파일 핸들러 설정
    file_handler = logging.FileHandler(os.path.join(log_dir, 'auto_sensor.log'), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 포맷터 설정 (로그인 로그와 동일한 형식)
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | AUTO_SENSOR | %(message)s')
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    return logger

logger = setup_auto_sensor_logger()

# 센서 데이터 조회 및 추출
def export_sensor_data(deviceid, channel, sd_start=None):
    # --- 1) ITS 로그인 및 연결 설정 ---
    user_id = 'cbk4689'
    user_pass = 'qudrhks7460!@'
    config.config_load()
    ITS_CLIENT = tcp_client.TCPClient(
        config.SERVER_IP, config.SERVER_PORT, config.ITS_NUM, config.certfile
    )
    t = threading.Thread(target=ITS_CLIENT.receive_messages)
    t.daemon = True
    t.start()
    time.sleep(1)
    ITS_CLIENT.set_user_password(user_id, user_pass)
    res = ITS_CLIENT.message('login')
    if res.get('result') != 'Success':
        logger.error(f"ITS 로그인 실패: {res.get('msg')}")
        return
    logger.info("ITS 로그인 성공")

    result = ITS_CLIENT.message_getdata(
        'query_device_channel_data',
        start_date=sd_start,
        end_date=None,
        projectid=None,
        structureid=None,
        deviceid=deviceid,
        channel=channel
    )

    df = pd.DataFrame(result)
    if df.empty:
        logger.info(f"{deviceid}/{channel} 신규 데이터 없음.")
        return

    df['time'] = pd.to_datetime(df['time'])
    # temperature 필터
    df = df[(df['temperature'] > -20) & (df['temperature'] < 80)]
    if df.empty:
        logger.info(f"{deviceid}/{channel} 필터 후 데이터 없음.")
        return

    df['hour'] = df['time'].dt.floor('h')
    numeric_cols = df.select_dtypes(include='number').columns.tolist()
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
        df_sensors = pd.read_sql(sql_query, conn)
        
        # 중복 제거 결과 확인
        total_sensors_query = "SELECT COUNT(*) as cnt FROM sensor;"
        total_sensors = pd.read_sql(total_sensors_query, conn).iloc[0]['cnt']
        unique_sensors = len(df_sensors)
        
        if total_sensors != unique_sensors:
            logger.info(f"센서 중복 제거: 전체 {total_sensors}개 → 유니크 {unique_sensors}개")
            print(f"📊 센서 중복 제거: 전체 {total_sensors}개 → 유니크 {unique_sensors}개")
        
        records = df_sensors.to_dict(orient='records')
        
        # 진행도 추적 변수들
        total_count = len(records)
        processed_count = 0
        success_count = 0
        fail_count = 0
        start_time = datetime.now()
        
        print(f"🚀 센서 데이터 수집 시작 - 총 {total_count}개 센서 (중복 제거 후)")
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
                progress = (idx / total_count) * 100
                print(f"[{idx:3d}/{total_count}] ({progress:5.1f}%) 처리 중: {device_id}/{channel}", end=" ")
                
                logger.info(f"{device_id}/{channel} 기준 start_date={sd_start}")

                agg = export_sensor_data(device_id, channel, sd_start)
                if agg is None or agg.empty:
                    print("⚠️  신규 데이터 없음")
                    processed_count += 1
                    continue

                # INSERT/UPDATE 처리
                insert_count = 0
                update_count = 0
                
                try:
                    for row in agg.to_dict(orient='records'):
                        ts = row['time'].strftime('%Y-%m-%d %H:%M:%S')
                        hmd, sv, tmp = row['humidity'], row['sv'], row['temperature']

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

                    conn.commit()
                    print(f"✅ 완료 (신규:{insert_count}, 갱신:{update_count})")
                    success_count += 1
                    processed_count += 1
                    
                except Exception as e:
                    print(f"❌ 실패: {str(e)[:50]}...")
                    logger.error(f"{device_id}/{channel} 처리 오류: {e}")
                    fail_count += 1
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