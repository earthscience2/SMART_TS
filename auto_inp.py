import sys
import os

import api_db
from datetime import datetime, timedelta
import json
from scipy.interpolate import RBFInterpolator
from shapely.geometry import Polygon, Point
import numpy as np
import logging

# 0) 로거 설정
LOG_PATH = 'log/auto_inp.log'
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 1) 유틸리티 함수들

def get_subfolders(path):
    try:
        subs = [name for name in os.listdir(path)
                if os.path.isdir(os.path.join(path, name))]
        logger.info(f"Found subfolders in '{path}': {subs}")
        return subs
    except Exception as e:
        logger.error(f"get_subfolders error for path '{path}': {e}")
        return []


def get_files(path):
    try:
        files = [name for name in os.listdir(path)
                 if os.path.isfile(os.path.join(path, name))]
        logger.info(f"Found files in '{path}': {files}")
        return files
    except Exception as e:
        logger.error(f"get_files error for path '{path}': {e}")
        return []


def get_latest_csv(path):
    try:
        files = [f for f in os.listdir(path) if f.endswith('.inp') and len(f) == 14]
        if not files:
            logger.info(f"No .inp files in '{path}'")
            return None
        files_sorted = sorted(files, key=lambda x: x[:10], reverse=True)
        latest = os.path.splitext(files_sorted[0])[0]
        logger.info(f"Latest .inp file in '{path}': {latest}")
        return latest
    except Exception as e:
        logger.error(f"get_latest_csv error for path '{path}': {e}")
        return None


def get_concrete_pk_by_sensor(device_id, channel):
    try:
        sensor_df = api_db.get_sensors_data(device_id=device_id, channel=channel)
        if not sensor_df.empty:
            pk = sensor_df.iloc[0]['concrete_pk']
            logger.info(f"Sensor {device_id}/{channel} -> concrete_pk {pk}")
            return pk
        else:
            logger.warning(f"No sensor record for device_id={device_id}, channel={channel}")
            return None
    except Exception as e:
        logger.error(f"get_concrete_pk_by_sensor error: {e}")
        return None


def get_concrete_dict(concrete_pk):
    try:
        concrete_df = api_db.get_concrete_data(concrete_pk=concrete_pk)
        if not concrete_df.empty:
            data = concrete_df.iloc[0].to_dict()
            logger.info(f"Fetched concrete data for {concrete_pk}")
            return data
        else:
            logger.warning(f"No concrete data for concrete_pk={concrete_pk}")
            return None
    except Exception as e:
        logger.error(f"get_concrete_dict error: {e}")
        return None


def get_prev_hour_str():
    prev_hour = datetime.now() - timedelta(hours=1)
    s = prev_hour.strftime('%Y%m%d%H')
    logger.debug(f"Previous hour string: {s}")
    return s


def get_hourly_time_list(start_time=None):
    try:
        end_dt = datetime.strptime(get_prev_hour_str(), '%Y%m%d%H')
        if start_time is None:
            start_dt = end_dt - timedelta(days=30)
        else:
            start_dt = datetime.strptime(start_time, '%Y%m%d%H')
        time_list = []
        cur = start_dt
        while cur <= end_dt:
            time_list.append(cur.strftime('%Y-%m-%d %H:%M:%S'))
            cur += timedelta(hours=1)
        logger.info(f"Generated time list from {start_dt} to {end_dt}, count={len(time_list)}")
        return time_list
    except Exception as e:
        logger.error(f"get_hourly_time_list error: {e}")
        return []

