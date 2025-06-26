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
    """생성일로부터 경과 시간을 DD.HH 형식으로 계산"""
    try:
        if isinstance(created_at, str):
            created_time = datetime.fromisoformat(created_at.replace('Z', ''))
        else:
            created_time = created_at
        
        now = datetime.now()
        elapsed = now - created_time
        days = elapsed.days
        hours = elapsed.seconds // 3600
        
        return f"{days:02d}.{hours:02d}"
    except:
        return "00.00"



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

            # 콘크리트 리스트 생성
            concrete_list = []
            if not project_concretes.empty:
                for _, concrete in project_concretes.iterrows():
                    concrete_pk = concrete["concrete_pk"]
                    concrete_sensors = df_sensors[df_sensors["concrete_pk"] == concrete_pk]
                    sensor_count = len(concrete_sensors)
                    
                    analysis_status = "분석중" if concrete["activate"] == 1 else "미분석"
                    status_color = "success" if concrete["activate"] == 1 else "secondary"
                    
                    concrete_list.append(
                        html.Tr([
                            html.Td(concrete["name"], className="py-2"),
                            html.Td(format_date(concrete["created_at"]), className="py-2"),
                            html.Td(calculate_elapsed_time(concrete["created_at"]), className="py-2"),
                            html.Td(f"{sensor_count}개", className="py-2"),
                            html.Td(dbc.Badge(analysis_status, color=status_color, className="px-2"), className="py-2")
                        ])
                    )

            # ITS 센서 리스트 생성
            sensor_list = []
            if not its_sensors_df.empty:
                for _, sensor in its_sensors_df.iterrows():
                    sensor_list.append(
                        html.Tr([
                            html.Td(sensor["deviceid"], className="py-2"),
                            html.Td(f"Ch.{sensor['channel']}", className="py-2"),
                            html.Td(dbc.Badge("정상", color="success", className="px-2"), className="py-2")
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
                                "프로젝트 열기 →",
                                href=f"/project?page={proj_pk}",
                                className="btn btn-outline-primary btn-sm"
                            )
                        ])
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
                                                html.Th("이름", className="border-0 text-muted small"),
                                                html.Th("생성일", className="border-0 text-muted small"),
                                                html.Th("경과일", className="border-0 text-muted small"),
                                                html.Th("센서", className="border-0 text-muted small"),
                                                html.Th("분석", className="border-0 text-muted small")
                                            ])
                                        ]),
                                        html.Tbody(concrete_list)
                                    ], className="table-sm", hover=True, borderless=True) if concrete_list else 
                                    html.P("콘크리트가 없습니다", className="text-muted small")
                                ], style={"maxHeight": "300px", "overflowY": "auto"})
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
                                                html.Th("Device ID", className="border-0 text-muted small"),
                                                html.Th("채널", className="border-0 text-muted small"),
                                                html.Th("수집", className="border-0 text-muted small")
                                            ])
                                        ]),
                                        html.Tbody(sensor_list)
                                    ], className="table-sm", hover=True, borderless=True) if sensor_list else 
                                    html.P("센서가 없습니다", className="text-muted small")
                                ], style={"maxHeight": "300px", "overflowY": "auto"})
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
