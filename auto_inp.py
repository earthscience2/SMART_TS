import api_db
import os
from datetime import datetime, timedelta
import json
from scipy.interpolate import RBFInterpolator
from shapely.geometry import Polygon, Point
import numpy as np
from scipy.spatial.distance import pdist, squareform

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
    end_dt = datetime.strptime(get_prev_hour_str(), '%Y%m%d%H')  # 문자열 → datetime
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

def generate_calculix_inp(nodes, elements, node_temperatures, output_path):
    with open(output_path, "w") as f:
        f.write("*HEADING\nConcrete Curing Thermal Stress Analysis\n\n")
        f.write("*NODE\n")
        for nid, (x, y, z) in nodes.items():
            f.write(f"{nid}, {x:.2f}, {y:.2f}, {z:.2f}\n")
        max_nid = max(nodes.keys())
        f.write("*NSET, NSET=ALLNODES, GENERATE\n")
        f.write(f"1, {max_nid}, 1\n")
        f.write("*ELEMENT, TYPE=C3D8, ELSET=SolidSet\n")
        for eid, node_list in elements.items():
            f.write(f"{eid}, {', '.join(map(str, node_list))}\n")
        f.write("*MATERIAL, NAME=Conc\n")
        f.write("*ELASTIC\n30000, 0.2\n")
        f.write("*DENSITY\n2400\n")
        f.write("*EXPANSION\n1.0e-5\n")
        f.write("*SOLID SECTION, ELSET=SolidSet, MATERIAL=Conc\n\n")
        f.write("*INITIAL CONDITIONS, TYPE=TEMPERATURE\n")
        f.write("ALLNODES, 20.0\n")
        f.write("*STEP\n*STATIC\n")
        f.write("*BOUNDARY\n")
        for nid, (x, y, z) in nodes.items():
            if z == 0.0:
                f.write(f"{nid}, 1, 3, 0.0\n")
        f.write("*TEMPERATURE\n")
        for nid, temp in node_temperatures.items():
            f.write(f"{nid}, {temp:.2f}\n")
        f.write("*NODE PRINT, NSET=ALLNODES\nU\n")
        f.write("*EL PRINT, ELSET=SolidSet\nS\n")
        f.write("*NODE FILE, NSET=ALLNODES\nU\n")
        f.write("*EL FILE, ELSET=SolidSet\nS\n")
        f.write("*END STEP\n")

    print(f'{output_path} 파일 생성 완료')

def compute_epsilon(sensor_coords, sensor_temps, alpha=1.0):
    N = sensor_coords.shape[0]
    d_prime = np.zeros((N, N))
    for i in range(N):
        for j in range(i + 1, N):
            spatial = np.linalg.norm(sensor_coords[i] - sensor_coords[j])
            temp_diff = abs(sensor_temps[i] - sensor_temps[j])
            d = np.sqrt(spatial**2 + alpha * temp_diff**2)
            d_prime[i, j] = d_prime[j, i] = d

    # 자기 자신 제외
    np.fill_diagonal(d_prime, np.inf)
    nn_distances = np.min(d_prime, axis=1)

    mean_nn = np.mean(nn_distances)
    return 1.0 / mean_nn
    
def make_inp(concrete, sensor_data_list, latest_csv):
    plan_points = json.loads(concrete['dims'])['nodes']
    thickness = float(json.loads(concrete['dims'])['h'])
    element_size = float(concrete['con_unit'])
    start_time = latest_csv
    time_list = get_hourly_time_list(start_time)
    sensor_count = len(sensor_data_list)
    if sensor_count != 0:
        for time in time_list:
            sensors = []
            num = 1
            for sensor in sensor_data_list:
                sensor_data_df = api_db.get_sensor_data_by_time(sensor_pk=sensor['sensor_pk'], time=time)
                position = json.loads(sensor['dims'])['nodes']
                if not sensor_data_df.empty:
                    row_dict = sensor_data_df.iloc[0].to_dict()
                    temp = row_dict['temperature']
                    sensors.append((num, position[0], position[1], position[2], float(temp)))
                    num += 1
                else:
                    temp = None

            if sensor_count == len(sensors):
                print(time, thickness, element_size, sensors)

                sensor_coords_e = np.array([[x, y, z] for _, x, y, z, _ in sensors])
                sensor_temps_e  = np.array([temp for _, x, y, z, temp in sensors])
                epsilon = compute_epsilon(sensor_coords_e, sensor_temps_e)
                print(epsilon)

                #============ 여기부터 inp 생성 주요 코드 ============
                polygon = Polygon(plan_points)
                nodes = {}
                node_id = 1
                z_levels = np.arange(0, thickness + 1e-3, element_size)
                x_range = np.arange(0, 11, element_size)
                y_range = np.arange(0, 11, element_size)

                for z in z_levels:
                    for x in x_range:
                        for y in y_range:
                            if polygon.contains(Point(x, y)):
                                nodes[node_id] = (x, y, z)
                                node_id += 1

                # 4. Interpolate sensor temperatures to all nodes
                sensor_coords = np.array([[x, y, z] for _, x, y, z, _ in sensors])
                sensor_temps = np.array([t for *_, t in sensors])
                node_ids = list(nodes.keys())
                node_coords = np.array([nodes[nid] for nid in node_ids])

                interpolator = RBFInterpolator(sensor_coords, sensor_temps, kernel='gaussian', epsilon=epsilon)
                interp_temps = interpolator(node_coords)
                node_temp_map = dict(zip(node_ids, interp_temps))

                # 5. Create ordered C3D8 elements using node coordinates
                coord_to_node = {v: k for k, v in nodes.items()}
                elements = {}
                eid = 1
                x_vals = sorted(set(x for x, y, z in coord_to_node))
                y_vals = sorted(set(y for x, y, z in coord_to_node))
                z_vals = sorted(set(z for x, y, z in coord_to_node))

                for x in x_vals[:-1]:
                    for y in y_vals[:-1]:
                        for z in z_vals[:-1]:
                            try:
                                n000 = coord_to_node[(x, y, z)]
                                n100 = coord_to_node[(x + 1, y, z)]
                                n110 = coord_to_node[(x + 1, y + 1, z)]
                                n010 = coord_to_node[(x, y + 1, z)]
                                n001 = coord_to_node[(x, y, z + 1)]
                                n101 = coord_to_node[(x + 1, y, z + 1)]
                                n111 = coord_to_node[(x + 1, y + 1, z + 1)]
                                n011 = coord_to_node[(x, y + 1, z + 1)]
                                elements[eid] = [n000, n100, n110, n010, n001, n101, n111, n011]
                                eid += 1
                            except KeyError:
                                continue
                time_YYYYMMDDHH = time.strftime('%Y%m%d%H')
                final_path = f"inp/{concrete['concrete_pk']}/{time_YYYYMMDDHH}.inp"
                generate_calculix_inp(nodes, elements, node_temp_map, final_path)



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
