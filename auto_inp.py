import api_db
import os

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
    files = [f for f in os.listdir(path) if f.endswith('.csv') and len(f) == 14]
    if not files:
        return None
    # 파일명에서 날짜시간 부분만 추출해서 정렬
    files_sorted = sorted(files, key=lambda x: x[:10], reverse=True)
    # 확장자 제외한 파일명만 반환
    return os.path.splitext(files_sorted[0])[0]

# 센서 데이터 자동 저장 및 업데이트
def auto_inp():
    sensor_df = api_db.get_sensors_data()
    sensor_db_list = sensor_df.to_dict(orient='records')
    sensor_inp_list = get_subfolders('inp')

    for sensor in sensor_db_list:
        if sensor['sensor_pk'] in sensor_inp_list:
            files = get_files(f'inp/{sensor["sensor_pk"]}')
            if len(files) == 0:
                print(f'{sensor["sensor_pk"]} 폴더에 파일이 없습니다.')
                sensor_data_df = api_db.get_sensor_data(sensor_pk=sensor['sensor_pk'], start=None, end=None)
                sensor_data_list = (sensor_data_df.to_dict(orient='records'))[:-1]
                for dd in sensor_data_list:
                    print(dd)
            else:
                print(f'{sensor["sensor_pk"]} 폴더에 파일이 있습니다.')
                latest_csv = get_latest_csv(f'inp/{sensor["sensor_pk"]}')
                sensor_data_df = api_db.get_sensor_data(sensor_pk=sensor['sensor_pk'], start=latest_csv, end=None)
                sensor_data_list = (sensor_data_df.to_dict(orient='records'))[:-1]
                for dd in sensor_data_list:
                    print(dd)

        else:
            os.makedirs(f'inp/{sensor["sensor_pk"]}', exist_ok=True)
            print(f'{sensor["sensor_pk"]} 폴더를 생성했습니다.')
            sensor_data_df = api_db.get_sensor_data(sensor_pk=sensor['sensor_pk'], start=None, end=None)
            sensor_data_list = (sensor_data_df.to_dict(orient='records'))[:-1]
            for dd in sensor_data_list:
                print(dd)

auto_inp()
