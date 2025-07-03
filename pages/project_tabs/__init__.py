"""
프로젝트 페이지 탭 모듈들

각 탭별로 분리된 컴포넌트와 콜백을 포함합니다.
"""

from .tab_3d import create_3d_tab, register_3d_callbacks
from .tab_section import create_section_tab, register_section_callbacks
from .tab_temp import create_temp_tab, register_temp_callbacks
from .tab_analysis import create_analysis_tab, register_analysis_callbacks
from .tab_tci import create_tci_tab, register_tci_callbacks

__all__ = [
    'create_3d_tab', 'register_3d_callbacks',
    'create_section_tab', 'register_section_callbacks', 
    'create_temp_tab', 'register_temp_callbacks',
    'create_analysis_tab', 'register_analysis_callbacks',
    'create_tci_tab', 'register_tci_callbacks'
] 