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
        dbc.Container([
            # 간단한 테스트 레이아웃
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H4("🔧 관리자 대시보드", className="mb-0 text-primary")
                        ]),
                        dbc.CardBody([
                            html.P("관리자 대시보드가 정상적으로 로드되었습니다.", className="text-center"),
                            html.Hr(),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.H5("📊 프로젝트 관리", className="card-title text-primary"),
                                            html.P("프로젝트 생성, 수정, 삭제 및 권한 관리", className="card-text"),
                                            dcc.Link(
                                                dbc.Button("프로젝트 관리", color="primary", className="w-100"),
                                                href="/admin_projects"
                                            )
                                        ])
                                    ], className="mb-3")
                                ], width=4),
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.H5("📋 일반 로그", className="card-title text-success"),
                                            html.P("로그인, 센서, 프로젝트, 콘크리트 로그 확인", className="card-text"),
                                            dcc.Link(
                                                dbc.Button("일반 로그", color="success", className="w-100"),
                                                href="/admin_logs"
                                            )
                                        ])
                                    ], className="mb-3")
                                ], width=4),
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardBody([
                                            html.H5("⚙️ 자동화 로그", className="card-title text-warning"),
                                            html.P("자동화 작업 로그 및 모니터링", className="card-text"),
                                            dcc.Link(
                                                dbc.Button("자동화 로그", color="warning", className="w-100"),
                                                href="/admin_automation"
                                            )
                                        ])
                                    ], className="mb-3")
                                ], width=4)
                            ])
                        ])
                    ], className="shadow")
                ])
            ])
        ], fluid=True)
    ])

# 복잡한 콜백들은 임시로 제거하여 페이지 로딩 문제를 해결합니다 