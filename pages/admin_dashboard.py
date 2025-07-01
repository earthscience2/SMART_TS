from dash import html, dcc, register_page, callback, Input, Output
import dash_bootstrap_components as dbc
from flask import request as flask_request
from api_db import get_project_data_with_stats
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objs as go
import plotly.express as px

register_page(__name__, path="/admin_dashboard", title="관리자 대시보드")

def get_system_stats():
    """시스템 통계 데이터를 가져옵니다"""
    try:
        from api_db import _get_its_engine, text
        
        # 프로젝트 데이터 조회
        projects_df = get_project_data_with_stats()
        active_projects = len(projects_df) if not projects_df.empty else 0
        
        # 센서 수는 프로젝트 데이터에서 집계
        total_sensors = projects_df['sensor_count'].sum() if not projects_df.empty else 0
        
        # ITS 엔진으로 더 상세한 통계 수집
        eng = _get_its_engine(1)
        
        # 오늘 수집된 데이터 수 조회
        today = datetime.now().strftime('%Y-%m-%d')
        today_data_query = text("""
            SELECT COUNT(*) as count 
            FROM tb_sensor_data 
            WHERE DATE(created_at) = :today
        """)
        today_data_result = pd.read_sql(today_data_query, eng, params={"today": today})
        today_data_count = today_data_result.iloc[0]['count'] if not today_data_result.empty else 0
        
        # 최근 7일간 데이터 수집 추이
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        weekly_data_query = text("""
            SELECT DATE(created_at) as date, COUNT(*) as count 
            FROM tb_sensor_data 
            WHERE DATE(created_at) >= :week_ago
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at)
        """)
        weekly_data = pd.read_sql(weekly_data_query, eng, params={"week_ago": week_ago})
        
        # 활성 센서 상태 조회 (최근 2시간 내 데이터 있는 센서)
        active_sensor_query = text("""
            SELECT DISTINCT deviceid, channel
            FROM tb_sensor_data 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 2 HOUR)
        """)
        active_sensors_result = pd.read_sql(active_sensor_query, eng)
        active_sensors_count = len(active_sensors_result) if not active_sensors_result.empty else 0
        
        # 최근 로그인 사용자 수 (오늘)
        recent_login_query = text("""
            SELECT COUNT(DISTINCT userid) as count
            FROM tb_user_log 
            WHERE DATE(created_at) = :today
            AND action = 'LOGIN_SUCCESS'
        """)
        recent_login_result = pd.read_sql(recent_login_query, eng, params={"today": today})
        recent_login_count = recent_login_result.iloc[0]['count'] if not recent_login_result.empty else 0
        
        # 시스템 건강 상태 계산
        health_score = 100
        if active_sensors_count == 0:
            health_score -= 30
        elif active_sensors_count < total_sensors * 0.8:
            health_score -= 15
        
        if today_data_count == 0:
            health_score -= 20
        
        if health_score >= 90:
            system_status = '우수'
            status_color = 'success'
        elif health_score >= 70:
            system_status = '양호'
            status_color = 'warning'
        else:
            system_status = '주의'
            status_color = 'danger'
        
        return {
            'active_projects': active_projects,
            'total_sensors': total_sensors,
            'active_sensors': active_sensors_count,
            'today_data_count': today_data_count,
            'weekly_data': weekly_data,
            'recent_login_count': recent_login_count,
            'health_score': health_score,
            'system_status': system_status,
            'status_color': status_color
        }
    except Exception as e:
        print(f"시스템 통계 조회 오류: {e}")
        return {
            'active_projects': 0,
            'total_sensors': 0,
            'active_sensors': 0,
            'today_data_count': 0,
            'weekly_data': pd.DataFrame(),
            'recent_login_count': 0,
            'health_score': 0,
            'system_status': '오류',
            'status_color': 'danger'
        }

def create_feature_card(title, description, href, color):
    """기능 카드 컴포넌트 생성"""
    return dbc.Card([
        dbc.CardBody([
            html.H5(title, className=f"card-title text-{color}"),
            html.P(description, className="card-text"),
            dcc.Link(
                dbc.Button(title.split(" ")[-1], color=color, className="w-100"),
                href=href
            )
        ])
    ], className="mb-3")

