#!/usr/bin/env python3
# test_frd_parsing.py
# FRD 파일 파싱 테스트

import os
import numpy as np
from datetime import datetime
import re

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
        current_block = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # 좌표 블록 시작 확인 (2C로 시작하는 라인)
            if line.startswith('2C'):
                current_block = 'coordinates'
                print(f"좌표 블록 시작: 라인 {i+1}")
                continue
            
            # 응력 블록 시작 확인
            if '-4  STRESS' in line:
                current_block = 'stress'
                print(f"응력 블록 시작: 라인 {i+1}")
                continue
            
            # 좌표 데이터 파싱 (-1로 시작하고 5개 값)
            if current_block == 'coordinates' and line.startswith('-1'):
                nums = re.findall(r'[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?', line)
                print(f"[좌표] 라인 {i+1}: nums={nums}")
                if len(nums) == 4:
                    try:
                        node_id = int(nums[0])
                        x, y, z = float(nums[1]), float(nums[2]), float(nums[3])
                        node_coords[node_id] = [x, y, z]
                    except Exception as e:
                        print(f"좌표 파싱 오류 (라인 {i+1}): {e}, 데이터: {line}")
                        continue
            
            # 응력 데이터 파싱 (-1로 시작하고 7개 값: 노드ID + 6개 응력 성분)
            elif current_block == 'stress' and line.startswith('-1'):
                nums = re.findall(r'[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?', line)
                print(f"[응력] 라인 {i+1}: nums={nums}")
                if len(nums) == 7:
                    try:
                        node_id = int(nums[0])
                        sxx = float(nums[1])
                        syy = float(nums[2])
                        szz = float(nums[3])
                        sxy = float(nums[4])
                        syz = float(nums[5])
                        sxz = float(nums[6])
                        # von Mises 응력 계산
                        von_mises = np.sqrt(0.5 * ((sxx - syy)**2 + (syy - szz)**2 + (szz - sxx)**2 + 6 * (sxy**2 + syz**2 + sxz**2)))
                        stress_values[node_id] = von_mises
                    except Exception as e:
                        print(f"응력 파싱 오류 (라인 {i+1}): {e}, 데이터: {line}")
                        continue
        
        print(f"파싱된 좌표 수: {len(node_coords)}")
        print(f"파싱된 응력 값 수: {len(stress_values)}")
        
        # 좌표와 응력 값의 노드 ID를 맞춤
        if node_coords and stress_values:
            coord_node_ids = set(node_coords.keys())
            stress_node_ids = set(stress_values.keys())
            common_node_ids = coord_node_ids.intersection(stress_node_ids)
            
            print(f"공통 노드 ID 수: {len(common_node_ids)}")
            
            if common_node_ids:
                # 공통 노드 ID만 사용
                stress_data['coordinates'] = [node_coords[i] for i in sorted(common_node_ids)]
                stress_data['nodes'] = sorted(common_node_ids)
                stress_data['stress_values'] = [{i: stress_values[i] for i in common_node_ids}]
        
        # 시간 정보 파싱
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
    # 테스트할 FRD 파일
    frd_file = "frd/C000001/2025061215.frd"
    
    if os.path.exists(frd_file):
        print(f"파일 테스트: {frd_file}")
        result = read_frd_stress_data(frd_file)
        
        if result:
            print(f"\n=== 파싱 결과 ===")
            print(f"시간: {result['times']}")
            print(f"노드 수: {len(result['nodes'])}")
            print(f"좌표 수: {len(result['coordinates'])}")
            print(f"응력 값 수: {len(result['stress_values'][0]) if result['stress_values'] else 0}")
            
            if result['stress_values'] and result['stress_values'][0]:
                stress_vals = list(result['stress_values'][0].values())
                print(f"응력 범위: {min(stress_vals):.6f} ~ {max(stress_vals):.6f}")
                print(f"응력 평균: {np.mean(stress_vals):.6f}")
                print(f"샘플 응력 값들: {stress_vals[:5]}")
        else:
            print("파싱 실패")
    else:
        print(f"파일이 존재하지 않습니다: {frd_file}") 