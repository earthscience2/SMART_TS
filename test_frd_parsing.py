#!/usr/bin/env python3
# test_frd_parsing.py
# FRD 파일 파싱 테스트

import os
import re
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
        current_block = None
        
        print(f"파일 읽기 시작: {frd_path}")
        print(f"총 라인 수: {len(lines)}")
        
        for i, line in enumerate(lines):
            line = line.strip()
            # 좌표 블록 시작 확인 (2C로 시작하는 라인)
            if line.startswith('2C'):
                current_block = 'coordinates'
                print(f"라인 {i+1}: 좌표 블록 시작 - {line}")
                continue
            # 응력 블록 시작 확인 (STRESS만, ERROR 제외)
            if '-4  STRESS' in line:
                current_block = 'stress'
                print(f"라인 {i+1}: 응력 블록 시작 - {line}")
                continue
            # ERROR 블록 시작 시 stress 블록 종료
            if '-4  ERROR' in line:
                current_block = None
                print(f"라인 {i+1}: ERROR 블록 시작 - stress 블록 종료")
                continue
            # -1로 시작하는 라인에서 모든 숫자 추출
            if line.startswith('-1') and current_block in ['coordinates', 'stress']:
                # 과학적 표기법을 포함한 숫자 추출 (E, e 포함)
                nums = re.findall(r'-?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?', line)
                if len(nums) >= 2:
                    node_id = int(nums[1])
                    # 좌표: -1, node_id, x, y, z
                    if current_block == 'coordinates' and len(nums) == 5:
                        try:
                            x, y, z = float(nums[2]), float(nums[3]), float(nums[4])
                            node_coords[node_id] = [x, y, z]
                            print(f"라인 {i+1}: 좌표 파싱 성공 - 노드 {node_id}: ({x}, {y}, {z})")
                        except Exception as e:
                            print(f"라인 {i+1}: 좌표 파싱 오류 - {e}, 라인: {line}")
                            continue
                    # 응력: -1, node_id, sxx, syy, szz, sxy, syz, sxz 또는 -1, node_id, von_mises
                    elif current_block == 'stress':
                        try:
                            # 응력 값들이 붙어있을 수 있으므로 더 정확한 파싱
                            # 라인에서 노드 ID 이후의 모든 숫자를 추출
                            stress_nums = re.findall(r'-?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?', line[line.find(str(node_id)) + len(str(node_id)):])
                            
                            if len(stress_nums) >= 6:
                                # 6개 응력 성분이 있는 경우 (SXX, SYY, SZZ, SXY, SYZ, SZX)
                                sxx = float(stress_nums[0])
                                syy = float(stress_nums[1])
                                szz = float(stress_nums[2])
                                sxy = float(stress_nums[3])
                                syz = float(stress_nums[4])
                                sxz = float(stress_nums[5])
                                
                                # von Mises 응력 계산
                                von_mises = np.sqrt(0.5 * ((sxx - syy)**2 + (syy - szz)**2 + (szz - sxx)**2 + 6 * (sxy**2 + syz**2 + sxz**2)))
                                stress_values[node_id] = von_mises
                                print(f"라인 {i+1}: 응력 파싱 성공 (6성분) - 노드 {node_id}: von Mises = {von_mises:.2e} Pa")
                            elif len(stress_nums) == 1:
                                # 단일 응력 값인 경우 (이미 von Mises 응력일 가능성)
                                von_mises = float(stress_nums[0])
                                stress_values[node_id] = von_mises
                                print(f"라인 {i+1}: 응력 파싱 성공 (단일값) - 노드 {node_id}: 응력 = {von_mises:.2e} Pa")
                            else:
                                print(f"라인 {i+1}: 응력 값 개수 부족 - {len(stress_nums)}개, 라인: {line}")
                        except Exception as e:
                            print(f"라인 {i+1}: 응력 파싱 오류 - {e}, 라인: {line}")
                            continue
        
        print(f"\n파싱 결과:")
        print(f"좌표 데이터: {len(node_coords)}개 노드")
        print(f"응력 데이터: {len(stress_values)}개 노드")
        
        # 좌표와 응력 값의 노드 ID를 맞춤
        if node_coords and stress_values:
            coord_node_ids = set(node_coords.keys())
            stress_node_ids = set(stress_values.keys())
            common_node_ids = coord_node_ids.intersection(stress_node_ids)
            
            print(f"공통 노드 ID: {len(common_node_ids)}개")
            if common_node_ids:
                print(f"공통 노드 ID 목록: {sorted(list(common_node_ids))[:10]}...")  # 처음 10개만 출력
                
                # 공통 노드 ID만 사용
                stress_data['coordinates'] = [node_coords[i] for i in sorted(common_node_ids)]
                stress_data['nodes'] = sorted(common_node_ids)
                stress_data['stress_values'] = [{i: stress_values[i] for i in common_node_ids}]
                
                print(f"최종 데이터:")
                print(f"  - 좌표: {len(stress_data['coordinates'])}개")
                print(f"  - 노드: {len(stress_data['nodes'])}개")
                print(f"  - 응력 값: {len(stress_data['stress_values'][0])}개")
                
                # 응력 값 범위 출력
                if stress_data['stress_values'][0]:
                    stress_vals = list(stress_data['stress_values'][0].values())
                    print(f"  - 응력 범위: {min(stress_vals):.2e} ~ {max(stress_vals):.2e} Pa")
                    print(f"  - 응력 범위 (GPa): {min(stress_vals)/1e9:.6f} ~ {max(stress_vals)/1e9:.6f} GPa")
        
        # 시간 정보 파싱
        try:
            filename = os.path.basename(frd_path)
            time_str = filename.split(".")[0]
            dt = datetime.strptime(time_str, "%Y%m%d%H")
            stress_data['times'].append(dt)
            print(f"시간 정보: {dt}")
        except Exception as e:
            print(f"시간 파싱 오류: {e}")
            stress_data['times'].append(0)
        
        return stress_data
    except Exception as e:
        print(f"FRD 파일 읽기 오류: {e}")
        return None

def test_frd_files():
    """frd 디렉토리의 모든 FRD 파일을 테스트합니다."""
    frd_dir = "frd"
    if not os.path.exists(frd_dir):
        print(f"frd 디렉토리가 없습니다: {frd_dir}")
        return
    
    # 모든 하위 디렉토리 검색
    for root, dirs, files in os.walk(frd_dir):
        for file in files:
            if file.endswith('.frd'):
                frd_path = os.path.join(root, file)
                print(f"\n{'='*60}")
                print(f"테스트 파일: {frd_path}")
                print(f"{'='*60}")
                
                result = read_frd_stress_data(frd_path)
                if result:
                    print(f"✅ 파싱 성공!")
                else:
                    print(f"❌ 파싱 실패!")

if __name__ == "__main__":
    test_frd_files() 