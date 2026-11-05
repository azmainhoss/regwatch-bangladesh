import logging
import sys
from typing import Any, Dict


def setup_logging(debug: bool = True) -> logging.Logger:
    log_level = logging.DEBUG if debug else logging.INFO
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(log_level)

    logger = logging.getLogger("regwatch")
    logger.setLevel(log_level)
    
    # Avoid duplicate handlers if reloaded
    if not logger.handlers:
        logger.addHandler(handler)

    return logger


logger = setup_logging()