# 2) 재령에 따른 탄성계수 계산 함수
def calculate_elastic_modulus(concrete_data, analysis_time):
    """
    재령에 따른 탄성계수 계산 (CEB-FIB 모델)
    E(t) = E28 * ((t / (t + β))^n)
    concrete_data: 콘크리트 정보 딕셔너리
    analysis_time: 해석 시간 (문자열, '%Y-%m-%d %H:%M:%S' 형식)
    """
    try:
        # 타설일 가져오기
        casting_date_str = concrete_data.get('con_t')
        if not casting_date_str:
            logger.warning("타설일 정보가 없습니다. 기본 탄성계수 30000 MPa 사용")
            return 30000.0
        
        # CEB-FIB 모델 매개변수 가져오기
        e28_gpa = concrete_data.get('con_e')  # E28 (GPa 단위)
        beta = concrete_data.get('con_b')     # β (베타 상수)
        n = concrete_data.get('con_n')        # n (지수)
        
        # 기본값 설정
        if not e28_gpa:
            logger.warning("E28 정보가 없습니다. 기본값 30 GPa 사용")
            e28_gpa = 30.0
        if not beta:
            logger.warning("베타 상수 정보가 없습니다. 기본값 0.2 사용")
            beta = 0.2
        if not n:
            logger.warning("N 상수 정보가 없습니다. 기본값 0.5 사용")
            n = 0.5
        
        # 단위 변환: GPa -> MPa
        e28_mpa = float(e28_gpa) * 1000.0
        beta = float(beta)
        n = float(n)
        
        # 재령 계산 (일 단위)
        # 타설일이 datetime 형태인지 문자열인지 확인하여 처리
        if isinstance(casting_date_str, str):
            # 날짜 형식이 다양할 수 있으므로 처리
            if 'T' in casting_date_str:
                casting_date = datetime.fromisoformat(casting_date_str.replace('T', ' ').replace('Z', ''))
            else:
                casting_date = datetime.strptime(casting_date_str[:10], '%Y-%m-%d')
        else:
            casting_date = casting_date_str
            
        analysis_date = datetime.strptime(analysis_time, '%Y-%m-%d %H:%M:%S')
        age_days = (analysis_date - casting_date).days + (analysis_date - casting_date).seconds / 86400.0
        
        # 재령이 음수이거나 0인 경우 처리
        if age_days <= 0:
            logger.warning(f"재령이 {age_days}일입니다. 최소값 0.1일로 설정")
            age_days = 0.1
        
        # CEB-FIB 모델 적용: E(t) = E28 * ((t / (t + β))^n)
        age_factor = (age_days / (age_days + beta)) ** n
        elastic_modulus = e28_mpa * age_factor
        
        logger.info(f"재령 {age_days:.1f}일, E28={e28_mpa:.0f}MPa, β={beta}, n={n}, 계수={age_factor:.3f}, E(t)={elastic_modulus:.0f}MPa")
        return elastic_modulus
        
    except Exception as e:
        logger.error(f"탄성계수 계산 오류: {e}")
        return 30000.0  # 기본값 반환

# 3) INP 파일 생성 함수
def generate_calculix_inp(nodes, elements, node_temperatures, output_path, concrete_data, analysis_time):
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 재령에 따른 탄성계수 계산
        elastic_modulus = calculate_elastic_modulus(concrete_data, analysis_time)
        
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
            f.write(f"*ELASTIC\n{elastic_modulus:.0f}, 0.2\n")
            f.write("*DENSITY\n2400\n")
            f.write("*EXPANSION\n1.0e-5\n")
            f.write("*SOLID SECTION, ELSET=SolidSet, MATERIAL=Conc\n\n")
            f.write("*INITIAL CONDITIONS, TYPE=TEMPERATURE\nALLNODES, 20.0\n")
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
        logger.info(f"Generated INP file: {output_path}")
    except Exception as e:
        logger.exception(f"generate_calculix_inp error for '{output_path}': {e}")

# 3) epsilon 계산 함수
def compute_epsilon(sensor_coords, sensor_temps, alpha=1.0):
    try:
        N = sensor_coords.shape[0]
        d_prime = np.zeros((N, N))
        for i in range(N):
            for j in range(i + 1, N):
                spatial = np.linalg.norm(sensor_coords[i] - sensor_coords[j])
                temp_diff = abs(sensor_temps[i] - sensor_temps[j])
                d_prime[i, j] = d_prime[j, i] = np.sqrt(spatial**2 + alpha * temp_diff**2)
        np.fill_diagonal(d_prime, np.inf)
        nn_distances = np.min(d_prime, axis=1)
        epsilon = 1.0 / np.mean(nn_distances)
        logger.info(f"Computed epsilon={epsilon:.4f} with alpha={alpha}")
        return epsilon
    except Exception as e:
        logger.exception(f"compute_epsilon error: {e}")
        return None

