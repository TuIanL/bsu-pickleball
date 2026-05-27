"""日志配置 —— 统一的日志格式和级别管理。"""

import logging


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        level=level,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
