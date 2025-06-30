from dash import html, dcc, register_page, callback, Input, Output, State
import dash_bootstrap_components as dbc
from flask import request as flask_request
import pandas as pd
import os
from datetime import datetime, timedelta
import re

register_page(__name__, path="/admin_logs", title="일반 로그")

def read_log_file(log_type):
    """로그 파일을 읽어서 파싱된 데이터를 반환합니다."""
    log_files = {
        "login": "log/login.log",
        "project": "log/project.log", 
        "concrete": "log/concrete.log",
        "sensor": "log/sensor.log"
    }
    
    if log_type not in log_files:
        return []
    
    file_path = log_files[log_type]
    
    if not os.path.exists(file_path):
        return []
    
    logs = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # 로그 형식 파싱: 날짜/시간 | 레벨 | 작업_유형 | ID | Details
                parts = line.split(' | ')
                if len(parts) >= 3:
                    timestamp = parts[0]
                    level = parts[1]
                    
                    if log_type == "login":
                        # 로그인 로그 형식이 다를 수 있음
                        action = "LOGIN"
                        target_id = ""
                        details = " | ".join(parts[2:])
                    else:
                        # PROJECT_CREATE, CONCRETE_UPDATE 등의 형식
                        action = parts[2] if len(parts) > 2 else ""
                        target_id = parts[3] if len(parts) > 3 else ""
                        details = parts[4] if len(parts) > 4 else ""
                        
                        # Project: P000001, Concrete: C000001 등에서 ID 추출
                        if ":" in target_id:
                            target_id = target_id.split(": ")[1] if ": " in target_id else target_id
                        
                        # Details: 접두사 제거
                        if details.startswith("Details: "):
                            details = details[9:]
                    
                    logs.append({
                        "timestamp": timestamp,
                        "level": level,
                        "log_type": log_type,
                        "action": action,
                        "target_id": target_id,
                        "details": details
                    })
    except Exception as e:
        print(f"Error reading log file {file_path}: {e}")
    
    return logs

def get_all_logs():
    """모든 로그 파일에서 로그를 읽어와서 통합합니다."""
    all_logs = []
    
    for log_type in ["login", "project", "concrete", "sensor"]:
        logs = read_log_file(log_type)
        all_logs.extend(logs)
    
    # 시간순으로 정렬 (최신순)
    all_logs.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return all_logs

def get_log_badge_color(log_type, action):
    """로그 유형과 액션에 따른 배지 색상을 반환합니다."""
    if log_type == "login":
        return "success"
    elif log_type == "project":
        if "CREATE" in action:
            return "primary"
        elif "UPDATE" in action:
            return "warning"
        elif "DELETE" in action:
            return "danger"
        else:
            return "info"
    elif log_type == "concrete":
        if "CREATE" in action:
            return "primary"
        elif "UPDATE" in action:
            return "warning"
        elif "DELETE" in action:
            return "danger"
        else:
            return "info"
    elif log_type == "sensor":
        if "CREATE" in action:
            return "primary"
        elif "UPDATE" in action:
            return "warning"
        elif "DELETE" in action:
            return "danger"
        else:
            return "info"
    else:
        return "secondary"

