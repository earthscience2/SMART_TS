import re
import os

def parse_frd(filename):
    nodes = {}
    elements = []
    with open(filename, 'r') as f:
        lines = f.readlines()

    # 노드 파싱
    for line in lines:
        l = line.strip()
        # 노드 데이터: -1로 시작하고, 5개 값이 있는 경우만
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

    return nodes, elements

def write_vtk(nodes, elements, outname):
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
                f.write('12\n')  # Hexahedron
            elif len(elem) == 4:
                f.write('10\n')  # Tetrahedron
            else:
                f.write('7\n')   # Polygon (fallback)

def convert_all_frd_to_vtk(concrete_pk_dir, vtk_root_dir):
    for pk_name in os.listdir(concrete_pk_dir):
        pk_path = os.path.join(concrete_pk_dir, pk_name)
        if not os.path.isdir(pk_path):
            continue
        vtk_pk_path = os.path.join(vtk_root_dir, pk_name)
        os.makedirs(vtk_pk_path, exist_ok=True)
        for fname in os.listdir(pk_path):
            if fname.lower().endswith('.frd'):
                frd_path = os.path.join(pk_path, fname)
                vtk_path = os.path.join(vtk_pk_path, fname[:-4] + '.vtk')
                print(f"변환: {frd_path} -> {vtk_path}")
                nodes, elements = parse_frd(frd_path)
                write_vtk(nodes, elements, vtk_path)

if __name__ == "__main__":
    # concrete_pk 폴더와 vtk 폴더는 workspace 최상위에 있다고 가정
    convert_all_frd_to_vtk('concrete_pk', 'vtk')