# 4) INP 생성 메인 함수
def make_inp(concrete, sensor_data_list, latest_csv):
    try:
        cpk = concrete['concrete_pk']
        logger.info(f"make_inp start for concrete_pk={cpk}, latest_csv={latest_csv}")
        plan_points = json.loads(concrete['dims'])['nodes']
        thickness = float(json.loads(concrete['dims'])['h'])
        element_size = float(concrete['con_unit'])
        time_list = get_hourly_time_list(latest_csv)
        sensor_count = len(sensor_data_list)

        for time in time_list:
            sensors = []
            num = 1
            for sensor in sensor_data_list:
                df_time = api_db.get_sensor_data_by_time(device_id=sensor['device_id'], channel=sensor['channel'], time=time)
                position = json.loads(sensor['dims'])['nodes']
                if not df_time.empty:
                    temp = float(df_time.iloc[0]['temperature'])
                    sensors.append((num, position[0], position[1], position[2], temp))
                    num += 1

            if len(sensors) == sensor_count and len(sensors) > 0:
                # epsilon 계산 및 보간
                coords = np.array([[x, y, z] for _, x, y, z, _ in sensors])
                temps  = np.array([t for *_, t in sensors])
                epsilon = compute_epsilon(coords, temps)
                if epsilon is None:
                    logger.error(f"Skipping interpolation at time={time} due to epsilon error")
                    continue

                # 도메인 내 노드 생성
                polygon = Polygon(plan_points)
                nodes = {}
                node_id = 1
                z_levels = np.arange(0, thickness + 1e-3, element_size)
                x_range = np.arange(min([p[0] for p in plan_points]), max([p[0] for p in plan_points]) + element_size, element_size)
                y_range = np.arange(min([p[1] for p in plan_points]), max([p[1] for p in plan_points]) + element_size, element_size)
                for z in z_levels:
                    for x in x_range:
                        for y in y_range:
                            if polygon.contains(Point(x, y)):
                                nodes[node_id] = (x, y, z)
                                node_id += 1

                # 요소 생성
                coord_to_node = {v: k for k, v in nodes.items()}
                elements = {}
                eid = 1
                xs = sorted({c[0] for c in coord_to_node})
                ys = sorted({c[1] for c in coord_to_node})
                zs = sorted({c[2] for c in coord_to_node})
                for x in xs[:-1]:
                    for y in ys[:-1]:
                        for z in zs[:-1]:
                            try:
                                n000 = coord_to_node[(x, y, z)]
                                n100 = coord_to_node[(x+element_size, y, z)]
                                n110 = coord_to_node[(x+element_size, y+element_size, z)]
                                n010 = coord_to_node[(x, y+element_size, z)]
                                n001 = coord_to_node[(x, y, z+element_size)]
                                n101 = coord_to_node[(x+element_size, y, z+element_size)]
                                n111 = coord_to_node[(x+element_size, y+element_size, z+element_size)]
                                n011 = coord_to_node[(x, y+element_size, z+element_size)]
                                elements[eid] = [n000, n100, n110, n010, n001, n101, n111, n011]
                                eid += 1
                            except KeyError:
                                continue

                # 보간 실행
                interpolator = RBFInterpolator(coords, temps, kernel='gaussian', epsilon=epsilon)
                interp_vals = interpolator(np.array([nodes[i] for i in sorted(nodes)]))
                node_temp_map = dict(zip(sorted(nodes), interp_vals))

                time_dt = datetime.strptime(time, '%Y-%m-%d %H:%M:%S')
                ts_str = time_dt.strftime('%Y%m%d%H')
                final_path = f"inp/{cpk}/{ts_str}.inp"
                generate_calculix_inp(nodes, elements, node_temp_map, final_path, concrete, time)

        logger.info(f"make_inp completed for concrete_pk={cpk}")
    except Exception as e:
        logger.exception(f"make_inp error for concrete_pk={concrete.get('concrete_pk')}: {e}")

# 5) 전체 실행 함수
def auto_inp():
    print("auto_inp started")
    logger.info("auto_inp started")
    try:
        concrete_list = api_db.get_concrete_data().to_dict(orient='records')
        existing = get_subfolders('inp')
        logger.info(f"Concretes to process: {[c['concrete_pk'] for c in concrete_list]}")
        for conc in concrete_list:
            # activate가 0인 경우에만 처리
            if conc.get('activate', 1) != 0:
                logger.info(f"Skipping concrete_pk={conc['concrete_pk']} because activate != 0")
                continue
                
            cpk = conc['concrete_pk']
            if cpk not in existing:
                os.makedirs(f'inp/{cpk}', exist_ok=True)
                logger.info(f"Created folder for {cpk}")
            files = get_files(f'inp/{cpk}')
            latest = get_latest_csv(f'inp/{cpk}')
            logger.info(f"Processing {cpk}: existing files={files}, latest={latest}")
            sensor_data_list = api_db.get_sensors_data(concrete_pk=cpk).to_dict('records')
            make_inp(conc, sensor_data_list, latest)
        logger.info("auto_inp completed successfully")
    except Exception as e:
        logger.exception(f"auto_inp error: {e}")


auto_inp()
