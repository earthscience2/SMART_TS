import dash
from dash import dcc, html, Input, Output, callback
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import re

dash.register_page(__name__, path="/admin_automation")

# 상수 정의
MODULE_COLORS = {
    'AUTO_RUN': 'primary',
    'AUTO_SENSOR': 'success', 
    'AUTO_INP': 'info',
    'AUTO_INP_TO_FRD': 'warning',
    'AUTO_FRD_TO_VTK': 'secondary'
}

LEVEL_COLORS = {
    "INFO": "primary",
    "WARNING": "warning", 
    "ERROR": "danger",
    "DEBUG": "secondary"
}

LOG_FILES = [
    ('auto_run.log', 'AUTO_RUN'),
    ('auto_inp.log', 'AUTO_INP'), 
    ('auto_sensor.log', 'AUTO_SENSOR'),
    ('auto_inp_to_frd.log', 'AUTO_INP_TO_FRD'),
    ('auto_frd_to_vtk.log', 'AUTO_FRD_TO_VTK')
]

def parse_automation_log_line(line):
    """자동화 로그 라인을 파싱하여 구조화된 데이터로 변환"""
    line = line.strip()
    
    # 새로운 형식 1: 2025-01-13 14:30:25 | INFO | AUTO_RUN | 메시지
    pattern1 = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\w+) \| (AUTO_\w+) \| (.+)$'
    match1 = re.match(pattern1, line)
    
    if match1:
        timestamp, level, module, message = match1.groups()
        return {
            'timestamp': timestamp,
            'level': level,
            'module': module,
            'message': message
        }
    
    # 새로운 형식 2 (쉼표 포함): 2025-06-30 22:15:10,036 | INFO | AUTO_RUN | 메시지
    pattern2 = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \| (\w+) \| (AUTO_\w+) \| (.+)$'
    match2 = re.match(pattern2, line)
    
    if match2:
        timestamp, level, module, message = match2.groups()
        return {
            'timestamp': timestamp,
            'level': level,
            'module': module,
            'message': message
        }
    
    # 기존 형식: 2025-06-21 22:02:06 [INFO] 메시지
    pattern3 = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (.+)$'
    match3 = re.match(pattern3, line)
    
    if match3:
        timestamp, level, message = match3.groups()
        return {
            'timestamp': timestamp,
            'level': level,
            'module': "AUTO_UNKNOWN",
            'message': message
        }
    
    return None

def parse_automation_timestamp(timestamp_str):
    """자동화 로그 타임스탬프 문자열을 datetime 객체로 변환"""
    try:
        return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(timestamp_str.split(',')[0], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.now()

def filter_automation_logs_by_date(logs, start_date, end_date):
    """날짜 범위에 따라 자동화 로그를 필터링"""
    if not start_date or not end_date:
        return logs
    
    filtered_logs = []
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    
    for log in logs:
        log_dt = parse_automation_timestamp(log["timestamp"])
        if start_dt <= log_dt <= end_dt:
            filtered_logs.append(log)
    
    return filtered_logs

def read_automation_logs():
    """자동화 로그 파일들을 읽어서 통합된 로그 리스트 반환"""
    all_logs = []
    
    for log_file, module_name in LOG_FILES:
        log_path = os.path.join('log', log_file)
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        parsed = parse_automation_log_line(line)
                        if parsed:
                            # 모듈명이 AUTO_UNKNOWN인 경우 파일명 기반으로 설정
                            if parsed['module'] == 'AUTO_UNKNOWN':
                                parsed['module'] = module_name
                            all_logs.append(parsed)
            except Exception as e:
                print(f"로그 파일 읽기 오류 ({log_file}): {e}")
    
    # 시간순으로 정렬 (최신순)
    all_logs.sort(key=lambda x: x['timestamp'], reverse=True)
    return all_logs

def create_stats_component(logs):
    """로그 통계 컴포넌트 생성"""
    total_logs = len(logs)
    module_stats = {}
    
    for log in logs:
        module = log['module']
        module_stats[module] = module_stats.get(module, 0) + 1
    
    stats_cards = [
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.H4(str(total_logs), className="text-primary"),
                    html.P("총 로그", className="text-muted mb-0")
                ])
            ], className="text-center")
        ], width=2)
    ]
    
    for module, count in module_stats.items():
        color = MODULE_COLORS.get(module, 'dark')
        stats_cards.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H5(str(count), className=f"text-{color}"),
                        html.P(module.replace('AUTO_', ''), className="text-muted mb-0 small")
                    ])
                ], className="text-center")
            ], width=2)
        )
    
    return dbc.Row(stats_cards)

