#!/usr/bin/env python3
# pages/download.py
"""Dash 페이지: 파일 다운로드 (inp, frd, vtk)
프로젝트 선택 → 콘크리트 선택 → 파일 유형 탭에서 다중 파일 선택 후 다운로드
"""

from __future__ import annotations

import os, glob, io, zipfile
import pandas as pd
from datetime import datetime

import dash
from dash import html, dcc, Input, Output, State, dash_table, register_page
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

import api_db

register_page(__name__, path="/download")

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    children=[
        dcc.Location(id="download-url", refresh=False),
        dbc.Alert(id="download-alert", is_open=False, duration=3000, color="info"),
        # ── 프로젝트 / 콘크리트 선택 영역
        dbc.Row([
            dbc.Col([
                html.H6("프로젝트 선택"),
                dcc.Dropdown(id="dl-ddl-project", clearable=False, placeholder="프로젝트 선택"),
                html.H6("콘크리트 리스트", className="mt-3"),
                dash_table.DataTable(
                    id="dl-tbl-concrete", page_size=10, row_selectable="single",
                    style_table={"overflowY": "auto", "height": "45vh"},
                    style_cell={"whiteSpace": "nowrap", "textAlign": "center"},
                    style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
                ),
            ], md=3),
            dbc.Col([
                html.H6(id="dl-concrete-title"),
                dbc.Tabs([
                    dbc.Tab(label="inp", tab_id="tab-inp"),
                    dbc.Tab(label="frd", tab_id="tab-frd"),
                    dbc.Tab(label="vtk", tab_id="tab-vtk"),
                ], id="dl-tabs", active_tab="tab-inp"),
                html.Div(id="dl-tab-content"),
            ], md=9),
        ], className="g-3"),
    ]
)

# ───────────────────── ① 프로젝트 목록 초기화 ─────────────────────
@dash.callback(
    Output("dl-ddl-project", "options"),
    Output("dl-ddl-project", "value"),
    Input("dl-ddl-project", "value"),
    prevent_initial_call=False,
)
def dl_init_project(selected_value):
    df_proj = api_db.get_project_data()
    opts = [{"label": row["name"], "value": row["project_pk"]} for _, row in df_proj.iterrows()]
    if not opts:
        return [], None
    # 최초: 첫 번째 프로젝트로
    if selected_value is None:
        return opts, opts[0]["value"]
    return opts, selected_value

# ───────────────────── ② 프로젝트 선택 → 콘크리트 테이블 ────────────────────
@dash.callback(
    Output("dl-tbl-concrete", "data"),
    Output("dl-tbl-concrete", "columns"),
    Output("dl-tbl-concrete", "selected_rows"),
    Output("dl-concrete-title", "children"),
    Input("dl-ddl-project", "value"),
    prevent_initial_call=True,
)
def dl_on_project_change(project_pk):
    if not project_pk:
        return [], [], [], ""
    df_conc = api_db.get_concrete_data(project_pk=project_pk)
    data = df_conc[["concrete_pk", "name"]].to_dict("records")
    columns = [{"name": "이름", "id": "name"}]
    title = f"프로젝트 {project_pk} · 콘크리트 {len(data)}개"
    return data, columns, [], title

# ───────────────────── ③ 콘크리트 선택 → 탭 콘텐츠 업데이트 ────────────────────
@dash.callback(
    Output("dl-tab-content", "children"),
    Input("dl-tabs", "active_tab"),
    Input("dl-tbl-concrete", "selected_rows"),
    State("dl-tbl-concrete", "data"),
    prevent_initial_call=True,
)
def dl_switch_tab(active_tab, sel_rows, tbl_data):
    if not sel_rows:
        return html.Div("콘크리트를 선택하세요.")
    concrete_pk = tbl_data[sel_rows[0]]["concrete_pk"]

    if active_tab == "tab-inp":
        folder = f"inp/{concrete_pk}"
        ext = ".inp"
        table_id = "dl-inp-table"
        dl_btn_id = "btn-dl-inp"
        dl_component_id = "dl-inp-download"
    elif active_tab == "tab-frd":
        folder = f"frd/{concrete_pk}"
        ext = ".frd"
        table_id = "dl-frd-table"
        dl_btn_id = "btn-dl-frd"
        dl_component_id = "dl-frd-download"
    else:
        folder = f"assets/vtk/{concrete_pk}"
        ext = ".vtk"
        table_id = "dl-vtk-table"
        dl_btn_id = "btn-dl-vtk"
        dl_component_id = "dl-vtk-download"

    files = []
    if os.path.exists(folder):
        files = sorted([f for f in os.listdir(folder) if f.endswith(ext)])
    columns = [{"name": "파일명", "id": "filename"}]
    table = dash_table.DataTable(
        id=table_id,
        data=[{"filename": f} for f in files],
        columns=columns,
        page_size=10,
        row_selectable="multi",
        style_cell={"textAlign": "center"},
        style_header={"backgroundColor": "#f1f3f5", "fontWeight": 600},
        style_table={"width": "70%", "margin": "auto"},
    )
    return html.Div([
        table,
        html.Div([
            dbc.Button("전체 선택", id=f"btn-select-all-{active_tab}", color="secondary", className="me-2 mt-3", n_clicks=0),
            dbc.Button("전체 해제", id=f"btn-deselect-all-{active_tab}", color="light", className="me-2 mt-3", n_clicks=0),
            dbc.Button("선택 파일 다운로드", id=dl_btn_id, color="success", className="mt-3", n_clicks=0),
            dcc.Download(id=dl_component_id)
        ], style={"textAlign": "center"})
    ])

