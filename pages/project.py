#!/usr/bin/env python3
"""Dash 페이지: 프로젝트 및 콘크리트 관리

* 왼쪽에서 프로젝트를 선택 → 해당 프로젝트의 콘크리트 리스트 표시
* 콘크리트 분석 시작/삭제 기능
* 3D 히트맵 뷰어로 시간별 온도 분포 확인
"""

from __future__ import annotations

import os
import glob
import shutil
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import dash
from dash import (
    html, dcc, Input, Output, State,
    dash_table, register_page, callback, clientside_callback
)
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
from scipy.interpolate import griddata
import ast
import json
import auto_sensor
import auto_inp
import time
from urllib.parse import parse_qs, urlparse
from dash.dependencies import ALL
from dash import html
import dash_vtk

import api_db

# 탭 모듈들 import
from .project_tabs import (
    create_3d_tab, register_3d_callbacks,
    create_section_tab, register_section_callbacks,
    create_temp_tab, register_temp_callbacks,
    create_analysis_tab, register_analysis_callbacks,
    create_tci_tab, register_tci_callbacks
)

# 유틸리티 함수들 import
from .project_utils import format_scientific_notation, create_probability_curve_figure, parse_material_info_from_inp

register_page(__name__, path="/project", title="프로젝트 관리")

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    className="px-4 py-3",
    children=[
        # ────────────────────────────── 프로젝트 선택 섹션 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H4("🏠 프로젝트 선택", className="mb-3"),
                dcc.Dropdown(
                    id="dropdown-project",
                    placeholder="프로젝트를 선택하세요",
                    clearable=False,
                    style={"marginBottom": "20px"}
                ),
                html.Div([
                    html.Button("🔄 새로고침", id="btn-refresh-projects", 
                               className="btn btn-outline-primary btn-sm me-2"),
                    html.Button("➕ 새 프로젝트", id="btn-new-project", 
                               className="btn btn-outline-success btn-sm")
                ])
            ], md=4),
            dbc.Col([
                html.H4("🌳 콘크리트 리스트", className="mb-3"),
                dash_table.DataTable(
                    id="tbl-concrete",
                    columns=[
                        {"name": "콘크리트 이름", "id": "name"},
                        {"name": "상태", "id": "activate"},
                        {"name": "센서 수", "id": "sensor_count"},
                        {"name": "생성일", "id": "created_at"},
                        {"name": "작업", "id": "actions"}
                    ],
                    style_header={
                        'backgroundColor': '#f8f9fa',
                        'fontWeight': 'bold',
                        'textAlign': 'center'
                    },
                    style_cell={
                        'textAlign': 'center',
                        'padding': '10px'
                    },
                    style_data_conditional=[
                        {
                            'if': {'row_index': 'odd'},
                            'backgroundColor': '#f8f9fa'
                        }
                    ],
                    page_size=10,
                    sort_action='native',
                    filter_action='native'
                )
            ], md=8)
        ], className="mb-4"),
        
        # ────────────────────────────── 콘크리트 선택 ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H4("🏗️ 콘크리트 선택", className="mb-3"),
                dcc.Dropdown(
                    id="dropdown-concrete",
                    placeholder="콘크리트를 선택하세요",
                    clearable=False,
                    style={"marginBottom": "20px"}
                ),
                html.Div([
                    html.Button("🔄 새로고침", id="btn-refresh-concrete", 
                               className="btn btn-outline-primary btn-sm me-2"),
                    html.Button("🗑️ 삭제", id="btn-delete-concrete", 
                               className="btn btn-outline-danger btn-sm")
                ])
            ], md=12)
        ], className="mb-4"),
        
        # ────────────────────────────── 탭 컨테이너 ────────────────────────────
        dbc.Row([
            dbc.Col([
                dcc.Tabs([
                    dcc.Tab(
                        label="🎯 3D 뷰",
                        value="tab-3d",
                        children=create_3d_tab()
                    ),
                    dcc.Tab(
                        label="📐 단면도",
                        value="tab-section", 
                        children=create_section_tab()
                    ),
                    dcc.Tab(
                        label="🌡️ 온도 변화",
                        value="tab-temp",
                        children=create_temp_tab()
                    ),
                    dcc.Tab(
                        label="🔬 수치해석",
                        value="tab-analysis",
                        children=create_analysis_tab()
                    ),
                    dcc.Tab(
                        label="📊 TCI 분석",
                        value="tab-tci",
                        children=create_tci_tab()
                    )
                ], id="tabs-main", value="tab-3d")
            ], md=12)
        ]),
        
        # ────────────────────────────── 스토어 컴포넌트들 ────────────────────────────
        dcc.Store(id="store-3d-view", storage_type="session"),
        dcc.Store(id="store-section-view", storage_type="session"),
        dcc.Store(id="store-temp-view", storage_type="session"),
        dcc.Store(id="store-analysis-view", storage_type="session"),
        dcc.Store(id="store-tci-view", storage_type="session"),
        
        # ────────────────────────────── 모달들 ────────────────────────────
        dbc.Modal([
            dbc.ModalHeader("새 프로젝트 생성"),
            dbc.ModalBody([
                dbc.Input(id="input-new-project", placeholder="프로젝트 이름을 입력하세요", type="text")
            ]),
            dbc.ModalFooter([
                dbc.Button("취소", id="btn-cancel-new-project", className="ms-auto"),
                dbc.Button("생성", id="btn-confirm-new-project", color="primary")
            ])
        ], id="modal-new-project"),
        
        dbc.Modal([
            dbc.ModalHeader("콘크리트 삭제 확인"),
            dbc.ModalBody("정말로 이 콘크리트를 삭제하시겠습니까?"),
            dbc.ModalFooter([
                dbc.Button("취소", id="btn-cancel-delete", className="ms-auto"),
                dbc.Button("삭제", id="btn-confirm-delete", color="danger")
            ])
        ], id="modal-delete-concrete")
    ]
)

