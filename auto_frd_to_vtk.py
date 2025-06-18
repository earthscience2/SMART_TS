import re
import os
import shutil
import numpy as np

def parse_frd(filename):
    nodes = {}
    elements = []
    displacements = {}
    stresses = {}

    with open(filename, 'r') as f:
        lines = f.readlines()

    # 노드 파싱
    nodes = {}
    node_order = []
    for line in lines:
        l = line.strip()
        if l.startswith('-1'):
            parts = l.split()
            if len(parts) == 5:
                try:
                    node_id = int(parts[1])
                    x, y, z = map(float, parts[2:5])
                    nodes[node_id] = (x, y, z)
                    node_order.append(node_id)
                except:
                    continue

    # 요소 파싱
    elements = []
    element_ids = []
    elem_section = False
    for i, line in enumerate(lines):
        l = line.strip()
        if l.startswith('3C'):
            elem_section = True
            continue
        if elem_section:
            if l.startswith('-1'):
                try:
                    elem_id = int(l.split()[1])
                    element_ids.append(elem_id)
                except:
                    continue
                continue
            elif l.startswith('-2'):
                parts = l.split()
                if len(parts) == 9:
                    try:
                        node_ids = [int(n) for n in parts[1:]]
                        elements.append(node_ids)
                    except:
                        continue
            elif l.startswith('-3'):
                break

    # 변위 파싱
    displacements = {}
    disp_section = False
    for line in lines:
        l = line.strip()
        if l.startswith('-4') and 'DISP' in l:
            disp_section = True
            continue
        if disp_section:
            if l.startswith('-4') or l.startswith('1PSTEP') or l.startswith('100CL'):
                disp_section = False
                continue
            if l.startswith('-1'):
                parts = l.split()
                if len(parts) == 5:
                    try:
                        node_id = int(parts[1])
                        dx, dy, dz = map(float, parts[2:5])
                        displacements[node_id] = (dx, dy, dz)
                    except:
                        continue
    # 모든 노드에 대해 값이 없으면 0으로 채움
    for nid in nodes:
        if nid not in displacements:
            displacements[nid] = (0.0, 0.0, 0.0)

    # 스트레스 파싱
    stresses = {}
    stress_section = False
    for line in lines:
        l = line.strip()
        if l.startswith('-4') and 'STRESS' in l:
            stress_section = True
            continue
        if stress_section:
            if l.startswith('-4') or l.startswith('1PSTEP') or l.startswith('100CL'):
                stress_section = False
                continue
            if l.startswith('-1'):
                parts = l.split()
                if len(parts) == 8:
                    try:
                        elem_id = int(parts[1])
                        sxx = float(parts[2])
                        stresses[elem_id] = sxx
                    except:
                        continue

    print(f"노드 개수: {len(nodes)}")
    print(f"변위 개수: {len(displacements)}")
    print(f"응력 개수: {len(stresses)}")
    # 응력 데이터의 key와 노드/요소ID 비교용 출력
    print("frd 응력 데이터 key(앞 10개):", list(stresses.keys())[:10])
    print("frd 응력 데이터 예시(앞 3개):", [stresses[k] for k in list(stresses.keys())[:3]])
    print("frd 노드ID(앞 10개):", list(nodes.keys())[:10])
    print("frd 요소ID(앞 10개):", element_ids[:10])

    return nodes, elements, displacements, stresses

