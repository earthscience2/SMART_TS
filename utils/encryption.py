#!/usr/bin/env python3
# utils/encryption.py
"""URL 암호화/복호화 유틸리티

프로젝트 키를 URL에서 노출되지 않도록 암호화하여 사용합니다.
"""

import base64
import hashlib
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 암호화 키 생성 (실제 운영환경에서는 환경변수나 설정 파일에서 관리)
SECRET_KEY = b'your-secret-key-here-32-bytes-long!!'
SALT = b'your-salt-here-16-bytes!!'

def _get_encryption_key():
    """암호화 키를 생성합니다."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(SECRET_KEY))
    return key

def encrypt_project_key(project_pk: str) -> str:
    """프로젝트 키를 암호화합니다."""
    if not project_pk:
        return ""
    
    try:
        fernet = Fernet(_get_encryption_key())
        encrypted_data = fernet.encrypt(project_pk.encode())
        # URL 안전한 base64 인코딩
        return base64.urlsafe_b64encode(encrypted_data).decode()
    except Exception as e:
        print(f"암호화 오류: {e}")
        return project_pk  # 암호화 실패 시 원본 반환

def decrypt_project_key(encrypted_pk: str) -> str:
    """암호화된 프로젝트 키를 복호화합니다."""
    if not encrypted_pk:
        return ""
    
    try:
        fernet = Fernet(_get_encryption_key())
        # URL 안전한 base64 디코딩
        encrypted_data = base64.urlsafe_b64decode(encrypted_pk.encode())
        decrypted_data = fernet.decrypt(encrypted_data)
        return decrypted_data.decode()
    except Exception as e:
        print(f"복호화 오류: {e}")
        return encrypted_pk  # 복호화 실패 시 원본 반환

def create_project_url(base_path: str, project_pk: str) -> str:
    """프로젝트 URL을 생성합니다."""
    if not project_pk:
        return base_path
    
    encrypted_pk = encrypt_project_key(project_pk)
    return f"{base_path}?p={encrypted_pk}"

def parse_project_key_from_url(search: str) -> str:
    """URL에서 프로젝트 키를 추출합니다."""
    if not search:
        return ""
    
    try:
        from urllib.parse import parse_qs
        params = parse_qs(search.lstrip('?'))
        
        # 기존 'page' 파라미터 지원 (하위 호환성)
        if 'page' in params:
            return params.get('page', [None])[0] or ""
        
        # 새로운 'p' 파라미터 (암호화된 키)
        if 'p' in params:
            encrypted_pk = params.get('p', [None])[0]
            if encrypted_pk:
                return decrypt_project_key(encrypted_pk)
        
        return ""
    except Exception as e:
        print(f"URL 파싱 오류: {e}")
        return "" 