def create_enhanced_status_card(title, value, subtitle, icon, color, progress=None, extra_info=None):
    """향상된 상태 카드 컴포넌트 생성"""
    card_content = [
        html.Div([
            html.Div([
                html.I(className=f"fas {icon} fa-2x text-{color} mb-2"),
                html.H6(title, className="text-muted mb-1"),
                html.H2(str(value), className=f"fw-bold text-{color} mb-1"),
                html.Small(subtitle, className="text-muted")
            ], className="text-center")
        ])
    ]
    
    # 프로그레스 바 추가
    if progress is not None:
        card_content.append(
            html.Div([
                dbc.Progress(
                    value=progress,
                    color=color,
                    className="mt-3",
                    style={"height": "8px"}
                ),
                html.Small(f"{progress}%", className="text-muted mt-1")
            ])
        )
    
    # 추가 정보 표시
    if extra_info:
        card_content.append(
            html.Div([
                html.Hr(className="my-2"),
                html.Small(extra_info, className="text-muted")
            ])
        )
    
    return dbc.Card([
        dbc.CardBody(card_content, className="p-3")
    ], className="h-100 shadow-sm border-0", 
       style={"borderLeft": f"4px solid var(--bs-{color})"})

def create_data_trend_chart(weekly_data):
    """데이터 수집 추이 차트 생성"""
    if weekly_data.empty:
        return html.Div([
            html.P("데이터가 없습니다", className="text-muted text-center my-4")
        ])
    
    # 최근 7일 날짜 생성
    dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    
    # 데이터 정렬 및 누락된 날짜 0으로 채우기
    data_dict = dict(zip(weekly_data['date'].astype(str), weekly_data['count']))
    counts = [data_dict.get(date, 0) for date in dates]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates,
        y=counts,
        mode='lines+markers',
        line=dict(color='#28a745', width=3),
        marker=dict(size=8, color='#28a745'),
        fill='tonexty',
        fillcolor='rgba(40, 167, 69, 0.1)',
        name='수집 데이터'
    ))
    
    fig.update_layout(
        title="최근 7일 데이터 수집 추이",
        xaxis_title="날짜",
        yaxis_title="데이터 수",
        height=250,
        margin=dict(l=40, r=40, t=40, b=40),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12),
        showlegend=False
    )
    
    fig.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.1)')
    fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.1)')
    
    return dcc.Graph(figure=fig, config={'displayModeBar': False})

def create_sensor_status_donut(active_sensors, total_sensors):
    """센서 상태 도넛 차트 생성"""
    if total_sensors == 0:
        return html.Div([
            html.P("센서 데이터가 없습니다", className="text-muted text-center my-4")
        ])
    
    inactive_sensors = max(0, total_sensors - active_sensors)
    
    fig = go.Figure(data=[go.Pie(
        labels=['활성', '비활성'],
        values=[active_sensors, inactive_sensors],
        hole=.6,
        marker_colors=['#28a745', '#dc3545']
    )])
    
    fig.update_layout(
        title="센서 상태 분포",
        height=200,
        margin=dict(l=20, r=20, t=40, b=20),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
    )
    
    # 가운데 텍스트 추가
    fig.add_annotation(
        text=f"{active_sensors}<br><span style='font-size:12px'>활성</span>",
        x=0.5, y=0.5,
        font_size=20,
        showarrow=False
    )
    
    return dcc.Graph(figure=fig, config={'displayModeBar': False})

