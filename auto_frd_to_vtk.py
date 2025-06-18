import re
import os
import shutil

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
    if os.path.exists(sample_frd):
        nodes, elements, displacements, stresses = parse_frd(sample_frd)
        print("[샘플 변위] 앞 5개:")
        for k in list(displacements.keys())[:5]:
            print(f"노드 {k}: {displacements[k]}")
        print("[샘플 스트레스] 앞 5개:")
        for k in list(stresses.keys())[:5]:
            print(f"요소/노드 {k}: {stresses[k]}")
    else:
        print(f"샘플 파일 {sample_frd} 없음")
    # 전체 변환 실행
    convert_all_frd_to_vtk('frd', 'vtk')

