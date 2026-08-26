"""独立 analysis-worker 进程入口。

API 进程可以使用 uvicorn reload；本入口只负责初始化任务控制面、恢复失联任务
并持有 Worker runtime，因此不会随 Web 进程热重载退出。
"""

from __future__ import annotations

import logging
import signal
import time

from app.core.logging import configure_logging
from app.database import init_db
from app.services.mock_analysis import recover_zombie_jobs, start_analysis_worker, stop_analysis_worker

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    stopping = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    init_db()
    recover_zombie_jobs()
    start_analysis_worker(force=True)
    logger.info("analysis-worker started")
    try:
        while not stopping:
            time.sleep(0.5)
    finally:
        logger.info("analysis-worker stopping")
        stop_analysis_worker()


if __name__ == "__main__":
    main()
