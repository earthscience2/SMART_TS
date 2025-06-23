import mysqldb
import time
import threading
from logger import Logger as log

itsdb_conn = None

def itsdb_init(host, user, pwd, dbname):
    global itsdb_conn

    itsdb_conn = mysqldb.Mysqlhandler(host, user, pwd, dbname)
    itsdb_conn.connect()

def get_project_list(project_list = None):
    if project_list == None:
        sql = f"SELECT p.projectid, p.projectname, p.regdate, p.closedate \
            FROM tb_project p;"
    else:
        project_ids_str = ', '.join(["'" + str(id) + "'" for id in project_list])
        sql = f"SELECT p.projectid, p.projectname, p.regdate, p.closedate \
            FROM tb_project p \
            WHERE p.projectid IN ({project_ids_str});"

    try:
        df_result = itsdb_conn.do_select_pd(sql)
    except Exception as e:
        log.error(sql)
        log.error(str(e))
        return None

    return df_result

'''
def get_structure_list(project_list = None):
    if project_list == None:
        sql = f"SELECT s.stid FROM tb_structure s JOIN tb_group g ON s.groupid = g.groupid"
    else:
        project_ids_str = ', '.join(["'" + str(id) + "'" for id in project_list])
        sql = f"SELECT s.stid FROM tb_structure s JOIN tb_group g ON s.groupid = g.groupid \
            WHERE g.projectid IN ({project_ids_str});"

    try:
        df_result = itsdb_conn.do_select_pd(sql)
    except Exception as e:
        log.error(sql)
        log.error(str(e))
        return None

    return df_result

def get_stid_list(project_id):
    sql = "SELECT s.stid \
        FROM tb_structure s \
        JOIN tb_group g ON s.groupid = g.groupid \
        WHERE g.projectid = \'{}\';".format(project_id)

    try:
        df_result = itsdb_conn.do_select_pd(sql)
    except Exception as e:
        log.error(sql)
        log.error(str(e))
        return None

    return df_result
'''
def get_stid_list(project_id):
    sql = "SELECT s.stid, s.stname, s.staddr \
        FROM tb_structure s \
        JOIN tb_group g ON s.groupid = g.groupid \
        WHERE g.projectid = \'{}\';".format(project_id)

    try:
        df_result = itsdb_conn.do_select_pd(sql)
    except Exception as e:
        log.error(sql)
        log.error(str(e))
        return None

    return df_result

def get_stid_list_from_project_list(project_list):
    project_ids_str = ', '.join(["'" + str(id) + "'" for id in project_list])
    sql = f"SELECT s.stid, s.stname, s.staddr \
        FROM tb_structure s \
        JOIN tb_group g ON s.groupid = g.groupid \
        WHERE g.projectid IN ({project_ids_str});"

    try:
        df_result = itsdb_conn.do_select_pd(sql)
    except Exception as e:
        log.error(sql)
        log.error(str(e))
        return None

    return df_result

def get_project_stid_list(project_list = None):
    if project_list == None:
        sql = f"SELECT tp.projectid, tp.projectname, s.stid, s.stname, s.staddr, tp.regdate, tp.closedate FROM tb_structure s \
            JOIN tb_group g ON s.groupid = g.groupid \
            JOIN tb_project tp ON g.projectid = tp.projectid;"
    else:
        project_ids_str = ', '.join(["'" + str(id) + "'" for id in project_list])
        sql = f"SELECT tp.projectid, tp.projectname, s.stid, s.stname, s.staddr, tp.regdate, tp.closedate FROM tb_structure s \
            JOIN tb_group g ON s.groupid = g.groupid \
            JOIN tb_project tp ON g.projectid = tp.projectid \
            WHERE tp.projectid IN ({project_ids_str});"

    try:
        df_result = itsdb_conn.do_select_pd(sql)
    except Exception as e:
        log.error(sql)
        log.error(str(e))
        return None

    return df_result

def get_sensor_list(group_code: str, id: str) -> list:
    result = []

    group_codes = ("P", "G", "S", "D")
    if group_code not in group_codes:
        return result

    if group_code == "P":
        group = "p.projectid"
    elif group_code == "G":
        group = "g.groupid"
    elif group_code == "S":
        group = "st.stid"
    elif group_code == "D":
        group = "d.deviceid"
    else:
        return result

    sql = f"SELECT s.deviceid, CAST(IFNULL(s.channel,1) AS CHAR) AS channel \
        , d.devicetype AS device_type, tddt.data_type \
        , IF(tdc.modelname IS NOT NULL,'Y','N') AS is3axis \
        FROM tb_sensor s \
        JOIN tb_device d ON d.deviceid = s.deviceid \
        JOIN tb_structure st ON st.stid = d.stid \
        JOIN tb_group g ON g.groupid = st.groupid \
        JOIN tb_project p ON p.projectid = g.projectid \
        LEFT JOIN tb_device_data_type tddt ON d.devicetype = tddt.device_type \
        LEFT JOIN tb_device_catalog tdc ON tdc.idx = d.modelidx AND tdc.modelname IN ('SSC-320HR(2.0g)','SSC-320HR(5.0g)','SSC-320(3.0g)') \
        WHERE {group} = '{id}' \
        AND d.manageyn = 'Y' AND s.manageyn = 'Y' \
        ORDER BY p.projectid, g.groupid, st.stid, d.deviceid, s.channel;"
    
    try:
        df_result = itsdb_conn.do_select_pd(sql)
    except Exception as e:
        log.error(sql)
        log.error(str(e))
        return None

    return df_result

