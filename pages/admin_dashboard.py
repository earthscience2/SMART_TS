from dash import html, dcc, register_page, callback, Input, Output
import dash_bootstrap_components as dbc
from flask import request as flask_request
from api_db import get_project_data_with_stats
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objs as go

register_page(__name__, path="/admin_dashboard", title="관리자 대시보드")

def get_system_stats():
    """시스템 통계 데이터를 가져옵니다"""
    try:
        from api_db import _get_its_engine, text
        import os
        import re
        
        # 프로젝트 데이터 조회
        projects_df = get_project_data_with_stats()
        active_projects = len(projects_df) if not projects_df.empty else 0
        
        # 센서 수는 프로젝트 데이터에서 집계
        total_sensors = projects_df['sensor_count'].sum() if not projects_df.empty else 0
        
        # ITS 엔진으로 더 상세한 통계 수집
        eng = _get_its_engine(1)
        
        # 최근 7일 날짜 생성
        dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
        
        # === 시스템 현황 데이터 ===
        
        # 1. 최근 7일간 로그인 횟수 (일별)
        login_data = []
        for date in dates:
            try:
                login_query = text("""
                    SELECT COUNT(*) as count FROM tb_user_log 
                    WHERE DATE(created_at) = :date AND action = 'LOGIN_SUCCESS'
                """)
                result = pd.read_sql(login_query, eng, params={"date": date})
                count = result.iloc[0]['count'] if not result.empty and 'count' in result.columns else 0
                login_data.append(int(count) if count is not None else 0)
            except Exception as e:
                print(f"로그인 데이터 조회 오류: {e}")
                login_data.append(0)
        
        # 2. 프로젝트 수 (누적)
        project_cumulative = []
        for date in dates:
            try:
                project_query = text("""
                    SELECT COUNT(*) as count FROM tb_project 
                    WHERE DATE(created_at) <= :date
                """)
                result = pd.read_sql(project_query, eng, params={"date": date})
                count = result.iloc[0]['count'] if not result.empty and 'count' in result.columns else 0
                project_cumulative.append(int(count) if count is not None else 0)
            except Exception as e:
                print(f"프로젝트 데이터 조회 오류: {e}")
                project_cumulative.append(0)
        
        # 3. 콘크리트 수 (누적)
        concrete_cumulative = []
        for date in dates:
            try:
                concrete_query = text("""
                    SELECT COUNT(*) as count FROM tb_concrete 
                    WHERE DATE(created_at) <= :date
                """)
                result = pd.read_sql(concrete_query, eng, params={"date": date})
                count = result.iloc[0]['count'] if not result.empty and 'count' in result.columns else 0
                concrete_cumulative.append(int(count) if count is not None else 0)
            except Exception as e:
                print(f"콘크리트 데이터 조회 오류: {e}")
                concrete_cumulative.append(0)
        
        # 4. 센서 데이터 수 (누적)
        sensor_data_cumulative = []
        for date in dates:
            try:
                sensor_query = text("""
                    SELECT COUNT(*) as count FROM tb_sensor_data 
                    WHERE DATE(created_at) <= :date
                """)
                result = pd.read_sql(sensor_query, eng, params={"date": date})
                count = result.iloc[0]['count'] if not result.empty and 'count' in result.columns else 0
                sensor_data_cumulative.append(int(count) if count is not None else 0)
            except Exception as e:
                print(f"센서 데이터 조회 오류: {e}")
                sensor_data_cumulative.append(0)
        
        # === 데이터 분석 데이터 (로그 파일 기반) ===
        
        # 로그 파일들을 읽어서 분석
        log_dir = "log"
        sensor_data_daily = [0] * 7
        inp_conversion_daily = [0] * 7
        inp_to_frd_daily = [0] * 7
        frd_to_vtk_daily = [0] * 7
        
        try:
            if os.path.exists(log_dir):
                import glob
                for i, date in enumerate(dates):
                    if i >= 7:  # 안전 체크
                        break
                    
                    try:
                        date_str = str(date).replace('-', '')  # YYYYMMDD 형식
                        
                        # 센서 데이터 수집 로그
                        sensor_log_pattern = f"sensor_{date_str}_*.log"
                        sensor_files = glob.glob(os.path.join(log_dir, sensor_log_pattern))
                        
                        for file_path in sensor_files:
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                    matches = re.findall(r'데이터 수집', content)
                                    sensor_data_daily[i] += len(matches) if matches else 0
                            except Exception as e:
                                print(f"센서 로그 파일 읽기 오류 ({file_path}): {e}")
                                continue
                        
                        # 자동화 로그에서 변환 작업 횟수 추출
                        auto_log_file = os.path.join(log_dir, f"automation_{date_str}.log")
                        if os.path.exists(auto_log_file):
                            try:
                                with open(auto_log_file, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                    inp_matches = re.findall(r'inp.*변환.*완료', content, re.IGNORECASE)
                                    inp_frd_matches = re.findall(r'inp.*frd.*변환.*완료', content, re.IGNORECASE)
                                    frd_vtk_matches = re.findall(r'frd.*vtk.*변환.*완료', content, re.IGNORECASE)
                                    
                                    inp_conversion_daily[i] = len(inp_matches) if inp_matches else 0
                                    inp_to_frd_daily[i] = len(inp_frd_matches) if inp_frd_matches else 0
                                    frd_to_vtk_daily[i] = len(frd_vtk_matches) if frd_vtk_matches else 0
                            except Exception as e:
                                print(f"자동화 로그 파일 읽기 오류 ({auto_log_file}): {e}")
                                continue
                    except Exception as e:
                        print(f"날짜 {date} 로그 처리 오류: {e}")
                        continue
        except Exception as e:
            print(f"로그 디렉토리 처리 오류: {e}")
            # 기본값은 이미 설정됨
        
        # 오늘 데이터
        today = datetime.now().strftime('%Y-%m-%d')
        today_data_query = text("""
            SELECT COUNT(*) as count 
            FROM tb_sensor_data 
            WHERE DATE(created_at) = :today
        """)
        today_data_result = pd.read_sql(today_data_query, eng, params={"today": today})
        today_data_count = today_data_result.iloc[0]['count'] if not today_data_result.empty else 0
        
        # 활성 센서 상태 조회
        active_sensor_query = text("""
            SELECT DISTINCT deviceid, channel
            FROM tb_sensor_data 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 2 HOUR)
        """)
        active_sensors_result = pd.read_sql(active_sensor_query, eng)
        active_sensors_count = len(active_sensors_result) if not active_sensors_result.empty else 0
        
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
            'dates': dates,
            'active_projects': active_projects,
            'total_sensors': total_sensors,
            'active_sensors': active_sensors_count,
            'today_data_count': today_data_count,
            'health_score': health_score,
            'system_status': system_status,
            'status_color': status_color,
            # 시스템 현황 데이터
            'login_daily': login_data,
            'project_cumulative': project_cumulative,
            'concrete_cumulative': concrete_cumulative,
            'sensor_data_cumulative': sensor_data_cumulative,
            # 데이터 분석 데이터
            'sensor_data_daily': sensor_data_daily,
            'inp_conversion_daily': inp_conversion_daily,
            'inp_to_frd_daily': inp_to_frd_daily,
            'frd_to_vtk_daily': frd_to_vtk_daily
        }
    except Exception as e:
        print(f"시스템 통계 조회 오류: {e}")
        dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
        return {
            'dates': dates,
            'active_projects': 0,
            'total_sensors': 0,
            'active_sensors': 0,
            'today_data_count': 0,
            'health_score': 0,
            'system_status': '오류',
            'status_color': 'danger',
            'login_daily': [0] * 7,
            'project_cumulative': [0] * 7,
            'concrete_cumulative': [0] * 7,
            'sensor_data_cumulative': [0] * 7,
            'sensor_data_daily': [0] * 7,
            'inp_conversion_daily': [0] * 7,
            'inp_to_frd_daily': [0] * 7,
            'frd_to_vtk_daily': [0] * 7
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

def create_mini_chart(dates, data, title, color, chart_type='line', unit='개'):
    """미니 차트 생성 (시스템 현황용)"""
    try:
        if not data or not dates or len(data) == 0 or len(dates) == 0:
            return html.Div([
                html.P("데이터가 없습니다", className="text-muted text-center my-4")
            ])
        
        # 안전한 날짜 변환
        display_dates = []
        for date in dates:
            try:
                display_dates.append(datetime.strptime(str(date), '%Y-%m-%d').strftime('%m-%d'))
            except:
                display_dates.append(str(date)[-5:])  # 마지막 5자리 (MM-DD)
        
        # 색상을 안전하게 처리
        def hex_to_rgba(hex_color, alpha=0.1):
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 6:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return f'rgba({r},{g},{b},{alpha})'
            return 'rgba(0,0,0,0.1)'
        
        fig = go.Figure()
        
        if chart_type == 'line':
            fig.add_trace(go.Scatter(
                x=display_dates,
                y=data,
                mode='lines+markers',
                line=dict(color=color, width=3),
                marker=dict(size=6, color=color),
                fill='tonexty',
                fillcolor=hex_to_rgba(color, 0.1),
                name=title
            ))
        else:  # bar chart
            fig.add_trace(go.Bar(
                x=display_dates,
                y=data,
                marker_color=color,
                name=title
            ))
        
        fig.update_layout(
            title=dict(
                text=f"<b>{title}</b>",
                font=dict(size=14, color='#2c3e50')
            ),
            height=180,
            margin=dict(l=30, r=20, t=40, b=30),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(size=10, family="Arial, sans-serif"),
            showlegend=False,
            xaxis=dict(
                showgrid=False,
                tickfont=dict(size=9),
                title=""
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='rgba(0,0,0,0.05)',
                tickfont=dict(size=9),
                title=""
            )
        )
        
        # 마지막 값 표시 (안전하게)
        if data and len(data) > 0 and len(display_dates) > 0:
            last_value = data[-1] if data[-1] is not None else 0
            fig.add_annotation(
                x=display_dates[-1],
                y=last_value,
                text=f"<b>{last_value:,}{unit}</b>",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=2,
                arrowcolor=color,
                font=dict(size=10, color=color, family="Arial, sans-serif"),
                bgcolor="white",
                bordercolor=color,
                borderwidth=1
            )
        
        return dcc.Graph(figure=fig, config={'displayModeBar': False})
    
    except Exception as e:
        print(f"차트 생성 오류: {e}")
        return html.Div([
            html.P("차트 생성 중 오류가 발생했습니다", className="text-muted text-center my-4")
        ])

def create_analysis_chart(dates, data, title, color, unit='회'):
    """분석 차트 생성 (데이터 분석용)"""
    try:
        if not data or not dates or len(data) == 0 or len(dates) == 0:
            return html.Div([
                html.Div([
                    html.I(className="fas fa-chart-line fa-3x text-muted mb-3"),
                    html.P("데이터가 없습니다", className="text-muted")
                ], className="text-center py-4")
            ])
        
        # 안전한 날짜 변환
        display_dates = []
        for date in dates:
            try:
                display_dates.append(datetime.strptime(str(date), '%Y-%m-%d').strftime('%m-%d'))
            except:
                display_dates.append(str(date)[-5:])  # 마지막 5자리 (MM-DD)
        
        # 색상을 안전하게 처리
        def hex_to_rgba(hex_color, alpha=0.3):
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 6:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return f'rgba({r},{g},{b},{alpha})'
            return 'rgba(0,0,0,0.3)'
        
        fig = go.Figure()
        
        # 안전한 데이터 변환
        safe_data = [int(x) if x is not None else 0 for x in data]
        
        # 그라데이션 효과를 위한 바 차트
        fig.add_trace(go.Bar(
            x=display_dates,
            y=safe_data,
            marker=dict(
                color=safe_data,
                colorscale=[[0, hex_to_rgba(color, 0.3)], [1, color]],
                line=dict(color=color, width=1)
            ),
            name=title,
            text=[f'{val}{unit}' if val > 0 else '' for val in safe_data],
            textposition='outside',
            textfont=dict(size=10, color=color)
        ))
        
        fig.update_layout(
            title=dict(
                text=f"<b>{title}</b>",
                font=dict(size=14, color='#2c3e50'),
                x=0.5
            ),
            height=200,
            margin=dict(l=30, r=20, t=50, b=30),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(size=10, family="Arial, sans-serif"),
            showlegend=False,
            xaxis=dict(
                showgrid=False,
                tickfont=dict(size=9),
                title=""
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='rgba(0,0,0,0.08)',
                tickfont=dict(size=9),
                title=""
            )
        )
        
        return dcc.Graph(figure=fig, config={'displayModeBar': False})
    
    except Exception as e:
        print(f"분석 차트 생성 오류: {e}")
        return html.Div([
            html.Div([
                html.I(className="fas fa-exclamation-triangle fa-3x text-warning mb-3"),
                html.P("차트 생성 중 오류가 발생했습니다", className="text-muted")
            ], className="text-center py-4")
        ])

def layout(**kwargs):
    """Admin dashboard layout."""
    return html.Div([
        dcc.Location(id="admin-dashboard-url", refresh=False),
        dcc.Interval(
            id='dashboard-interval',
            interval=30*1000,  # 30초마다 업데이트
            n_intervals=0
        ),
        # 카스텀 CSS 스타일
        html.Style("""
            .hover-card {
                transition: all 0.3s ease !important;
                border: 1px solid rgba(0,0,0,0.1) !important;
            }
            .hover-card:hover {
                transform: translateY(-2px) !important;
                box-shadow: 0 8px 25px rgba(0,0,0,0.15) !important;
                border-color: rgba(0,123,255,0.3) !important;
            }
            .card-body {
                border-radius: 8px;
            }
            .card-header {
                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                border-bottom: 1px solid rgba(0,0,0,0.1);
                font-weight: 600;
            }
        """),
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
                            
                            # 시스템 현황
                            dbc.Row([
                                dbc.Col([
                                    html.H5("📈 시스템 현황", className="text-dark mb-3"),
                                    html.Div(id="system-overview-charts")
                                ])
                            ]),
                            
                            # 데이터 분석
                            dbc.Row([
                                dbc.Col([
                                    html.H5("📊 데이터 분석", className="text-dark mb-3 mt-4"),
                                    html.Div(id="data-analysis-charts")
                                ])
                            ])
                        ])
                    ], className="shadow")
                ])
            ])
        ], fluid=True)
    ])

