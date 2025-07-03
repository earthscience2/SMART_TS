"""
프로젝트 페이지 공통 유틸리티 함수들
"""

def format_scientific_notation(value):
    """과학적 표기법을 ×10ⁿ 형식으로 변환합니다.
    
    예: 1.0e-05 → 1.0×10⁻⁵
    """
    if value == 0:
        return "0"
    
    # 과학적 표기법으로 변환
    exp_str = f"{value:.1e}"
    
    # e 표기법을 × 표기법으로 변환
    if 'e' in exp_str:
        mantissa, exponent = exp_str.split('e')
        exp_num = int(exponent)
        
        # 상첨자 숫자 변환
        superscript_map = {
            '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', 
            '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹', 
            '-': '⁻'
        }
        
        # 지수를 상첨자로 변환
        exp_super = ''.join(superscript_map.get(c, c) for c in str(exp_num))
        
        return f"{mantissa}×10{exp_super}"
    
    return exp_str

def create_probability_curve_figure():
    """로지스틱 근사식을 이용한 균열발생확률 곡선 그래프를 생성합니다."""
    import numpy as np
    import plotly.graph_objects as go
    
    # TCI 값 범위 (0.1 ~ 1.0)
    tci_values = np.linspace(0.1, 1.0, 300)
    
    # 수정된 로지스틱 근사식: 0.4에서 100%, 0.5에서 40%, 2.0에서 0%
    # P(x) = 100 / (1 + e^(54(x-0.4925))) (오버플로우 방지)
    exponents = 54 * (tci_values - 0.4925)
    # 오버플로우 방지: 큰 값은 클리핑
    exponents = np.clip(exponents, -700, 700)
    probabilities = 100 / (1 + np.exp(exponents))
    
    fig = go.Figure()
    
    # 메인 곡선
    fig.add_trace(go.Scatter(
        x=tci_values,
        y=probabilities,
        mode='lines',
        name='균열발생확률',
        line=dict(color='#3b82f6', width=3),
        hovertemplate='TCI: %{x:.2f}<br>확률: %{y:.1f}%<extra></extra>'
    ))
    
    # 중요한 기준선들 추가
    # TCI = 0.5 기준선 (40% 확률)
    fig.add_vline(x=0.5, line_dash="dash", line_color="red", line_width=2, 
                  annotation_text="TCI = 0.5 (40%)", annotation_position="top left")
    
    # TCI = 0.4 기준선 (100% 확률)
    fig.add_vline(x=0.4, line_dash="dash", line_color="orange", line_width=2,
                  annotation_text="TCI = 0.4 (100%)", annotation_position="top right")
    
    # TCI = 1.0 기준선 (낮은 확률)  
    fig.add_vline(x=1.0, line_dash="dash", line_color="green", line_width=2,
                  annotation_text="TCI = 1.0 (3%)", annotation_position="bottom right")
    
    # 안전/위험 영역 표시
    fig.add_vrect(x0=0.1, x1=0.5, fillcolor="rgba(239, 68, 68, 0.1)", 
                  annotation_text="위험 영역", annotation_position="top left",
                  annotation=dict(font_size=12, font_color="red"))
    
    fig.add_vrect(x0=0.5, x1=1.0, fillcolor="rgba(34, 197, 94, 0.1)",
                  annotation_text="안전 영역", annotation_position="top right",
                  annotation=dict(font_size=12, font_color="green"))
    
    # 그래프 스타일링
    fig.update_layout(
        title={
            'text': "온도균열지수(TCI)와 균열발생확률의 관계",
            'x': 0.5,
            'font': {'size': 18, 'color': '#1f2937'}
        },
        xaxis=dict(
            title="온도균열지수 (TCI)",
            gridcolor='#f3f4f6',
            showgrid=True,
            range=[0.1, 1.0],
            dtick=0.1
        ),
        yaxis=dict(
            title="균열발생확률 (%)",
            gridcolor='#f3f4f6',
            showgrid=True,
            range=[0, 100],
            dtick=10
        ),
        plot_bgcolor='white',
        paper_bgcolor='white',
        showlegend=False,
        margin=dict(l=60, r=60, t=80, b=60),
        font=dict(family="Arial, sans-serif", size=12, color="#374151")
    )
    
    return fig

def parse_material_info_from_inp(lines):
    """INP 파일 라인 리스트에서 물성치 정보를 추출하여 문자열로 반환합니다.

    반환 형식 예시: "탄성계수: 30000MPa, 포아송비: 0.200, 밀도: 2500kg/m³, 열팽창: 1.0×10⁻⁵/°C"
    해당 값이 없으면 항목을 건너뛴다. 아무 항목도 없으면 "물성치 정보 없음" 반환.
    """
    elastic_modulus = None  # MPa
    poisson_ratio = None
    density = None          # kg/m³
    expansion = None        # 1/°C

    section = None  # 현재 파싱 중인 섹션 이름
    for raw in lines:
        line = raw.strip()

        # 섹션 식별
        if line.startswith("*"):
            u = line.upper()
            if u.startswith("*ELASTIC"):
                section = "elastic"
            elif u.startswith("*DENSITY"):
                section = "density"
            elif u.startswith("*EXPANSION"):
                section = "expansion"
            else:
                section = None
            continue

        if not section or not line:
            continue

        tokens = [tok.strip() for tok in line.split(',') if tok.strip()]
        if not tokens:
            continue

        try:
            if section == "elastic":
                elastic_modulus = float(tokens[0])
                if len(tokens) >= 2:
                    poisson_ratio = float(tokens[1])
                # Pa → GPa 변환
                elastic_modulus /= 1e9
                section = None  # 한 줄만 사용

            elif section == "density":
                density = float(tokens[0])
                # 단위 자동 변환
                if density < 1e-3:      # tonne/mm^3 (예: 2.40e-9)
                    density *= 1e12     # 1 tonne/mm³ = 1e12 kg/m³
                elif density < 10:      # g/cm³ (예: 2.4)
                    density *= 1000     # g/cm³ → kg/m³
                section = None

            elif section == "expansion":
                expansion = float(tokens[0])
                section = None
        except ValueError:
            # 숫자 파싱 실패 시 해당 항목 무시
            continue

    parts = []
    if elastic_modulus is not None:
        parts.append(f"탄성계수: {elastic_modulus:.1f}GPa")
    if poisson_ratio is not None:
        parts.append(f"포아송비: {poisson_ratio:.1f}")
    if density is not None:
        parts.append(f"밀도: {density:.0f}kg/m³")
    if expansion is not None:
        parts.append(f"열팽창: {expansion:.1f}×10⁻⁵/°C")

    return ", ".join(parts) if parts else "물성치 정보 없음" 