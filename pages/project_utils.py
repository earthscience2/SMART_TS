#!/usr/bin/env python3
"""프로젝트 페이지 공통 유틸리티 함수들"""

import numpy as np
import plotly.graph_objects as go
from datetime import datetime

def format_scientific_notation(value):
    """과학적 표기법을 ×10ⁿ 형식으로 변환합니다."""
    if value == 0:
        return "0"
    
    exp_str = f"{value:.1e}"
    if 'e' in exp_str:
        mantissa, exponent = exp_str.split('e')
        exp_num = int(exponent)
        
        superscript_map = {
            '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', 
            '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹', 
            '-': '⁻'
        }
        
        exp_super = ''.join(superscript_map.get(c, c) for c in str(exp_num))
        return f"{mantissa}×10{exp_super}"
    
    return exp_str

def parse_material_info_from_inp(lines):
    """INP 파일에서 물성치 정보를 추출합니다."""
    elastic_modulus = None
    poisson_ratio = None
    density = None
    expansion = None

    section = None
    for raw in lines:
        line = raw.strip()

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
                elastic_modulus /= 1e9
                section = None

            elif section == "density":
                density = float(tokens[0])
                if density < 1:
                    if density < 0.01:
                        density *= 1e12
                    else:
                        density *= 1000
                section = None

            elif section == "expansion":
                expansion = float(tokens[0])
                section = None

        except (ValueError, IndexError):
            continue

    info_parts = []
    
    if elastic_modulus is not None:
        info_parts.append(f"탄성계수: {elastic_modulus:.0f}GPa")
    
    if poisson_ratio is not None:
        info_parts.append(f"포아송비: {poisson_ratio:.3f}")
    
    if density is not None:
        info_parts.append(f"밀도: {density:.0f}kg/m³")
    
    if expansion is not None:
        formatted_expansion = format_scientific_notation(expansion)
        info_parts.append(f"열팽창: {formatted_expansion}/°C")
    
    return ", ".join(info_parts) if info_parts else "물성치 정보 없음"

def create_probability_curve_figure():
    """TCI 확률 곡선 그래프를 생성합니다."""
    tci_values = np.linspace(0.1, 3.0, 300)
    probabilities = 100 / (1 + np.exp(6 * (tci_values - 0.6)))
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=tci_values,
        y=probabilities,
        mode='lines',
        name='균열발생확률',
        line=dict(color='#3b82f6', width=3),
        hovertemplate='TCI: %{x:.2f}<br>확률: %{y:.1f}%<extra></extra>'
    ))
    
    # 기준선들
    fig.add_vline(x=1.0, line_dash="dash", line_color="red", line_width=2, 
                  annotation_text="TCI = 1.0 (40%)", annotation_position="top left")
    fig.add_vline(x=0.4, line_dash="dash", line_color="orange", line_width=2,
                  annotation_text="TCI = 0.4 (100%)", annotation_position="top right")
    fig.add_vline(x=2.0, line_dash="dash", line_color="green", line_width=2,
                  annotation_text="TCI = 2.0 (0%)", annotation_position="bottom right")
    
    # 영역 표시
    fig.add_vrect(x0=0.1, x1=1.0, fillcolor="rgba(239, 68, 68, 0.1)", 
                  annotation_text="위험 영역", annotation_position="top left",
                  annotation=dict(font_size=12, font_color="red"))
    
    fig.add_vrect(x0=1.0, x1=3.0, fillcolor="rgba(34, 197, 94, 0.1)",
                  annotation_text="안전 영역", annotation_position="top right",
                  annotation=dict(font_size=12, font_color="green"))
    
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
            range=[0.1, 3.0],
            dtick=0.2
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

def format_pour_date(con_t):
    """타설 날짜를 포맷팅합니다."""
    if not con_t or con_t in ["", "N/A", None]:
        return "N/A"
    
    try:
        # datetime 객체인 경우
        if hasattr(con_t, 'strftime'):
            dt = con_t
        # 문자열인 경우 파싱
        elif isinstance(con_t, str):
            if 'T' in con_t:
                # ISO 형식 (2024-01-01T10:00 또는 2024-01-01T10:00:00)
                dt = datetime.fromisoformat(con_t.replace('Z', ''))
            else:
                # 다른 형식 시도
                dt = datetime.strptime(str(con_t), '%Y-%m-%d %H:%M:%S')
        else:
            dt = None
        
        if dt:
            return dt.strftime('%y.%m.%d')
    except Exception:
        pass
    
    return "N/A"

def calculate_elapsed_days(pour_date):
    """경과일을 계산합니다."""
    if pour_date == "N/A":
        return "N/A"
    
    try:
        pour_dt = datetime.strptime(pour_date, '%y.%m.%d')
        now = datetime.now()
        elapsed = (now - pour_dt).days
        return f"{elapsed}일"
    except Exception:
        return "N/A" 