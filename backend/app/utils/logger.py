import logging
import os
import sys


def setup_logging(log_level: str = "INFO", log_file: str = "./logs/app.log"):
    """配置 Python logging，双输出到 stdout 和文件"""
    # 确保日志目录存在
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)

    # 根 logger 配置
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除已有 handler（防止重复添加）
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)

    # 文件 handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 应用 logger
    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)

    # ncclient logger 设为 WARNING（减少噪音）
    logging.getLogger("ncclient").setLevel(logging.WARNING)
    # paramiko logger 设为 WARNING
    logging.getLogger("paramiko").setLevel(logging.WARNING)

    app_logger.info(f"日志系统初始化完成, 级别: {log_level.upper()}")
