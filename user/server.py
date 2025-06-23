import socket
import threading
import json, time
import bcrypt
from datetime import datetime
import pandas as pd
import ssl

from logger import Logger as log
import config
import itsdb1, itsdb2
import timeseriesdb as tsdb

import traceback
import logging

# 로깅 설정
# logging.basicConfig(level=logging.ERROR)
# log = logging.getLogger(__name__)

REGISTED_USER = {}

def is_valid_date(date_str):
    try:
        datetime.strptime(date_str, '%Y%m%d')
        return True
    except ValueError:
        return False
    
def date_formatted(start_date, end_date):

    date_obj_start = datetime.strptime(start_date, "%Y%m%d %H%M%S")
    formatted_start_date = date_obj_start.strftime("%Y-%m-%d %H:%M:%S")

    date_obj_end = datetime.strptime(end_date, "%Y%m%d %H%M%S")
    formatted_end_date = date_obj_end.strftime("%Y-%m-%d %H:%M:%S")

    return formatted_start_date, formatted_end_date

def add_failure(df, d_id, ch):
    new_row = pd.DataFrame({'device_id': [d_id], 'channel': [ch]})
    df = pd.concat([df, new_row], ignore_index=True)
    return df

def message_parser(message_dict, addr):

    global REGISTED_USER

    # REGISTED_USER example
    # {('127.0.0.1', 58824): {'user': 'cbktest', 'dbpass': b'$2a$10$421aWIAmP0u0BV6DoWDx3OiwvHktblN2nkMaXL4Wh3doMtcrerYcu', 'grade': 'CM', 'auth': ['P_000002', 'P_000003']}}

    print(message_dict)

    try:

        response = {}

        print(f"Recv from {addr} in message parser")

        if message_dict['command'] == 'login':
            response['command'] = 'login'
            user = message_dict['user']
            password = message_dict['password']
            its_num = message_dict['its']

            if its_num == '1':
                db_result = itsdb1.user_regist(user)
                if db_result.empty:
                    response['result'] = 'Fail'
                    response['msg'] = f'userid : {user} is not exist'
                else:
                    input_password = password.encode('utf-8')
                    stored_password_hash = db_result.iloc[0]['userpw'].encode('utf-8')
                    grade = db_result.iloc[0]['grade']

                    if bcrypt.checkpw(input_password, stored_password_hash):
                        response['result'] = 'Success'
                        REGISTED_USER[addr]['user'] = user
                        REGISTED_USER[addr]['dbpass'] = stored_password_hash
                        REGISTED_USER[addr]['grade'] = grade
                        REGISTED_USER[addr]['auth'] = []

                        if grade == 'CT' or grade == 'CM':
                            authstartdate = db_result.iloc[0]['authstartdate']
                            authenddate = db_result.iloc[0]['authenddate']

                            if authstartdate != None and authenddate != None:
                                startdate = datetime.strptime(authstartdate, "%Y-%m-%d")
                                enddate = datetime.strptime(authenddate, "%Y-%m-%d")
                                today = datetime.today()

                                if today >= startdate and today <= enddate:
                                    pass
                                else:
                                    response['result'] = 'Fail'
                                    response['msg'] = f'Your ID permissions have expired.'

                            db_result = itsdb1.check_auth_project_structure(user)
                            if db_result.empty:
                                response['result'] = 'Fail'
                                response['msg'] = f'You({user}) currently do not have access to any projects or structures.'
                            else:
                                REGISTED_USER[addr]['auth'] = db_result['id'].tolist()
                            
                    else:
                        response['result'] = 'Fail'
                        response['msg'] = f'Invalid password'

            elif its_num == '2':
                db_result = itsdb2.user_regist(user)
                if db_result.empty:
                    response['result'] = 'Fail'
                    response['msg'] = f'userid : {user} is not exist'
                else:
                    input_password = password.encode('utf-8')
                    stored_password_hash = db_result.iloc[0]['userpw'].encode('utf-8')
                    grade = db_result.iloc[0]['grade']

                    if bcrypt.checkpw(input_password, stored_password_hash):
                        response['result'] = 'Success'
                        REGISTED_USER[addr]['user'] = user
                        REGISTED_USER[addr]['dbpass'] = stored_password_hash
                        REGISTED_USER[addr]['grade'] = grade
                        REGISTED_USER[addr]['auth'] = []

                        if grade == 'CT' or grade == 'CM':
                            authstartdate = db_result.iloc[0]['authstartdate']
                            authenddate = db_result.iloc[0]['authenddate']

                            if authstartdate != None and authenddate != None:
                                startdate = datetime.strptime(authstartdate, "%Y-%m-%d")
                                enddate = datetime.strptime(authenddate, "%Y-%m-%d")
                                today = datetime.today()

                                if today >= startdate and today <= enddate:
                                    pass
                                else:
                                    response['result'] = 'Fail'
                                    response['msg'] = f'Your ID permissions have expired.'

                            db_result = itsdb2.check_auth_project_structure(user)
                            if db_result.empty:
                                response['result'] = 'Fail'
                                response['msg'] = f'You({user}) currently do not have access to any projects or structures.'
                            else:
                                REGISTED_USER[addr]['auth'] = db_result['id'].tolist()
                            
                    else:
                        response['result'] = 'Fail'
                        response['msg'] = f'Invalid password'
            else:
                print("error")
        
        elif message_dict['command'] == 'get_project_structure_list':
            if 'user' in REGISTED_USER[addr].keys():
                if REGISTED_USER[addr]['grade'] == 'AD':
                    if message_dict['its'] == '1':
                        df_result = itsdb1.get_project_stid_list()
                    else:
                        df_result = itsdb2.get_project_stid_list()
                    if df_result.empty:
                        response['result'] = 'Fail'
                        response['msg'] = f'Projects are not exist'
                    else:
                        json_data = df_result.to_json()
                        response['result'] = 'Success'
                        response['data'] = json_data
                else:
                    allow_project_list =  REGISTED_USER[addr]['auth']
                    if len(allow_project_list ) != 0:
                        if message_dict['its'] == '1':
                            df_result = itsdb1.get_project_stid_list(allow_project_list)
                        else:
                            df_result = itsdb2.get_project_stid_list(allow_project_list)
                        if df_result.empty:
                            response['result'] = 'Fail'
                            response['msg'] = f'Projects are not exist'
                        else:
                            json_data = df_result.to_json()
                            response['result'] = 'Success'
                            response['data'] = json_data
                    else:
                        response['result'] = 'Fail'
                        response['msg'] = f'You do not have access to any projects. Please contact the administrator.'
            else:
                response['result'] = 'Fail'
                response['msg'] = f'Login first'

        elif message_dict['command'] == 'get_project_list':
            if 'user' in REGISTED_USER[addr].keys():
                
                if REGISTED_USER[addr]['grade'] == 'AD':
                    if message_dict['its'] == '1':
                        df_result = itsdb1.get_project_list()
                    else:
                        df_result = itsdb2.get_project_list()
                    if df_result.empty:
                        response['result'] = 'Fail'
                        response['msg'] = f'Projects are not exist'
                    else:
                        json_data = df_result.to_json()
                        response['result'] = 'Success'
                        response['data'] = json_data
                else:
                    allow_project_list =  REGISTED_USER[addr]['auth']
                    if len(allow_project_list ) != 0:
                        if message_dict['its'] == '1':
                            df_result = itsdb1.get_project_list(allow_project_list)
                        else:
                            df_result = itsdb2.get_project_list(allow_project_list)
                        if df_result.empty:
                            response['result'] = 'Fail'
                            response['msg'] = f'Projects are not exist'
                        else:
                            json_data = df_result.to_json()
                            response['result'] = 'Success'
                            response['data'] = json_data
                    else:
                        response['result'] = 'Fail'
                        response['msg'] = f'You do not have access to any projects. Please contact the administrator.'
            else:
                response['result'] = 'Fail'
                response['msg'] = f'Login first'

        elif message_dict['command'] == 'get_structure_list':
            if 'user' in REGISTED_USER[addr].keys():
                projectid = message_dict['projectid']
                if REGISTED_USER[addr]['grade'] == 'AD':
                    if message_dict['its'] == '1':
                        df_result = itsdb1.get_stid_list(projectid)
                    else:
                        df_result = itsdb2.get_stid_list(projectid)
                    if df_result.empty:
                        response['result'] = 'Fail'
                        response['msg'] = f'Structures are not exist'
                    else:
                        json_data = df_result.to_json()
                        response['result'] = 'Success'
                        response['data'] = json_data
                else:
                    allow_project_list =  REGISTED_USER[addr]['auth']
                    if projectid in allow_project_list:
                        if message_dict['its'] == '1':
                            df_result = itsdb1.get_stid_list(projectid)
                        else:
                            df_result = itsdb2.get_stid_list(projectid)
                        if df_result.empty:
                            response['result'] = 'Fail'
                            response['msg'] = f'Structures are not exist'
                        else:
                            json_data = df_result.to_json()
                            response['result'] = 'Success'
                            response['data'] = json_data
                    else:
                        response['result'] = 'Fail'
                        response['msg'] = f'You do not have access to any structures. Please contact the administrator.'

            else:
                response['result'] = 'Fail'
                response['msg'] = f'Login first'
        
        elif message_dict['command'] == 'get_device_list':
            projectid = message_dict.get('projectid')
            structureid = message_dict.get('structureid')
            its = message_dict.get('its')

            if not projectid and not structureid:
                return json.dumps({'result': 'Fail', 'msg': 'projectid or structureid required'})

            if its == '1':
                db = itsdb1
            else:
                db = itsdb2

            if structureid:
                sensors = db.get_sensor_list('S', structureid)
                device_info = db.get_device_info('S', structureid)
            else:
                sensors = db.get_sensor_list('P', projectid)
                device_info = db.get_device_info('P', projectid)
                
            if sensors is None or sensors.empty:
                return json.dumps({'result': 'Fail', 'msg': 'No sensors found'})

            response = {
                'result': 'Success',
                'data': sensors.to_json(),
                'device_info': device_info.to_json()
            }

            return json.dumps(response)

        elif message_dict['command'] in ['download_sensordata', 'download_sensordata_as_df']:
            if addr in REGISTED_USER:
                if 'user' in REGISTED_USER[addr].keys():
                    projectid = message_dict['projectid']
                    structureid = message_dict['structureid']

                    if REGISTED_USER[addr]['grade'] == 'AD':

                        if message_dict.get('structureid') is None:
                            if message_dict['its'] == '1':
                                sensors = itsdb1.get_sensor_list('P', projectid)
                                device_info = itsdb1.get_device_info('P', projectid)
                            else:
                                sensors = itsdb2.get_sensor_list('P', projectid)
                                device_info = itsdb2.get_device_info('P', projectid)
                        else:
                            if message_dict['its'] == '1':
                                sensors = itsdb1.get_sensor_list('S', structureid)
                                device_info = itsdb1.get_device_info('S', structureid)
                            else:
                                sensors = itsdb2.get_sensor_list('S', structureid)
                                device_info = itsdb2.get_device_info('S', structureid)

                        if sensors.empty:
                            response['result'] = 'Fail'
                        else:
                            response['result'] = 'Success'
                            response['data'] = sensors.to_json()
                            response['dbinfo'] = {}
                            response['device_info'] = device_info.to_json()
                            if message_dict['its'] == '1':
                                response['dbinfo']['host'] = config.its1_host
                                response['dbinfo']['port'] = config.its1_tsdb_port
                                response['dbinfo']['token'] = config.its1_tsdb_token
                                response['dbinfo']['org'] = config.its1_tsdb_org
                                response['dbinfo']['bucket'] = config.its1_tsdb_bucket
                            else:
                                response['dbinfo']['host'] = config.its2_host
                                response['dbinfo']['port'] = config.its2_tsdb_port
                                response['dbinfo']['token'] = config.its2_tsdb_token
                                response['dbinfo']['org'] = config.its2_tsdb_org
                                response['dbinfo']['bucket'] = config.its2_tsdb_bucket

                    else:
                        allow_project_list =  REGISTED_USER[addr]['auth']
                        if projectid in allow_project_list:
                            if message_dict['its'] == '1':
                                df_result = itsdb1.get_stid_list(projectid)
                            else:
                                df_result = itsdb2.get_stid_list(projectid)
                            if df_result.empty:
                                response['result'] = 'Fail'
                                response['msg'] = f'Structures are not exist'
                            else:

                                if message_dict.get('structureid') is None:
                                    if message_dict['its'] == '1':
                                        sensors = itsdb1.get_sensor_list('P', projectid)
                                        device_info = itsdb1.get_device_info('P', projectid)
                                    else:
                                        sensors = itsdb2.get_sensor_list('P', projectid)
                                        device_info = itsdb2.get_device_info('P', projectid)

                                else:
                                    temp_st_list = df_result['stid'].to_list()
                                    if message_dict.get('structureid') in temp_st_list:
                                        if message_dict['its'] == '1':
                                            sensors = itsdb1.get_sensor_list('S', structureid)
                                            device_info = itsdb1.get_device_info('S', structureid)
                                        else:
                                            sensors = itsdb2.get_sensor_list('S', structureid)
                                            device_info = itsdb2.get_device_info('S', structureid)
                                    else:
                                        response['result'] = 'Fail'
                                        response['msg'] = f'You do not have access to this structure. Please contact the administrator.'

                                if sensors.empty:
                                    response['result'] = 'Fail'
                                else:
                                    response['result'] = 'Success'
                                    response['data'] = sensors.to_json()
                                    response['dbinfo'] = {}
                                    response['device_info'] = device_info.to_json()
                                    if message_dict['its'] == '1':
                                        response['dbinfo']['host'] = config.its1_host
                                        response['dbinfo']['port'] = config.its1_tsdb_port
                                        response['dbinfo']['token'] = config.its1_tsdb_token
                                        response['dbinfo']['org'] = config.its1_tsdb_org
                                        response['dbinfo']['bucket'] = config.its1_tsdb_bucket
                                    else:
                                        response['dbinfo']['host'] = config.its2_host
                                        response['dbinfo']['port'] = config.its2_tsdb_port
                                        response['dbinfo']['token'] = config.its2_tsdb_token
                                        response['dbinfo']['org'] = config.its2_tsdb_org
                                        response['dbinfo']['bucket'] = config.its2_tsdb_bucket

                        elif projectid == None and structureid != None:
                            if message_dict['its'] == '1':
                                df_result = itsdb1.get_stid_list_from_project_list(allow_project_list)
                            else:
                                df_result = itsdb2.get_stid_list_from_project_list(allow_project_list)
                            print("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
                            print(df_result)
                            if df_result.empty:
                                response['result'] = 'Fail'
                                response['msg'] = f'Structures are not exist'
                            else:
                                sensors = pd.DataFrame()
                                temp_st_list = df_result['stid'].to_list()
                                if message_dict.get('structureid') in temp_st_list:
                                    if message_dict['its'] == '1':
                                        sensors = itsdb1.get_sensor_list('S', structureid)
                                        device_info = itsdb1.get_device_info('S', structureid)
                                    else:
                                        sensors = itsdb2.get_sensor_list('S', structureid)
                                        device_info = itsdb2.get_device_info('S', structureid)
                                else:
                                    response['result'] = 'Fail'
                                    response['msg'] = f'You do not have access to this structure. Please contact the administrator.'

                                if sensors.empty:
                                    response['result'] = 'Fail'
                                    response['msg'] = 'sensor data is empty'
                                else:
                                    response['result'] = 'Success'
                                    response['data'] = sensors.to_json()
                                    response['dbinfo'] = {}
                                    response['device_info'] = device_info.to_json()
                                    if message_dict['its'] == '1':
                                        response['dbinfo']['host'] = config.its1_host
                                        response['dbinfo']['port'] = config.its1_tsdb_port
                                        response['dbinfo']['token'] = config.its1_tsdb_token
                                        response['dbinfo']['org'] = config.its1_tsdb_org
                                        response['dbinfo']['bucket'] = config.its1_tsdb_bucket
                                    else:
                                        response['dbinfo']['host'] = config.its2_host
                                        response['dbinfo']['port'] = config.its2_tsdb_port
                                        response['dbinfo']['token'] = config.its2_tsdb_token
                                        response['dbinfo']['org'] = config.its2_tsdb_org
                                        response['dbinfo']['bucket'] = config.its2_tsdb_bucket
                        else:
                            response['result'] = 'Fail'
                            response['msg'] = f'You do not have access to any structures. Please contact the administrator.'
                else:
                    response['result'] = 'Fail'
                    response['msg'] = f'Login first'
            else:
                response['result'] = 'Fail'
                response['msg'] = f'Login first'

        elif message_dict['command'] == 'query_device_channel_data':
            deviceid = message_dict.get('deviceid')
            channel = message_dict.get('channel')
            its = message_dict.get('its')

            if not deviceid or not channel:
                response['result'] = 'Fail'
                response['msg'] = 'deviceid and channel are required'
                return json.dumps(response)

            if addr not in REGISTED_USER or 'user' not in REGISTED_USER[addr]:
                response['result'] = 'Fail'
                response['msg'] = 'Login first'
                return json.dumps(response)

            grade = REGISTED_USER[addr]['grade']
            user_auth = REGISTED_USER[addr]['auth']

            db = itsdb1 if its == '1' else itsdb2

            sensor_df = db.get_sensor_structure_info(deviceid, channel)
            meta_df = db.get_sensor_meta(deviceid, channel)

            if sensor_df is None or sensor_df.empty:
                response['result'] = 'Fail'
                response['msg'] = 'Device/Channel not found'
                return json.dumps(response)

            structure_id = sensor_df.iloc[0]['stid']
            project_id = sensor_df.iloc[0]['projectid']

            if grade != 'AD' and project_id not in user_auth and structure_id not in user_auth:
                response['result'] = 'Fail'
                response['msg'] = f'Access denied for device {deviceid}, channel {channel}'
                return json.dumps(response)

            if meta_df is None or meta_df.empty:
                response['result'] = 'Fail'
                response['msg'] = 'Sensor metadata not found'
                return json.dumps(response)

            # ✅ 완전한 통일을 위해 필요한 컬럼만 추출
            result_df = pd.DataFrame([{
                'deviceid': deviceid,
                'channel': channel,
                'd_type': meta_df.iloc[0]['device_type'],
                'data_type': meta_df.iloc[0]['data_type'],
                'is3axis': str(meta_df.iloc[0]['is3axis'])
            }])

            response['result'] = 'Success'
            response['data'] = result_df.to_json()  # ✅ 다른 명령들과 동일한 포맷
            response['dbinfo'] = {
                'host': config.its1_host if its == '1' else config.its2_host,
                'port': config.its1_tsdb_port if its == '1' else config.its2_tsdb_port,
                'token': config.its1_tsdb_token if its == '1' else config.its2_tsdb_token,
                'org': config.its1_tsdb_org if its == '1' else config.its2_tsdb_org,
                'bucket': config.its1_tsdb_bucket if its == '1' else config.its2_tsdb_bucket
            }
            
        else:
            print("not defined")

        # if response['result'] == 'Fail':
        #     del REGISTED_USER[addr]

        send_response = json.dumps(response)

        return send_response
    
    except Exception as e:
        log.error(str(e))
        log.error("An error occurred: %s", str(e))
        log.error("Traceback: %s", traceback.format_exc())

def handle_client(client_socket, addr):
    while True:
        try:
            message = client_socket.recv(1024).decode()
            if not message:
                break
            print(f"Received: {message}")

            message_dict = json.loads(message)
            result = message_parser(message_dict, addr)
            print(result)
            client_socket.send(result.encode())
        except json.JSONDecodeError as e:
            print(f"JSON decode error from {addr}: {e}")
            break
        except ssl.SSLError as e:
            print(f"SSL error from {addr}: {e}")
            break
        except Exception as e:
            print(f"Error from {addr}: {e}")
            break
    if addr in REGISTED_USER:
        del REGISTED_USER[addr]
        print(f"Disconnected from {addr}, removed from REGISTED_USER")
    client_socket.close()

def start_server(host, port, certfile, keyfile):

    global REGISTED_USER

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=certfile, keyfile=keyfile)

    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                server.bind((host, port))
                server.listen(50)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 40960)
                log.info(f"Server started and listening on port {host}:{port}")

                while True:
                    try:
                        client_socket, addr = server.accept()
                        log.info(f"Accepted connection from {addr}")

                        REGISTED_USER[addr] = {}

                        ssl_client_socket = context.wrap_socket(client_socket, server_side=True)
                        client_handler = threading.Thread(target=handle_client, args=(ssl_client_socket, addr))
                        client_handler.start()
                    except Exception as e:
                        log.error(f"Error accepting connection: {e}")
        except Exception as e:
            log.error(f"Server error: {e}")
            log.info("Restarting server...")
            continue
    '''
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((host, port))
        server.listen(50)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 40960)
        print(f"Server started and listening on port {host}:{port}")

        while True:
            client_socket, addr = server.accept()
            print(f"Accepted connection from {addr}")
            REGISTED_USER[addr] = {}

            ssl_client_socket = context.wrap_socket(client_socket, server_side=True)
            client_handler = threading.Thread(target=handle_client, args=(ssl_client_socket, addr))
            client_handler.start()
    '''
    '''
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', port))
    server.listen(50)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 40960)
    print(f"Server started and listening on port {port}")

    while True:
        client_socket, addr = server.accept()
        print(f"Accepted connection from {addr}")
        REGISTED_USER[addr] = {}
        client_handler = threading.Thread(target=handle_client, args=(client_socket, addr))
        client_handler.start()
    '''

def server_thread():

    host = config.SERVER_IP
    port = config.SERVER_PORT
    certfile = config.certfile 
    keyfile = config.keyfile
    start_server(host, port, certfile, keyfile)

if __name__ == "__main__":
    config.config_load()

    itsdb1.itsdb_init(config.its1_host, config.its1_itsdb_user, config.its1_itsdb_pwd, config.its1_itsdb_name)
    itsdb2.itsdb_init(config.its2_host, config.its2_itsdb_user, config.its2_itsdb_pwd, config.its2_itsdb_name)
    # tsdb.tsdb_init(config.its1_host, config.its1_tsdb_port, config.its1_tsdb_token, config.its1_tsdb_org, config.its1_tsdb_bucket)

    server_thread = threading.Thread(target=server_thread)
    server_thread.daemon = True
    server_thread.start()

    while True:

        time.sleep(5)
        log.info(REGISTED_USER)