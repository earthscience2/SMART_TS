#!/usr/bin/env python3
# test_frd_parsing.py

import os
import numpy as np
from datetime import datetime

def read_frd_stress_data(frd_path):
    """FRD 파일에서 응력 데이터를 읽어옵니다."""
    try:
        with open(frd_path, 'r') as f:
            lines = f.readlines()
        
        stress_data = {
            'times': [],
            'nodes': [],
            'coordinates': [],
            'stress_values': []
        }
        
        node_coords = {}
        stress_values = {}
        block = 'coord'  # 처음엔 좌표 블록
        for line in lines:
            line = line.strip()
            if line.startswith('-1') or line.startswith(' -1'):
                parts = line.split()
                # 좌표 블록: 5개
                if block == 'coord' and len(parts) == 5:
                    try:
                        node_id = int(parts[1])
                        x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
                        node_coords[node_id] = [x, y, z]
                    except:
                        continue
                # 응력 블록: 8개
                elif len(parts) == 8:
                    block = 'stress'  # 응력 블록 시작
                    try:
                        node_id = int(parts[1])
                        sxx = float(parts[2])
                        syy = float(parts[3])
                        szz = float(parts[4])
                        sxy = float(parts[5])
                        syz = float(parts[6])
                        sxz = float(parts[7])
                        von_mises = np.sqrt(0.5 * ((sxx - syy)**2 + (syy - szz)**2 + (szz - sxx)**2 + 6 * (sxy**2 + syz**2 + sxz**2)))
                        stress_values[node_id] = von_mises
                    except:
                        continue
        if node_coords:
            stress_data['coordinates'] = [node_coords[i] for i in sorted(node_coords.keys())]
            stress_data['nodes'] = sorted(node_coords.keys())
        if stress_values:
            stress_data['stress_values'].append(stress_values)
        try:
            filename = os.path.basename(frd_path)
            time_str = filename.split(".")[0]
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            stress_data['times'].append(dt)
        except:
            stress_data['times'].append(0)
        return stress_data
    except Exception as e:
        print(f"FRD 파일 읽기 오류: {e}")
        return None

if __name__ == "__main__":
    # FRD 파일 테스트
    frd_file = 'frd/C000001/2025061215.frd'
    if os.path.exists(frd_file):
        print(f"파일 존재: {frd_file}")
        data = read_frd_stress_data(frd_file)
        if data:
            print(f'노드 수: {len(data["nodes"])}')
            print(f'좌표 수: {len(data["coordinates"])}')
            print(f'응력 값 수: {len(data["stress_values"][0]) if data["stress_values"] else 0}')
            print(f'시간: {data["times"]}')
            if data['stress_values'] and data['stress_values'][0]:
                stress_vals = list(data['stress_values'][0].values())
                print(f'응력 범위: {min(stress_vals):.6f} ~ {max(stress_vals):.6f} MPa')
                print(f'응력 샘플 (처음 5개): {stress_vals[:5]}')
        else:
            print('데이터 파싱 실패')
    else:
        print('파일이 존재하지 않습니다') 