def get_device_info(group_code: str, id: str):

    result = []

    group_codes = ("P", "G", "S", "D")
    if group_code not in group_codes:
        return result

    if group_code == "P":
        group = "p.projectid"
    elif group_code == "G":
        group = "g.groupid"
    elif group_code == "S":
        group = "st.stid"
    elif group_code == "D":
        group = "d.deviceid"
    else:
        return result

    sql = f"SELECT s.deviceid, CAST(IFNULL(s.channel,1) AS CHAR) AS channel \
        , s.sensortype, s.sensoralias, s.sn \
        FROM tb_sensor s \
        JOIN tb_device d ON d.deviceid = s.deviceid \
        JOIN tb_structure st ON st.stid = d.stid \
        JOIN tb_group g ON g.groupid = st.groupid \
        JOIN tb_project p ON p.projectid = g.projectid \
        LEFT JOIN tb_device_data_type tddt ON d.devicetype = tddt.device_type \
        LEFT JOIN tb_device_catalog tdc ON tdc.idx = d.modelidx AND tdc.modelname IN ('SSC-320HR(2.0g)','SSC-320HR(5.0g)','SSC-320(3.0g)') \
        WHERE {group} = '{id}' \
        AND d.manageyn = 'Y' AND s.manageyn = 'Y' \
        ORDER BY p.projectid, g.groupid, st.stid, d.deviceid, s.channel;"
    
    try:
        df_result = itsdb_conn.do_select_pd(sql)
    except Exception as e:
        log.error(sql)
        log.error(str(e))
        return None

    return df_result
    
def user_regist(user):
    sql = f"SELECT userid, userpw, grade, authstartdate, authenddate FROM tb_user WHERE userid = '{user}';"
    
    try:
        df_result = itsdb_conn.do_select_pd(sql)
    except Exception as e:
        log.error(sql)
        log.error(str(e))
        return None

    return df_result

def check_auth_project_structure(user):
    sql = f"SELECT userid, satype, id, auth FROM tb_sensor_auth_mapping WHERE userid = '{user}';"
    
    try:
        df_result = itsdb_conn.do_select_pd(sql)
    except Exception as e:
        log.error(sql)
        log.error(str(e))
        return None

    return df_result

def get_sensor_meta(deviceid, channel):
    sql = f"""
        SELECT 
            s.deviceid, 
            s.channel, 
            d.devicetype AS device_type,
            tddt.data_type,
            IF(tdc.modelname IS NOT NULL, 'Y', 'N') AS is3axis
        FROM tb_sensor s
        JOIN tb_device d ON d.deviceid = s.deviceid
        LEFT JOIN tb_device_data_type tddt ON d.devicetype = tddt.device_type
        LEFT JOIN tb_device_catalog tdc ON tdc.idx = d.modelidx AND tdc.modelname IN ('SSC-320HR(2.0g)','SSC-320HR(5.0g)','SSC-320(3.0g)')
        WHERE s.deviceid = '{deviceid}' AND s.channel = '{channel}'
        AND d.manageyn = 'Y' AND s.manageyn = 'Y'
        LIMIT 1;
    """
    try:
        df_result = itsdb_conn.do_select_pd(sql)
        return df_result
    except Exception as e:
        log.error(f"[get_sensor_meta] SQL ERROR: {sql}")
        log.error(str(e))
        return None
    
def get_sensor_structure_info(deviceid, channel):
    sql = f"""
        SELECT 
            s.deviceid, 
            s.channel, 
            st.stid, 
            p.projectid
        FROM tb_sensor s
        JOIN tb_device d ON d.deviceid = s.deviceid
        JOIN tb_structure st ON st.stid = d.stid
        JOIN tb_group g ON g.groupid = st.groupid
        JOIN tb_project p ON p.projectid = g.projectid
        WHERE s.deviceid = '{deviceid}' AND s.channel = '{channel}'
        AND d.manageyn = 'Y' AND s.manageyn = 'Y'
        LIMIT 1;
    """
    try:
        df_result = itsdb_conn.do_select_pd(sql)
        return df_result
    except Exception as e:
        log.error(f"[get_sensor_structure_info] SQL ERROR: {sql}")
        log.error(str(e))
        return None
'''
def get_project_list():
    sql = "SELECT p.projectid, p.projectname, p.regdate, p.closedate \
        FROM tb_project p;"

    try:
        df_result = itsdb_conn.do_select_pd(sql)
    except Exception as e:
        log.error(sql)
        log.error(str(e))
        return None

    return df_result
'''
if __name__ == '__main__':
    itsdb_init('112.166.16.97', 'smart', 'smart001', 'itsdb')

    result = get_project_stid_list()
    print(result)

    temp = ['P_000002', 'P_000003']
    result = get_project_stid_list(temp)
    print(result)
