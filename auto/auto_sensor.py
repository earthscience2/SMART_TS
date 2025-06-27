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

        with conn.cursor() as cursor:
            for rec in records:
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

                logger.info(f"{device_id}/{channel} 기준 start_date={sd_start}")

                agg = export_sensor_data(device_id, channel, sd_start)
                if agg is None or agg.empty:
                    continue

                # INSERT/UPDATE
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
                        logger.info(f"UPDATED {device_id}/{channel} @ {ts}: hmd={hmd}, sv={sv}, tmp={tmp}")
                    else:
                        cursor.execute("""
                            INSERT INTO sensor_data
                              (device_id, channel, time, humidity, sv, temperature, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                        """, (device_id, channel, ts, hmd, sv, tmp))
                        logger.info(f"INSERTED {device_id}/{channel} @ {ts}: hmd={hmd}, sv={sv}, tmp={tmp}")

                conn.commit()
    except Exception as e:
        logger.error(f"auto_sensor_data 오류: {e}")
    finally:
        conn.close()

auto_sensor_data()