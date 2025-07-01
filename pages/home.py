from dash import html, dcc, register_page
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

            # 콘크리트 리스트 생성 (최대 5개까지만 표시)
            concrete_list = []
            concrete_total_count = len(project_concretes)
            concrete_display_count = min(5, concrete_total_count)
            
            if not project_concretes.empty:
                for idx, (_, concrete) in enumerate(project_concretes.iterrows()):
                    if idx >= 5:  # 5개까지만 표시
                        break
                        
                    concrete_pk = concrete["concrete_pk"]
                    concrete_sensors = df_sensors[df_sensors["concrete_pk"] == concrete_pk]
                    sensor_count = len(concrete_sensors)
                    
                    analysis_status = "분석중" if concrete["activate"] == 0 else "미분석"
                    status_color = "success" if concrete["activate"] == 0 else "secondary"
                    
                    concrete_list.append(
                        html.Tr([
                            html.Td(concrete["name"], className="py-2 text-center"),
                            html.Td(format_date(concrete["created_at"]), className="py-2 text-center"),
                            html.Td(calculate_elapsed_time(concrete["created_at"]), className="py-2 text-center"),
                            html.Td(f"{sensor_count}개", className="py-2 text-center"),
                            html.Td(dbc.Badge(analysis_status, color=status_color, className="px-2"), className="py-2 text-center")
                        ])
                    )
                
                # 5개 이상이면 "더 보기" 행 추가
                if concrete_total_count > 5:
                    concrete_list.append(
                        html.Tr([
                            html.Td([
                                dcc.Link(
                                    f"+ {concrete_total_count - 5}개 더 보기",
                                    href=f"/concrete?page={proj_pk}",
                                    className="text-primary text-decoration-none small fw-bold"
                                )
                            ], colSpan=5, className="py-2 text-center")
                        ])
                    )

            # ITS 센서 리스트 생성 (최대 5개까지만 표시)
            sensor_list = []
            sensor_total_count = len(its_sensors_df)
            sensor_display_count = min(5, sensor_total_count)
            
            if not its_sensors_df.empty:
                for idx, (_, sensor) in enumerate(its_sensors_df.iterrows()):
                    if idx >= 5:  # 5개까지만 표시
                        break
                        
                    device_id = sensor["deviceid"]
                    channel = sensor["channel"]
                    
                    # 실제 센서 데이터 수집 상태 확인
                    status_text, badge_color = check_sensor_data_status(device_id, channel)
                    
                    sensor_list.append(
                        html.Tr([
                            html.Td(device_id, className="py-2 text-center"),
                            html.Td(f"Ch.{channel}", className="py-2 text-center"),
                            html.Td(dbc.Badge(status_text, color=badge_color, className="px-2"), className="py-2 text-center")
                        ])
                    )
                
                # 5개 이상이면 "더 보기" 행 추가
                if sensor_total_count > 5:
                    sensor_list.append(
                        html.Tr([
                            html.Td([
                                dcc.Link(
                                    f"+ {sensor_total_count - 5}개 더 보기",
                                    href=f"/sensor?page={proj_pk}",
                                    className="text-primary text-decoration-none small fw-bold"
                                )
                            ], colSpan=3, className="py-2 text-center")
                        ])
                    )

            # 프로젝트 카드 생성
            projects.append(
                html.Div([
                    # 프로젝트 헤더
                    html.Div([
                        html.Div([
                            html.H4(f"📁 {row['name']}", className="mb-1 text-dark"),
                            html.P(f"생성일: {format_date(row['created_at'])}", className="text-muted mb-0")
                        ], className="d-flex flex-column"),
                        html.Div([
                            dcc.Link(
                                "분석결과 보기 →",
                                href=f"/project?page={proj_pk}",
                                className="btn btn-primary btn-sm me-2",
                                style={"boxShadow": "0 2px 4px rgba(0,0,0,0.1)"}
                            ),
                            dcc.Link(
                                "콘크리트 관리 →",
                                href=f"/concrete?page={proj_pk}",
                                className="btn btn-secondary btn-sm me-2",
                                style={"boxShadow": "0 2px 4px rgba(0,0,0,0.1)"}
                            ),
                            dcc.Link(
                                "센서 관리 →",
                                href=f"/sensor?page={proj_pk}",
                                className="btn btn-info btn-sm me-2",
                                style={"boxShadow": "0 2px 4px rgba(0,0,0,0.1)"}
                            ),
                            dcc.Link(
                                "데이터 다운로드 →",
                                href=f"/download?page={proj_pk}",
                                className="btn btn-warning btn-sm",
                                style={"boxShadow": "0 2px 4px rgba(0,0,0,0.1)"}
                            )
                        ], className="d-flex flex-wrap gap-1")
                    ], className="d-flex justify-content-between align-items-center mb-4"),
                    
                    # 콘텐츠 그리드
                    dbc.Row([
                        # 콘크리트 섹션
                        dbc.Col([
                            html.Div([
                                html.H6("🧱 콘크리트", className="mb-3 text-secondary fw-bold"),
                                html.Div([
                                    dbc.Table([
                                        html.Thead([
                                            html.Tr([
                                                html.Th("이름", className="border-0 text-muted small text-center", style={"width": "30%"}),
                                                html.Th("생성일", className="border-0 text-muted small text-center", style={"width": "20%"}),
                                                html.Th("경과시간", className="border-0 text-muted small text-center", style={"width": "20%"}),
                                                html.Th("센서", className="border-0 text-muted small text-center", style={"width": "15%"}),
                                                html.Th("분석", className="border-0 text-muted small text-center", style={"width": "15%"})
                                            ])
                                        ]),
                                        html.Tbody(concrete_list)
                                    ], className="table-sm", hover=True, borderless=True) if concrete_list else 
                                    html.P("콘크리트가 없습니다", className="text-muted small")
                                ], style={"height": "300px", "overflowY": "auto"})
                            ], className="bg-light p-3 rounded")
                        ], md=8),
                        
                        # 센서 섹션
                        dbc.Col([
                            html.Div([
                                html.H6("📡 ITS 센서", className="mb-3 text-secondary fw-bold"),
                                html.Div([
                                    dbc.Table([
                                        html.Thead([
                                            html.Tr([
                                                html.Th("Device ID", className="border-0 text-muted small text-center", style={"width": "40%"}),
                                                html.Th("채널", className="border-0 text-muted small text-center", style={"width": "30%"}),
                                                html.Th("데이터", className="border-0 text-muted small text-center", style={"width": "30%"})
                                            ])
                                        ]),
                                        html.Tbody(sensor_list)
                                    ], className="table-sm", hover=True, borderless=True) if sensor_list else 
                                    html.P("센서가 없습니다", className="text-muted small")
                                ], style={"height": "300px", "overflowY": "auto"})
                            ], className="bg-light p-3 rounded")
                        ], md=4)
                    ])
                ], className="mb-5 p-4 bg-white rounded shadow-sm border", 
                   style={"transition": "all 0.2s ease"})
            )

    # 프로젝트가 없는 경우
    if not projects:
        return html.Div([
            dbc.Container([
                # 헤더
                html.Div([
                    html.H2("📋 프로젝트 대시보드", className="mb-2"),
                    html.P(f"안녕하세요, {user_id}님!", className="text-muted mb-4")
                ], className="mb-5"),
                
                # 빈 상태
                html.Div([
                    html.Div([
                        html.H4("🏗️", className="mb-3", style={"fontSize": "3rem"}),
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
                html.H2("📋 프로젝트 대시보드", className="mb-2"),
                html.P(f"안녕하세요, {user_id}님! 총 {len(projects)}개의 프로젝트에 접근할 수 있습니다.", 
                       className="text-muted mb-4")
            ], className="mb-5"),
            
            # 프로젝트 리스트
            html.Div(projects)
            
        ], className="py-5", style={"maxWidth": "1200px"}, fluid=False)
    ], style={"backgroundColor": "#f8f9fa", "minHeight": "100vh"})
