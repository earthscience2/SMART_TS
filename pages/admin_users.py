from dash import html, dcc, register_page, callback, Input, Output
import dash_bootstrap_components as dbc
from flask import request as flask_request
from api_db import get_user_data
from datetime import datetime

register_page(__name__, path="/admin_users", title="사용자 관리")

# 권한 등급 매핑
AUTHORITY_MAPPING = {
    'AD': {'label': 'Administrator', 'description': '관리자 - 모든 기능 접근 가능', 'color': 'danger'},
    'CM': {'label': 'Contract Manager', 'description': '계약 관리자 - 프로젝트 관리 권한', 'color': 'warning'},
    'CT': {'label': 'Contractor', 'description': '계약자 - 제한된 프로젝트 접근', 'color': 'info'},
    'US': {'label': 'User', 'description': '일반 사용자 - 기본 기능만 접근', 'color': 'secondary'}
}

def get_user_status(end_date):
    """사용자 권한 상태 확인"""
    if not end_date:
        return {'status': '무기한', 'color': 'primary'}
    
    try:
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
        today = datetime.now().date()
        
        if end_dt >= today:
            return {'status': '활성', 'color': 'success'}
        else:
            return {'status': '만료', 'color': 'secondary'}
    except:
        return {'status': '오류', 'color': 'danger'}

def create_user_table_rows(users_data):
    """사용자 테이블 행 생성"""
    if not users_data:
        return [html.Tr([html.Td("사용자 데이터가 없습니다.", colSpan=6, className="text-center")])]
    
    rows = []
    for user in users_data:
        authority = user.get('authority', 'US')
        auth_info = AUTHORITY_MAPPING.get(authority, AUTHORITY_MAPPING['US'])
        status_info = get_user_status(user.get('authority_end_date'))
        
        row = html.Tr([
            html.Td(user.get('user_id', '')),
            html.Td(dbc.Badge(authority, color=auth_info['color'])),
            html.Td(user.get('authority_start_date', '-')),
            html.Td(user.get('authority_end_date', '무기한')),
            html.Td(dbc.Badge(status_info['status'], color=status_info['color'])),
            html.Td([
                dbc.Button("수정", size="sm", color="primary", className="me-1"),
                dbc.Button("권한", size="sm", color="warning", className="me-1"),
                dbc.Button("삭제", size="sm", color="danger")
            ])
        ])
        rows.append(row)
    
    return rows

def create_authority_description():
    """권한 등급 설명 생성"""
    descriptions = []
    for auth_code, info in AUTHORITY_MAPPING.items():
        descriptions.append(html.Strong(f"{auth_code} ({info['label']}): "))
        descriptions.append(info['description'])
        descriptions.append(html.Br())
    
    # 마지막 Br() 제거
    if descriptions:
        descriptions.pop()
    
    return dbc.Alert(descriptions, color="light", className="mb-3")

def layout(**kwargs):
    """Admin users management layout."""
    return html.Div([
        dcc.Location(id="admin-users-url", refresh=False),
        dcc.Interval(id="users-refresh-interval", interval=30000, n_intervals=0),  # 30초마다 새로고침
        dbc.Container([
            # 메인 콘텐츠
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H4("👥 사용자 관리", className="mb-0 text-info"),
                            html.Small("사용자 계정 및 권한 관리", className="text-muted")
                        ]),
                        dbc.CardBody([
                            # 사용자 추가 버튼
                            dbc.Row([
                                dbc.Col([
                                    dbc.Button([
                                        html.Span("➕", className="me-2"),
                                        "새 사용자 추가"
                                    ], color="success", className="mb-3", id="add-user-btn")
                                ], width=12)
                            ]),
                            
                            # 사용자 목록 테이블
                            html.Div(id="users-table-container"),
                            
                            # 권한 등급 설명
                            dbc.Row([
                                dbc.Col([
                                    html.H6("권한 등급 설명", className="mt-4 mb-2"),
                                    create_authority_description()
                                ])
                            ]),
                            
                            # 페이지네이션
                            dbc.Row([
                                dbc.Col([
                                    html.Div(id="users-pagination-container", className="d-flex justify-content-center mt-3")
                                ])
                            ])
                        ])
                    ], className="shadow")
                ])
            ])
        ], fluid=True)
    ])

@callback(
    [Output("users-table-container", "children"),
     Output("users-pagination-container", "children")],
    [Input("users-refresh-interval", "n_intervals")]
)
def update_users_table(n_intervals):
    """사용자 테이블 업데이트"""
    try:
        users_df = get_user_data()
        
        if users_df.empty:
            table_content = dbc.Alert("등록된 사용자가 없습니다.", color="info")
            pagination = ""
        else:
            # DataFrame을 딕셔너리 리스트로 변환
            users_data = users_df.to_dict('records')
            
            # 테이블 생성
            table_rows = create_user_table_rows(users_data)
            
            table_content = dbc.Table([
                html.Thead([
                    html.Tr([
                        html.Th("사용자 ID"),
                        html.Th("권한 등급"),
                        html.Th("권한 시작일"),
                        html.Th("권한 종료일"),
                        html.Th("상태"),
                        html.Th("작업")
                    ])
                ]),
                html.Tbody(table_rows)
            ], striped=True, bordered=True, hover=True, responsive=True)
            
            # 페이지네이션 (현재는 간단히 처리)
            total_users = len(users_data)
            if total_users > 10:
                pagination = dbc.Pagination(
                    id="user-pagination",
                    max_value=5,
                    fully_expanded=False,
                    first_last=True,
                    previous_next=True,
                    className="justify-content-center mt-3"
                )
            else:
                pagination = ""
        
        return table_content, pagination
        
    except Exception as e:
        error_msg = f"사용자 데이터 로딩 오류: {str(e)}"
        return dbc.Alert(error_msg, color="danger"), ""

@callback(
    [Output("admin-users-url", "pathname")],
    [Input("admin-users-url", "pathname")],
    allow_duplicate=True
)
def check_admin_access(pathname):
    """관리자 권한 확인"""
    if not flask_request.cookies.get("admin_user"):
        return ["/admin"]
    return [pathname] 