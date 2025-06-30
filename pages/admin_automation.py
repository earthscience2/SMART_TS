import dash
from dash import dcc, html, Input, Output, callback
import dash_bootstrap_components as dbc
from flask import request
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import re

dash.register_page(__name__, path="/admin_automation")

def parse_automation_log_line(line):
    """자동화 로그 라인을 파싱하여 구조화된 데이터로 변환"""
    # 로그 형식: 2025-01-13 14:30:25 | INFO | AUTO_RUN | 자동화 사이클 1 시작
    pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\w+) \| (AUTO_\w+) \| (.+)$'
    match = re.match(pattern, line.strip())
    
    if match:
        timestamp, level, module, message = match.groups()
        return {
            'timestamp': timestamp,
            'level': level,
            'module': module,
            'message': message
        }
    return None

def read_automation_logs():
    """자동화 로그 파일들을 읽어서 통합된 로그 리스트 반환"""
    log_files = [
        'auto_run.log',
        'auto_inp.log', 
        'auto_sensor.log',
        'auto_inp_to_frd.log',
        'auto_frd_to_vtk.log'
    ]
    
    all_logs = []
    
    for log_file in log_files:
        log_path = os.path.join('log', log_file)
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in lines:
                        parsed = parse_automation_log_line(line)
                        if parsed:
                            all_logs.append(parsed)
            except Exception as e:
                print(f"로그 파일 읽기 오류 ({log_file}): {e}")
    
    # 시간순으로 정렬 (최신순)
    all_logs.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return all_logs

def layout():
    """자동화 로그 페이지 레이아웃"""
    
    return dbc.Container([
        # 자동 새로고침을 위한 인터벌 컴포넌트
        dcc.Interval(
            id='automation-logs-interval',
            interval=10*1000,  # 10초마다 새로고침
            n_intervals=0
        ),
        
        dbc.Row([
            dbc.Col([
                html.H2("⚙️ 자동화 로그", className="mb-4 text-center"),
                html.Hr(),
            ])
        ]),
        
        # 로그 통계 카드
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H4("📊 로그 통계", className="mb-0")
                    ]),
                    dbc.CardBody([
                        html.Div(id="automation-log-stats")
                    ])
                ], className="mb-4")
            ])
        ]),
        
        # 필터 옵션
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H4("🔍 필터 옵션", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    dbc.Label("모듈 유형"),
                                    dbc.Select(
                                        id="automation-module-filter",
                                        options=[
                                            {"label": "전체", "value": "all"},
                                            {"label": "AUTO_RUN", "value": "AUTO_RUN"},
                                            {"label": "AUTO_SENSOR", "value": "AUTO_SENSOR"},
                                            {"label": "AUTO_INP", "value": "AUTO_INP"},
                                            {"label": "AUTO_INP_TO_FRD", "value": "AUTO_INP_TO_FRD"},
                                            {"label": "AUTO_FRD_TO_VTK", "value": "AUTO_FRD_TO_VTK"},
                                        ],
                                        value="all"
                                    )
                                ], className="mb-3")
                            ], width=4),
                            dbc.Col([
                                html.Div([
                                    dbc.Label("로그 레벨"),
                                    dbc.Select(
                                        id="automation-level-filter",
                                        options=[
                                            {"label": "전체", "value": "all"},
                                            {"label": "INFO", "value": "INFO"},
                                            {"label": "WARNING", "value": "WARNING"},
                                            {"label": "ERROR", "value": "ERROR"},
                                        ],
                                        value="all"
                                    )
                                ], className="mb-3")
                            ], width=4),
                            dbc.Col([
                                html.Div([
                                    dbc.Label("표시 개수"),
                                    dbc.Select(
                                        id="automation-count-filter",
                                        options=[
                                            {"label": "50개", "value": 50},
                                            {"label": "100개", "value": 100},
                                            {"label": "200개", "value": 200},
                                            {"label": "500개", "value": 500},
                                        ],
                                        value=100
                                    )
                                ], className="mb-3")
                            ], width=4),
                        ])
                    ])
                ], className="mb-4")
            ])
        ]),
        
        # 로그 테이블
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H4("📋 자동화 로그", className="mb-0"),
                        html.Small("(10초마다 자동 새로고침)", className="text-muted")
                    ]),
                    dbc.CardBody([
                        html.Div(id="automation-logs-table")
                    ])
                ])
            ])
        ])
    ], fluid=True)

