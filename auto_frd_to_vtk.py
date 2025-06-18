import re
import os

def parse_frd(filename):
    nodes = {}
    elements = []
    displacements = {}
    stresses = {}

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
                except:
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
                    except:
                        continue

    # 스트레스 파싱
    stress_section = False
    for line in lines:
        l = line.strip()
        if l.startswith('-4') and 'STRESS' in l:
            stress_section = True
            continue
        if stress_section:
            if l.startswith('-5') or l.startswith('-3') or l.startswith('1PSTEP') or l.startswith('100CL'):
                stress_section = False
                continue
            if l.startswith('-1'):
                parts = l.split()
                if len(parts) >= 3:
                    try:
                        elem_id = int(parts[1])
                        stress_value = float(parts[2])  # 첫 번째 값 사용 (예: Von Mises)
                        stresses[elem_id] = stress_value
                    except:
                        continue

    return nodes, elements, displacements, stresses

def write_vtk(nodes, elements, outname, displacements=None, stresses=None):
    with open(outname, 'w') as f:
        f.write('# vtk DataFile Version 3.0\n')
        f.write('Converted from FRD\n')
        f.write('ASCII\n')
        f.write('DATASET UNSTRUCTURED_GRID\n')
        f.write(f'POINTS {len(nodes)} float\n')
        for node_id in sorted(nodes):
            f.write(f"{nodes[node_id][0]} {nodes[node_id][1]} {nodes[node_id][2]}\n")
        total_indices = sum([len(e) for e in elements])
        f.write(f'CELLS {len(elements)} {len(elements) + len(elements)}\n')
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

        # 변위 출력
        if displacements and len(displacements) > 0:
            f.write(f'\nPOINT_DATA {len(nodes)}\n')
            f.write('VECTORS displacement float\n')
            for node_id in sorted(nodes):
                dx, dy, dz = displacements.get(node_id, (0.0, 0.0, 0.0))
                f.write(f"{dx} {dy} {dz}\n")

        # 스트레스 출력
        if stresses and len(stresses) > 0:
            f.write(f'\nCELL_DATA {len(elements)}\n')
            f.write('SCALARS stress float 1\n')
            f.write('LOOKUP_TABLE default\n')
            for i in range(len(elements)):
                elem_id = i + 1
                s = stresses.get(elem_id, 0.0)
                f.write(f"{s}\n")

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
                nodes, elements, displacements, stresses = parse_frd(frd_path)
                write_vtk(nodes, elements, vtk_path, displacements, stresses)

if __name__ == "__main__":
    convert_all_frd_to_vtk('frd', 'vtk')

