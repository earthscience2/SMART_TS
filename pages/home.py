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


def layout():
    # 로그인된 사용자 정보 가져오기
    user_id = request.cookies.get("login_user")
    if not user_id:
        return dcc.Location(pathname="/login", id="redirect-login")

    # 사용자 인증 정보 가져오기
    auth_result = api_db.authenticate_user(user_id, "dummy", its_num=1)  # 비밀번호는 이미 확인됨
    if auth_result["result"] != "Success":
        return dcc.Location(pathname="/login", id="redirect-login")
    
    grade = auth_result["grade"]
    auth_list = auth_result["auth"]

    # 사용자가 접근 가능한 ITS 프로젝트 목록 조회
    its_projects_result = api_db.get_accessible_projects(user_id, its_num=1)
    
    # get_project_structure_list 결과 가져오기
    try:
        project_structure_df = api_db.get_project_structure_list(its_num=1, allow_list=auth_list, grade=grade)
    except Exception as e:
        project_structure_df = pd.DataFrame()
    
    if its_projects_result["result"] != "Success" and project_structure_df.empty:
        # 권한이 없거나 오류가 발생한 경우
        return html.Div([
            dbc.Container([
                dbc.Alert([
                    html.H4("접근 권한 없음", className="alert-heading"),
                    html.P(its_projects_result["msg"]),
                    html.Hr(),
                    html.P("관리자에게 문의하시기 바랍니다.", className="mb-0")
                ], color="warning", className="mt-5")
            ])
        ])

    # ITS 프로젝트가 있는 경우 표시
    its_projects_df = its_projects_result.get("projects", pd.DataFrame())
    
    # 기존 로컬 프로젝트도 함께 표시 (선택적)
    local_projects_df = api_db.get_project_data()

    sections = []

    # 1. 프로젝트-구조 목록 섹션 (get_project_structure_list 결과)
    if not project_structure_df.empty:
        sections.append(html.H3("ITS 프로젝트 구조 목록", className="text-center mb-4 text-success"))
        
        # 테이블 형태로 표시
        table_data = []
        for _, row in project_structure_df.iterrows():
            table_data.append([
                row["projectid"],
                row["projectname"], 
                row["stid"],
                row["stname"],
                row["staddr"],
                format_date(row["regdate"]),
                "진행중" if pd.isna(row["closedate"]) else "완료"
            ])
        
        sections.append(
            dbc.Table.from_dataframe(
                pd.DataFrame(table_data, columns=[
                    "프로젝트ID", "프로젝트명", "구조ID", "구조명", "주소", "시작일", "상태"
                ]),
                striped=True,
                bordered=True,
                hover=True,
                responsive=True,
                className="mb-5"
            )
        )
        
        sections.append(html.Hr(className="my-5"))

    cards = []

    # 2. ITS 프로젝트 카드 생성
    if not its_projects_df.empty:
        cards.append(html.H3("ITS 프로젝트", className="text-center mb-4 text-primary"))
        
        for _, row in its_projects_df.iterrows():
            proj_id = row["projectid"]
            proj_name = row["projectname"]
            reg_date = row["regdate"]
            close_date = row["closedate"]
            
            # 상태 표시
            status = "진행중" if pd.isna(close_date) else "완료"
            status_color = "success" if status == "진행중" else "secondary"
            
            card_style = {
                "width": "200px",
                "height": "200px",
                "backgroundColor": "#e8f5e8",
                "borderRadius": "0.5rem",
                "overflow": "hidden",
                "transition": "transform 0.2s, box-shadow 0.2s",
                "boxShadow": "0 4px 8px rgba(40, 167, 69, 0.4)",
                "cursor": "pointer",
                "textDecoration": "none"
            }

            cards.append(
                dbc.Col([
                    dbc.Card(
                        dbc.CardBody([
                            html.H5(
                                proj_name,
                                className="card-title fw-bold fs-5 mb-2"
                            ),
                            dbc.Badge(
                                status,
                                color=status_color,
                                className="mb-2"
                            ),
                            html.P(
                                f"프로젝트 ID: {proj_id}",
                                className="card-text fs-7 mb-1"
                            ),
                            html.P(
                                f"시작일: {format_date(reg_date)}",
                                className="card-text fs-7 mb-1"
                            ),
                            html.P(
                                "ITS 시스템",
                                className="card-text fs-8 text-muted"
                            ),
                        ], className="d-flex flex-column align-items-center justify-content-center h-100"),
                        style=card_style,
                        className="project-card mb-4"
                    )
                ], xs=12, sm=6, md=3, lg=3)
            )

    # 3. 로컬 프로젝트 카드 생성 (기존 로직 유지)
    if not local_projects_df.empty:
        if cards:  # ITS 프로젝트가 있으면 구분선 추가
            cards.append(html.Hr(className="my-5"))
        cards.append(html.H3("로컬 프로젝트", className="text-center mb-4 text-info"))
        
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
                                html.P(
                                    f"{row['user_company_pk']}",
                                    className="card-text fs-9 mb-1"
                                ),
                            ], className="d-flex flex-column align-items-center justify-content-center h-100"),
                            style=card_style,
                            className="project-card mb-4"
                        )
                    )
                ], xs=12, sm=6, md=3, lg=3)
            )

    # 프로젝트와 구조가 모두 없는 경우
    if not sections and not cards:
        return html.Div([
            dbc.Container([
                dbc.Alert([
                    html.H4("프로젝트가 없습니다", className="alert-heading"),
                    html.P("현재 접근 가능한 프로젝트가 없습니다."),
                    html.Hr(),
                    html.P("관리자에게 문의하시기 바랍니다.", className="mb-0")
                ], color="info", className="mt-5")
            ])
        ])

    # 카드가 있으면 카드 그리드 생성
    card_grid = None
    if cards:
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
                *sections,  # 프로젝트-구조 테이블
                card_grid if card_grid else html.Div()  # 프로젝트 카드들
            ]
        )
    ])