def layout(**kwargs):
    """Admin logs management layout."""
    return html.Div([
        dcc.Location(id="admin-logs-url", refresh=False),
        dcc.Interval(id="log-refresh-interval", interval=10000, n_intervals=0),  # 10초마다 새로고침
        dbc.Container([
            # 메인 콘텐츠
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H4("📋 일반 로그", className="mb-0 text-success"),
                            html.Small("로그인, 센서, 프로젝트, 콘크리트 로그 확인", className="text-muted")
                        ]),
                        dbc.CardBody([
                            # 로그 필터링 옵션
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("로그 유형", className="fw-bold"),
                                    dcc.Dropdown(
                                        id="log-type-dropdown",
                                        options=[
                                            {"label": "전체", "value": "all"},
                                            {"label": "로그인", "value": "login"},
                                            {"label": "프로젝트", "value": "project"},
                                            {"label": "콘크리트", "value": "concrete"},
                                            {"label": "센서", "value": "sensor"}
                                        ],
                                        value="all",
                                        className="mb-3"
                                    )
                                ], width=3),
                                dbc.Col([
                                    dbc.Label("액션 유형", className="fw-bold"),
                                    dcc.Dropdown(
                                        id="log-action-dropdown",
                                        options=[
                                            {"label": "전체", "value": "all"},
                                            {"label": "생성 (CREATE)", "value": "CREATE"},
                                            {"label": "수정 (UPDATE)", "value": "UPDATE"},
                                            {"label": "삭제 (DELETE)", "value": "DELETE"},
                                            {"label": "로그인", "value": "LOGIN"}
                                        ],
                                        value="all",
                                        className="mb-3"
                                    )
                                ], width=3),
                                dbc.Col([
                                    dbc.Label("표시 개수", className="fw-bold"),
                                    dcc.Dropdown(
                                        id="log-limit-dropdown",
                                        options=[
                                            {"label": "최근 50개", "value": 50},
                                            {"label": "최근 100개", "value": 100},
                                            {"label": "최근 200개", "value": 200},
                                            {"label": "전체", "value": 1000}
                                        ],
                                        value=100,
                                        className="mb-3"
                                    )
                                ], width=3),
                                dbc.Col([
                                    dbc.Label("", className="fw-bold"),
                                    dbc.Button("🔄 새로고침", id="refresh-logs-btn", color="primary", className="w-100")
                                ], width=3)
                            ], className="mb-4"),
                            
                            # 로그 테이블 컨테이너
                            html.Div(id="logs-table-container"),
                            
                            # 로그 통계
                            dbc.Row([
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.H6("총 로그 수", className="text-primary"),
                                            html.H4(id="total-logs-count", className="fw-bold text-primary")
                                        ])
                                    ])
                                ], width=3),
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.H6("프로젝트 로그", className="text-info"),
                                            html.H4(id="project-logs-count", className="fw-bold text-info")
                                        ])
                                    ])
                                ], width=3),
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.H6("콘크리트 로그", className="text-warning"),
                                            html.H4(id="concrete-logs-count", className="fw-bold text-warning")
                                        ])
                                    ])
                                ], width=3),
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.H6("센서 로그", className="text-success"),
                                            html.H4(id="sensor-logs-count", className="fw-bold text-success")
                                        ])
                                    ])
                                ], width=3),
                            ], className="mt-4")
                        ])
                    ], className="shadow")
                ])
            ])
        ], fluid=True)
    ])

@callback(
    [Output("logs-table-container", "children"),
     Output("total-logs-count", "children"),
     Output("project-logs-count", "children"),
     Output("concrete-logs-count", "children"),
     Output("sensor-logs-count", "children")],
    [Input("log-refresh-interval", "n_intervals"),
     Input("refresh-logs-btn", "n_clicks"),
     Input("log-type-dropdown", "value"),
     Input("log-action-dropdown", "value"),
     Input("log-limit-dropdown", "value")]
)
def update_logs_table(n_intervals, refresh_clicks, log_type_filter, action_filter, limit):
    """로그 테이블을 업데이트합니다."""
    all_logs = get_all_logs()
    
    # 필터링 적용
    filtered_logs = all_logs
    
    if log_type_filter != "all":
        filtered_logs = [log for log in filtered_logs if log["log_type"] == log_type_filter]
    
    if action_filter != "all":
        filtered_logs = [log for log in filtered_logs if action_filter in log["action"]]
    
    # 개수 제한
    if limit < len(filtered_logs):
        filtered_logs = filtered_logs[:limit]
    
    # 통계 계산
    total_count = len(all_logs)
    project_count = len([log for log in all_logs if log["log_type"] == "project"])
    concrete_count = len([log for log in all_logs if log["log_type"] == "concrete"])
    sensor_count = len([log for log in all_logs if log["log_type"] == "sensor"])
    
    # 테이블 생성
    if not filtered_logs:
        table_content = dbc.Alert("표시할 로그가 없습니다.", color="info")
    else:
        table_rows = []
        for log in filtered_logs:
            color = get_log_badge_color(log["log_type"], log["action"])
            
            row = html.Tr([
                html.Td(log["timestamp"]),
                html.Td(dbc.Badge(log["log_type"].upper(), color=color)),
                html.Td(log["action"]),
                html.Td(log["target_id"] if log["target_id"] else "-"),
                html.Td(log["details"], style={"max-width": "300px", "word-wrap": "break-word"}),
                html.Td(dbc.Badge("정상", color="success"))
            ])
            table_rows.append(row)
        
        table_content = dbc.Table([
            html.Thead([
                html.Tr([
                    html.Th("시간"),
                    html.Th("유형"),
                    html.Th("액션"),
                    html.Th("대상 ID"),
                    html.Th("상세 내용"),
                    html.Th("상태")
                ])
            ]),
            html.Tbody(table_rows)
        ], striped=True, bordered=True, hover=True, responsive=True)
    
    return (
        table_content,
        str(total_count),
        str(project_count),
        str(concrete_count),
        str(sensor_count)
    )

@callback(
    [Output("admin-logs-url", "pathname")],
    [Input("admin-logs-url", "pathname")],
    allow_duplicate=True
)
def check_admin_access(pathname):
    """관리자 권한 확인"""
    if not flask_request.cookies.get("admin_user"):
        return ["/admin"]
    return [pathname] 