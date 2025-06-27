import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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
    # SQLAlchemy 엔진 생성
    engine = create_engine('mysql+pymysql://root:smart001!@localhost:3306/ITS_TS?charset=utf8mb4')
    
    # PyMySQL 연결 (cursor 작업용)
    conn = pymysql.connect(
        host='localhost', port=3306,
        user='root', password='smart001!',
        database='ITS_TS', charset='utf8mb4'
    )

    try:
        df_sensors = pd.read_sql("SELECT device_id,channel,d_type FROM sensor;", engine)
        records = df_sensors.to_dict(orient='records')
        
        # 진행도 추적 변수들
        total_sensors = len(records)
        processed_count = 0
        success_count = 0
        fail_count = 0
        start_time = datetime.now()
        
        print(f"🚀 센서 데이터 수집 시작 - 총 {total_sensors}개 센서")
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

                try:
                    agg = export_sensor_data(device_id, channel, sd_start)
                    if agg is None or agg.empty:
                        print("❌ 신규 데이터 없음")
                        processed_count += 1
                        continue

                    # INSERT/UPDATE
                    insert_count = 0
                    update_count = 0
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

auto_sensor_data()