import os
import threading
import time
import pandas as pd


from ITS_CLI import config
from ITS_CLI import tcp_client
from ITS_CLI import api

###
command_login = 'login'
command_get_project_list = 'get_project_list'
command_get_structure_list = 'get_structure_list'
command_get_deivce_list = 'get_device_list'
command_get_project_structure_list = 'get_project_structure_list'
command_download_sensor_data = 'download_sensordata'
command_download_sensor_data_as_df = 'download_sensordata_as_df'
command_query_sensor_data_by_device = 'query_device_channel_data'
###

def run_self_program():

    user_id = 'cbk4689'
    user_pass = 'qudrhks7460!@'

    config.config_load()
    config.certfile

    ITS_CLIENT = tcp_client.TCPClient(config.SERVER_IP, config.SERVER_PORT, config.ITS_NUM, config.certfile)

    client_thread = threading.Thread(target=ITS_CLIENT.receive_messages)
    client_thread.daemon = True  # This ensures the thread will exit when the main program exits
    client_thread.start()

    time.sleep(1)

    ITS_CLIENT.set_user_password(user_id, user_pass)

    result = ITS_CLIENT.message(command_login)

    if result['result'] != 'Success':
        print(f"Login Failed({result['msg']})")
        return
    else:
        print("Login Success")

    result = ITS_CLIENT.message(command_get_project_list)
    if result['result'] != 'Success':
        print(f"Login Failed({result['msg']})")
        return
    elif 'data' in result.keys():
        data = result['data']
        df = pd.DataFrame(data)
        df.reset_index(inplace=True)
        df['regdate'] = pd.to_datetime(df['regdate'], unit='ms', errors='coerce')
        df['closedate'] = pd.to_datetime(df['closedate'], unit='ms', errors='coerce')

        api.print_table(df)

    result = ITS_CLIENT.message(command_get_structure_list, projectid = 'P_000078')
    if result['result'] != 'Success':
        print(f"Login Failed({result['msg']})")
        return
    elif 'data' in result.keys():
        data = result['data']
        df = pd.DataFrame(data)
        df.reset_index(inplace=True)

        api.print_table(df)

    result = ITS_CLIENT.message(command_get_structure_list, projectid = 'P_000078')
    if result['result'] != 'Success':
        print(f"Login Failed({result['msg']})")
        return
    elif 'data' in result.keys():
        data = result['data']
        df = pd.DataFrame(data)
        df.reset_index(inplace=True)

        api.print_table(df)

    # result = ITS_CLIENT.message_getdata(command_download_sensor_data, start_date='20240701', end_date='20240705', \
    #                                     projectid= 'P_000002', structureid = None)

    # result = ITS_CLIENT.message_getdata(command_download_sensor_data, start_date='20240701', end_date='20240705', \
    #                                     projectid= None, structureid = 'S_000004')
    
    # result = ITS_CLIENT.message_getdata(command_download_sensor_data_as_df, start_date='20240701', end_date='20240705', \
    #                                     projectid= None, structureid = 'S_000004')

    result = ITS_CLIENT.message(command_get_deivce_list, projectid= None, structureid = 'S_000455')
    if result['result'] != 'Success':
        print(f"Login Failed({result['msg']})")
        return
    elif 'data' in result.keys():
        data = result['data']
        df = pd.DataFrame(data)
        df.reset_index(inplace=True)
        api.print_table(df[['deviceid', 'channel', 'device_type']].drop_duplicates())

    
    result = ITS_CLIENT.message_getdata(command_query_sensor_data_by_device, start_date=None, end_date=None, \
                                        projectid= None, structureid = None, deviceid='shytest01', channel=1)
    print(result)
    # result = ITS_CLIENT.message(command_get_project_structure_list)
    # if result['result'] != 'Success':
    #     print(f"Login Failed({result['msg']})")
    #     return
    # elif 'data' in result.keys():
    #     data = result['data']
    #     df = pd.DataFrame(data)
    #     df.reset_index(inplace=True)
    #     df['regdate'] = pd.to_datetime(df['regdate'], unit='ms', errors='coerce')
    #     df['closedate'] = pd.to_datetime(df['closedate'], unit='ms', errors='coerce')

    #     df.to_csv("./structure_info.csv", index=False)

    #     api.print_table(df)
   

def run_demo_program():
    api.run_demo_program()

if __name__ == '__main__':

    # run_demo_program()

    run_self_program()
    