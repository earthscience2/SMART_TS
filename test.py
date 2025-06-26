#!/usr/bin/env python3
"""
센서 정보 조회 테스트 스크립트
S_000455 구조의 센서 정보를 조회하고 상세 정보를 출력합니다.
"""

import pandas as pd
import api_db


def test_sensor_info():
    """S_000455 구조의 센서 정보를 조회하고 출력"""
    
    print("=" * 60)
    print("📡 센서 정보 조회 테스트")
    print("=" * 60)
    
    s_code = "S_000455"
    print(f"🔍 조회 대상 구조: {s_code}")
    print(f"🎯 프로젝트: P_000078")
    print("-" * 60)
    
    try:
        # 센서 정보 조회
        sensors_df = api_db.get_sensor_list_for_structure(s_code, its_num=1)
        
        if sensors_df.empty:
            print("❌ 해당 구조에서 센서를 찾을 수 없습니다.")
            return
        
        print(f"✅ 총 {len(sensors_df)}개의 센서를 발견했습니다.")
        print()
        
        # 센서 상세 정보 출력
        for idx, (_, row) in enumerate(sensors_df.iterrows(), 1):
            device_id = row['deviceid']
            channel = row['channel']
            device_type = row.get('device_type', 'N/A')
            data_type = row.get('data_type', 'N/A')
            is3axis = "3축" if row.get('is3axis') == 'Y' else "1축"
            
            print(f"📡 센서 #{idx}")
            print(f"   ├─ Device ID: {device_id}")
            print(f"   ├─ Channel: {channel}")
            print(f"   ├─ 장비타입: {device_type}")
            print(f"   ├─ 데이터타입: {data_type}")
            print(f"   └─ 센서타입: {is3axis}")
            print()
        
        # DataFrame 전체 출력
        print("-" * 60)
        print("📊 전체 데이터 (DataFrame)")
        print("-" * 60)
        print(sensors_df.to_string(index=False))
        
        # 컬럼 정보 출력
        print()
        print("-" * 60)
        print("📋 컬럼 정보")
        print("-" * 60)
        for col in sensors_df.columns:
            print(f"   • {col}: {sensors_df[col].dtype}")
        
        # 통계 정보
        print()
        print("-" * 60)
        print("📈 통계 정보")
        print("-" * 60)
        
        # 장비타입별 통계
        if 'device_type' in sensors_df.columns:
            device_stats = sensors_df['device_type'].value_counts()
            print("🔧 장비타입별 분포:")
            for device_type, count in device_stats.items():
                print(f"   • {device_type}: {count}개")
        
        print()
        
        # 데이터타입별 통계
        if 'data_type' in sensors_df.columns:
            data_stats = sensors_df['data_type'].value_counts()
            print("📊 데이터타입별 분포:")
            for data_type, count in data_stats.items():
                print(f"   • {data_type}: {count}개")
        
        print()
        
        # 3축/1축 센서 통계
        if 'is3axis' in sensors_df.columns:
            axis_stats = sensors_df['is3axis'].value_counts()
            print("⚖️ 센서타입별 분포:")
            for axis_type, count in axis_stats.items():
                axis_label = "3축" if axis_type == 'Y' else "1축"
                print(f"   • {axis_label}: {count}개")
                
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


def test_multiple_structures():
    """여러 구조의 센서 정보를 비교 조회"""
    
    print("\n" + "=" * 60)
    print("🔄 여러 구조 센서 비교")
    print("=" * 60)
    
    structures = ["S_000455", "S_000456"]
    
    for s_code in structures:
        print(f"\n🏗️ 구조: {s_code}")
        print("-" * 40)
        
        try:
            sensors_df = api_db.get_sensor_list_for_structure(s_code, its_num=1)
            
            if sensors_df.empty:
                print("   ❌ 센서 없음")
            else:
                print(f"   ✅ 센서 개수: {len(sensors_df)}개")
                
                # 간단한 요약
                if 'device_type' in sensors_df.columns:
                    unique_devices = sensors_df['device_type'].nunique()
                    print(f"   📡 장비타입 종류: {unique_devices}가지")
                
                if 'is3axis' in sensors_df.columns:
                    axis3_count = len(sensors_df[sensors_df['is3axis'] == 'Y'])
                    axis1_count = len(sensors_df[sensors_df['is3axis'] == 'N'])
                    print(f"   ⚖️ 3축센서: {axis3_count}개, 1축센서: {axis1_count}개")
                    
        except Exception as e:
            print(f"   ❌ 오류: {e}")


if __name__ == "__main__":
    # 메인 테스트 실행
    test_sensor_info()
    
    # 추가 테스트 (여러 구조 비교)
    test_multiple_structures()
    
    print("\n" + "=" * 60)
    print("🎉 테스트 완료!")
    print("=" * 60)