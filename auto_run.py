import auto_inp
import auto_sensor
import auto_inp_to_frd
import auto_frd_to_vtk
import time
import logging
import os

# 로거 설정
def setup_auto_run_logger():
    """auto_run 전용 로거 설정"""
    log_dir = "log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger('auto_run_logger')
    logger.setLevel(logging.INFO)
    
    # 기존 핸들러 제거 (중복 방지)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 파일 핸들러 설정
    file_handler = logging.FileHandler(os.path.join(log_dir, 'auto_run.log'), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 포맷터 설정 (로그인 로그와 동일한 형식)
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | AUTO_RUN | %(message)s')
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    return logger

if __name__ == '__main__':
    logger = setup_auto_run_logger()
    logger.info("자동화 시스템 시작")
    
    cycle_count = 0
    while True:
        cycle_count += 1
        logger.info(f"자동화 사이클 {cycle_count} 시작")
        
        try:
            logger.info("센서 데이터 수집 시작")
            auto_sensor.auto_sensor_data()
            logger.info("센서 데이터 수집 완료")
            time.sleep(10)
            
            logger.info("INP 파일 생성 시작")
            auto_inp.auto_inp()
            logger.info("INP 파일 생성 완료")
            time.sleep(10)
            
            logger.info("INP to FRD 변환 시작")
            auto_inp_to_frd.convert_all_inp_to_frd()
            logger.info("INP to FRD 변환 완료")
            time.sleep(10)
            
            logger.info("FRD to VTK 변환 시작")
            auto_frd_to_vtk.convert_all_frd_to_vtk()
            logger.info("FRD to VTK 변환 완료")
            
            logger.info(f"자동화 사이클 {cycle_count} 완료 - 20분 대기")
            time.sleep(1200)
            
        except Exception as e:
            logger.error(f"자동화 사이클 {cycle_count} 오류: {e}")
            logger.info("10분 후 재시도")
            time.sleep(600)

