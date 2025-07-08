#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
응력 시각화 코드 테스트 스크립트
"""

import os
import sys
from create_stress_visualization import StressVisualizer

def test_stress_visualization():
    """응력 시각화 코드를 테스트합니다."""
    
    # 실제 FRD 파일 경로
    frd_file = "frd/C000001/2025070218.frd"
    
    if not os.path.exists(frd_file):
        print(f"❌ FRD 파일이 없습니다: {frd_file}")
        return False
    
    print(f"✅ FRD 파일 발견: {frd_file}")
    
    # 응력 시각화 객체 생성
    visualizer = StressVisualizer(frd_file)
    
    # FRD 파일 파싱
    print("📖 FRD 파일 파싱 중...")
    if not visualizer.parse_frd_file():
        print("❌ FRD 파일 파싱 실패")
        return False
    
    print("✅ FRD 파일 파싱 완료")
    
    # 응력 통계 출력
    stats = visualizer.get_stress_statistics()
    if stats:
        print("\n📊 응력 통계:")
        for component, stat in stats.items():
            print(f"\n{component}:")
            for key, value in stat.items():
                print(f"  {key}: {value:.2e} Pa")
    
    # 출력 디렉토리 생성
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Von Mises 등응력면 시각화
    print("\n🎨 Von Mises 등응력면 시각화 생성 중...")
    fig_isosurface = visualizer.create_isosurface_visualization(
        stress_component='von_mises',
        isovalues=None,  # 자동 계산
        opacity=0.4,
        colorscale='Viridis'
    )
    
    if fig_isosurface:
        output_path = os.path.join(output_dir, "von_mises_isosurface.png")
        if visualizer.save_visualization(fig_isosurface, output_path, width=1200, height=800):
            print(f"✅ 등응력면 이미지 저장 완료: {output_path}")
        else:
            print("❌ 등응력면 이미지 저장 실패")
    else:
        print("❌ 등응력면 시각화 생성 실패")
    
    # 2. 응력 히트맵
    print("\n🎨 응력 히트맵 생성 중...")
    fig_heatmap = visualizer.create_stress_heatmap(
        stress_component='von_mises',
        colorscale='Viridis'
    )
    
    if fig_heatmap:
        output_path = os.path.join(output_dir, "stress_heatmap.png")
        if visualizer.save_visualization(fig_heatmap, output_path, width=1200, height=800):
            print(f"✅ 히트맵 이미지 저장 완료: {output_path}")
        else:
            print("❌ 히트맵 이미지 저장 실패")
    else:
        print("❌ 히트맵 생성 실패")
    
    # 3. SXX 응력 성분 시각화
    print("\n🎨 SXX 응력 성분 시각화 생성 중...")
    fig_sxx = visualizer.create_isosurface_visualization(
        stress_component='SXX',
        isovalues=None,
        opacity=0.4,
        colorscale='RdBu'
    )
    
    if fig_sxx:
        output_path = os.path.join(output_dir, "sxx_isosurface.png")
        if visualizer.save_visualization(fig_sxx, output_path, width=1200, height=800):
            print(f"✅ SXX 등응력면 이미지 저장 완료: {output_path}")
        else:
            print("❌ SXX 등응력면 이미지 저장 실패")
    else:
        print("❌ SXX 등응력면 시각화 생성 실패")
    
    # 4. 종합 시각화
    print("\n🎨 종합 응력 시각화 생성 중...")
    output_path = os.path.join(output_dir, "comprehensive_stress.png")
    fig_comprehensive = visualizer.create_comprehensive_visualization(output_path=output_path)
    
    if fig_comprehensive:
        print(f"✅ 종합 시각화 이미지 저장 완료: {output_path}")
    else:
        print("❌ 종합 시각화 생성 실패")
    
    print("\n🎉 모든 시각화 생성 완료!")
    return True

if __name__ == "__main__":
    success = test_stress_visualization()
    if success:
        print("\n✅ 테스트 성공!")
    else:
        print("\n❌ 테스트 실패!")
        sys.exit(1) 