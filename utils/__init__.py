from flask import request

def get_user_info():
    """현재 로그인된 사용자 정보를 반환합니다.
    
    Returns:
        dict: {
            'user_id': str,
            'user_grade': str,
            'user_its': int,
            'is_logged_in': bool
        }
    """
    user_id = request.cookies.get("login_user")
    user_grade = request.cookies.get("user_grade")
    user_its = request.cookies.get("user_its", "1")
    
    if not user_id:
        return {
            'user_id': None,
            'user_grade': None,
            'user_its': 1,
            'is_logged_in': False
        }
    
    return {
        'user_id': user_id,
        'user_grade': user_grade,
        'user_its': int(user_its) if user_its else 1,
        'is_logged_in': True
    } 