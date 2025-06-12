# -*- coding: utf-8 -*-
"""
콘크리트-ID 를 입력하면
1. API(api_concrete.load_all())에서 dims 정보를 읽어 폴리곤과 높이를 얻음
2. Sensors CSV 를 읽어 시간(시 단위)별로 평균 병합 → 공통 시간대만 선별
3. dims 폴리곤을 0.01m 간격으로 2D 격자 생성, (x,y)에 대해 위/아래(z=0, z=h) 두 레이어로 hexahedron 메쉬 생성
4. 각 노드에 대해 KDTree를 사용해 최근접 센서 온도 부여 → VTK UnstructuredGrid 생성
5. assets/numerical_analysis/<concrete_id>_YYYYmmdd_HH.vtu 로 저장 (비압축 이진)
6. PyVista로 VTU 불러와 HTML(WebGL)로 내보내기 → assets/previews/<concrete_id>_YYYYmmdd_HH.html

※ 실행 전: pip install "pyvista[jupyter]" 또는 "pyvista[all]" 반드시 필요
"""
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
import ast

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import vtk
import pyvista as pv  # PyVista: WebGL용 HTML 렌더링

import api_concrete   # 내부 API: concrete_id/name/dims/created
import api_sensor     # 내부 API: sensor_id/concrete_id/dims(위치 포함)...

# ─────────────────────────────────────────────────────────────────────────────
def load_sensor_hourly(sensor_id: str) -> pd.Series:
    """CSV → 시(시 단위)별 평균 온도 시계열 반환"""
    csv_path = Path("sensors") / f"{sensor_id}.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"센서 CSV가 없습니다: {csv_path}")
    df = pd.read_csv(csv_path, parse_dates=["time"])
    df["hour"] = df["time"].dt.floor("h")
    hourly = df.groupby("hour")["temperature"].mean().sort_index()
    return hourly

