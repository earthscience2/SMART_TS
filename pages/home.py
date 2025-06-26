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

    cards = []

    # 로컬 프로젝트 카드 생성
    if not local_projects_df.empty:
        cards.append(html.H3("프로젝트 목록", className="text-center mb-4 text-info"))
        
        # 콘크리트 및 센서 메타데이터 로드
        df_concrete = api_db.get_concrete_data()
        df_sensors = api_db.get_sensors_data()

        for _, row in local_projects_df.iterrows():
            proj_pk = row["project_pk"]
            # 해당 프로젝트의 콘크리트 개수
            conc_cnt = df_concrete[df_concrete["project_pk"] == str(proj_pk)].shape[0]
            # 해당 콘크리트의 sensor 개수
            conc_ids = df_concrete[df_concrete["project_pk"] == str(proj_pk)]["concrete_pk"].tolist()
            sensor_cnt = df_sensors[df_sensors["concrete_pk"].isin(conc_ids)].shape[0]

            card_style = {
                "width": "200px",
                "height": "200px",
                "backgroundColor": "#f0f8ff",
                "borderRadius": "0.5rem",
                "overflow": "hidden",
                "transition": "transform 0.2s, box-shadow 0.2s",
                "boxShadow": "0 4px 8px rgba(135, 206, 250, 0.4)",
                "cursor": "pointer",
                "textDecoration": "none"
            }

            cards.append(
                dbc.Col([
                    dcc.Link(
                        href=f"/project?page={proj_pk}",
                        style={"textDecoration": "none"},
                        children=dbc.Card(
                            dbc.CardBody([
                                html.H5(
                                    row["name"],
                                    className="card-title fw-bold fs-5 mb-2"
                                ),
                                html.P(
                                    f"생성일: {format_date(row['created_at'])}",
                                    className="card-text fs-7 mb-1"
                                ),
                                html.P(
                                    f"콘크리트 : {conc_cnt} 개",
                                    className="card-text fs-7 mb-1"
                                ),
                                html.P(
                                    f"센서 : {sensor_cnt} 개",
                                    className="card-text fs-7 mb-1"
                                ),
                            ], className="d-flex flex-column align-items-center justify-content-center h-100"),
                            style=card_style,
                            className="project-card mb-4"
                        )
                    )
                ], xs=12, sm=6, md=3, lg=3)
            )

    # 프로젝트가 없는 경우
    if not cards:
        return html.Div([
            dbc.Container([
                html.H2(f"프로젝트 목록 ({user_id})", className="text-center mb-4"),
                dbc.Alert([
                    html.H4("접근 가능한 프로젝트가 없습니다", className="alert-heading"),
                    html.P("현재 권한으로 접근 가능한 프로젝트가 없습니다."),
                    html.Hr(),
                    html.P("관리자에게 문의하시기 바랍니다.", className="mb-0")
                ], color="info", className="mt-5")
            ])
        ])

    # 카드 그리드 생성
    card_grid = dbc.Row(
        cards,
        justify="center",
        style={
            "rowGap": "4rem",       # 세로 간격
            "columnGap": "4rem"     # 가로 간격
        }
    )

    return html.Div([
        dbc.Container(
            fluid=True,
            className="mt-5 d-flex flex-column align-items-center",
            children=[
                html.H2(f"프로젝트 목록 ({user_id})", className="text-center mb-4"),
                card_grid  # 프로젝트 카드들
            ]
        )
    ])
