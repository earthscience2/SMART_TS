import pymysql
from datetime import datetime, timedelta
import pandas as pd
import api_db

# 센서 데이터 자동 저장 및 업데이트
def auto_sensor_data(start_ymdh, end_ymdh):
    start_dt = api_db.parse_ymdh(start_ymdh)
    end_dt = api_db.parse_ymdh(end_ymdh)
    sensors = api_db.get_sensors_data()
    for sensor in sensors:
        sensor_pk = sensor['sensor_pk']
        device_id = sensor['device_id']
