from dash import html, dcc, register_page, dash_table
import dash_bootstrap_components as dbc
from flask import request
import pandas as pd
from datetime import datetime

import api_db

register_page(__name__, path="/", title="프로젝트 목록")

def format_date(value):
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y.%m.%d")
    # 그 외(혹시 문자열) 처리
    s = str(value).rstrip("Z")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.strptime(s, "%Y-%m-%d")
    return dt.strftime("%Y.%m.%d")


def calculate_elapsed_time(created_at):
    """생성일로부터 경과 시간을 DD일 HH시간 형식으로 계산"""
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
        return "0일 0시간"


def check_sensor_data_status(device_id: str, channel: str):
    """센서 데이터 수집 상태를 확인합니다.
    
    Args:
        device_id: 디바이스 ID
        channel: 채널 번호
    
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



def filter_local_projects(grade: str, auth_list: list) -> pd.DataFrame:
    """사용자 권한에 따라 로컬 프로젝트를 필터링합니다.
    
    Args:
        grade: 사용자 권한 (AD, CM, CT, US 등)
        auth_list: 사용자가 접근 가능한 권한 목록
    
    Returns:
        필터링된 프로젝트 DataFrame
    """
    # 모든 프로젝트 가져오기
    all_projects_df = api_db.get_project_data()
    
    # 1. AD 권한이면 모든 프로젝트 반환
    if grade == "AD":
        return all_projects_df
    
    # 2. CM 또는 CT 권한인 경우
    if grade in ["CM", "CT"]:
        # 접근 가능한 프로젝트 ID 추출
        project_ids = [auth_id for auth_id in auth_list if auth_id.startswith('P_')]
        
        # P_000078에 접근 가능하면 모든 프로젝트 반환
        if "P_000078" in project_ids:
            return all_projects_df
        
        # 접근 가능한 구조 ID 추출
        structure_ids = [auth_id for auth_id in auth_list if auth_id.startswith('S_')]
        
        if structure_ids:
            # s_code가 구조 ID와 매칭되는 프로젝트만 필터링
            filtered_projects = all_projects_df[
                all_projects_df['s_code'].isin(structure_ids)
            ]
            return filtered_projects
    
    # 3. 기타 권한 (US 등)의 경우 빈 DataFrame 반환
    return pd.DataFrame()


def layout():
    # 로그인된 사용자 정보 가져오기
    user_id = request.cookies.get("login_user")
    if not user_id:
        return dcc.Location(pathname="/login", id="redirect-login")

    # 사용자 권한 정보 조회 (로컬 프로젝트 필터링용)
    try:
        from api_db import _get_its_engine, text
        
        eng = _get_its_engine(1)
        user_query = text("SELECT userid, grade FROM tb_user WHERE userid = :uid LIMIT 1")
        df_user = pd.read_sql(user_query, eng, params={"uid": user_id})
        
        if df_user.empty:
            grade = "AD"  # 기본값으로 관리자 권한
            auth_list = []
        else:
            grade = df_user.iloc[0]["grade"]
            if grade == "AD":
                auth_list = []
            else:
                auth_query = text("SELECT id FROM tb_sensor_auth_mapping WHERE userid = :uid")
                df_auth = pd.read_sql(auth_query, eng, params={"uid": user_id})
                auth_list = df_auth["id"].tolist() if not df_auth.empty else []
        
    except Exception as e:
        print(f"Error getting user info: {e}")
        grade = "AD"
        auth_list = []
    
    # 로컬 프로젝트 필터링 로직
    local_projects_df = filter_local_projects(grade, auth_list)

    # 프로젝트 통계 정보 가져오기
    try:
        projects_with_stats = api_db.get_project_data_with_stats()
        # 로컬 프로젝트와 통계 정보 병합
        if not local_projects_df.empty and not projects_with_stats.empty:
            local_projects_df = local_projects_df.merge(
                projects_with_stats[['project_pk', 'concrete_count', 'sensor_count']], 
                on='project_pk', 
                how='left'
            )
            # NaN 값을 0으로 채우기
            local_projects_df['concrete_count'] = local_projects_df['concrete_count'].fillna(0).astype(int)
            local_projects_df['sensor_count'] = local_projects_df['sensor_count'].fillna(0).astype(int)
    except Exception as e:
        print(f"Error loading project statistics: {e}")
        # 통계 정보 로드 실패 시 기본값 설정
        local_projects_df['concrete_count'] = 0
        local_projects_df['sensor_count'] = 0

    projects = []

    # 로컬 프로젝트 생성
    if not local_projects_df.empty:
        # 콘크리트 및 센서 메타데이터 로드
        df_concrete = api_db.get_concrete_data()
        df_sensors = api_db.get_sensors_data()

        for _, row in local_projects_df.iterrows():
            proj_pk = row["project_pk"]
            s_code = row["s_code"]
            
            # 해당 프로젝트의 콘크리트 데이터
            project_concretes = df_concrete[df_concrete["project_pk"] == str(proj_pk)]
            
            # P_000078 프로젝트에서 해당 구조의 ITS 센서 리스트 조회
            its_sensors_df = api_db.get_sensor_list_for_structure(s_code)

            # 콘크리트 리스트 생성 (DataTable용 데이터)
            concrete_data = []
            
            if not project_concretes.empty:
                for _, concrete in project_concretes.iterrows():
                    concrete_pk = concrete["concrete_pk"]
                    concrete_sensors = df_sensors[df_sensors["concrete_pk"] == concrete_pk]
                    sensor_count = len(concrete_sensors)
                    
                    analysis_status = "분석중" if concrete["activate"] == 0 else "미분석"
                    
                    concrete_data.append({
                        "name": concrete["name"],
                        "created_at": format_date(concrete["created_at"]),
                        "elapsed_time": calculate_elapsed_time(concrete["created_at"]),
                        "sensor_count": f"{sensor_count}개",
                        "status": analysis_status
                    })

            # ITS 센서 리스트 생성 (DataTable용 데이터)
            sensor_data = []
            
            if not its_sensors_df.empty:
                for _, sensor in its_sensors_df.iterrows():
                    device_id = sensor["deviceid"]
                    channel = sensor["channel"]
                    
                    # 실제 센서 데이터 수집 상태 확인
                    status_text, badge_color = check_sensor_data_status(device_id, channel)
                    
                    sensor_data.append({
                        "device_id": device_id,
                        "channel": f"Ch.{channel}",
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
                            # 분석 결과 드롭다운
                            html.Div([
                                dbc.Row([
                                    dbc.Col([
                                        dcc.Link(
                                            html.Div([
                                                html.Span("🌡️", className="me-2", style={"fontSize": "16px"}),
                                                html.Span("온도분석", style={"fontSize": "13px", "fontWeight": "500"})
                                            ]),
                                            href=f"/temp?page={proj_pk}",
                                            className="btn btn-outline-primary btn-sm w-100",
                                            style={
                                                "textDecoration": "none",
                                                "borderRadius": "6px",
                                                "padding": "8px 18px",
                                                "height": "40px",
                                                "display": "flex",
                                                "alignItems": "center",
                                                "justifyContent": "center",
                                                "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
                                                "transition": "all 0.2s ease"
                                            }
                                        )
                                    ], width=3),
                                    dbc.Col([
                                        dcc.Link(
                                            html.Div([
                                                html.Span("🔬", className="me-1", style={"fontSize": "16px"}),
                                                html.Span("응력분석", style={"fontSize": "13px", "fontWeight": "500"})
                                            ]),
                                            href=f"/stress?page={proj_pk}",
                                            className="btn btn-outline-warning btn-sm w-100",
                                            style={
                                                "textDecoration": "none",
                                                "borderRadius": "6px",
                                                "padding": "8px 18px",
                                                "height": "40px",
                                                "display": "flex",
                                                "alignItems": "center",
                                                "justifyContent": "center",
                                                "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
                                                "transition": "all 0.2s ease",
                                                "whiteSpace": "nowrap",
                                                "overflow": "hidden",
                                                "textOverflow": "ellipsis"
                                            }
                                        )
                                    ], width=3),
                                    dbc.Col([
                                        dcc.Link(
                                            html.Div([
                                                html.Span("⚠️", className="me-2", style={"fontSize": "16px"}),
                                                html.Span("TCI분석", style={"fontSize": "13px", "fontWeight": "500"})
                                            ]),
                                            href=f"/tci?page={proj_pk}",
                                            className="btn btn-outline-danger btn-sm w-100",
                                            style={
                                                "textDecoration": "none",
                                                "borderRadius": "6px",
                                                "padding": "8px 18px",
                                                "height": "40px",
                                                "display": "flex",
                                                "alignItems": "center",
                                                "justifyContent": "center",
                                                "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
                                                "transition": "all 0.2s ease"
                                            }
                                        )
                                    ], width=3),
                                    dbc.Col([
                                        dcc.Link(
                                            html.Div([
                                                html.Span("💪", className="me-1", style={"fontSize": "16px"}),
                                                html.Span("강도분석", style={"fontSize": "13px", "fontWeight": "500"})
                                            ]),
                                            href=f"/strength?page={proj_pk}",
                                            className="btn btn-outline-success btn-sm w-100",
                                            style={
                                                "textDecoration": "none",
                                                "borderRadius": "6px",
                                                "padding": "8px 18px",
                                                "height": "40px",
                                                "display": "flex",
                                                "alignItems": "center",
                                                "justifyContent": "center",
                                                "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
                                                "transition": "all 0.2s ease",
                                                "whiteSpace": "nowrap",
                                                "overflow": "hidden",
                                                "textOverflow": "ellipsis"
                                            }
                                        )
                                    ], width=3)
                                ], className="g-2")
                            ], className="bg-light p-2 rounded border", style={"borderColor": "#e9ecef"}),
                            dcc.Link(
                                "해석 파일 다운로드",
                                href=f"/download?page={proj_pk}",
                                className="btn btn-warning btn-sm text-center",
                                style={
                                    "boxShadow": "0 2px 4px rgba(0,0,0,0.1)",
                                    "borderRadius": "6px",
                                    "fontWeight": "500",
                                    "textDecoration": "none",
                                    "textAlign": "center !important",
                                    "display": "flex",
                                    "alignItems": "center",
                                    "justifyContent": "center",
                                    "padding": "8px 18px",
                                    "height": "40px",
                                    "fontSize": "13px"
                                }
                            )
                        ], className="d-flex flex-wrap gap-1 align-items-center")
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
                                        style_table={"height": "180px", "overflowY": "auto"},
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
                                                    'filter_query': '{status} = 미분석',
                                                    'column_id': 'status'
                                                },
                                                'backgroundColor': '#f3f4f6',
                                                'color': '#6b7280',
                                                'fontWeight': '600',
                                                'borderRadius': '4px'
                                            }
                                        ]
                                    ) if concrete_data else 
                                    html.P("콘크리트가 없습니다", className="text-muted small text-center", style={"paddingTop": "50px"})
                                ], style={"height": "150px"}),
                                html.Div([
                                    dcc.Link(
                                        "콘크리트 모델링 추가/수정",
                                        href=f"/concrete?page={proj_pk}",
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
                                        href=f"/sensor?page={proj_pk}",
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
                                            {"name": "데이터", "id": "status", "type": "text"},
                                        ],
                                        style_table={"height": "180px", "overflowY": "auto"},
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
                                    html.P("센서가 없습니다", className="text-muted small text-center", style={"paddingTop": "50px"})
                                ], style={"height": "150px"}),
                                html.Div([
                                    dcc.Link(
                                        "센서 데이터 확인",
                                        href=f"/sensor?page={proj_pk}",
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
                    html.H2("프로젝트 대시보드", className="mb-2"),
                    html.P(f"안녕하세요, {user_id}님!", className="text-muted mb-4")
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
                html.H2("프로젝트 대시보드", className="mb-2"),
                html.P(f"안녕하세요, {user_id}님! 총 {len(projects)}개의 프로젝트에 접근할 수 있습니다.", 
                       className="text-muted mb-4")
            ], className="mb-5"),
            
            # 프로젝트 리스트
            html.Div(projects)
            
        ], className="py-5", style={"maxWidth": "1200px"}, fluid=False)
    ], style={"backgroundColor": "#f8f9fa", "minHeight": "100vh"})