def layout(**kwargs):
    """Admin dashboard layout."""
    return html.Div([
        dcc.Location(id="admin-dashboard-url", refresh=False),
        dcc.Interval(
            id='dashboard-interval',
            interval=30*1000,  # 30초마다 업데이트
            n_intervals=0
        ),
        dbc.Container([
            # 메인 콘텐츠
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.Div([
                                html.H4("🔧 관리자 기능", className="mb-0 text-primary"),
                                html.Small("실시간 모니터링 • 30초마다 자동 업데이트", className="text-muted")
                            ])
                        ]),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    create_feature_card(
                                        "📊 프로젝트 관리",
                                        "프로젝트 생성, 수정, 삭제 및 권한 관리",
                                        "/admin_projects",
                                        "primary"
                                    )
                                ], width=3),
                                dbc.Col([
                                    create_feature_card(
                                        "📋 일반 로그",
                                        "로그인, 센서, 프로젝트, 콘크리트 로그 확인",
                                        "/admin_logs",
                                        "success"
                                    )
                                ], width=3),
                                dbc.Col([
                                    create_feature_card(
                                        "⚙️ 자동화 로그",
                                        "자동화 작업 로그 및 모니터링",
                                        "/admin_automation",
                                        "warning"
                                    )
                                ], width=3),
                            ]),
                            
                            html.Hr(className="my-4"),
                            
                            # 시스템 상태 요약
                            dbc.Row([
                                dbc.Col([
                                    html.H5("📈 시스템 현황", className="text-dark mb-3"),
                                    html.Div(id="system-status-cards")
                                ])
                            ]),
                            
                            # 상세 통계 및 차트
                            dbc.Row([
                                dbc.Col([
                                    html.H5("📊 데이터 분석", className="text-dark mb-3 mt-4"),
                                    html.Div(id="system-charts")
                                ])
                            ])
                        ])
                    ], className="shadow")
                ])
            ])
        ], fluid=True)
    ])

@callback(
    [Output("system-status-cards", "children"),
     Output("system-charts", "children")],
    [Input("admin-dashboard-url", "pathname"),
     Input("dashboard-interval", "n_intervals")]
)
def update_system_status(pathname, n_intervals):
    """시스템 상태 카드 및 차트 업데이트"""
    stats = get_system_stats()
    
    # 메인 상태 카드들
    sensor_ratio = (stats['active_sensors'] / stats['total_sensors'] * 100) if stats['total_sensors'] > 0 else 0
    
    status_cards = dbc.Row([
        dbc.Col([
            create_enhanced_status_card(
                "활성 프로젝트",
                stats['active_projects'],
                "등록된 프로젝트",
                "fa-folder-open",
                "primary",
                extra_info="프로젝트 관리에서 상세 확인"
            )
        ], width=3),
        dbc.Col([
            create_enhanced_status_card(
                "오늘 수집 데이터",
                f"{stats['today_data_count']:,}",
                "건의 센서 데이터",
                "fa-database",
                "success",
                extra_info="실시간 센서 데이터 수집"
            )
        ], width=3),
        dbc.Col([
            create_enhanced_status_card(
                "활성 센서",
                f"{stats['active_sensors']}/{stats['total_sensors']}",
                f"센서 활성률",
                "fa-satellite-dish",
                "info",
                progress=sensor_ratio,
                extra_info="최근 2시간 내 데이터 수집 기준"
            )
        ], width=3),
        dbc.Col([
            create_enhanced_status_card(
                "시스템 상태",
                stats['system_status'],
                f"건강도 {stats['health_score']}%",
                "fa-heartbeat",
                stats['status_color'],
                progress=stats['health_score'],
                extra_info="종합 시스템 건강도"
            )
        ], width=3),
    ], className="g-3")
    
    # 추가 통계 및 차트
    charts_section = dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H6("📈 데이터 수집 추이", className="mb-0 text-success")
                ]),
                dbc.CardBody([
                    create_data_trend_chart(stats['weekly_data'])
                ])
            ], className="shadow-sm border-0")
        ], width=8),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H6("🎯 센서 상태", className="mb-0 text-info")
                ]),
                dbc.CardBody([
                    create_sensor_status_donut(stats['active_sensors'], stats['total_sensors'])
                ])
            ], className="shadow-sm border-0 mb-3"),
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.I(className="fas fa-users fa-2x text-warning mb-2"),
                        html.H6("오늘 로그인", className="text-muted mb-1"),
                        html.H3(str(stats['recent_login_count']), className="fw-bold text-warning mb-1"),
                        html.Small("명의 사용자", className="text-muted"),
                        html.Hr(className="my-2"),
                        html.Small("오늘 접속한 고유 사용자 수", className="text-muted")
                    ], className="text-center")
                ])
            ], className="shadow-sm border-0",
               style={"borderLeft": "4px solid var(--bs-warning)"})
        ], width=4)
    ], className="g-3 mt-2")
    
    return status_cards, charts_section

@callback(
    [Output("admin-dashboard-url", "pathname")],
    [Input("admin-dashboard-url", "pathname")],
    allow_duplicate=True
)
def check_admin_access(pathname):
    """관리자 권한 확인"""
    if not flask_request.cookies.get("admin_user"):
        return ["/admin"]
    return [pathname] 