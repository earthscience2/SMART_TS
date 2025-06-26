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
                # 프로젝트 선택 카드
                html.Div([
                    html.Div([
                        html.H6("🏗️ 프로젝트 선택", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                        dcc.Dropdown(
                            id="dl-ddl-project", 
                            clearable=False, 
                            placeholder="프로젝트를 선택하세요",
                            style={"fontSize": "0.85rem"},
                            className="mb-2"
                        ),
                    ], className="p-3")
                ], className="bg-white rounded shadow-sm border mb-3"),

                # 콘크리트 목록 카드
                html.Div([
                    html.Div([
                        html.H6("🧱 콘크리트 목록", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                        html.Small("💡 콘크리트를 클릭하여 선택할 수 있습니다", className="text-muted mb-2 d-block", style={"fontSize": "0.75rem"}),
                        dash_table.DataTable(
                            id="dl-tbl-concrete", 
                            page_size=10, 
                            row_selectable="single",
                            style_table={"overflowY": "auto", "height": "45vh"},
                            style_cell={
                                "whiteSpace": "nowrap", 
                                "textAlign": "center",
                                "fontSize": "0.8rem",
                                "padding": "12px 10px",
                                "border": "none",
                                "borderBottom": "1px solid #f1f1f0",
                                "fontFamily": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
                            },
                            style_header={
                                "backgroundColor": "#fafafa", 
                                "fontWeight": 600,
                                "color": "#37352f",
                                "border": "none",
                                "borderBottom": "1px solid #e9e9e7",
                                "fontSize": "0.75rem",
                                "textTransform": "uppercase",
                                "letterSpacing": "0.5px"
                            },
                            style_data={
                                "backgroundColor": "white",
                                "border": "none",
                                "color": "#37352f"
                            },
                            style_data_conditional=[
                                {
                                    'if': {'row_index': 'odd'},
                                    'backgroundColor': '#fbfbfa'
                                },
                                {
                                    'if': {'state': 'selected'},
                                    'backgroundColor': '#e8f4fd',
                                    'border': '1px solid #579ddb',
                                    'borderRadius': '6px',
                                    'boxShadow': '0 0 0 1px rgba(87, 157, 219, 0.3)',
                                    'color': '#1d4ed8'
                                }
                            ],
                            css=[
                                {
                                    'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner table',
                                    'rule': 'border-collapse: separate; border-spacing: 0;'
                                },
                                {
                                    'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner tr:hover',
                                    'rule': 'background-color: #f8fafc !important; transition: background-color 0.15s ease;'
                                }
                            ]
                        ),
                    ], className="p-3")
                ], className="bg-white rounded shadow-sm border")
            ], md=3),
            dbc.Col([
                # 파일 다운로드 카드
                html.Div([
                    html.Div([
                        html.H6("📁 파일 다운로드", id="dl-concrete-title", className="mb-2 text-secondary fw-bold", style={"fontSize": "0.9rem"}),
                        html.Small("💡 탭을 선택하여 파일 유형을 변경할 수 있습니다", className="text-muted mb-3 d-block", style={"fontSize": "0.75rem"}),
                        dbc.Tabs([
                            dbc.Tab(label="INP 파일", tab_id="tab-inp", 
                                   style={"fontSize": "0.85rem", "padding": "8px 16px"},
                                   active_label_style={"backgroundColor": "#e8f4fd", "color": "#1d4ed8", "fontWeight": "600"}),
                            dbc.Tab(label="FRD 파일", tab_id="tab-frd",
                                   style={"fontSize": "0.85rem", "padding": "8px 16px"},
                                   active_label_style={"backgroundColor": "#e8f4fd", "color": "#1d4ed8", "fontWeight": "600"}),
                            dbc.Tab(label="VTK 파일", tab_id="tab-vtk",
                                   style={"fontSize": "0.85rem", "padding": "8px 16px"},
                                   active_label_style={"backgroundColor": "#e8f4fd", "color": "#1d4ed8", "fontWeight": "600"}),
                        ], id="dl-tabs", active_tab="tab-inp", className="mb-3"),
                        html.Div(id="dl-tab-content"),
                    ], className="p-3")
                ], className="bg-white rounded shadow-sm border"),
            ], md=9),
        ], className="g-3"),
    ],
    className="py-3"
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
        return [], [], [], "📁 파일 다운로드"
    df_conc = api_db.get_concrete_data(project_pk=project_pk)
    data = df_conc[["concrete_pk", "name"]].to_dict("records")
    columns = [{"name": "이름", "id": "name"}]
    return data, columns, [], "📁 파일 다운로드"

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
        return html.Div([
            html.Div([
                html.I(className="fas fa-info-circle me-2", style={"color": "#6b7280", "fontSize": "1.2rem"}),
                html.Span("콘크리트를 선택하면 파일 목록이 표시됩니다", style={"color": "#6b7280", "fontSize": "0.9rem"})
            ], className="d-flex align-items-center justify-content-center p-4", style={"backgroundColor": "#f9fafb", "borderRadius": "8px", "border": "1px dashed #d1d5db"})
        ])
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
        style_cell={
            "textAlign": "center",
            "fontSize": "0.8rem",
            "padding": "12px 10px",
            "border": "none",
            "borderBottom": "1px solid #f1f1f0",
            "fontFamily": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        },
        style_header={
            "backgroundColor": "#fafafa", 
            "fontWeight": 600,
            "color": "#37352f",
            "border": "none",
            "borderBottom": "1px solid #e9e9e7",
            "fontSize": "0.75rem",
            "textTransform": "uppercase",
            "letterSpacing": "0.5px"
        },
        style_data={
            "backgroundColor": "white",
            "border": "none",
            "color": "#37352f"
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': '#fbfbfa'
            },
            {
                'if': {'state': 'selected'},
                'backgroundColor': '#e8f4fd',
                'border': '1px solid #579ddb',
                'borderRadius': '6px',
                'boxShadow': '0 0 0 1px rgba(87, 157, 219, 0.3)',
                'color': '#1d4ed8'
            }
        ],
        css=[
            {
                'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner table',
                'rule': 'border-collapse: separate; border-spacing: 0;'
            },
            {
                'selector': '.dash-table-container .dash-spreadsheet-container .dash-spreadsheet-inner tr:hover',
                'rule': 'background-color: #f8fafc !important; transition: background-color 0.15s ease;'
            }
        ],
        style_table={"width": "100%", "margin": "auto", "marginBottom": "20px"},
    )
    return html.Div([
        html.Small(f"💾 {len(files)}개의 파일이 있습니다", className="text-muted mb-2 d-block", style={"fontSize": "0.75rem"}),
        table,
        html.Div([
            dbc.Button("전체 선택", id=f"btn-select-all-{active_tab}", color="outline-secondary", size="sm", className="me-2", n_clicks=0),
            dbc.Button("전체 해제", id=f"btn-deselect-all-{active_tab}", color="outline-light", size="sm", className="me-2", n_clicks=0),
            dbc.Button("선택 파일 다운로드", id=dl_btn_id, color="primary", size="sm", className="ms-2", n_clicks=0),
            dcc.Download(id=dl_component_id)
        ], className="d-flex justify-content-center")
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