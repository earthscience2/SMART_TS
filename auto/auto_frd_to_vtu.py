#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FRD → VTU 변환 스크립트 (ccx2paraview 사용)
- ccx2paraview 라이브러리를 사용하여 안정적인 변환
- frd 폴더의 모든 파일을 assets/vtu에 동일한 경로로 변환
"""

import os
import logging
from ccx2paraview import Converter


def convert_frd_to_vtu(frd_path, vtu_path):
    """ccx2paraview를 사용하여 FRD → VTU 변환"""
    try:
        # vtu 디렉토리 생성
        vtu_dir = os.path.dirname(vtu_path)
        os.makedirs(vtu_dir, exist_ok=True)
        
        # ccx2paraview 변환기 생성 및 실행
        converter = Converter(frd_path, ['vtu'])
        converter.run()
        
        # 생성된 vtu 파일을 원하는 위치로 이동
        # ccx2paraview는 입력 파일과 같은 디렉토리에 출력
        generated_vtu = frd_path.replace('.frd', '.vtu')
        if os.path.exists(generated_vtu):
            # 파일이 이미 존재하면 덮어쓰기
            if os.path.exists(vtu_path):
                os.remove(vtu_path)
            os.rename(generated_vtu, vtu_path)
            return True, "변환 성공"
        else:
            return False, "VTU 파일이 생성되지 않았습니다"
            
    except Exception as e:
        return False, f"변환 오류: {str(e)}"


def validate_vtu_file(vtu_path):
    """VTU 파일이 올바른 형식인지 검증"""
    try:
        with open(vtu_path, 'r') as f:
            lines = f.readlines()
        
        if len(lines) < 10:
            return False, "파일이 너무 짧습니다"
        
        # XML 헤더 확인
        if not lines[0].startswith('<?xml'):
            return False, "XML 헤더가 없습니다"
        
        # VTKFile 태그 확인
        vtkfile_found = False
        for line in lines:
            if '<VTKFile' in line:
                vtkfile_found = True
                break
        
        if not vtkfile_found:
            return False, "VTKFile 태그가 없습니다"
        
        # UnstructuredGrid 태그 확인
        grid_found = False
        for line in lines:
            if '<UnstructuredGrid' in line:
                grid_found = True
                break
        
        if not grid_found:
            return False, "UnstructuredGrid 태그가 없습니다"
        
        # Piece 태그에서 노드 개수 확인
        n_points = 0
        for line in lines:
            if '<Piece' in line and 'NumberOfPoints' in line:
                try:
                    # NumberOfPoints="486" 형태에서 숫자 추출
                    import re
                    match = re.search(r'NumberOfPoints="(\d+)"', line)
                    if match:
                        n_points = int(match.group(1))
                        break
                except:
                    pass
        
        return True, f"검증 통과 (노드: {n_points}개)"
        
    except Exception as e:
        return False, f"파일 읽기 오류: {e}"


def convert_all_frd_to_vtu(frd_root_dir="frd", vtu_root_dir="assets/vtu"):
    """frd 폴더의 모든 .frd 파일을 assets/vtu에 동일한 경로로 변환"""
    if not os.path.exists(frd_root_dir):
        print(f"❌ frd 폴더가 없습니다: {frd_root_dir}")
        return
    
    # assets/vtu 폴더 생성
    os.makedirs(vtu_root_dir, exist_ok=True)
    
    converted_count = 0
    error_count = 0
    validation_errors = []
    
    # frd 폴더 내 모든 하위 폴더와 파일을 재귀적으로 탐색
    for root, dirs, files in os.walk(frd_root_dir):
        # frd 폴더 기준의 상대 경로 계산
        rel_path = os.path.relpath(root, frd_root_dir)
        if rel_path == ".":
            rel_path = ""
        
        # assets/vtu에 동일한 폴더 구조 생성
        vtu_dir = os.path.join(vtu_root_dir, rel_path)
        os.makedirs(vtu_dir, exist_ok=True)
        
        # 현재 폴더의 .frd 파일들 처리
        for file in files:
            if file.lower().endswith('.frd'):
                frd_path = os.path.join(root, file)
                vtu_filename = file[:-4] + '.vtu'  # .frd → .vtu
                vtu_path = os.path.join(vtu_dir, vtu_filename)
                
                try:
                    print(f"변환 중: {frd_path} → {vtu_path}")
                    success, message = convert_frd_to_vtu(frd_path, vtu_path)
                    
                    if success:
                        # VTU 파일 검증
                        is_valid, validation_msg = validate_vtu_file(vtu_path)
                        if is_valid:
                            converted_count += 1
                            print(f"✅ 성공: {validation_msg}")
                        else:
                            error_count += 1
                            validation_errors.append(f"{vtu_path}: {validation_msg}")
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


if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # 전체 frd → vtu 변환 실행
    print("🚀 frd → vtu 전체 변환 시작...")
    convert_all_frd_to_vtu()
