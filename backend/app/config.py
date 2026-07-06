from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，从环境变量加载"""

    LOG_LEVEL: str = "INFO"
    ENCRYPTION_KEY: str = ""
    # v2.6.1 fix-backup-data-integrity Task 3a: 改绝对路径，避免依赖 cwd
    # 容器内 WORKDIR=/app，所以 /app/data/data.db 即 volume 挂载的 data 目录
    # monolith 模式可用 .env DB_PATH=./data/dev.db 覆盖（本地开发机不一定有 /app 目录）
    DB_PATH: str = "/app/data/data.db"
    BACKEND_PORT: int = 8000

    # 备份配置（v2.2）
    BACKUP_DIR: str = "/data/backups"  # Docker volume 挂载的备份文件目录
    BACKUP_KEEP: int = 5  # 每设备保留总份数（含锁定），锁定优先保留不被轮转（v2.3.1 patch 改）

    # 默认设备配置（V1.0 单设备）
    DEVICE_HOST: str = "192.168.100.100"
    DEVICE_PORT: int = 830
    DEVICE_USERNAME: str = "python"
    DEVICE_PASSWORD: str = ""

    # 资产陈旧阈值（v2.6.1 fix-asset-stale-status）
    # 超过阈值的 online 资产视为"陈旧"——dashboard 单独计 stale，启动时 data 容器主动降级
    # ASSET_STALE_HOURS 支持小数（如 0.01 = 36 秒）便于调试
    ASSET_STALE_HOURS: float = 1.0
    # False = 关闭降级 + dashboard 不过滤（兼容历史数据场景）
    ASSET_STALE_ENABLED: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
