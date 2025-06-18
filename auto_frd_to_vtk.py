import re
import os

def parse_frd(filename):
    nodes = {}
    elements = []
    displacements = {}  # 노드별 변위 결과
    with open(filename, 'r') as f:
        lines = f.readlines()

    # 노드 파싱
    for line in lines:
        l = line.strip()
        if l.startswith('-1'):
            parts = l.split()
            if len(parts) == 5:
                try:
                    node_id = int(parts[1])
                    x, y, z = map(float, parts[2:5])
                    nodes[node_id] = (x, y, z)
                except Exception:
                    continue

    # 요소 파싱
    elements = []
    elem_section = False
    for i, line in enumerate(lines):
        l = line.strip()
        if l.startswith('3C'):
            elem_section = True
            continue
        if elem_section:
            if l.startswith('-1'):
                continue  # 요소 헤더는 무시
            elif l.startswith('-2'):
                parts = l.split()
                if len(parts) == 9:
                    try:
                        node_ids = [int(n) for n in parts[1:]]
                        elements.append(node_ids)
                    except Exception:
                        continue
            elif l.startswith('-3'):
                break  # 요소 섹션 끝

    # DISP 결과 파싱 (노드별 변위)
    disp_section = False
    for line in lines:
        l = line.strip()
        if l.startswith('-4') and 'DISP' in l:
            disp_section = True
            continue
        if disp_section:
            if l.startswith('-5') or l.startswith('-3') or l.startswith('1PSTEP') or l.startswith('100CL'):
                disp_section = False
                continue
            if l.startswith('-1'):
                parts = l.split()
                if len(parts) == 5:
                    try:
                        node_id = int(parts[1])
                        dx, dy, dz = map(float, parts[2:5])
                        displacements[node_id] = (dx, dy, dz)
                    except Exception:
                        continue
    return nodes, elements, displacements

def write_vtk(nodes, elements, outname, displacements=None):
    with open(outname, 'w') as f:
        f.write('# vtk DataFile Version 3.0\n')
        f.write('Converted from FRD\n')
        f.write('ASCII\n')
        f.write('DATASET UNSTRUCTURED_GRID\n')
        f.write(f'POINTS {len(nodes)} float\n')
        for node_id in sorted(nodes):
            f.write(f"{nodes[node_id][0]} {nodes[node_id][1]} {nodes[node_id][2]}\n")
        total_indices = sum([len(e) for e in elements])
        f.write(f'CELLS {len(elements)} {len(elements) + total_indices}\n')
        for elem in elements:
            f.write(f"{len(elem)} {' '.join(str(n-1) for n in elem)}\n")
        f.write(f'CELL_TYPES {len(elements)}\n')
        for elem in elements:
            if len(elem) == 8:
                f.write('12\n')
            elif len(elem) == 4:
                f.write('10\n')
            else:
                f.write('7\n')
        # 변위 결과 추가
        if displacements and len(displacements) > 0:
            f.write(f'\nPOINT_DATA {len(nodes)}\n')
            f.write('VECTORS displacement float\n')
            for node_id in sorted(nodes):
                dx, dy, dz = displacements.get(node_id, (0.0, 0.0, 0.0))
                f.write(f"{dx} {dy} {dz}\n")

def convert_all_frd_to_vtk(frd_root_dir, vtk_root_dir):
    for pk_name in os.listdir(frd_root_dir):
        pk_path = os.path.join(frd_root_dir, pk_name)
        if not os.path.isdir(pk_path):
            continue
        vtk_pk_path = os.path.join(vtk_root_dir, pk_name)
        os.makedirs(vtk_pk_path, exist_ok=True)
        for fname in os.listdir(pk_path):
            if fname.lower().endswith('.frd'):
                frd_path = os.path.join(pk_path, fname)
                vtk_path = os.path.join(vtk_pk_path, fname[:-4] + '.vtk')
                print(f"변환: {frd_path} -> {vtk_path}")
                nodes, elements, displacements = parse_frd(frd_path)
                write_vtk(nodes, elements, vtk_path, displacements)

if __name__ == "__main__":
    convert_all_frd_to_vtk('frd', 'vtk')
