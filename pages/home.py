from dash import html, register_page, dcc
import dash_bootstrap_components as dbc

register_page(__name__, path="/")   # 메인 URL

layout = html.Div([
    html.H2("Welcome 👋", className="display-6 mb-4"),
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader("프로젝트 개요"),
            dbc.CardBody("대용량 콘크리트 내부 온도 모니터링 시스템.")
        ], className="h-100"), md=4),
        dbc.Col(dbc.Card([
            dbc.CardHeader("빠른 시작"),
            dbc.ListGroup([
                dbc.ListGroupItem(dcc.Link("콘크리트 추가 페이지 →", href="/concrete")),
                dbc.ListGroupItem(dcc.Link("센서 추가 페이지 →", href="/sensor")),
            ])
        ], className="h-100"), md=4),
    ], className="g-4")
])