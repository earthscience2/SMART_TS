import pymysql
from datetime import datetime, timedelta
import pandas as pd
import os
import glob
import threading
import time
from ITS_CLI import config, tcp_client

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
        print(f"[ERROR] 로그인 실패: {res.get('msg')}")
        return
    print("[OK] ITS 로그인 성공")

    result = ITS_CLIENT.message_getdata(
        'query_device_channel_data',
        start_date=sd_start,
        end_date=None,
        projectid=None,
        structureid = None,
        deviceid=deviceid,
        channel=channel
    )

    df = pd.DataFrame(result)
    if df.empty:
        print(f"[INFO] {deviceid} // {channel} 신규 데이터 없음.")
        return

    df['time'] = pd.to_datetime(df['time'])
    if df.empty:
        print(f"[INFO] {deviceid} // {channel} 필터 후 데이터 없음.")
        return
    
    # --- 추가: temperature 범위 필터링 (–20 < temp < 80) ---
    df = df[(df['temperature'] > -20) & (df['temperature'] < 80)]
    if df.empty:
        print(f"[INFO] {deviceid} // {channel} 온도 필터 후 데이터 없음.")
        return

    df['hour'] = df['time'].dt.floor('h')
    numeric_cols = df.select_dtypes(include='number').columns.tolist()
    agg = (
        df
        .groupby('hour', as_index=False)[numeric_cols]
        .mean()
        .rename(columns={'hour': 'time'})
    )

    agg['date'] = agg['time'].dt.date
    unique_dates = sorted(agg['date'].unique())

    return agg


def auto_sensor_data():
    # 1) DB 연결 설정
    conn = pymysql.connect(
        host='localhost',
        port=3306,
        user='root',
        password='smart001!',
        database='ITS_TS',
        charset='utf8mb4'
    )

    try:
        # 2) sensor 기본 정보 조회
        sql_sensors = """
        SELECT
        sensor_pk,
        device_id,
        channel,
        d_type
        FROM sensor;
        """
        df_sensors = pd.read_sql(sql_sensors, conn)
        records = df_sensors.to_dict(orient='records')

        # 3) cursor로 최신 시간 조회
        with conn.cursor() as cursor:
            for rec in records:
                sensor_pk = rec['sensor_pk']

                # sensor_data에서 해당 센서의 최대(time) 조회
                cursor.execute(
                    "SELECT MAX(`time`) FROM `sensor_data` WHERE `sensor_pk` = %s",
                    (sensor_pk,)
                )
                result = cursor.fetchone()
                last_time = result[0]  # 없으면 None

                if last_time is not None:
                    # 문자열로 읽혔을 경우 datetime으로 변환
                    if isinstance(last_time, str):
                        last_time = datetime.strptime(last_time, '%Y-%m-%d %H:%M:%S')

                    # 1시간 전 시각 계산
                    prev_hour = last_time - timedelta(hours=1)
                    formatted = prev_hour.strftime('%Y%m%d%H')
                else:
                    formatted = None

                print(f"{sensor_pk} → {formatted}")

                fillter_db = export_sensor_data(rec['device_id'], rec['channel'], formatted)
                if fillter_db is None or fillter_db.empty:
                    continue

                # 3-3) agg된 행을 하나씩 INSERT or UPDATE
                for row in fillter_db.to_dict(orient='records'):
                    ts = row['time'].strftime('%Y-%m-%d %H:%M:%S')
                    hmd = row.get('humidity', None)
                    sv  = row.get('sv', None)
                    tmp = row.get('temperature', None)

                    # 존재 여부 체크
                    cursor.execute(
                        "SELECT COUNT(*) FROM sensor_data WHERE sensor_pk=%s AND time=%s",
                        (sensor_pk, ts)
                    )
                    exists = cursor.fetchone()[0] > 0

                    if exists:
                        # 업데이트
                        cursor.execute("""
                            UPDATE sensor_data
                            SET humidity=%s, sv=%s, temperature=%s, updated_at=NOW()
                            WHERE sensor_pk=%s AND time=%s
                        """, (hmd, sv, tmp, sensor_pk, ts))
                    else:
                        # 삽입
                        cursor.execute("""
                            INSERT INTO sensor_data
                              (sensor_pk, time, humidity, sv, temperature, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                        """, (sensor_pk, ts, hmd, sv, tmp))

                # 변경사항 커밋
                conn.commit()

    finally:
        conn.close()


if __name__ == '__main__':
    while True:
        try:
            auto_sensor_data()
        except Exception as e:
            print(f"[ERROR] auto_sensor_data 실행 중 오류: {e}")
        # 30분 (1,800초) 대기
        time.sleep(1800)
