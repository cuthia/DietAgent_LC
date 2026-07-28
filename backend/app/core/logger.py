'''
自定义日志模块
使得输出日志更清晰，方便调试
'''
import sys
from loguru import logger
from .config_api import settings


def setup_logger():
    """初始化日志配置"""
    # 移除默认处理器
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stdout,
        level=settings.logging.level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        enqueue=True
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

    return logger


# 全局日志实例
logger = setup_logger()