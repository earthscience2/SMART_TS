from dash import html, dcc, register_page, dash_table
import dash_bootstrap_components as dbc
from flask import request
import pandas as pd
from datetime import datetime

import api_db
from utils.encryption import create_project_url
from utils import get_user_info

register_page(__name__, path="/", title="프로젝트 목록")

def format_date(value):
    # None, NaT, NaN 값 처리
    if value is None or pd.isna(value) or str(value) == 'NaT':
        return "N/A"
    
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y.%m.%d")
    
    # 그 외(혹시 문자열) 처리
    s = str(value).rstrip("Z")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            return "N/A"
    return dt.strftime("%Y.%m.%d")


def calculate_elapsed_time(created_at):
    """생성일로부터 경과 시간을 DD일 HH시간 형식으로 계산"""
    # None, NaT, NaN 값 처리
    if created_at is None or pd.isna(created_at) or str(created_at) == 'NaT':
        return "N/A"
    
    try:
        if isinstance(created_at, str):
            created_time = datetime.fromisoformat(created_at.replace('Z', ''))
        else:
            created_time = created_at
        
        now = datetime.now()
        elapsed = now - created_time
        days = elapsed.days
        hours = elapsed.seconds // 3600
        
        return f"{days}일 {hours}시간"
    except:
        return "N/A"


def check_sensor_data_status(device_id: str, channel: str, its_num: int = 1):
    """센서 데이터 수집 상태를 확인합니다.
    
    Args:
        device_id: 디바이스 ID
        channel: 채널 번호
        its_num: ITS 번호 (1 또는 2)
    
    Returns:
        tuple: (status_text, badge_color)
    """
    try:
        result = api_db.get_latest_sensor_data_time(device_id, channel)
        
        if result["status"] == "fail":
            return ("데이터없음", "secondary")
        
        latest_time = result["time"]
        now = datetime.now()
        
        # 시간 차이 계산 (시간 단위)
        time_diff = (now - latest_time).total_seconds() / 3600
        
        if time_diff <= 2:  # 2시간 이하
            return ("수집중", "success")
        else:  # 2시간 초과
            return ("수집불가", "danger")
            
    except Exception as e:
        print(f"Error checking sensor status for {device_id}/{channel}: {e}")
        return ("오류", "warning")






