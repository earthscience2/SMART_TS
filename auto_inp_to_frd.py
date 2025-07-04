import subprocess
import shutil
import os
import logging

# 로거 설정
def setup_auto_inp_to_frd_logger():
    """auto_inp_to_frd 전용 로거 설정"""
    log_dir = "log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger('auto_inp_to_frd_logger')
    logger.setLevel(logging.INFO)
    
    # 기존 핸들러 제거 (중복 방지)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 파일 핸들러 설정
    file_handler = logging.FileHandler(os.path.join(log_dir, 'auto_inp_to_frd.log'), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 포맷터 설정 (로그인 로그와 동일한 형식)
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | AUTO_INP_TO_FRD | %(message)s')
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    return logger

logger = setup_auto_inp_to_frd_logger()

# 로그 기록할 이벤트만 정의
def log_frd_conversion_success(concrete_pk, base):
    """FRD 변환 성공 시에만 로그 기록"""
    logger.info(f"{concrete_pk}/{base}.inp → frd/dat 변환 완료")

def log_error(message):
    """오류 로그 기록"""
    logger.error(message)

def inp_to_frd(concrete_pk, inp_path):
    """
    ccx 로 inp 를 실행한 뒤,
      - frd 는 frd/{concrete_pk}/ 아래로,
      - dat 는 dat/{concrete_pk}/ 아래로
    옮기고,
      - .cvg, .sta 파일은 삭제
    """
    base = os.path.splitext(os.path.basename(inp_path))[0]
    work_dir = os.path.dirname(inp_path)

    # 대상 디렉토리 생성
    frd_dir = os.path.join('frd', concrete_pk)
    dat_dir = os.path.join('dat', concrete_pk)
    os.makedirs(frd_dir, exist_ok=True)
    os.makedirs(dat_dir, exist_ok=True)

    # 이미 파일이 존재하는지 확인
    frd_target = os.path.join(frd_dir, f"{base}.frd")
    dat_target = os.path.join(dat_dir, f"{base}.dat")
    
    if os.path.exists(frd_target) and os.path.exists(dat_target):
        return

    try:
        # 1) CCX 실행 (.frd, .dat, .cvg, .sta 생성) - 파일명만 사용, 확장자 제외
        subprocess.run(['ccx', base], cwd=work_dir, check=True)
        
        # 3) .frd, .dat 이동
        frd_src = os.path.join(work_dir, f"{base}.frd")
        dat_src = os.path.join(work_dir, f"{base}.dat")
        if os.path.exists(frd_src):
            shutil.move(frd_src, frd_target)
        if os.path.exists(dat_src):
            shutil.move(dat_src, dat_target)

        # 4) .cvg, .sta 파일 삭제
        for ext in ('.cvg', '.sta'):
            p = os.path.join(work_dir, f"{base}{ext}")
            if os.path.exists(p):
                os.remove(p)
                
        # FRD 변환 성공 시에만 로그 기록
        log_frd_conversion_success(concrete_pk, base)
        
    except Exception as e:
        log_error(f"{concrete_pk}/{base} INP to FRD 변환 오류: {e}")

def convert_all_inp_to_frd():
    """
    inp/ 하위 모든 .inp 파일을 찾아서:
      1) ccx 로 실행
      2) frd/{concrete_pk}/ 에 .frd
         dat/{concrete_pk}/ 에 .dat
      3) .cvg, .sta 파일 삭제
    """
    total_files = 0
    converted_files = 0
    skipped_files = 0
    error_files = 0
    
    for root, dirs, files in os.walk('inp'):
        for fname in files:
            if not fname.endswith('.inp'):
                continue

            total_files += 1
            inp_path = os.path.join(root, fname)
            # root 예: inp/C000001
            concrete_pk = os.path.basename(root)
            base = os.path.splitext(fname)[0]

            # 대상 디렉토리 생성
            frd_dir = os.path.join('frd', concrete_pk)
            dat_dir = os.path.join('dat', concrete_pk)
            os.makedirs(frd_dir, exist_ok=True)
            os.makedirs(dat_dir, exist_ok=True)

            # 이미 파일이 존재하는지 확인
            frd_target = os.path.join(frd_dir, f"{base}.frd")
            dat_target = os.path.join(dat_dir, f"{base}.dat")
            
            if os.path.exists(frd_target) and os.path.exists(dat_target):
                skipped_files += 1
                continue

            try:
                # 1) CCX 실행 (파일명만 사용, 확장자 제외)
                subprocess.run(['ccx', base], cwd=root, check=True)

                # 3) .frd, .dat 이동
                frd_src = os.path.join(root, f"{base}.frd")
                dat_src = os.path.join(root, f"{base}.dat")
                if os.path.exists(frd_src):
                    shutil.move(frd_src, frd_target)
                if os.path.exists(dat_src):
                    shutil.move(dat_src, dat_target)

                # 4) .cvg, .sta 파일 삭제
                for ext in ('.cvg', '.sta'):
                    p = os.path.join(root, f"{base}{ext}")
                    if os.path.exists(p):
                        os.remove(p)

                # FRD 변환 성공 시에만 로그 기록
                log_frd_conversion_success(concrete_pk, base)
                converted_files += 1
                
            except Exception as e:
                log_error(f"{concrete_pk}/{base} INP to FRD 변환 오류: {e}")
                error_files += 1

# 스크립트 맨 아래나 auto_inp() 호출 직후에 추가:
if __name__ == "__main__":
    convert_all_inp_to_frd()
