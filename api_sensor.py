import pandas as pd
import os
import csv
import json
from datetime import datetime
import api_concrete

from ITS_CLI import config, tcp_client
import threading, time, glob

# ITS 연동을 위한 모듈(필요 시 import)
# from ITS_CLI import config, tcp_client
# import threading, time, glob

# ──────────────────────────────────────────────────────────────────────────────
# 설정: CSV 파일 경로
# ──────────────────────────────────────────────────────────────────────────────
DATA_DIR = "data"
SENSOR_CSV = os.path.join(DATA_DIR, "sensor.csv")
os.makedirs(DATA_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# 1) load_all_sensors(): 센서 메타데이터 전체 로드
# ──────────────────────────────────────────────────────────────────────────────
def load_all_sensors() -> pd.DataFrame:
    """
    sensor.csv 파일을 읽어 DataFrame으로 반환.
    JSON 문자열이 들어있는 sensor_id 컬럼을 dims로 재매핑하여 반환.
    컬럼: ["sensor_pk","concrete_pk","name","dims","created_at","updated_at"]
    파일이 없으면 빈 DataFrame 반환.
    """
    if not os.path.isfile(SENSOR_CSV):
        return pd.DataFrame(columns=[
            "sensor_pk","concrete_pk","name","dims","created_at","updated_at"
        ])
    df = pd.read_csv(SENSOR_CSV, dtype=str)
    # sensor_id 컬럼에 저장된 JSON → dims
    df['dims'] = df['sensor_id']
    df = df[["sensor_pk","concrete_pk","name","dims","created_at","updated_at"]]
    return df

# ──────────────────────────────────────────────────────────────────────────────
# 2) get_sensor(sensor_pk): 단일 센서 조회
# ──────────────────────────────────────────────────────────────────────────────
def get_sensor(sensor_pk: str) -> dict | None:
    """
    주어진 sensor_pk에 해당하는 센서 정보를 dict로 반환.
    dims는 Python dict로 파싱.
    """
    df = load_all_sensors()
    row = df[df['sensor_pk'] == sensor_pk]
    if row.empty:
        return None
    data = row.iloc[0].to_dict()
    try:
        data['dims'] = json.loads(data['dims'])
    except Exception:
        pass
    return data

# ──────────────────────────────────────────────────────────────────────────────
# 3) add_sensor(concrete_pk, name, dims): 새로운 센서 추가
# ──────────────────────────────────────────────────────────────────────────────
def add_sensor(concrete_pk: str, name: str, dims: dict) -> str:
    """
    새로운 sensor_pk를 자동 생성 (예: S001 → S002 → ...)
    CSV에 한 줄 추가 후 저장. 반환값: 생성된 sensor_pk
    """
    df = load_all_sensors()
    # PK 생성
    if df.empty:
        new_pk = 'S001'
    else:
        nums = df['sensor_pk'].str.extract(r'(\d+)$')[0].astype(int)
        new_pk = f"S{nums.max()+1:03d}"

    now = datetime.utcnow().isoformat() + 'Z'
    new_row = {
        'sensor_pk': new_pk,
        'concrete_pk': concrete_pk,
        'name': name,
        'sensor_id': json.dumps(dims, ensure_ascii=False),
        'created_at': now,
        'updated_at': now
    }
    # 기존 CSV 읽기
    orig = pd.read_csv(SENSOR_CSV, dtype=str) if os.path.isfile(SENSOR_CSV) else pd.DataFrame()
    out = orig.append(new_row, ignore_index=True)
    out.to_csv(SENSOR_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)
    return new_pk

# ──────────────────────────────────────────────────────────────────────────────
# 4) update_sensor(sensor_pk, name=None, dims=None): 센서 수정
# ──────────────────────────────────────────────────────────────────────────────
def update_sensor(sensor_pk: str, name: str|None=None, dims: dict|None=None):
    """
    주어진 sensor_pk 행을 찾아 name, dims, updated_at을 수정 후 저장.
    """
    df = pd.read_csv(SENSOR_CSV, dtype=str)
    mask = df['sensor_pk'] == sensor_pk
    if not mask.any():
        raise ValueError(f"존재하지 않는 Sensor PK: {sensor_pk}")
    if name is not None:
        df.loc[mask, 'name'] = name
    if dims is not None:
        df.loc[mask, 'sensor_id'] = json.dumps(dims, ensure_ascii=False)
    df.loc[mask, 'updated_at'] = datetime.utcnow().isoformat() + 'Z'
    df.to_csv(SENSOR_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)

# ──────────────────────────────────────────────────────────────────────────────
# 5) delete_sensor(sensor_pk): 센서 삭제
# ──────────────────────────────────────────────────────────────────────────────
def delete_sensor(sensor_pk: str):
    """
    주어진 sensor_pk 행을 삭제 후 CSV 저장.
    """
    df = pd.read_csv(SENSOR_CSV, dtype=str)
    if sensor_pk not in df['sensor_pk'].values:
        raise ValueError(f"존재하지 않는 Sensor PK: {sensor_pk}")
    df = df[df['sensor_pk'] != sensor_pk]
    df.to_csv(SENSOR_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)

# ──────────────────────────────────────────────────────────────────────────────
# 5) export_recent_3months_data_by_sensor(ITS_CLIENT): 최근 3개월 센서 데이터 추출 및 저장
# ──────────────────────────────────────────────────────────────────────────────
# ITS_CLI 환경에서 ITS_CLIENT 인스턴스를 전달해야 합니다.
def export_sensor_data(start_date=None, end_date=None):
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

    # --- 2) 전체 센서 메타 로드 ---
    df_meta = load_all_sensors()
    total_sensors = len(df_meta)

    # 최상위 저장 폴더
    base_dir = "sensors"
    os.makedirs(base_dir, exist_ok=True)

    for idx, (_, row)in enumerate(df_meta.iterrows(), start=1):
        sensor_id = row["sensor_pk"]
        sensor_dir = os.path.join(base_dir, sensor_id)

        if not os.path.exists(sensor_dir):
            os.makedirs(sensor_dir)

        if not glob.glob(os.path.join(sensor_dir, "*.csv")):
            sd_start = None
        else:
            pattern = os.path.join(sensor_dir, f"*.csv")
            files = glob.glob(pattern)
            if files:
                hours = [
                    os.path.basename(f).split(".")[0]
                    for f in files
                ]
                last_day = max(
                    datetime.strptime(h, "%Y%m%d") for h in hours
                )
                sd_start = last_day.strftime("%Y%m%d")  # 그 이후부터 새로 수집

        result = ITS_CLIENT.message_getdata(
            'query_device_channel_data',
            start_date=sd_start,
            end_date=None,
            projectid=None,
            structureid = None,
            deviceid=sensor_id,
            channel=1
        )

        df = pd.DataFrame(result)
        if df.empty:
            print(f"[INFO] {sensor_id} 신규 데이터 없음.")
            continue

        df['time'] = pd.to_datetime(df['time'])
        if df.empty:
            print(f"[INFO] {sensor_id} 필터 후 데이터 없음.")
            continue

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
        total_days = len(unique_dates)


        for d_idx, day in enumerate(unique_dates, start=1):
            group = agg[agg['date'] == day]
            df_day = (
                group
                .drop(columns=['date'])
                .sort_values('time')
            )

            filename = f"{day.strftime('%Y%m%d')}.csv"
            path = os.path.join(sensor_dir, filename)

            # 기존 파일 병합이 필요하면 여기에 로직 추가
            df_day.to_csv(path, index=False)

            # 일별 진행도 출력
            print(f"[{idx}/{total_sensors}] {sensor_id} {day.strftime('%Y-%m-%d')} 저장 완료")

export_sensor_data()