#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FRD → VTK 변환 스크립트 (ccx2paraview 사용)
- ccx2paraview 라이브러리를 사용하여 안정적인 변환
- frd 폴더의 모든 파일을 assets/vtk에 동일한 경로로 변환
"""

import os
import logging
from ccx2paraview import Converter


def fix_vtk_format(vtk_path):
    """ccx2paraview로 생성된 VTK 파일의 POINTS 형식을 수정"""
    try:
        with open(vtk_path, 'r') as f:
            lines = f.readlines()
        
        fixed_lines = []
        in_points_section = False
        points_count = 0
        
        for line in lines:
            # POINTS 섹션 시작 확인
            if line.startswith('POINTS'):
                in_points_section = True
                parts = line.split()
                if len(parts) >= 2:
                    points_count = int(parts[1])
                fixed_lines.append(line)
                continue
            
            # POINTS 섹션 종료 조건
            if in_points_section and (line.startswith('CELLS') or line.startswith('CELL_TYPES') or line.startswith('POINT_DATA')):
                in_points_section = False
                fixed_lines.append(line)
                continue
            
            # POINTS 섹션 내 데이터 처리
            if in_points_section and line.strip():
                # 한 줄에 여러 점이 있으면 분리
                coords = line.strip().split()
                # 3개씩 묶어서 각각 새 줄로 만들기
                for i in range(0, len(coords), 3):
                    if i + 2 < len(coords):
                        x, y, z = coords[i], coords[i+1], coords[i+2]
                        fixed_lines.append(f"{x} {y} {z}\n")
            else:
                fixed_lines.append(line)
        
        # 수정된 내용을 파일에 다시 저장
        with open(vtk_path, 'w') as f:
            f.writelines(fixed_lines)
        
        return True, "VTK 형식 수정 완료"
        
    except Exception as e:
        return False, f"VTK 형식 수정 오류: {str(e)}"


def convert_frd_to_vtk(frd_path, vtk_path):
    """ccx2paraview를 사용하여 FRD → VTK 변환 + 형식 수정"""
    try:
        # vtk 디렉토리 생성
        vtk_dir = os.path.dirname(vtk_path)
        os.makedirs(vtk_dir, exist_ok=True)
        
        # ccx2paraview 변환기 생성 및 실행
        converter = Converter(frd_path, ['vtk'])
        converter.run()
        
        # 생성된 vtk 파일을 원하는 위치로 이동
        # ccx2paraview는 입력 파일과 같은 디렉토리에 출력
        generated_vtk = frd_path.replace('.frd', '.vtk')
        if os.path.exists(generated_vtk):
            # 목적지에 파일이 이미 있으면 생성된 임시 파일 삭제
            if os.path.exists(vtk_path):
                os.remove(generated_vtk)
                return True, "이미 존재하는 파일 (변환 건너뛰기)"
            else:
                os.rename(generated_vtk, vtk_path)
            
            # VTK 형식 수정
            fix_success, fix_message = fix_vtk_format(vtk_path)
            if fix_success:
                return True, f"변환 성공 ({fix_message})"
            else:
                return True, f"변환 성공 (형식 수정 실패: {fix_message})"
        else:
            return False, "VTK 파일이 생성되지 않았습니다"
            
    except Exception as e:
        return False, f"변환 오류: {str(e)}"


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
            if line.startswith('DATASET'):
                dataset_found = True
                break
        
        if not dataset_found:
            return False, "DATASET 섹션이 없습니다"
        
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
                        break
                    except ValueError:
                        return False, "POINTS 개수가 숫자가 아닙니다"
        
        if not points_found:
            return False, "POINTS 섹션이 없습니다"
        
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
                
                # 이미 VTK 파일이 존재하면 건너뛰기
                if os.path.exists(vtk_path):
                    print(f"⏭️ 건너뛰기 (이미 존재): {vtk_path}")
                    converted_count += 1  # 이미 변환된 것으로 계산
                    continue
                
                try:
                    print(f"변환 중: {frd_path} → {vtk_path}")
                    success, message = convert_frd_to_vtk(frd_path, vtk_path)
                    
                    if success:
                        # VTK 파일 검증
                        is_valid, validation_msg = validate_vtk_file(vtk_path)
                        if is_valid:
                            converted_count += 1
                            print(f"✅ 성공: {validation_msg}")
                        else:
                            error_count += 1
                            validation_errors.append(f"{vtk_path}: {validation_msg}")
                            print(f"❌ 검증 실패: {validation_msg}")
                    else:
                        error_count += 1
                        print(f"❌ 변환 실패: {message}")
                        
                except Exception as e:
                    error_count += 1
                    print(f"❌ 처리 오류: {frd_path} - {e}")
    
    print(f"\n🎉 변환 완료!")
    print(f"✅ 성공: {converted_count}개")
    print(f"❌ 실패: {error_count}개")
    
    if validation_errors:
        print(f"\n⚠️ 검증 오류:")
        for error in validation_errors:
            print(f"  - {error}")


def test_single_conversion():
    """단일 파일 변환 테스트"""
    frd_path = "frd/C000001/2025061215.frd"
    vtk_path = "assets/vtk/C000001/2025061215.vtk"
    
    if not os.path.exists(frd_path):
        print(f"❌ 테스트 파일이 없습니다: {frd_path}")
        return
    
    print(f"🧪 단일 파일 변환 테스트")
    print(f"입력: {frd_path}")
    print(f"출력: {vtk_path}")
    
    success, message = convert_frd_to_vtk(frd_path, vtk_path)
    
    if success:
        is_valid, validation_msg = validate_vtk_file(vtk_path)
        print(f"✅ 변환 성공: {validation_msg}")
    else:
        print(f"❌ 변환 실패: {message}")


if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # 전체 frd → vtk 변환 실행
    print("🚀 frd → vtk 전체 변환 시작...")
    convert_all_frd_to_vtk()