@callback(
    [Output("system-overview-charts", "children"),
     Output("data-analysis-charts", "children")],
    [Input("admin-dashboard-url", "pathname"),
     Input("dashboard-interval", "n_intervals")]
)
def update_dashboard_charts(pathname, n_intervals):
    """대시보드 차트 업데이트"""
    try:
        stats = get_system_stats()
        
        # 안전한 데이터 추출
        dates = stats.get('dates', [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)])
        login_daily = stats.get('login_daily', [0] * 7)
        project_cumulative = stats.get('project_cumulative', [0] * 7)
        concrete_cumulative = stats.get('concrete_cumulative', [0] * 7)
        sensor_data_cumulative = stats.get('sensor_data_cumulative', [0] * 7)
        sensor_data_daily = stats.get('sensor_data_daily', [0] * 7)
        inp_conversion_daily = stats.get('inp_conversion_daily', [0] * 7)
        inp_to_frd_daily = stats.get('inp_to_frd_daily', [0] * 7)
        frd_to_vtk_daily = stats.get('frd_to_vtk_daily', [0] * 7)
        
        # === 시스템 현황 차트 ===
        overview_charts = dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        create_mini_chart(
                            dates, 
                            login_daily, 
                            "일별 로그인 횟수", 
                            "#007bff", 
                            "bar", 
                            "회"
                        )
                    ], className="p-2")
                ], className="h-100 shadow-sm border-0 hover-card")
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        create_mini_chart(
                            dates, 
                            project_cumulative, 
                            "누적 프로젝트 수", 
                            "#28a745", 
                            "line", 
                            "개"
                        )
                    ], className="p-2")
                ], className="h-100 shadow-sm border-0 hover-card")
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        create_mini_chart(
                            dates, 
                            concrete_cumulative, 
                            "누적 콘크리트 수", 
                            "#ffc107", 
                            "line", 
                            "개"
                        )
                    ], className="p-2")
                ], className="h-100 shadow-sm border-0 hover-card")
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        create_mini_chart(
                            dates, 
                            sensor_data_cumulative, 
                            "누적 센서 데이터 수", 
                            "#17a2b8", 
                            "line", 
                            "건"
                        )
                    ], className="p-2")
                ], className="h-100 shadow-sm border-0 hover-card")
            ], width=3)
        ], className="g-3")
        
        # === 데이터 분석 차트 ===
        analysis_charts = dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H6("📊 센서 데이터 수집", className="mb-0 text-primary")
                    ]),
                    dbc.CardBody([
                        create_analysis_chart(
                            dates, 
                            sensor_data_daily, 
                            "일별 센서 데이터 수집", 
                            "#007bff"
                        )
                    ], className="p-2")
                ], className="h-100 shadow-sm border-0 hover-card")
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H6("🔄 INP 파일 변환", className="mb-0 text-success")
                    ]),
                    dbc.CardBody([
                        create_analysis_chart(
                            dates, 
                            inp_conversion_daily, 
                            "일별 INP 변환 작업", 
                            "#28a745"
                        )
                    ], className="p-2")
                ], className="h-100 shadow-sm border-0 hover-card")
            ], width=6)
        ], className="g-3 mb-3")
        
        analysis_charts_2 = dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H6("🔄 INP → FRD 변환", className="mb-0 text-warning")
                    ]),
                    dbc.CardBody([
                        create_analysis_chart(
                            dates, 
                            inp_to_frd_daily, 
                            "일별 INP to FRD 변환", 
                            "#ffc107"
                        )
                    ], className="p-2")
                ], className="h-100 shadow-sm border-0 hover-card")
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H6("🔄 FRD → VTK 변환", className="mb-0 text-info")
                    ]),
                    dbc.CardBody([
                        create_analysis_chart(
                            dates, 
                            frd_to_vtk_daily, 
                            "일별 FRD to VTK 변환", 
                            "#17a2b8"
                        )
                    ], className="p-2")
                ], className="h-100 shadow-sm border-0 hover-card")
            ], width=6)
        ], className="g-3")
        
        # 분석 차트들을 하나의 div로 결합
        analysis_section = html.Div([
            analysis_charts,
            analysis_charts_2
        ])
        
        return overview_charts, analysis_section
    
    except Exception as e:
        print(f"대시보드 차트 업데이트 오류: {e}")
        # 에러 발생 시 기본 메시지 반환
        error_message = html.Div([
            html.Div([
                html.I(className="fas fa-exclamation-triangle fa-3x text-warning mb-3"),
                html.H5("데이터 로딩 중 오류가 발생했습니다", className="text-muted"),
                html.P("잠시 후 다시 시도해주세요.", className="text-muted")
            ], className="text-center py-5")
        ])
        return error_message, error_message

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