@callback(
    [Output("automation-log-stats", "children"),
     Output("automation-logs-table", "children")],
    [Input("automation-logs-interval", "n_intervals"),
     Input("automation-module-filter", "value"),
     Input("automation-level-filter", "value"),
     Input("automation-count-filter", "value")]
)
def update_automation_logs(n_intervals, module_filter, level_filter, count_filter):
    """자동화 로그를 읽어서 테이블로 표시"""
    
    # 로그 데이터 읽기
    logs = read_automation_logs()
    
    # 필터 적용
    filtered_logs = logs.copy()
    
    if module_filter != "all":
        filtered_logs = [log for log in filtered_logs if log['module'] == module_filter]
    
    if level_filter != "all":
        filtered_logs = [log for log in filtered_logs if log['level'] == level_filter]
    
    # 표시 개수 제한
    if isinstance(count_filter, (int, str)):
        count_filter = int(count_filter)
        filtered_logs = filtered_logs[:count_filter]
    
    # 통계 계산
    total_logs = len(logs)
    module_stats = {}
    level_stats = {}
    
    for log in logs:
        module = log['module']
        level = log['level']
        
        module_stats[module] = module_stats.get(module, 0) + 1
        level_stats[level] = level_stats.get(level, 0) + 1
    
    # 통계 카드 생성
    stats_cards = []
    
    # 총 로그 수
    stats_cards.append(
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H4(str(total_logs), className="text-primary"),
                    html.P("총 로그", className="text-muted mb-0")
                ])
            ], className="text-center")
        ], width=2)
    )
    
    # 모듈별 통계
    module_colors = {
        'AUTO_RUN': 'primary',
        'AUTO_SENSOR': 'success', 
        'AUTO_INP': 'info',
        'AUTO_INP_TO_FRD': 'warning',
        'AUTO_FRD_TO_VTK': 'secondary'
    }
    
    for module, count in module_stats.items():
        stats_cards.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H5(str(count), className=f"text-{module_colors.get(module, 'dark')}"),
                        html.P(module.replace('AUTO_', ''), className="text-muted mb-0 small")
                    ])
                ], className="text-center")
            ], width=2)
        )
    
    stats_component = dbc.Row(stats_cards)
    
    # 레벨별 색상 매핑
    level_colors = {
        "INFO": "primary",
        "WARNING": "warning", 
        "ERROR": "danger"
    }
    
    # 모듈별 색상 매핑
    module_badge_colors = {
        "AUTO_RUN": "primary",
        "AUTO_SENSOR": "success",
        "AUTO_INP": "info", 
        "AUTO_INP_TO_FRD": "warning",
        "AUTO_FRD_TO_VTK": "secondary"
    }
    
    if not filtered_logs:
        table_component = dbc.Alert("표시할 로그가 없습니다.", color="info")
    else:
        # 테이블 헤더
        header = dbc.Row([
            dbc.Col("시간", width=2, className="fw-bold"),
            dbc.Col("모듈", width=2, className="fw-bold"),
            dbc.Col("레벨", width=1, className="fw-bold"),
            dbc.Col("메시지", width=7, className="fw-bold"),
        ], className="border-bottom pb-2 mb-2")
        
        # 테이블 행들
        rows = []
        for log in filtered_logs:
            row = dbc.Row([
                dbc.Col(log["timestamp"], width=2, className="small"),
                dbc.Col(
                    dbc.Badge(
                        log["module"].replace("AUTO_", ""),
                        color=module_badge_colors.get(log["module"], "secondary"),
                        className="text-white"
                    ),
                    width=2
                ),
                dbc.Col(
                    dbc.Badge(
                        log["level"],
                        color=level_colors.get(log["level"], "secondary"),
                        className="text-white"
                    ),
                    width=1
                ),
                dbc.Col(log["message"], width=7, className="small"),
            ], className="border-bottom py-2")
            rows.append(row)
        
        table_component = [header] + rows
    
    return stats_component, table_component 