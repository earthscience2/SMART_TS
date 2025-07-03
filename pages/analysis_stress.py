# pages/project.py
# Dash 페이지: 수치해석 탭만 남긴 버전

from __future__ import annotations
import os
import glob
import pandas as pd
import dash
from dash import html, dcc, Input, Output, State, register_page, callback
import dash_bootstrap_components as dbc
import dash_vtk
import api_db

register_page(__name__, path="/project", title="수치해석 관리")

# ────────────────────────────── 레이아웃 ────────────────────────────
layout = dbc.Container(
    fluid=True,
    className="px-4 py-3",
    style={"backgroundColor": "#f7f9fc", "minHeight": "100vh"},
    children=[
        dcc.Location(id="project-url", refresh=False),
        # 프로젝트 및 콘크리트 선택 영역
        dbc.Row([
            dbc.Col([  # 콘크리트 목록
                html.H5("🏗️ 콘크리트 목록", className="mb-3"),
                dash.dash_table.DataTable(
                    id="tbl-concrete",
                    page_size=10,
                    row_selectable="single",
                    columns=[{"name": "이름", "id": "name"}, {"name": "상태", "id": "status"}],
                    style_table={"height": "400px", "overflowY": "auto"}
                )
            ], width=3),
            dbc.Col([  # 수치해석 탭 콘텐츠
                html.H6("🔬 수치해석", className="mb-3"),
                # 시간 설정 슬라이더
                html.Div([
                    html.Label("⏰ 시간 설정", className="d-block mb-2"),
                    dcc.Slider(id="analysis-time-slider", min=0, max=0, value=0, marks={}, tooltip={"always_visible": True})
                ], className="mb-4 p-3 bg-light border rounded"),
                # 분석 설정
                html.Div([
                    html.Label("컬러맵 필드", className="d-block mb-1"),
                    dcc.Dropdown(id="analysis-field-dropdown", options=[
                        {"label": "변위 X", "value": "U:0"},
                        {"label": "변위 Y", "value": "U:1"},
                        {"label": "변위 Z", "value": "U:2"},
                    ], value="U:0"),
                    html.Label("컬러맵 프리셋", className="d-block mt-3 mb-1"),
                    dcc.Dropdown(id="analysis-preset-dropdown", options=[
                        {"label": "무지개", "value": "rainbow"},
                        {"label": "블루-레드", "value": "Cool to Warm"},
                        {"label": "회색", "value": "Grayscale"},
                    ], value="rainbow"),
                    dbc.Checklist(
                        options=[{"label": "단면 보기 활성화", "value": "on"}],
                        value=[], id="slice-enable", switch=True, className="mt-3"
                    ),
                    html.Div(id="slice-detail-controls", style={"display": "none"}, children=[
                        html.Label("축 선택", className="d-block mb-1"),
                        dcc.Dropdown(id="slice-axis", options=[
                            {"label": "X축", "value": "X"},
                            {"label": "Y축", "value": "Y"},
                            {"label": "Z축", "value": "Z"},
                        ], value="Z"),
                        html.Label("절단 위치", className="d-block mt-3 mb-1"),
                        dcc.Slider(id="slice-slider", min=0, max=1, step=0.05, value=0.5)
                    ])
                ], className="p-3 bg-light border rounded mb-4"),
                # 파일 정보 표시
                html.Div(id="analysis-current-file-label", className="mb-3 p-2 bg-white border rounded"),
                # 3D 뷰어
                html.Div(id="analysis-3d-viewer", style={"height": "60vh"})
            ], width=9)
        ], className="g-4")
    ]
)

# ───────────────────── 수치해석 콜백 ─────────────────────
@callback(
    Output("analysis-3d-viewer", "children", allow_duplicate=True),
    Output("analysis-current-file-label", "children", allow_duplicate=True),
    Output("analysis-time-slider", "min"),
    Output("analysis-time-slider", "max"),
    Input("analysis-field-dropdown", "value"),
    Input("analysis-preset-dropdown", "value"),
    Input("analysis-time-slider", "value"),
    Input("slice-enable", "value"),
    Input("slice-axis", "value"),
    Input("slice-slider", "value"),
    State("tbl-concrete", "selected_rows"),
    State("tbl-concrete", "data"),
    prevent_initial_call=False
)
def update_analysis_3d_view(field_name, preset, time_idx, slice_enable, slice_axis, slice_slider, selected_rows, tbl_data):
    import os
    from datetime import datetime
    import vtk
    from dash_vtk.utils import to_mesh_state
    import dash_vtk
    import html as dh

    # 콘크리트 선택 확인
    if not selected_rows or not tbl_data:
        return dh.Html("콘크리트를 선택하세요."), "", 0, 1

    pkg = pd.DataFrame(tbl_data).iloc[selected_rows[0]]
    pk = pkg["concrete_pk"]
    vtk_dir = f"assets/vtk/{pk}"
    if not os.path.exists(vtk_dir):
        return dh.Html("VTK 파일이 없습니다."), "", 0, 1

    files = sorted([f for f in os.listdir(vtk_dir) if f.endswith('.vtk')])
    times = []
    for f in files:
        try:
            dt = datetime.strptime(os.path.splitext(f)[0], "%Y%m%d%H")
            times.append((dt, f))
        except:
            continue
    if not times:
        return dh.Html("시간 정보가 포함된 VTK 파일이 없습니다."), "", 0, 1
    times.sort()
    max_idx = len(times) - 1
    idx = min(int(time_idx) if time_idx is not None else max_idx, max_idx)
    sel_file = times[idx][1]
    path = os.path.join(vtk_dir, sel_file)

    # VTK 읽기
    reader = vtk.vtkUnstructuredGridReader() if path.endswith('.vtk') else vtk.vtkXMLPolyDataReader()
    reader.SetFileName(path)
    reader.Update()
    ds = reader.GetOutput()

    # 단면 처리 (생략: 내부 클리핑 로직 유지)
    ds_vis = ds  # 단순화

    # 필드 컴포넌트 처리
    base, comp = (field_name.split(":") + [None])[:2]
    arr = ds_vis.GetPointData().GetArray(base)
    if comp is not None and arr and arr.GetNumberOfComponents() > int(comp):
        # 컴포넌트 추출
        import vtk.util.numpy_support as nps
        import numpy as np
        vec = nps.vtk_to_numpy(arr)
        comp_data = vec[:, int(comp)]
        carr = vtk.vtkFloatArray(); carr.SetName(f"{base}_{comp}"); carr.SetNumberOfValues(len(comp_data))
        for i,v in enumerate(comp_data): carr.SetValue(i, v)
        ds_vis.GetPointData().AddArray(carr)
        field_name = carr.GetName()

    mesh_state = to_mesh_state(ds_vis, field_name)
    mesh = dash_vtk.Mesh(state=mesh_state)
    geo = dash_vtk.GeometryRepresentation(children=[mesh], colorMapPreset=preset)
    view = dash_vtk.View(children=[geo], style={"height": "60vh"})

    # 파일명 표시
    dt = times[idx][0].strftime("%Y년 %m월 %d일 %H시")
    label = f"📅 {dt}"
    if "on" in slice_enable:
        label += f" | {slice_axis}≥{slice_slider}"

    return view, label, 0, max_idx
