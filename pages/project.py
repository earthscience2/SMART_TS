#!/usr/bin/env python3
# pages/project.py
"""Dash 페이지: 프로젝트 및 콘크리트 관리

* 왼쪽에서 프로젝트를 선택 → 해당 프로젝트의 콘크리트 리스트 표시
* 콘크리트 분석 시작/삭제 기능
"""

from __future__ import annotations

import os
import shutil
import pandas as pd
import dash
from dash import (
    html, dcc, Input, Output, State,
    dash_table, register_page, callback
)
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

import api_db

register_page(__name__, path="/project")

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    children=[
        # ── (★) 삭제 컨펌 다이얼로그
        dcc.ConfirmDialog(
            id="confirm-del-concrete",
            message="선택한 콘크리트를 정말 삭제하시겠습니까?"
        ),

        # ── (★) Alert 메시지
        dbc.Alert(
            id="project-alert",
            is_open=False,
            duration=3000,
            color="danger",
        ),

        # 상단: 프로젝트 선택 → 콘크리트 테이블 + 버튼
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H6("프로젝트 선택"),
                        dcc.Dropdown(
                            id="ddl-project",
                            placeholder="프로젝트 선택",
                            clearable=False,
                        ),
                        html.H6("콘크리트 리스트", className="mt-3"),
                        dash_table.DataTable(
                            id="tbl-concrete",
                            page_size=10,
                            row_selectable="single",
                            style_table={"overflowY": "auto", "height": "45vh"},
                            style_cell={"whiteSpace": "nowrap", "textAlign": "center"},
                            style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
                        ),
                        dbc.ButtonGroup(
                            [
                                dbc.Button("분석 시작", id="btn-concrete-analyze", color="success", className="mt-2"),
                                dbc.Button("삭제", id="btn-concrete-del", color="danger", className="mt-2", disabled=True),
                            ],
                            size="sm",
                            vertical=True,
                            className="w-100",
                        ),
                    ],
                    md=3,
                ),
                dbc.Col(
                    [
                        html.H6(id="concrete-title", className="mb-2"),
                        # 3D 뷰는 비활성화
                        html.Div(
                            "3D 뷰는 비활성화되어 있습니다.",
                            className="d-flex justify-content-center align-items-center",
                            style={"height": "75vh", "backgroundColor": "#f8f9fa", "border": "1px solid #dee2e6"}
                        ),
                    ],
                    md=9,
                ),
            ],
            className="g-3",
        ),
    ],
)

# ───────────────────── ① 프로젝트 목록 초기화 ─────────────────────
@callback(
    Output("ddl-project", "options"),
    Output("ddl-project", "value"),
    Input("ddl-project", "value"),
    prevent_initial_call=False,
)
def init_dropdown(selected_value):
    """
    페이지 로드 또는 값이 None일 때 프로젝트 목록을 Dropdown 옵션으로 설정.
    """
    df_proj = api_db.get_project_data()
    options = [
        {"label": f"{row['name']}", "value": row["project_pk"]}
        for _, row in df_proj.iterrows()
    ]
    if not options:
        return [], None

    # 초기 로드 시(= selected_value가 None일 때)만 첫 번째 옵션을 기본값으로 지정
    if selected_value is None:
        return options, options[0]["value"]
    # 사용자가 이미 선택한 값이 있으면 그대로 유지
    return options, selected_value

