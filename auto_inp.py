import api_db
import os
from datetime import datetime, timedelta

def get_subfolders(path):
    # path 경로에 있는 하위 폴더(디렉토리)만 리스트로 반환
    return [name for name in os.listdir(path)
            if os.path.isdir(os.path.join(path, name))]

def get_files(path):
    # path 경로에 있는 파일만 리스트로 반환
    return [name for name in os.listdir(path)
            if os.path.isfile(os.path.join(path, name))]

def get_latest_csv(path):
    # 해당 폴더 내 YYYYMMDDHH.csv 형식의 파일 중 가장 최근 파일명 반환
    files = [f for f in os.listdir(path) if f.endswith('.inp') and len(f) == 14]
    if not files:
        return None
    # 파일명에서 날짜시간 부분만 추출해서 정렬
    files_sorted = sorted(files, key=lambda x: x[:10], reverse=True)
    # 확장자 제외한 파일명만 반환
    return os.path.splitext(files_sorted[0])[0]

def get_concrete_pk_by_sensor(sensor_pk):
    sensor_df = api_db.get_sensors_data(sensor_pk=sensor_pk)
    if not sensor_df.empty:
        # sensor_pk에 해당하는 row의 concrete_pk 반환
        return sensor_df.iloc[0]['concrete_pk']
    else:
        return None
    
def get_concrete_dict(concrete_pk):
    concrete_df = api_db.get_concrete_data(concrete_pk=concrete_pk)
    if not concrete_df.empty:
        return concrete_df.iloc[0].to_dict()
    else:
        return None
    
def get_prev_hour_str():
    prev_hour = datetime.now() - timedelta(hours=1)
    return prev_hour.strftime('%Y%m%d%H')

def get_hourly_time_list(start_time=None):
    end_dt = get_prev_hour_str()
    if start_time is None:
        start_dt = end_dt - timedelta(days=30)
    else:
        start_dt = datetime.strptime(start_time, '%Y%m%d%H')

    # 1시간 단위로 슬라이싱
    time_list = []
    cur = start_dt
    while cur <= end_dt:
        time_list.append(cur.strftime('%Y-%m-%d %H:%M:%S'))
        cur += timedelta(hours=1)
    return time_list

    
def make_inp(concrete, sensor_data_list, latest_csv):

    plan_points = concrete['dims']['nodes']
    thickness = concrete['dims']['h']
    element_size = concrete['con_uni']

    start_time = latest_csv
    time_list = get_hourly_time_list(start_time)
    print(plan_points, thickness, element_size, time_list)


# 센서 데이터 자동 저장 및 업데이트
def auto_inp():
    concrete_df = api_db.get_concrete_data()
    concrete_list = concrete_df.to_dict(orient='records')
    concrete_inp_list = get_subfolders('inp')

    for concrete in concrete_list:
        if concrete['concrete_pk'] in concrete_inp_list:
            files = get_files(f'inp/{concrete["concrete_pk"]}')
            if len(files) == 0:
                print(f'{concrete["concrete_pk"]} 폴더에 파일이 없습니다.')
                sensors_data_df = api_db.get_sensors_data(concrete_pk=concrete["concrete_pk"])
                sensors_data_list = (sensors_data_df.to_dict(orient='records'))
                latest_csv = get_latest_csv(f'inp/{concrete["concrete_pk"]}')
                print(latest_csv)
                make_inp(concrete, sensors_data_list, latest_csv)
            else:
                print(f'{concrete["concrete_pk"]} 폴더에 파일이 있습니다.')
                sensors_data_df = api_db.get_sensors_data(concrete_pk=concrete["concrete_pk"])
                sensors_data_list = (sensors_data_df.to_dict(orient='records'))
                latest_csv = get_latest_csv(f'inp/{concrete["concrete_pk"]}')
                print(latest_csv)
                make_inp(concrete, sensors_data_list, latest_csv)

        else:
            os.makedirs(f'inp/{concrete["concrete_pk"]}', exist_ok=True)
            print(f'{concrete["concrete_pk"]} 폴더를 생성했습니다.')
            sensors_data_df = api_db.get_sensors_data(concrete_pk=concrete["concrete_pk"])
            sensors_data_list = (sensors_data_df.to_dict(orient='records'))
            latest_csv = get_latest_csv(f'inp/{concrete["concrete_pk"]}')
            print(latest_csv)
            make_inp(concrete, sensors_data_list, latest_csv)

auto_inp()
