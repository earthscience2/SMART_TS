"""간단한 로깅 유틸리티.

프로젝트 전역에서 `from logger import Logger as log` 형식으로 불러 사용한다.
내부적으로 Python 내장 logging 모듈을 래핑해 동일한 인터페이스를 제공한다.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# --- 로깅 기본 설정 ---------------------------------------------------------
LOG_DIR = Path("log")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# 회전 로그 핸들러(5 MB × 3개 보관)
_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
_handler.setFormatter(_formatter)

logging.basicConfig(level=logging.INFO, handlers=[_handler, logging.StreamHandler()])


class Logger:  # pylint: disable=too-few-public-methods
    """프로젝트 공용 Logger 래퍼.

    사용 예::
        from logger import Logger as log
        log.info("Hello")
        log.error("Error message")
    """

    @staticmethod
    def debug(msg: str, *args, **kwargs):
        logging.debug(msg, *args, **kwargs)

    @staticmethod
    def info(msg: str, *args, **kwargs):
        logging.info(msg, *args, **kwargs)

    @staticmethod
    def warning(msg: str, *args, **kwargs):
        logging.warning(msg, *args, **kwargs)

    @staticmethod
    def error(msg: str, *args, **kwargs):
        logging.error(msg, *args, **kwargs)

    @staticmethod
    def critical(msg: str, *args, **kwargs):
        logging.critical(msg, *args, **kwargs) 