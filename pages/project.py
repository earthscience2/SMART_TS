#!/usr/bin/env python3
# pages/project_simple.py
"""Dash 페이지: 프로젝트 및 콘크리트 관리 (간단 버전)"""

from __future__ import annotations

import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime
import dash
from dash import (
    html, dcc, Input, Output, State,
    dash_table, register_page, callback
)
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import api_db

register_page(__name__, path="/project", title="프로젝트 관리")

# 레이아웃
layout = html.Div([
    # 프로젝트 선택
    html.Div([
        html.H4("프로젝트 관리", style={"marginBottom": "20px"}),
        html.Div(id="project-content")
    ])
])

# 콜백
@callback(
    Output("project-content", "children"),
    Input("url", "pathname"),
    Input("url", "search")
)
def load_project_content(pathname, search):
    """프로젝트 콘텐츠를 로드합니다."""
    return html.Div([
        html.H5("프로젝트 목록"),
        html.P("프로젝트 관리 기능이 준비 중입니다.")
    ]) 