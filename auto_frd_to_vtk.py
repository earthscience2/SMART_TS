#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FRD → VTK 변환·검증 스크립트
- parse_frd: 공백 무시 + regex로 숫자 추출, 누락된 응력은 0으로 채움
- write_vtk: CELL_DATA 응력 처리
- compare_frd_vtk: shape 체크로 AxisError 방지, 응력도 비교
"""

import os
import re
import shutil
import numpy as np


def parse_frd(filename):
    """
    FRD 파일 파싱:
      nodes          {nid: (x,y,z)}
      elements       [[nid,...],...]
      displacements  {nid: (dx,dy,dz)}
      stresses       {eid: sxx} (모든 eid에 대해 key 보장)
      node_order, element_ids
    """
    nodes, elements, displacements, stresses = {}, [], {}, {}
    node_order, element_ids = [], []

    lines = open(filename, "r").read().splitlines()

    # 노드 파싱
    node_section = False
    for line in lines:
        ls = line.lstrip()
        if ls.startswith("2C"):
            node_section = True; continue
        if node_section:
            if not ls.startswith("-1"):
                node_section = False; continue
            parts = ls.split()
            if len(parts) == 5:
                nid = int(parts[1])
                x, y, z = map(float, parts[2:])
                nodes[nid] = (x, y, z)
                node_order.append(nid)

    # 요소 파싱
    elem_section = False
    for line in lines:
        ls = line.lstrip()
        if ls.startswith("3C"):
            elem_section = True; continue
        if elem_section:
            if ls.startswith("-1"):
                element_ids.append(int(ls.split()[1]))
            elif ls.startswith("-2"):
                ids = list(map(int, ls.split()[1:]))
                elements.append(ids)
            elif ls.startswith("-3"):
                break

    # 변위 파싱
    disp_section = False
    for line in lines:
        ls = line.lstrip()
        if ls.startswith("-4") and "DISP" in ls:
            disp_section = True; continue
        if disp_section:
            if ls.startswith(("-4", "1PSTEP", "100CL")):
                disp_section = False; continue
            if ls.startswith("-1"):
                m_id = re.match(r"-1\s*([0-9]+)", ls)
                vals = re.findall(r"[+\-]?\d+\.\d+E[+\-]?\d+", ls)
                if m_id and len(vals) >= 3:
                    nid = int(m_id.group(1))
                    dx, dy, dz = map(float, vals[:3])
                    displacements[nid] = (dx, dy, dz)
    # 누락된 노드 disp = (0,0,0)
    for nid in nodes:
        displacements.setdefault(nid, (0.0, 0.0, 0.0))

    # 응력 파싱
    stress_section = False
    for line in lines:
        ls = line.lstrip()
        if ls.startswith("-4") and "STRESS" in ls:
            stress_section = True; continue
        if stress_section:
            if ls.startswith(("-4", "1PSTEP", "100CL")):
                stress_section = False; continue
            if ls.startswith("-1"):
                m_id = re.match(r"-1\s*([0-9]+)", ls)
                vals = re.findall(r"[+\-]?\d+\.\d+E[+\-]?\d+", ls)
                if m_id and vals:
                    eid = int(m_id.group(1))
                    stresses[eid] = float(vals[0])
    # **모든 요소에 대해 응력 누락 시 0.0 채움**
    for eid in element_ids:
        stresses.setdefault(eid, 0.0)

    return nodes, elements, displacements, stresses, node_order, element_ids


def write_vtk(nodes, elements, out_path,
              displacements=None, stresses=None,
              node_order=None, element_ids=None):
    """VTK UNSTRUCTURED_GRID으로 내보내기"""
    with open(out_path, "w") as f:
        f.write("# vtk DataFile Version 3.0\nConverted from FRD\nASCII\n")
        f.write("DATASET UNSTRUCTURED_GRID\n")

        # POINTS
        f.write(f"POINTS {len(nodes)} float\n")
        for nid in node_order:
            x, y, z = nodes[nid]
            f.write(f"{x} {y} {z}\n")

        # CELLS
        total = sum(len(e) for e in elements)
        f.write(f"CELLS {len(elements)} {len(elements)+total}\n")
        for elem in elements:
            idxs = " ".join(str(n-1) for n in elem)
            f.write(f"{len(elem)} {idxs}\n")

        # CELL_TYPES
        f.write(f"CELL_TYPES {len(elements)}\n")
        for elem in elements:
            t = 12 if len(elem)==8 else 10 if len(elem)==4 else 7
            f.write(f"{t}\n")

        # POINT_DATA (displacement)
        if displacements:
            f.write(f"\nPOINT_DATA {len(nodes)}\n")
            f.write("VECTORS displacement float\n")
            for nid in node_order:
                dx, dy, dz = displacements[nid]
                f.write(f"{dx} {dy} {dz}\n")

        # CELL_DATA (stress)
        if stresses:
            f.write(f"\nCELL_DATA {len(elements)}\n")
            f.write("SCALARS stress float 1\n")
            f.write("LOOKUP_TABLE default\n")
            for eid in element_ids:
                f.write(f"{stresses[eid]}\n")


def convert_frd_to_vtk(frd_path, vtk_path):
    ns, es, ds, ss, norder, eids = parse_frd(frd_path)
    write_vtk(ns, es, vtk_path, ds, ss, norder, eids)


def compare_frd_vtk(frd_path, vtk_path):
    """변환 결과 검증: 노드/요소/변위/응력 일치 확인"""
    if not os.path.exists(frd_path):
        print("❌ FRD 파일이 없습니다:", frd_path); return
    if not os.path.exists(vtk_path):
        print("❌ VTK 파일이 없습니다:", vtk_path); return

    nodes, elements, displacements, stresses, norder, _ = parse_frd(frd_path)
    if not nodes:
        print("⚠️ 노드 0개: 경로·파일 확인 필요."); return

    lines = open(vtk_path).read().splitlines()

    # POINTS
    pi = next(i for i,l in enumerate(lines) if l.startswith("POINTS"))
    n_pts = int(lines[pi].split()[1])
    vtk_pts = [tuple(map(float, lines[pi+1+j].split())) for j in range(n_pts)]

    # CELLS
    ci = next(i for i,l in enumerate(lines) if l.startswith("CELLS"))
    n_c = int(lines[ci].split()[1])
    vtk_cells = [list(map(int, lines[ci+1+j].split()[1:])) for j in range(n_c)]

    # VECTORS displacement
    di = next((i for i,l in enumerate(lines)
               if l.strip().startswith("VECTORS displacement")), None)
    vtk_disp = []
    if di is not None:
        vtk_disp = [tuple(map(float, lines[di+1+j].split()))
                    for j in range(n_pts)]

    # SCALARS stress
    si = next((i for i,l in enumerate(lines)
               if l.strip().startswith("SCALARS stress")), None)
    vtk_stress = []
    if si is not None:
        vtk_stress = [float(lines[si+2+j].strip()) for j in range(n_c)]

    # 출력
    print(f"노드 개수: frd={len(nodes)}, vtk={n_pts}")
    print(f"요소 개수: frd={len(elements)}, vtk={n_c}")

    # 좌표 비교
    frd_arr = np.array([nodes[n] for n in norder])
    vtk_arr = np.array(vtk_pts)
    if frd_arr.ndim==2 and vtk_arr.ndim==2 and frd_arr.shape==vtk_arr.shape:
        d = np.linalg.norm(frd_arr-vtk_arr, axis=1)
        print(f"좌표 오차: max={d.max():.3e}, mean={d.mean():.3e}")
    else:
        print("좌표 shape 불일치 → 비교 건너뜀")

    # 요소 비교
    m = sum(1 for e1,e2 in zip(elements, vtk_cells)
            if [n-1 for n in e1]==e2)
    print(f"요소 일치: {m}/{len(elements)} ({m/len(elements)*100:.1f}%)")

    # 변위 비교
    if len(vtk_disp)==len(displacements):
        fr = np.array([displacements[n] for n in norder])
        vt = np.array(vtk_disp)
        dd = np.linalg.norm(fr-vt, axis=1)
        print(f"변위 오차: max={dd.max():.3e}, mean={dd.mean():.3e}")
    else:
        print("변위 비교 생략")

    # 응력 비교
    if len(vtk_stress)==len(stresses):
        keys = sorted(stresses)
        frs = np.array([stresses[k] for k in keys])
        vs = np.array(vtk_stress)
        sd = np.abs(frs-vs)
        print(f"응력 오차: max={sd.max():.3e}, mean={sd.mean():.3e}")
    else:
        print("응력 비교 생략")


def validate_vtk_file(vtk_path):
    """VTK 파일이 올바른 형식인지 검증"""
    try:
        with open(vtk_path, 'r') as f:
            lines = f.readlines()
        
        if len(lines) < 10:
            return False, "파일이 너무 짧습니다"
        
        # 헤더 확인
        if not lines[0].startswith('# vtk DataFile'):
            return False, "VTK 헤더가 없습니다"
        
        # DATASET 확인
        dataset_found = False
        for line in lines:
            if line.startswith('DATASET UNSTRUCTURED_GRID'):
                dataset_found = True
                break
        
        if not dataset_found:
            return False, "UNSTRUCTURED_GRID가 없습니다"
        
        # POINTS 확인
        points_found = False
        n_points = 0
        for i, line in enumerate(lines):
            if line.startswith('POINTS'):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        n_points = int(parts[1])
                        points_found = True
                        # POINTS 데이터 확인
                        if i + 1 + n_points > len(lines):
                            return False, f"POINTS 데이터가 부족합니다 (예상: {n_points}, 실제: {len(lines) - i - 1})"
                        break
                    except ValueError:
                        return False, "POINTS 개수가 숫자가 아닙니다"
        
        if not points_found:
            return False, "POINTS 섹션이 없습니다"
        
        # CELLS 확인
        cells_found = False
        for line in lines:
            if line.startswith('CELLS'):
                cells_found = True
                break
        
        if not cells_found:
            return False, "CELLS 섹션이 없습니다"
        
        return True, f"검증 통과 (노드: {n_points}개)"
        
    except Exception as e:
        return False, f"파일 읽기 오류: {e}"


def convert_all_frd_to_vtk(frd_root_dir="frd", vtk_root_dir="assets/vtk"):
    """frd 폴더의 모든 .frd 파일을 assets/vtk에 동일한 경로로 변환"""
    if not os.path.exists(frd_root_dir):
        print(f"❌ frd 폴더가 없습니다: {frd_root_dir}")
        return
    
    # assets/vtk 폴더 생성
    os.makedirs(vtk_root_dir, exist_ok=True)
    
    converted_count = 0
    error_count = 0
    validation_errors = []
    
    # frd 폴더 내 모든 하위 폴더와 파일을 재귀적으로 탐색
    for root, dirs, files in os.walk(frd_root_dir):
        # frd 폴더 기준의 상대 경로 계산
        rel_path = os.path.relpath(root, frd_root_dir)
        if rel_path == ".":
            rel_path = ""
        
        # assets/vtk에 동일한 폴더 구조 생성
        vtk_dir = os.path.join(vtk_root_dir, rel_path)
        os.makedirs(vtk_dir, exist_ok=True)
        
        # 현재 폴더의 .frd 파일들 처리
        for file in files:
            if file.lower().endswith('.frd'):
                frd_path = os.path.join(root, file)
                vtk_filename = file[:-4] + '.vtk'  # .frd → .vtk
                vtk_path = os.path.join(vtk_dir, vtk_filename)
                
                try:
                    print(f"변환 중: {frd_path} → {vtk_path}")
                    convert_frd_to_vtk(frd_path, vtk_path)
                    
                    # VTK 파일 검증
                    is_valid, message = validate_vtk_file(vtk_path)
                    if is_valid:
                        converted_count += 1
                        print(f"✅ 성공: {message}")
                    else:
                        error_count += 1
                        validation_errors.append(f"{vtk_path}: {message}")
                        print(f"❌ 검증 실패: {message}")
                        
                except Exception as e:
                    error_count += 1
                    print(f"❌ 변환 실패: {frd_path} - {e}")
    
    print(f"\n🎉 변환 완료!")
    print(f"✅ 성공: {converted_count}개")
    print(f"❌ 실패: {error_count}개")
    
    if validation_errors:
        print(f"\n⚠️ 검증 오류:")
        for error in validation_errors:
            print(f"  - {error}")


if __name__ == "__main__":
    # 전체 frd → vtk 변환 실행
    print("🚀 frd → vtk 전체 변환 시작...")
    convert_all_frd_to_vtk()
