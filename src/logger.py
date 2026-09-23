"""Módulo de Logging Estruturado Dual para Job Copilot.

- StreamHandler: Saída concisa no terminal (INFO).
- RotatingFileHandler: Saída detalhada em arquivo rotativo de 5MB (DEBUG).
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "job_copilot.log"


def setup_logger(name: str = "job_copilot") -> logging.Logger:
    """Configura e retorna uma instância do logger com manipuladores duais."""
    custom_logger = logging.getLogger(name)

    if custom_logger.handlers:
        return custom_logger

    custom_logger.setLevel(logging.DEBUG)

    # 1. Console Handler (INFO)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)

    # 2. Rotating File Handler (DEBUG - 5MB x 5 backups)
    file_handler = RotatingFileHandler(
        filename=LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    custom_logger.addHandler(console_handler)
    custom_logger.addHandler(file_handler)

    return custom_logger


logger = setup_logger()
