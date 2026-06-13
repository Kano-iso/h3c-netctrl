from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，从环境变量加载"""

    LOG_LEVEL: str = "INFO"
    ENCRYPTION_KEY: str = ""
    DB_PATH: str = "./data/dev.db"
    BACKEND_PORT: int = 8000

    # 默认设备配置（V1.0 单设备）
    DEVICE_HOST: str = "192.168.100.100"
    DEVICE_PORT: int = 830
    DEVICE_USERNAME: str = "python"
    DEVICE_PASSWORD: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
