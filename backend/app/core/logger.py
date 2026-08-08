'''
自定义日志模块
使得输出日志更清晰，方便调试

特性：
1. loguru 统一输出（控制台+文件）
2. 通过 InterceptHandler 把所有标准 logging（包括第三方库、
   getLogger(__name__) 的业务日志）统一桥接到 loguru，
   避免业务日志"写了但控制台看不到"。
'''
import sys
import logging
from loguru import logger
from .config_api import settings


class InterceptHandler(logging.Handler):
    """
    将标准库 logging 产生的所有日志转发到 loguru。
    参考 loguru 官方文档的集成方式。
    """

    def emit(self, record: logging.LogRecord) -> None:
        # 获取对应的 loguru 级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 找调用方的帧信息，让 loguru 显示正确的文件/函数/行号
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logger():
    """初始化日志配置：loguru + 拦截标准 logging"""
    # 移除 loguru 默认处理器
    logger.remove()

    # 控制台输出（带彩色格式）
    logger.add(
        sys.stdout,
        level=settings.logging.level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        enqueue=True,
        backtrace=True,
        diagnose=False
    )

    # 文件输出（生产环境开启）
    if settings.env == "prod":
        logger.add(
            "logs/app.log",
            rotation="10 MB",
            retention="7 days",
            level="INFO",
            enqueue=True
        )

    # ========== 拦截标准库 logging 并转发到 loguru ==========
    # 1) 把根 logger 的 handler 替换为 InterceptHandler，
    #    级别设置为 DEBUG（真正的过滤由 loguru 侧控制）
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.DEBUG, force=True)

    # 2) 对已知常用 logger 也设置级别和 handler（双重保险：
    #    避免某些第三方 logger 把 propagate 设为 False 导致到不了根 logger）
    target_loggers = [
        logging.getLogger(),                         # root
        logging.getLogger("uvicorn"),
        logging.getLogger("uvicorn.access"),
        logging.getLogger("uvicorn.error"),
        logging.getLogger("sqlalchemy"),
        logging.getLogger("sqlalchemy.engine"),
        logging.getLogger("services"),
        logging.getLogger("agent"),
        logging.getLogger("api"),
        logging.getLogger("rag"),
        logging.getLogger("core"),
        logging.getLogger("db"),
        logging.getLogger("schemas"),
    ]
    intercept_handler = InterceptHandler()
    for lg in target_loggers:
        # 清理老 handler，避免重复打印
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.addHandler(intercept_handler)
        lg.setLevel(logging.DEBUG)
        # 不传播到 root，避免被 root 再打印一遍
        lg.propagate = False

    logger.info("[Logger] 日志系统初始化完成：标准 logging -> loguru 桥接已启用（level={})".format(settings.logging.level))

    return logger


# 全局日志实例
logger = setup_logger()