def layout(**kwargs):
    # 로그인된 사용자 정보 가져오기
    user_info = get_user_info()
    
    if not user_info['is_logged_in']:
        return dcc.Location(pathname="/login", id="redirect-login")

    # get_accessible_projects 함수를 사용하여 접근 가능한 프로젝트 조회 (ITS1과 ITS2 모두에서)
    try:
        # ITS1에서 먼저 시도
        accessible_projects_result = api_db.get_accessible_projects(user_info['user_id'], its_num=1)
        
        # ITS1에서 실패하면 ITS2에서 시도
        if accessible_projects_result["result"] != "Success":
            accessible_projects_result = api_db.get_accessible_projects(user_info['user_id'], its_num=2)
        
        if accessible_projects_result["result"] == "Success":
            its_projects_df = accessible_projects_result["projects"]
            
            # ITS 프로젝트 데이터를 로컬 형식으로 변환
            if not its_projects_df.empty:
                # ITS 프로젝트 데이터를 로컬 프로젝트 형식으로 변환
                local_projects_df = pd.DataFrame({
                    'project_pk': its_projects_df['projectid'],
                    'name': its_projects_df['projectname'],
                    'created_at': its_projects_df['regdate'],
                    'updated_at': its_projects_df['closedate'],
                    's_code': its_projects_df['projectid']  # 임시로 projectid를 s_code로 사용
                })
            else:
                local_projects_df = pd.DataFrame()
        else:
            print(f"Error getting accessible projects: {accessible_projects_result['msg']}")
            local_projects_df = pd.DataFrame()
            
    except Exception as e:
        print(f"Error getting accessible projects: {e}")
        local_projects_df = pd.DataFrame()

    # 프로젝트 통계 정보는 내부 DB를 사용하지 않으므로 기본값 설정
    if not local_projects_df.empty:
        local_projects_df['concrete_count'] = 0
        local_projects_df['sensor_count'] = 0
        
        # 수화열 관련 프로젝트만 필터링
        local_projects_df = local_projects_df[
            local_projects_df['name'].str.contains('수화열', na=False)
        ]

    projects = []

    # ITS 프로젝트 생성
    if not local_projects_df.empty:
        for _, row in local_projects_df.iterrows():
            proj_pk = row["project_pk"]
            s_code = row["s_code"]
            
            # 해당 프로젝트의 ITS 센서 리스트 조회 (프로젝트 ID 기반) - ITS1에서 먼저 시도
            its_sensors_df = api_db.get_sensor_list_for_project(proj_pk, its_num=1)
            
            # ITS1에서 센서가 없으면 ITS2에서 시도
            if its_sensors_df.empty:
                its_sensors_df = api_db.get_sensor_list_for_project(proj_pk, its_num=2)

            # 콘크리트 리스트는 내부 DB를 사용하지 않으므로 빈 리스트
            concrete_data = []

            # ITS 센서 리스트 생성 (DataTable용 데이터)
            sensor_data = []
            
            if not its_sensors_df.empty:
                for _, sensor in its_sensors_df.iterrows():
                    device_id = sensor["deviceid"]
                    channel = sensor["channel"]
                    
                    # 실제 센서 데이터 수집 상태 확인 (ITS1에서 먼저 시도)
                    status_text, badge_color = check_sensor_data_status(device_id, channel, 1)
                    
                    # ITS1에서 데이터가 없으면 ITS2에서 시도
                    if status_text == "데이터없음":
                        status_text, badge_color = check_sensor_data_status(device_id, channel, 2)
                    
                    sensor_data.append({
                        "device_id": device_id,
                        "channel": f"Ch.{channel}",
                        "structure": sensor.get("structure_name", "N/A"),
                        "status": status_text
                    })

            # 프로젝트 카드 생성
            projects.append(
                html.Div([
                    # 프로젝트 헤더
                    html.Div([
                        html.Div([
                            html.H4(f"{row['name']}", className="mb-1 text-dark"),
                            html.P(f"생성일: {format_date(row['created_at'])}", className="text-muted mb-0")
                        ], className="d-flex flex-column"),
                        html.Div([
                            dcc.Link(
                                "분석결과 확인",
                                                                    href=create_project_url("/temp", proj_pk),
                                className="btn btn-success btn-sm mt-2 me-2",
                                style={
                                    "fontSize": "12px",
                                    "fontWeight": "500",
                                    "textDecoration": "none",
                                    "textAlign": "center",
                                    "display": "flex",
                                    "alignItems": "center",
                                    "justifyContent": "center",
                                    "width": "auto",
                                    "minWidth": "fit-content"
                                }
                            ),
                            dcc.Link(
                                "해석 파일 다운로드",
                                                                    href=create_project_url("/download", proj_pk),
                                className="btn btn-warning btn-sm mt-2",
                                style={
                                    "fontSize": "12px",
                                    "fontWeight": "500",
                                    "textDecoration": "none",
                                    "textAlign": "center",
                                    "display": "flex",
                                    "alignItems": "center",
                                    "justifyContent": "center",
                                    "width": "auto",
                                    "minWidth": "fit-content"
                                }
                            )
                        ], className="mt-2 d-flex justify-content-end")
                    ], className="d-flex justify-content-between align-items-center mb-3"),
                    
                    # 콘텐츠 그리드
                    dbc.Row([
                        # 콘크리트 섹션
                        dbc.Col([
                            html.Div([
                                html.H6("콘크리트", className="mb-3 text-secondary fw-bold"),
                                html.Div([
                                    dash_table.DataTable(
                                        data=concrete_data,
                                        columns=[
                                            {"name": "이름", "id": "name", "type": "text"},
                                            {"name": "생성일", "id": "created_at", "type": "text"},
                                            {"name": "경과시간", "id": "elapsed_time", "type": "text"},
                                            {"name": "센서", "id": "sensor_count", "type": "text"},
                                            {"name": "분석", "id": "status", "type": "text"},
                                        ],
                                        style_table={"height": "200px", "overflowY": "auto"},
                                        style_cell={
                                            "textAlign": "center",
                                            "fontSize": "0.8rem",
                                            "padding": "8px 4px",
                                            "border": "none",
                                            "borderBottom": "1px solid #f1f1f0",
                                        },
                                        style_header={
                                            "backgroundColor": "#fafafa", 
                                            "fontWeight": 600,
                                            "color": "#37352f",
                                            "border": "none",
                                            "borderBottom": "1px solid #e9e9e7",
                                            "fontSize": "0.75rem",
                                        },
                                        style_data={
                                            "backgroundColor": "white",
                                            "border": "none",
                                            "color": "#37352f"
                                        },
                                        style_data_conditional=[
                                            {
                                                'if': {'row_index': 'odd'},
                                                'backgroundColor': '#fbfbfa'
                                            },
                                            {
                                                'if': {
                                                    'filter_query': '{status} = 분석중',
                                                    'column_id': 'status'
                                                },
                                                'backgroundColor': '#dcfce7',
                                                'color': '#166534',
                                                'fontWeight': '600',
                                                'borderRadius': '4px'
                                            },
                                            {
                                                'if': {
                                                    'filter_query': '{status} = 설정중',
                                                    'column_id': 'status'
                                                },
                                                'backgroundColor': '#f3f4f6',
                                                'color': '#6b7280',
                                                'fontWeight': '600',
                                                'borderRadius': '4px'
                                            }
                                        ]
                                    ) if concrete_data else 
                                    html.P("콘크리트가 없습니다", className="text-muted small text-center", style={"paddingTop": "75px"})
                                ], style={"height": "200px"}),
                                html.Div([
                                    dcc.Link(
                                        "콘크리트 모델링 추가/수정",
                                        href=create_project_url("/concrete", proj_pk),
                                        className="btn btn-secondary btn-sm mt-2 me-2",
                                        style={
                                            "fontSize": "12px",
                                            "fontWeight": "500",
                                            "textDecoration": "none",
                                            "textAlign": "center",
                                            "display": "flex",
                                            "alignItems": "center",
                                            "justifyContent": "center",
                                            "width": "auto",
                                            "minWidth": "fit-content"
                                        }
                                    ),
                                    dcc.Link(
                                        "센서 위치 추가/수정",
                                        href=create_project_url("/sensor", proj_pk),
                                        className="btn btn-info btn-sm mt-2",
                                        style={
                                            "fontSize": "12px",
                                            "fontWeight": "500",
                                            "textDecoration": "none",
                                            "textAlign": "center",
                                            "display": "flex",
                                            "alignItems": "center",
                                            "justifyContent": "center",
                                            "width": "auto",
                                            "minWidth": "fit-content"
                                        }
                                    )
                                ], className="mt-2 d-flex justify-content-end")
                            ], className="bg-light p-3 rounded")
                        ], md=8),
                        
                        # 센서 섹션
                        dbc.Col([
                            html.Div([
                                html.H6("ITS 센서", className="mb-3 text-secondary fw-bold"),
                                html.Div([
                                    dash_table.DataTable(
                                        data=sensor_data,
                                        columns=[
                                            {"name": "Device ID", "id": "device_id", "type": "text"},
                                            {"name": "채널", "id": "channel", "type": "text"},
                                            {"name": "구조", "id": "structure", "type": "text"},
                                            {"name": "데이터", "id": "status", "type": "text"},
                                        ],
                                        style_table={"height": "200px", "overflowY": "auto"},
                                        style_cell={
                                            "textAlign": "center",
                                            "fontSize": "0.8rem",
                                            "padding": "8px 4px",
                                            "border": "none",
                                            "borderBottom": "1px solid #f1f1f0",
                                        },
                                        style_header={
                                            "backgroundColor": "#fafafa", 
                                            "fontWeight": 600,
                                            "color": "#37352f",
                                            "border": "none",
                                            "borderBottom": "1px solid #e9e9e7",
                                            "fontSize": "0.75rem",
                                        },
                                        style_data={
                                            "backgroundColor": "white",
                                            "border": "none",
                                            "color": "#37352f"
                                        },
                                        style_data_conditional=[
                                            {
                                                'if': {'row_index': 'odd'},
                                                'backgroundColor': '#fbfbfa'
                                            },
                                            {
                                                'if': {
                                                    'filter_query': '{status} = 수집중',
                                                    'column_id': 'status'
                                                },
                                                'backgroundColor': '#dcfce7',
                                                'color': '#166534',
                                                'fontWeight': '600',
                                                'borderRadius': '4px'
                                            },
                                            {
                                                'if': {
                                                    'filter_query': '{status} = 수집불가',
                                                    'column_id': 'status'
                                                },
                                                'backgroundColor': '#fecaca',
                                                'color': '#991b1b',
                                                'fontWeight': '600',
                                                'borderRadius': '4px'
                                            },
                                            {
                                                'if': {
                                                    'filter_query': '{status} = 데이터없음',
                                                    'column_id': 'status'
                                                },
                                                'backgroundColor': '#f3f4f6',
                                                'color': '#6b7280',
                                                'fontWeight': '600',
                                                'borderRadius': '4px'
                                            },
                                            {
                                                'if': {
                                                    'filter_query': '{status} = 오류',
                                                    'column_id': 'status'
                                                },
                                                'backgroundColor': '#fef3c7',
                                                'color': '#92400e',
                                                'fontWeight': '600',
                                                'borderRadius': '4px'
                                            }
                                        ]
                                    ) if sensor_data else 
                                    html.P("센서가 없습니다", className="text-muted small text-center", style={"paddingTop": "75px"})
                                ], style={"height": "200px"}),
                                html.Div([
                                    dcc.Link(
                                        "센서 데이터 확인",
                                        href="/sensor_data_view",
                                        className="btn btn-danger btn-sm mt-2",
                                        style={
                                            "fontSize": "12px",
                                            "fontWeight": "500",
                                            "textDecoration": "none",
                                            "textAlign": "center",
                                            "display": "flex",
                                            "alignItems": "center",
                                            "justifyContent": "center",
                                            "width": "auto",
                                            "minWidth": "fit-content"
                                        }
                                    )
                                ], className="mt-2 d-flex justify-content-end")
                            ], className="bg-light p-3 rounded")
                        ], md=4)
                    ])
                ], className="mb-4 p-3 bg-white rounded shadow-sm border", 
                   style={"transition": "all 0.2s ease"})
            )

    # 프로젝트가 없는 경우
    if not projects:
        return html.Div([
            dbc.Container([
                # 헤더
                html.Div([
                    html.H2("프로젝트 대시보드", className="mb-2 text-center fw-bold"),
                    html.P(f"안녕하세요, {user_info['user_id']}님!", className="text-muted mb-4 text-center")
                ], className="mb-5"),
                
                # 빈 상태
                html.Div([
                    html.Div([
                        html.H4("", className="mb-3", style={"fontSize": "3rem"}),
                        html.H5("접근 가능한 프로젝트가 없습니다", className="text-muted mb-3"),
                        html.P("현재 권한으로 접근할 수 있는 프로젝트가 없습니다.", className="text-muted"),
                        html.P("관리자에게 문의하시기 바랍니다.", className="text-muted")
                    ], className="text-center py-5")
                ], className="bg-light rounded p-5")
            ], className="py-5", style={"maxWidth": "1200px"}, fluid=False)
        ], style={"backgroundColor": "#f8f9fa", "minHeight": "100vh"})

    # 메인 레이아웃
    return html.Div([
        dbc.Container([
            # 헤더
            html.Div([
                html.H2("프로젝트 대시보드", className="mb-2 text-center fw-bold"),
                html.P(f"안녕하세요, {user_info['user_id']}님! 총 {len(projects)}개의 프로젝트에 접근할 수 있습니다.", 
                       className="text-muted mb-4 text-center")
            ], className="mb-5"),
            
            # 프로젝트 리스트
            html.Div(projects)
            
        ], className="py-5", style={"maxWidth": "1200px"}, fluid=False)
    ], style={"backgroundColor": "#f8f9fa", "minHeight": "100vh"})