def create_table_component(filtered_logs):
    """로그 테이블 컴포넌트 생성"""
    if not filtered_logs:
        return dbc.Alert("표시할 로그가 없습니다.", color="info")
    
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
                    color=MODULE_COLORS.get(log["module"], "secondary"),
                    className="text-white"
                ),
                width=2
            ),
            dbc.Col(
                dbc.Badge(
                    log["level"],
                    color=LEVEL_COLORS.get(log["level"], "secondary"),
                    className="text-white"
                ),
                width=1
            ),
            dbc.Col(log["message"], width=7, className="small"),
        ], className="border-bottom py-2")
        rows.append(row)
    
    return [header] + rows

def layout():
    """자동화 로그 페이지 레이아웃"""
    return dbc.Container([
        # 자동 새로고침을 위한 인터벌 컴포넌트
        dcc.Interval(
            id='automation-logs-interval',
            interval=10*1000,  # 10초마다 새로고침
            n_intervals=0
        ),
        
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
                                            {"label": "통합실행", "value": "AUTO_RUN"},
                                            {"label": "센서 데이터 수집 및 저장", "value": "AUTO_SENSOR"},
                                            {"label": "INP 파일 생성", "value": "AUTO_INP"},
                                            {"label": "INP → FRD 파일 변환", "value": "AUTO_INP_TO_FRD"},
                                            {"label": "FRD → VTK 파일 변환", "value": "AUTO_FRD_TO_VTK"},
                                        ],
                                        value="all"
                                    )
                                ], className="mb-3")
                            ], width=3),
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
                                            {"label": "DEBUG", "value": "DEBUG"},
                                        ],
                                        value="all"
                                    )
                                ], className="mb-3")
                            ], width=3),
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
                            ], width=3),
                            dbc.Col([
                                html.Div([
                                    dbc.Label("날짜 범위"),
                                    dcc.DatePickerRange(
                                        id="automation-date-filter",
                                        start_date=(datetime.now() - timedelta(days=7)).date(),
                                        end_date=datetime.now().date(),
                                        display_format="YYYY-MM-DD",
                                        style={"width": "100%"}
                                    )
                                ], className="mb-3")
                            ], width=3),
                        ]),
                        dbc.Row([
                            dbc.Col([
                                dbc.Button("전체 기간", id="auto-btn-all-dates", color="outline-secondary", size="sm", className="me-2"),
                                dbc.Button("최근 7일", id="auto-btn-last-7days", color="outline-primary", size="sm", className="me-2"),
                                dbc.Button("최근 30일", id="auto-btn-last-30days", color="outline-primary", size="sm"),
                            ], width=12)
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
     Input("automation-count-filter", "value"),
     Input("automation-date-filter", "start_date"),
     Input("automation-date-filter", "end_date")]
)
def update_automation_logs(n_intervals, module_filter, level_filter, count_filter, start_date, end_date):
    """자동화 로그를 읽어서 테이블로 표시"""
    # 로그 데이터 읽기
    logs = read_automation_logs()
    
    # 날짜 필터링 적용
    if start_date and end_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        logs = filter_automation_logs_by_date(logs, start_dt, end_dt)
    
    # 필터 적용
    filtered_logs = logs.copy()
    
    if module_filter != "all":
        filtered_logs = [log for log in filtered_logs if log['module'] == module_filter]
    
    if level_filter != "all":
        filtered_logs = [log for log in filtered_logs if log['level'] == level_filter]
    
    # 표시 개수 제한
    count_filter = int(count_filter)
    filtered_logs = filtered_logs[:count_filter]
    
    # 통계 및 테이블 컴포넌트 생성
    stats_component = create_stats_component(logs)
    table_component = create_table_component(filtered_logs)
    
    return stats_component, table_component

@callback(
    [Output("automation-date-filter", "start_date"),
     Output("automation-date-filter", "end_date")],
    [Input("auto-btn-all-dates", "n_clicks"),
     Input("auto-btn-last-7days", "n_clicks"),
     Input("auto-btn-last-30days", "n_clicks")],
    prevent_initial_call=True
)
def update_automation_date_filter(btn_all, btn_7days, btn_30days):
    """자동화 로그 날짜 필터 버튼 클릭 시 날짜 범위를 업데이트"""
    from dash import ctx
    
    if not ctx.triggered:
        return datetime.now().date(), datetime.now().date()
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if button_id == "auto-btn-all-dates":
        start_date = (datetime.now() - timedelta(days=365)).date()
        end_date = datetime.now().date()
    elif button_id == "auto-btn-last-7days":
        start_date = (datetime.now() - timedelta(days=7)).date()
        end_date = datetime.now().date()
    elif button_id == "auto-btn-last-30days":
        start_date = (datetime.now() - timedelta(days=30)).date()
        end_date = datetime.now().date()
    else:
        start_date = (datetime.now() - timedelta(days=7)).date()
        end_date = datetime.now().date()
    
    return start_date, end_date 