#!/usr/bin/env python3
# app.py – 멀티-페이지 셸
from __future__ import annotations
import dash
from dash import html, dcc, page_container
import dash_bootstrap_components as dbc

# multipage 활성화
app = dash.Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,   # ← 추가
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)
app.title = "Concrete Dashboard"

# 공통 레이아웃
app.layout = dbc.Container(fluid=True, children=[
    dbc.NavbarSimple(
        brand="Concrete MONITOR", color="dark", dark=True, className="mb-4",
        children=[
            dbc.NavItem(dcc.Link("Home", href="/", className="nav-link")),
            dbc.NavItem(dcc.Link("concrete", href="/concrete", className="nav-link")),
            dbc.NavItem(dcc.Link("sensor", href="/sensor", className="nav-link")),
        ],
    ),
    dbc.Card(className="shadow-sm p-4", children=[
        page_container      # 각 pages/ 의 layout 이 여기에 렌더링
    ])
])

if __name__ == "__main__":
    app.run(debug=True)