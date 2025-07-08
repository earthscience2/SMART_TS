# FRD 파일 응력 시각화 코드

## 개요

이 코드는 CalculiX의 FRD 파일에서 노드 위치와 응력 데이터를 추출하여 등응력면(Isosurface) 이미지를 생성하는 Python 스크립트입니다.

## 주요 기능

### 1. FRD 파일 파싱
- **노드 좌표 추출**: `2C` 블록에서 노드 ID와 X, Y, Z 좌표 추출
- **응력 데이터 추출**: `-4 STRESS` 블록에서 6개 응력 성분(SXX, SYY, SZZ, SXY, SYZ, SZX) 추출
- **Von Mises 응력 계산**: 6개 응력 성분으로부터 Von Mises 응력 자동 계산

### 2. 시각화 기능
- **등응력면 시각화**: 특정 응력 값에 해당하는 3D 등응력면 생성
- **응력 히트맵**: 3D 공간에서 응력 분포를 색상으로 표현
- **종합 시각화**: 여러 응력 성분을 한 번에 비교 분석
- **통계 정보**: 각 응력 성분별 최솟값, 최댓값, 평균, 표준편차, 중앙값 제공

### 3. 이미지 저장
- **고해상도 이미지**: Plotly와 Kaleido를 사용한 고품질 PNG 이미지 생성
- **다양한 형식 지원**: PNG, JPG, SVG, PDF 형식 지원
- **자동 디렉토리 생성**: 출력 디렉토리 자동 생성

## 코드 구조

### StressVisualizer 클래스

```python
class StressVisualizer:
    def __init__(self, frd_file_path):
        # 초기화
        
    def parse_frd_file(self):
        # FRD 파일 파싱
        
    def create_isosurface_visualization(self, stress_component='von_mises', 
                                      isovalues=None, opacity=0.3, 
                                      colorscale='Viridis'):
        # 등응력면 시각화 생성
        
    def create_stress_heatmap(self, stress_component='von_mises', 
                            colorscale='Viridis'):
        # 응력 히트맵 생성
        
    def create_comprehensive_visualization(self, output_path=None):
        # 종합 시각화 생성
        
    def save_visualization(self, fig, output_path, format='png', 
                         width=1200, height=800):
        # 이미지 저장
        
    def get_stress_statistics(self):
        # 응력 통계 정보 반환
```

## 사용법

### 기본 사용법

```python
from create_stress_visualization import StressVisualizer

# 응력 시각화 객체 생성
visualizer = StressVisualizer("frd/C000001/2025070218.frd")

# FRD 파일 파싱
if visualizer.parse_frd_file():
    # Von Mises 등응력면 시각화
    fig = visualizer.create_isosurface_visualization(
        stress_component='von_mises',
        isovalues=None,  # 자동 계산
        opacity=0.4,
        colorscale='Viridis'
    )
    
    # 이미지 저장
    visualizer.save_visualization(fig, "output/von_mises.png")
```

### 다양한 응력 성분 시각화

```python
# SXX 응력 성분 시각화
fig_sxx = visualizer.create_isosurface_visualization(
    stress_component='SXX',
    colorscale='RdBu'  # 빨강-파랑 색상 스케일
)

# SYY 응력 성분 시각화
fig_syy = visualizer.create_isosurface_visualization(
    stress_component='SYY',
    colorscale='RdBu'
)

# SZZ 응력 성분 시각화
fig_szz = visualizer.create_isosurface_visualization(
    stress_component='SZZ',
    colorscale='RdBu'
)
```

### 응력 통계 확인

```python
# 응력 통계 정보 출력
stats = visualizer.get_stress_statistics()
for component, stat in stats.items():
    print(f"{component}:")
    for key, value in stat.items():
        print(f"  {key}: {value:.2e} Pa")
```

## 테스트 결과

### 파싱된 데이터
- **총 노드 수**: 891개
- **응력 성분**: 6개 (SXX, SYY, SZZ, SXY, SYZ, SZX)
- **Von Mises 응력**: 자동 계산

### 응력 범위 (테스트 파일 기준)
- **Von Mises**: 7.42×10⁶ ~ 3.22×10¹¹ Pa
- **SXX**: -1.85×10¹¹ ~ 5.33×10⁹ Pa
- **SYY**: -1.85×10¹¹ ~ 5.48×10⁹ Pa
- **SZZ**: -1.84×10¹¹ ~ 4.04×10¹⁰ Pa

## 생성된 이미지

1. **von_mises_isosurface.png**: Von Mises 응력 등응력면
2. **stress_heatmap.png**: 응력 분포 히트맵
3. **sxx_isosurface.png**: SXX 응력 성분 등응력면
4. **comprehensive_stress.png**: 4개 응력 성분 비교 시각화

## 온도분석 로직과의 비교

### 공통점
- **3D 시각화**: Plotly를 사용한 3D 그래프 생성
- **색상 매핑**: 응력/온도 값을 색상으로 표현
- **Volume 렌더링**: 3D 볼륨 데이터 시각화
- **이미지 저장**: Kaleido를 사용한 고해상도 이미지 생성

### 차이점
- **데이터 소스**: 온도분석은 INP 파일, 응력분석은 FRD 파일
- **데이터 구조**: 온도는 단일 값, 응력은 6개 성분 + Von Mises
- **시각화 방식**: 온도는 히트맵 중심, 응력은 등응력면 중심
- **통계 분석**: 응력은 더 복잡한 통계 정보 제공

## 개선 사항

### 1. 성능 최적화
- **메모리 효율성**: 대용량 FRD 파일 처리 시 메모리 사용량 최적화
- **파싱 속도**: 정규표현식 최적화로 파싱 속도 향상

### 2. 시각화 개선
- **인터랙티브 기능**: Dash와 연동하여 웹 기반 인터랙티브 시각화
- **애니메이션**: 시간에 따른 응력 변화 애니메이션
- **단면도**: 2D 단면 시각화 기능 추가

### 3. 분석 기능 확장
- **응력 집중**: 응력 집중 구역 자동 탐지
- **안전성 평가**: 허용 응력 대비 안전율 계산
- **피로 분석**: 반복 하중에 의한 피로 분석

### 4. 사용자 인터페이스
- **웹 대시보드**: Dash를 사용한 웹 기반 대시보드
- **파일 업로드**: 드래그 앤 드롭 파일 업로드
- **설정 패널**: 시각화 옵션 조정 패널

## 의존성

```txt
numpy>=1.23.2
pandas>=2.0.0
plotly>=5.0.0
kaleido>=0.2.1
```

## 설치 및 실행

```bash
# 의존성 설치
pip install numpy pandas plotly kaleido

# 테스트 실행
python test_stress_visualization.py
```

## 주의사항

1. **FRD 파일 형식**: CalculiX의 표준 FRD 파일 형식만 지원
2. **메모리 사용량**: 대용량 파일 처리 시 충분한 메모리 확보 필요
3. **이미지 생성 시간**: 고해상도 이미지 생성 시 시간 소요
4. **브라우저 의존성**: Kaleido가 Chrome 브라우저를 사용하여 이미지 생성

## 라이선스

이 코드는 MIT 라이선스 하에 배포됩니다. 