# ───────────────────── ④ 전체 선택/해제 콜백 (탭별) ────────────────────
@dash.callback(
    Output("dl-inp-table", "selected_rows"),
    Input("btn-select-all-tab-inp", "n_clicks"),
    Input("btn-deselect-all-tab-inp", "n_clicks"),
    State("dl-inp-table", "data"),
    prevent_initial_call=True,
)
def inp_select_deselect(all_click, none_click, table_data):
    ctx = dash.callback_context
    if not ctx.triggered or not table_data:
        raise PreventUpdate
    trig = ctx.triggered_id
    if trig == "btn-select-all-tab-inp":
        return list(range(len(table_data)))
    return []

@dash.callback(
    Output("dl-frd-table", "selected_rows"),
    Input("btn-select-all-tab-frd", "n_clicks"),
    Input("btn-deselect-all-tab-frd", "n_clicks"),
    State("dl-frd-table", "data"),
    prevent_initial_call=True,
)
def frd_select_deselect(all_click, none_click, table_data):
    ctx = dash.callback_context
    if not ctx.triggered or not table_data:
        raise PreventUpdate
    trig = ctx.triggered_id
    if trig == "btn-select-all-tab-frd":
        return list(range(len(table_data)))
    return []

@dash.callback(
    Output("dl-vtk-table", "selected_rows"),
    Input("btn-select-all-tab-vtk", "n_clicks"),
    Input("btn-deselect-all-tab-vtk", "n_clicks"),
    State("dl-vtk-table", "data"),
    prevent_initial_call=True,
)
def vtk_select_deselect(all_click, none_click, table_data):
    ctx = dash.callback_context
    if not ctx.triggered or not table_data:
        raise PreventUpdate
    trig = ctx.triggered_id
    if trig == "btn-select-all-tab-vtk":
        return list(range(len(table_data)))
    return []

# ───────────────────── ⑤ 파일 다운로드 콜백 (inp/frd/vtk 공통) ────────────────────
@dash.callback(
    Output("dl-inp-download", "data"),
    Input("btn-dl-inp", "n_clicks"),
    State("dl-inp-table", "selected_rows"),
    State("dl-inp-table", "data"),
    State("dl-tbl-concrete", "selected_rows"),
    State("dl-tbl-concrete", "data"),
    prevent_initial_call=True,
)
def dl_download_inp(n_clicks, sel_rows, table_data, sel_conc_rows, conc_data):
    return _download_generic(n_clicks, sel_rows, table_data, sel_conc_rows, conc_data, "inp")

@dash.callback(
    Output("dl-frd-download", "data"),
    Input("btn-dl-frd", "n_clicks"),
    State("dl-frd-table", "selected_rows"),
    State("dl-frd-table", "data"),
    State("dl-tbl-concrete", "selected_rows"),
    State("dl-tbl-concrete", "data"),
    prevent_initial_call=True,
)
def dl_download_frd(n_clicks, sel_rows, table_data, sel_conc_rows, conc_data):
    return _download_generic(n_clicks, sel_rows, table_data, sel_conc_rows, conc_data, "frd")

@dash.callback(
    Output("dl-vtk-download", "data"),
    Input("btn-dl-vtk", "n_clicks"),
    State("dl-vtk-table", "selected_rows"),
    State("dl-vtk-table", "data"),
    State("dl-tbl-concrete", "selected_rows"),
    State("dl-tbl-concrete", "data"),
    prevent_initial_call=True,
)
def dl_download_vtk(n_clicks, sel_rows, table_data, sel_conc_rows, conc_data):
    return _download_generic(n_clicks, sel_rows, table_data, sel_conc_rows, conc_data, "vtk")

# ───────────────────── 공통 다운로드 로직 ────────────────────
def _download_generic(n_clicks, sel_rows, table_data, sel_conc_rows, conc_data, ftype):
    if not n_clicks or not sel_rows or not sel_conc_rows:
        raise PreventUpdate
    concrete_pk = conc_data[sel_conc_rows[0]]["concrete_pk"]
    if ftype == "inp":
        folder = f"inp/{concrete_pk}"
    elif ftype == "frd":
        folder = f"frd/{concrete_pk}"
    else:
        folder = f"assets/vtk/{concrete_pk}"
    files = [table_data[i]["filename"] for i in sel_rows]
    if not files:
        raise PreventUpdate
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for fname in files:
            path = os.path.join(folder, fname)
            if os.path.exists(path):
                zf.write(path, arcname=fname)
    buf.seek(0)
    return dcc.send_bytes(buf.getvalue(), filename=f"{ftype}_files_{concrete_pk}.zip") 