# ────────────────────────────── 메인 콜백들 ────────────────────────────

@callback(
    Output("dropdown-project", "options"),
    Output("dropdown-project", "value"),
    Input("btn-refresh-projects", "n_clicks"),
    Input("btn-confirm-new-project", "n_clicks"),
    State("input-new-project", "value"),
    prevent_initial_call=True
)
def update_project_dropdown(refresh_clicks, new_project_clicks, project_name):
    """프로젝트 드롭다운 업데이트"""
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if trigger_id == "btn-refresh-projects":
        # 프로젝트 목록 새로고침
        projects = api_db.get_projects()
        options = [{"label": p["name"], "value": p["id"]} for p in projects]
        return options, dash.no_update
    
    elif trigger_id == "btn-confirm-new-project" and project_name:
        # 새 프로젝트 생성
        project_id = api_db.create_project(project_name)
        projects = api_db.get_projects()
        options = [{"label": p["name"], "value": p["id"]} for p in projects]
        return options, project_id
    
    raise PreventUpdate

@callback(
    Output("tbl-concrete", "data"),
    Output("dropdown-concrete", "options"),
    Output("dropdown-concrete", "value"),
    Input("dropdown-project", "value"),
    Input("btn-refresh-concrete", "n_clicks"),
    prevent_initial_call=True
)
def update_concrete_list(project_id, refresh_clicks):
    """콘크리트 목록 업데이트"""
    if not project_id:
        return [], [], None
    
    concretes = api_db.get_concretes_by_project(project_id)
    
    # 테이블 데이터 생성
    table_data = []
    dropdown_options = []
    
    for concrete in concretes:
        status = "✅ 활성" if concrete["activate"] else "❌ 비활성"
        action_buttons = html.Div([
            html.Button("시작", id={"type": "btn-start", "index": concrete["id"]}, 
                       className="btn btn-success btn-sm me-1"),
            html.Button("중지", id={"type": "btn-stop", "index": concrete["id"]}, 
                       className="btn btn-warning btn-sm")
        ])
        
        table_data.append({
            "name": concrete["name"],
            "activate": status,
            "sensor_count": concrete["sensor_count"],
            "created_at": concrete["created_at"],
            "actions": action_buttons
        })
        
        dropdown_options.append({
            "label": concrete["name"],
            "value": concrete["id"]
        })
    
    return table_data, dropdown_options, None

@callback(
    Output("modal-new-project", "is_open"),
    Input("btn-new-project", "n_clicks"),
    Input("btn-cancel-new-project", "n_clicks"),
    Input("btn-confirm-new-project", "n_clicks"),
    State("modal-new-project", "is_open"),
    prevent_initial_call=True
)
def toggle_new_project_modal(open_clicks, cancel_clicks, confirm_clicks, is_open):
    """새 프로젝트 모달 토글"""
    if open_clicks or cancel_clicks or confirm_clicks:
        return not is_open
    return is_open

@callback(
    Output("modal-delete-concrete", "is_open"),
    Input("btn-delete-concrete", "n_clicks"),
    Input("btn-cancel-delete", "n_clicks"),
    Input("btn-confirm-delete", "n_clicks"),
    State("modal-delete-concrete", "is_open"),
    prevent_initial_call=True
)
def toggle_delete_modal(open_clicks, cancel_clicks, confirm_clicks, is_open):
    """삭제 확인 모달 토글"""
    if open_clicks or cancel_clicks or confirm_clicks:
        return not is_open
    return is_open

# ────────────────────────────── 탭 콜백 등록 ────────────────────────────

def register_all_callbacks():
    """모든 탭의 콜백을 등록합니다."""
    register_3d_callbacks()
    register_section_callbacks()
    register_temp_callbacks()
    register_analysis_callbacks()
    register_tci_callbacks()

# 앱 시작 시 콜백 등록
register_all_callbacks()