from dash import html, dcc, register_page
import dash_bootstrap_components as dbc
from flask import request
import pandas as pd
import api_user
import api_concrete
import api_sensor
from datetime import datetime
import api_db

# 외부 assets/custom.css 파일에 hover 스타일 정의 필요:
# .project-card:hover {
#   transform: scale(1.05);
#   box-shadow: 0 6px 12px rgba(135, 206, 250, 0.6);
# }

register_page(__name__, path="/", title="프로젝트 목록")
projects_df = api_db.get_project_data()


def format_date(date_str: str) -> str:
    s = date_str.rstrip("Z")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.strptime(s, "%Y-%m-%d")
    return dt.strftime("%Y.%m.%d")


def layout():
    token = request.cookies.get("login_token")
    if not token or not api_user.validate_token(token):
        return dcc.Location(pathname="/login", id="redirect-login")

    user = api_user.get_user_info(token)
    if not user:
        return dcc.Location(pathname="/login", id="redirect-login")

    user_role = user["user_role"]
    user_company = user["user_company"]

    if user_role == "admin":
        filtered = projects_df
    else:
        filtered = projects_df[projects_df["user_company_pk"] == user_company]

    cards = []
    # 콘크리트 및 센서 메타데이터 로드
    df_concrete = api_concrete.load_all()
    df_sensors = api_sensor.load_all_sensors()

    for _, row in filtered.iterrows():
        proj_pk = row["pk"]
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
        }

        cards.append(
            dbc.Card(
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

    card_grid = dbc.Row(
        [dbc.Col(card, xs=12, sm=6, md=4) for card in cards],
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
                html.H2("프로젝트 목록", className="text-center mb-4"),
                card_grid
            ]
        )
    ])
