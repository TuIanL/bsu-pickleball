"""
日志配置 —— 统一的日志格式和级别管理。

"日志"就是程序运行时的文字记录（info / warning / error 等不同级别），
方便开发或运维排查问题。本文件把日志的格式和获取方式统一起来，
避免各个模块各写一套、五花八门。
"""

import logging


# 配置全局日志：设置输出格式和最低显示级别
def configure_logging(level: int = logging.INFO) -> None:
    # format 里各占位符含义：
    #   %(asctime)s   时间
    #   %(levelname)s 日志级别（INFO / WARNING / ERROR ...）
    #   %(name)s      产生这条日志的模块名
    #   %(message)s   日志内容本身
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        level=level,
    )


# 获取一个带名字的日志记录器（logger）；各模块用它来写日志，名字用于区分来源
def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
