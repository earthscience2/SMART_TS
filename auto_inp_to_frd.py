import subprocess
import shutil
import os
import logging
logger = logging.getLogger(__name__)

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

    # 1) CCX 실행 (.frd, .dat, .cvg, .sta 생성)
    subprocess.run(['ccx', inp_path], cwd=work_dir, check=True)
    
    # 2) 대상 디렉토리 생성
    frd_dir = os.path.join('frd', concrete_pk)
    dat_dir = os.path.join('dat', concrete_pk)
    os.makedirs(frd_dir, exist_ok=True)
    os.makedirs(dat_dir, exist_ok=True)

    # 3) .frd, .dat 이동
    frd_src = os.path.join(work_dir, f"{base}.frd")
    dat_src = os.path.join(work_dir, f"{base}.dat")
    if os.path.exists(frd_src):
        shutil.move(frd_src, os.path.join(frd_dir, f"{base}.frd"))
    if os.path.exists(dat_src):
        shutil.move(dat_src, os.path.join(dat_dir, f"{base}.dat"))

    # 4) .cvg, .sta 파일 삭제
    for ext in ('.cvg', '.sta'):
        p = os.path.join(work_dir, f"{base}{ext}")
        if os.path.exists(p):
            os.remove(p)

import subprocess
import shutil
import os

def convert_all_inp_to_frd():
    """
    inp/ 하위 모든 .inp 파일을 찾아서:
      1) ccx 로 실행
      2) frd/{concrete_pk}/ 에 .frd
         dat/{concrete_pk}/ 에 .dat
      3) .cvg, .sta 파일 삭제
    """
    for root, dirs, files in os.walk('inp'):
        for fname in files:
            if not fname.endswith('.inp'):
                continue

            inp_path    = os.path.join(root, fname)
            # root 예: inp/C000001
            concrete_pk = os.path.basename(root)
            base        = os.path.splitext(fname)[0]

            # 1) CCX 실행
            subprocess.run(['ccx', inp_path], cwd=root, check=True)

            # 2) 대상 디렉토리 생성
            frd_dir = os.path.join('frd', concrete_pk)
            dat_dir = os.path.join('dat', concrete_pk)
            os.makedirs(frd_dir, exist_ok=True)
            os.makedirs(dat_dir, exist_ok=True)

            # 3) .frd, .dat 이동
            frd_src = os.path.join(root, f"{base}.frd")
            dat_src = os.path.join(root, f"{base}.dat")
            if os.path.exists(frd_src):
                shutil.move(frd_src, os.path.join(frd_dir, f"{base}.frd"))
            if os.path.exists(dat_src):
                shutil.move(dat_src, os.path.join(dat_dir, f"{base}.dat"))

            # 4) .cvg, .sta 파일 삭제
            for ext in ('.cvg', '.sta'):
                p = os.path.join(root, f"{base}{ext}")
                if os.path.exists(p):
                    os.remove(p)

            logger.info(f"[convert_all_inp_to_frd] {concrete_pk}/{base}.inp → frd/dat 변환 완료 및 .cvg/.sta 삭제")

# 스크립트 맨 아래나 auto_inp() 호출 직후에 추가:
if __name__ == "__main__":
    convert_all_inp_to_frd()
