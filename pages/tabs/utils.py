#!/usr/bin/env python3
"""공통 유틸리티 함수들"""

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
                if density < 1:  # tonne/mm³ 또는 g/cm³로 추정
                    if density < 0.01:  # tonne/mm³
                        density *= 1e12  # tonne/mm³ → kg/m³
                    else:  # g/cm³
                        density *= 1000  # g/cm³ → kg/m³
                section = None  # 한 줄만 사용

            elif section == "expansion":
                expansion = float(tokens[0])
                section = None  # 한 줄만 사용

        except (ValueError, IndexError):
            continue

    # 결과 문자열 생성
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
    
    if info_parts:
        return ", ".join(info_parts)
    else:
        return "물성치 정보 없음" 