# ─────────────────────────────────────────────────────────────────────────────
def generate_vtu_and_html(
    concrete_id: str,
    vtu_dir: Path = Path("assets/numerical_analysis"),
    html_dir: Path = Path("assets/previews"),
) -> None:
    """
    1) api_concrete.load_all()에서 dims(JSON) 읽기 → 폴리곤 노드 목록 + 높이 h 추출
    2) 2D 폴리곤 영역을 0.01m 간격 격자화 → z=0 (바닥) & z=h (천장) 겹쳐 hexahedron 메쉬 구축
    3) api_sensor.load_all_sensors()에서 센서 메타 + CSV → 시간별 평균 온도 시리즈
    4) 공통 시간대(intersection)만 선별 → KDTree로 노드마다 최근접 센서 온도 할당
    5) VTK UnstructuredGrid 생성 → .vtu (비압축 이진) 저장
    6) PyVista로 .vtu 읽어와 export_html() → .html(WebGL) 저장
    """
    vtu_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 1) concrete metadata에서 dims 읽기
    df_conc = api_concrete.load_all()  # 반드시 dims 컬럼이 JSON 문자열이어야 함
    if "dims" not in df_conc.columns:
        raise RuntimeError("api_concrete.load_all() 결과에 'dims' 컬럼이 없습니다.")

    # concrete_id 행 찾기
    match = df_conc.query("concrete_id == @concrete_id")
    if match.shape[0] == 0:
        raise ValueError(f"콘크리트 '{concrete_id}' 메타를 찾을 수 없습니다.")
    row = match.iloc[0]
    dims = ast.literal_eval(row["dims"])
    # dims 예: {"nodes": [[1,1], [2,1], [2,2], [1,2]], "h": 0.5}
    poly_2d: list[list[float]] = dims["nodes"]  # 2D 폴리곤 꼭짓점 [[x0,y0],[x1,y1],...]
    h: float = float(dims.get("h", 0.0))

    # 2D 폴리곤 바운딩 박스 계산
    poly_arr = np.array(poly_2d, dtype=float)
    min_x, max_x = poly_arr[:, 0].min(), poly_arr[:, 0].max()
    min_y, max_y = poly_arr[:, 1].min(), poly_arr[:, 1].max()

    # 2) 0.01m 간격 격자 생성 (2D)
    xi = np.arange(min_x, max_x + 1e-8, 0.01, dtype=float)
    yi = np.arange(min_y, max_y + 1e-8, 0.01, dtype=float)
    X2d, Y2d = np.meshgrid(xi, yi)  # shape: (len(yi), len(xi))

    # Ray-casting 함수: (px,py)가 2D 폴리곤 내부인지 검사
    def point_in_poly(px: float, py: float, poly: list[list[float]]) -> bool:
        inside = False
        n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if ((y0 <= py < y1) or (y1 <= py < y0)):
                xinters = (py - y0) * (x1 - x0) / (y1 - y0 + 1e-12) + x0
                if xinters > px:
                    inside = not inside
        return inside

    mask_2d = np.zeros_like(X2d, dtype=bool)
    for i in range(X2d.shape[0]):
        for j in range(X2d.shape[1]):
            if point_in_poly(X2d[i, j], Y2d[i, j], poly_2d):
                mask_2d[i, j] = True

    # (floor_layer + ceiling_layer) 두 수준으로 노드 생성
    coords_list: list[list[float]] = []
    for layer_z in (0.0, h):
        for i in range(X2d.shape[0]):
            for j in range(X2d.shape[1]):
                if mask_2d[i, j]:
                    coords_list.append([X2d[i, j], Y2d[i, j], layer_z])
    points_np = np.array(coords_list, dtype=float)  # (N_nodes, 3)

    # node_id 대신 인덱스 번호(0~)만 쓰므로, node_id_to_index는 단순하게 0~(N_nodes-1)
    node_id_to_index = { idx: idx for idx in range(points_np.shape[0]) }

    # 2) 요소(Element) 구성 (각 2×2 사각형마다 hexahedron)
    #    → indexing을 편하게 하기 위해 2D 격자를 점별로 순서대로 저장했다고 가정
    #    → 사실상 2D 마스크에 True인 좌표들이 라인 단위로 저장되어 있으므로, 
    #       정확한 hexahedron 인덱싱을 위해서는 (i,j)→flattened_idx 매핑이 필요.
    #    여기서는 이해를 돕기 위해 간단한 “주변 4점 + 위/아래 4점” 순으로 hexahedron을 생성합니다.

    # “mask 좌표”를 (i,j) 인덱스로 저장해 두고, 나중에 위/아래 인덱스를 구함
    index_map = -np.ones_like(X2d, dtype=int)
    cnt = 0
    for i in range(X2d.shape[0]):
        for j in range(X2d.shape[1]):
            if mask_2d[i, j]:
                index_map[i, j] = cnt
                cnt += 1
    # 위층(ceil) 인덱스 = 바닥(True인 개수) + index_map[i,j]
    n2 = mask_2d.sum()  # floor 노드 개수
    # 총 노드 개수 = floor 개수 + ceil 개수 = 2 * n2

    elements: list[list[int]] = []
    # hexahedron 순서는 (바닥 4개) + (천장 4개)
    # 바닥 사각형 → (i,j), (i,j+1), (i+1,j+1), (i+1,j) 순으로, 
    # 천장도 동일한 순서이되 +n2 오프셋
    for i in range(X2d.shape[0] - 1):
        for j in range(X2d.shape[1] - 1):
            if mask_2d[i, j] and mask_2d[i, j + 1] and mask_2d[i + 1, j + 1] and mask_2d[i + 1, j]:
                b0 = index_map[i, j]
                b1 = index_map[i, j + 1]
                b2 = index_map[i + 1, j + 1]
                b3 = index_map[i + 1, j]
                c0 = b0 + n2
                c1 = b1 + n2
                c2 = b2 + n2
                c3 = b3 + n2
                # hexahedron 노드 순서 (VTK 기준)
                elements.append([b0, b1, b2, b3, c0, c1, c2, c3])
    elements_np = np.array(elements, dtype=int)

    # ─────────────────────────────────────────────────────────────────────────
    # 3) 센서 메타 & 시간대별 온도 시리즈 로드
    df_sensors = api_sensor.load_all_sensors()
    df_sensors = df_sensors[df_sensors["concrete_id"] == concrete_id].copy()
    if df_sensors.empty:
        raise ValueError(f"콘크리트 '{concrete_id}'에 연결된 센서가 없습니다.")

    sensor_positions: dict[str, np.ndarray] = {}
    sensor_hour_series: dict[str, pd.Series] = {}
    for _, row in df_sensors.iterrows():
        sid = row["sensor_id"]
        try:
            pos = ast.literal_eval(row["dims"])  # {'nodes':[x,y,z]}
            sensor_positions[sid] = np.array(pos["nodes"], dtype=float)
        except Exception:
            sensor_positions[sid] = np.array([0.0, 0.0, 0.0], dtype=float)
        sensor_hour_series[sid] = load_sensor_hourly(sid)

    # ─────────────────────────────────────────────────────────────────────────
    # 4) 공통 시간대 계산
    common_hours = set.intersection(*[set(s.index) for s in sensor_hour_series.values()])
    common_hours = sorted(common_hours)
    if not common_hours:
        raise ValueError("공통으로 포함된 시간대가 없습니다. VTU 파일 생성 불가.")

    print(f"▶ 공통 시간대({len(common_hours)}개): {common_hours[0]} ~ {common_hours[-1]}")

    # ─────────────────────────────────────────────────────────────────────────
    # 5) KDTree for 최근접 센서 보간
    sensor_coords = np.vstack(list(sensor_positions.values()))  # (N_sensors,3)
    sensor_ids = list(sensor_positions.keys())
    kdt = cKDTree(sensor_coords)

    # ─────────────────────────────────────────────────────────────────────────
    # 6) 시간대별 VTU & HTML 생성
    for hr in common_hours:
        # 6-1) 센서 온도 배열
        temps_this_hour = np.array([sensor_hour_series[sid].loc[hr] for sid in sensor_ids])

        # 6-2) KDTree query → 모든 격자 노드에 대해 가장 가까운 센서 온도
        _, idx = kdt.query(points_np)
        node_temps = temps_this_hour[idx]  # (N_nodes,)

        # 6-3) VTK Points 객체
        vtk_points = vtk.vtkPoints()
        for pt in points_np:
            vtk_points.InsertNextPoint(pt.tolist())

        # 6-4) VTK Cells(hexahedron) 구성
        vtk_cells = vtk.vtkCellArray()
        for elm in elements_np:
            hex_elem = vtk.vtkHexahedron()
            for i_node, nid in enumerate(elm):
                hex_elem.GetPointIds().SetId(i_node, nid)
            vtk_cells.InsertNextCell(hex_elem)

        # 6-5) UnstructuredGrid 생성
        ugrid = vtk.vtkUnstructuredGrid()
        ugrid.SetPoints(vtk_points)
        ugrid.SetCells(vtk.VTK_HEXAHEDRON, vtk_cells)

        # 6-6) Temperature 스칼라 배열 추가
        vtk_t = vtk.vtkFloatArray()
        vtk_t.SetName("Temperature")
        for tval in node_temps:
            vtk_t.InsertNextValue(float(tval))
        ugrid.GetPointData().SetScalars(vtk_t)

        # 6-7) VTU 파일명
        ts_str = pd.Timestamp(hr).strftime("%Y%m%d_%H")
        vtu_filename = f"{concrete_id}_{ts_str}.vtu"
        vtu_path = vtu_dir / vtu_filename

        writer = vtk.vtkXMLUnstructuredGridWriter()
        writer.SetFileName(str(vtu_path))
        writer.SetInputData(ugrid)
        writer.SetDataModeToBinary()  # 비압축 이진(Binary)
        writer.Write()
        print(f"📝 VTU 저장 → {vtu_filename}")

        # 6-8) PyVista로 VTU 읽어와 HTML(WebGL) 내보내기
        try:
            mesh = pv.read(str(vtu_path))
            pl = pv.Plotter(off_screen=True)
            pl.add_mesh(mesh, scalars="Temperature", cmap="viridis", show_scalar_bar=True)
            pl.set_background("white")
            pl.camera_position = "iso"
            html_filename = f"{concrete_id}_{ts_str}.html"
            html_path = html_dir / html_filename
            pl.export_html(str(html_path))
            print(f"📝 HTML 저장 → {html_filename}")
        except Exception as e:
            print(f"❗ PyVista HTML 내보내기 실패 ({ts_str}): {e}")

    print(f"✅ 완료: 총 {len(common_hours)}개 VTU 및 HTML 파일을 생성했습니다.")
    print(f"   VTU 디렉터리: {vtu_dir}")
    print(f"   HTML 디렉터리: {html_dir}")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cid = input("▶ 콘크리트 ID를 입력하세요: ").strip()
    if not cid:
        print("❗ 콘크리트 ID가 입력되지 않았습니다. 종료합니다.")
    else:
        try:
            generate_vtu_and_html(concrete_id=cid)
        except Exception as err:
            print(f"❗ 오류 발생: {err}")