# ───────────────────── ② 프로젝트 선택 콜백 ─────────────────────
@callback(
    Output("tbl-concrete", "data"),
    Output("tbl-concrete", "columns"),
    Output("tbl-concrete", "selected_rows"),
    Output("btn-concrete-del", "disabled"),
    Output("concrete-title", "children"),
    Input("ddl-project", "value"),
    prevent_initial_call=True,
)
def on_project_change(selected_proj):
    if not selected_proj:
        return [], [], [], True, ""

    # 1) 프로젝트 정보 로드
    try:
        proj_row = api_db.get_project_data(project_pk=selected_proj).iloc[0]
        proj_name = proj_row["name"]
    except Exception:
        return [], [], [], True, "프로젝트 정보를 불러올 수 없음"

    # 2) 콘크리트 데이터 로드
    df_conc = api_db.get_concrete_data(project_pk=selected_proj)
    table_data = []
    for _, row in df_conc.iterrows():
        try:
            dims = eval(row["dims"])
            nodes = dims["nodes"]
            h = dims["h"]
            shape_info = f"{len(nodes)}각형 (높이: {h:.2f}m)"
        except Exception:
            shape_info = "파싱 오류"
        
        table_data.append({
            "concrete_pk": row["concrete_pk"],
            "name": row["name"],
            "shape": shape_info,
            "activate": "활성" if row["activate"] == 1 else "비활성",
        })

    # 3) 테이블 컬럼 정의
    columns = [
        {"name": "콘크리트 ID", "id": "concrete_pk"},
        {"name": "이름", "id": "name"},
        {"name": "형상", "id": "shape"},
        {"name": "상태", "id": "activate"},
    ]

    title = f"{proj_name} · 콘크리트 전체"
    return table_data, columns, [], True, title

# ───────────────────── ③ 콘크리트 선택 콜백 ─────────────────────
@callback(
    Output("btn-concrete-del", "disabled", allow_duplicate=True),
    Input("tbl-concrete", "selected_rows"),
    prevent_initial_call=True,
)
def on_concrete_select(selected_rows):
    return not bool(selected_rows)

# ───────────────────── ④ 분석 시작 콜백 ─────────────────────
@callback(
    Output("project-alert", "children"),
    Output("project-alert", "color"),
    Output("project-alert", "is_open"),
    Output("tbl-concrete", "data", allow_duplicate=True),
    Input("btn-concrete-analyze", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def start_analysis(n_clicks, selected_rows, tbl_data):
    if not selected_rows:
        return "콘크리트를 선택하세요", "warning", True, dash.no_update

    row = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    concrete_pk = row["concrete_pk"]

    try:
        # activate를 0으로 변경
        api_db.update_concrete_data(concrete_pk=concrete_pk, activate=0)
        
        # 테이블 데이터 업데이트
        updated_data = tbl_data.copy()
        updated_data[selected_rows[0]]["activate"] = "비활성"
        
        return f"{concrete_pk} 분석이 시작되었습니다", "success", True, updated_data
    except Exception as e:
        return f"분석 시작 실패: {e}", "danger", True, dash.no_update

# ───────────────────── ⑤ 삭제 컨펌 토글 콜백 ───────────────────
@callback(
    Output("confirm-del-concrete", "displayed"),
    Input("btn-concrete-del", "n_clicks"),
    State("tbl-concrete", "selected_rows"),
    prevent_initial_call=True
)
def ask_delete_concrete(n, sel):
    return bool(n and sel)

# ───────────────────── ⑥ 삭제 실행 콜백 ─────────────────────
@callback(
    Output("project-alert", "children", allow_duplicate=True),
    Output("project-alert", "color", allow_duplicate=True),
    Output("project-alert", "is_open", allow_duplicate=True),
    Output("tbl-concrete", "data", allow_duplicate=True),
    Input("confirm-del-concrete", "submit_n_clicks"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=True,
)
def delete_concrete_confirm(_click, sel, tbl_data):
    if not sel:
        raise PreventUpdate

    row = pd.DataFrame(tbl_data).iloc[sel[0]]
    concrete_pk = row["concrete_pk"]

    try:
        # 1) /inp/{concrete_pk} 디렉토리 삭제
        inp_dir = f"inp/{concrete_pk}"
        if os.path.exists(inp_dir):
            shutil.rmtree(inp_dir)

        # 2) 센서 데이터 삭제
        df_sensors = api_db.get_sensors_data(concrete_pk=concrete_pk)
        for _, sensor in df_sensors.iterrows():
            api_db.delete_sensors_data(sensor["sensor_pk"])

        # 3) 콘크리트 삭제
        api_db.delete_concrete_data(concrete_pk)

        # 4) 테이블에서 해당 행 제거
        updated_data = tbl_data.copy()
        updated_data.pop(sel[0])

        return f"{concrete_pk} 삭제 완료", "success", True, updated_data
    except Exception as e:
        return f"삭제 실패: {e}", "danger", True, dash.no_update