def write_vtk(nodes, elements, outname, displacements=None, stresses=None, node_order=None, element_ids=None):
    with open(outname, 'w') as f:
        f.write('# vtk DataFile Version 3.0\n')
        f.write('Converted from FRD\n')
        f.write('ASCII\n')
        f.write('DATASET UNSTRUCTURED_GRID\n')
        # 노드 순서대로 기록
        f.write(f'POINTS {len(nodes)} float\n')
        for node_id in node_order:
            x, y, z = nodes[node_id]
            f.write(f"{x} {y} {z}\n")
        total_indices = sum([len(e) for e in elements])
        f.write(f'CELLS {len(elements)} {len(elements) + total_indices}\n')
        for elem in elements:
            f.write(f"{len(elem)} {' '.join(str(n-1) for n in elem)}\n")
        f.write(f'CELL_TYPES {len(elements)}\n')
        for elem in elements:
            if len(elem) == 8:
                f.write('12\n')  # HEXAHEDRON
            elif len(elem) == 4:
                f.write('10\n')  # TETRA
            else:
                f.write('7\n')   # Default: POLYGON

        # POINT_DATA (변위)
        if displacements and len(displacements) > 0:
            f.write(f'\nPOINT_DATA {len(nodes)}\n')
            f.write('VECTORS displacement float\n')
            for node_id in node_order:
                dx, dy, dz = displacements.get(node_id, (0.0, 0.0, 0.0))
                f.write(f"{dx} {dy} {dz}\n")

        # POINT_DATA (응력, 노드별)
        if stresses and len(stresses) > 0 and node_order is not None:
            f.write(f'\nSCALARS stress float 1\n')
            f.write('LOOKUP_TABLE default\n')
            for node_id in node_order:
                s = stresses.get(node_id, 0.0)
                f.write(f"{s}\n")

def compare_frd_vtk(frd_path, vtk_path):
    """
    frd와 vtk 파일의 노드/요소/데이터 정보를 비교하여 변환이 잘 되었는지 확인하는 함수
    더 자세하게: 좌표 오차, 요소 구성, 변위/응력 데이터까지 비교
    """
    nodes, elements, displacements, stresses = parse_frd(frd_path)
    node_order = sorted(nodes.keys())

    with open(vtk_path, 'r') as f:
        lines = f.readlines()

    # POINTS 파싱
    points_idx = [i for i, l in enumerate(lines) if l.startswith('POINTS')][0]
    n_points = int(lines[points_idx].split()[1])
    vtk_points = []
    for i in range(points_idx+1, points_idx+1+n_points):
        vtk_points.append(tuple(map(float, lines[i].split())))

    # CELLS 파싱
    cells_idx = [i for i, l in enumerate(lines) if l.startswith('CELLS')][0]
    n_cells = int(lines[cells_idx].split()[1])
    vtk_cells = []
    for i in range(cells_idx+1, cells_idx+1+n_cells):
        vtk_cells.append(list(map(int, lines[i].split()[1:])))

    # CELL_TYPES 파싱
    cell_types_idx = [i for i, l in enumerate(lines) if l.startswith('CELL_TYPES')][0]
    vtk_cell_types = [int(lines[cell_types_idx+1+i].strip()) for i in range(n_cells)]

    # 변위(VECTORS displacement) 파싱
    disp_idx = None
    for i, l in enumerate(lines):
        if l.strip().startswith('VECTORS displacement float'):
            disp_idx = i
            break
    vtk_disps = []
    if disp_idx is not None:
        for i in range(disp_idx+1, disp_idx+1+n_points):
            vtk_disps.append(tuple(map(float, lines[i].split())))
    
    # 응력(SCALARS stress) 파싱
    stress_idx = None
    for i, l in enumerate(lines):
        if l.strip().startswith('SCALARS stress float 1'):
            stress_idx = i
            break
    vtk_stresses = []
    if stress_idx is not None:
        # 'LOOKUP_TABLE default' 다음부터 n_points줄
        for i in range(stress_idx+2, stress_idx+2+n_points):
            vtk_stresses.append(float(lines[i].strip()))

    print(f"노드 개수: frd={len(nodes)}, vtk={len(vtk_points)}")
    print(f"요소 개수: frd={len(elements)}, vtk={len(vtk_cells)}")
    # 노드 좌표 오차
    frd_coords = np.array([nodes[nid] for nid in node_order])
    vtk_coords = np.array(vtk_points)
    if frd_coords.shape == vtk_coords.shape:
        coord_diff = np.linalg.norm(frd_coords - vtk_coords, axis=1)
        print(f"노드 좌표 오차 (최대/평균): {coord_diff.max():.3e} / {coord_diff.mean():.3e}")
    else:
        print("노드 좌표 shape 불일치!")
    # 요소 구성 비교
    elem_match = 0
    for e1, e2 in zip(elements, vtk_cells):
        # vtk는 0-based, frd는 1-based라서 -1
        if [n-1 for n in e1] == e2:
            elem_match += 1
    print(f"요소 구성 일치: {elem_match}/{len(elements)} ({elem_match/len(elements)*100:.1f}%)")
    # 변위 비교
    if vtk_disps and len(displacements) == len(vtk_disps):
        frd_disps = np.array([displacements.get(nid, (0.0,0.0,0.0)) for nid in node_order])
        vtk_disps_np = np.array(vtk_disps)
        disp_diff = np.linalg.norm(frd_disps - vtk_disps_np, axis=1)
        print(f"변위 오차 (최대/평균): {disp_diff.max():.3e} / {disp_diff.mean():.3e}")
    else:
        print("변위 데이터 비교 불가(개수 불일치 또는 없음)")
    # 응력 비교
    if vtk_stresses and len(stresses) == len(vtk_stresses):
        frd_stress = np.array([stresses.get(nid, 0.0) for nid in node_order])
        vtk_stress = np.array(vtk_stresses)
        stress_diff = np.abs(frd_stress - vtk_stress)
        print(f"응력 오차 (최대/평균): {stress_diff.max():.3e} / {stress_diff.mean():.3e}")
    else:
        print("응력 데이터 비교 불가(개수 불일치 또는 없음)")
    # 샘플 출력
    print("frd 첫 3개 노드:", [nodes[nid] for nid in node_order[:3]])
    print("vtk 첫 3개 POINTS:", vtk_points[:3])
    print("frd 첫 3개 요소:", elements[:3])
    print("vtk 첫 3개 CELLS:", vtk_cells[:3])
    if len(nodes) == len(vtk_points) and len(elements) == len(vtk_cells):
        print("기본 구조는 일치합니다.")
    else:
        print("구조 불일치! 변환 로직 점검 필요.")

