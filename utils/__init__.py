from flask import request

def get_user_info():
    """현재 로그인된 사용자 정보를 반환합니다.
    
    Returns:
        dict: {
            'user_id': str,
            'user_grade': str,
            'is_logged_in': bool
        }
    """
    user_id = request.cookies.get("login_user")
    user_grade = request.cookies.get("user_grade")
    
    if not user_id:
        return {
            'user_id': None,
            'user_grade': None,
            'is_logged_in': False
        }
    
    return {
        'user_id': user_id,
        'user_grade': user_grade,
        'is_logged_in': True
    } 