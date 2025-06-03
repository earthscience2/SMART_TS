
"""
MIT License

© 2024 SMARTC&S Co., Ltd

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# To use this program, you must:
# 
# Apply for membership in the ITS system and receive authorization from an administrator.
# Obtain the configuration file config.ini for basic connection settings from the administrator.
# Obtain the SSL certificate file for secure communication.

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
command_get_project_structure_list = 'get_project_structure_list'
command_download_sensor_data = 'download_sensordata'
###

def run_demo_program():
    api.run_demo_program()

def run_self_program():

    # Input your ITS user_id and user_password
    user_id = 'cbk4689'
    user_pass = 'qudrhks7460!@'

    # Load Configuration and Certficate
    config.config_load()
    config.certfile

    # TCP Connection
    ITS_CLIENT = tcp_client.TCPClient(config.SERVER_IP, config.SERVER_PORT, config.ITS_NUM, config.certfile)

    # receive_messages module
    client_thread = threading.Thread(target=ITS_CLIENT.receive_messages)
    client_thread.daemon = True
    client_thread.start()

    time.sleep(1)

    # User Authentication:
    # Verification that you are a legitimate user of the ITS platform and have the appropriate permissions to access the data.
    # If you do not successfully log in, you will not be able to use any features.
    ITS_CLIENT.set_user_password(user_id, user_pass)
    result = ITS_CLIENT.message(command_login)

    if result['result'] != 'Success':
        print(f"Login Failed({result['msg']})")
        return
    else:
        print("Login Success")

    # It shows a list of all projects you have data access permissions for.
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

    # From the retrieved projects, it shows a list of all structures under the specified project using the project ID(format = 'P_****').
    result = ITS_CLIENT.message(command_get_structure_list, projectid = '****')
    if result['result'] != 'Success':
        print(f"Login Failed({result['msg']})")
        return
    elif 'data' in result.keys():
        data = result['data']
        df = pd.DataFrame(data)
        df.reset_index(inplace=True)

        api.print_table(df)

    # It retrieves the data of all sensors within a project for a specified period and downloads it as a CSV file. projectid('P_****')
    result = ITS_CLIENT.message_getdata(command_download_sensor_data, start_date='20240701', end_date='20240705', \
                                        projectid= '******', structureid = None)
    
    # It retrieves the data of all sensors within a Structure for a specified period and downloads it as a CSV file. structureid('S_****')
    result = ITS_CLIENT.message_getdata(command_download_sensor_data, start_date='20240701', end_date='20240705', \
                                        projectid= None, structureid = '******')
   
    # It shows and downloads a list of all projects and structures you have data access permissions for.
    result = ITS_CLIENT.message(command_get_project_structure_list)
    if result['result'] != 'Success':
        print(f"Login Failed({result['msg']})")
        return
    elif 'data' in result.keys():
        data = result['data']
        df = pd.DataFrame(data)
        df.reset_index(inplace=True)
        df['regdate'] = pd.to_datetime(df['regdate'], unit='ms', errors='coerce')
        df['closedate'] = pd.to_datetime(df['closedate'], unit='ms', errors='coerce')
        df.to_csv("./structure_info.csv", index=False)
        api.print_table(df)

if __name__ == '__main__':

    # Functions for writing your own source code using the provided API.
    run_demo_program()

    # Functions that provide basic features in a CLI format.
    #run_self_program()
    