def convert_all_frd_to_vtk(frd_root_dir, vtk_root_dir):
    for pk_name in os.listdir(frd_root_dir):
        pk_path = os.path.join(frd_root_dir, pk_name)
        if not os.path.isdir(pk_path):
            continue
        vtk_pk_path = os.path.join(vtk_root_dir, pk_name)
        os.makedirs(vtk_pk_path, exist_ok=True)
        # assets/vtk/{concrete_pk} 폴더도 생성
        assets_vtk_pk_path = os.path.join('assets', 'vtk', pk_name)
        os.makedirs(assets_vtk_pk_path, exist_ok=True)
        for fname in os.listdir(pk_path):
            if fname.lower().endswith('.frd'):
                frd_path = os.path.join(pk_path, fname)
                vtk_path = os.path.join(vtk_pk_path, fname[:-4] + '.vtk')
                print(f"변환: {frd_path} -> {vtk_path}")
                nodes, elements, displacements, stresses = parse_frd(frd_path)
                # 노드/요소 순서 정보 추가
                node_order = sorted(nodes.keys())
                element_ids = list(range(1, len(elements)+1))
                write_vtk(nodes, elements, vtk_path, displacements, stresses, node_order, element_ids)
                # assets 폴더에도 복사
                assets_vtk_path = os.path.join(assets_vtk_pk_path, fname[:-4] + '.vtk')
                shutil.copyfile(vtk_path, assets_vtk_path)

if __name__ == "__main__":
    # 샘플 파일로 파싱 결과 확인 (C000001/2025061215.frd가 있다고 가정)
    sample_frd = os.path.join('frd', 'C000001', '2025061215.frd')
    sample_vtk = os.path.join('assets', 'vtk', 'C000001', '2025061215.vtk')
    if os.path.exists(sample_frd) and os.path.exists(sample_vtk):
        print("[FRD-VTK 비교 결과]")
        compare_frd_vtk(sample_frd, sample_vtk)
    else:
        print(f"샘플 파일 {sample_frd} 또는 {sample_vtk} 없음")
    # 전체 변환 실행
    convert_all_frd_to_vtk('frd', 'vtk')

