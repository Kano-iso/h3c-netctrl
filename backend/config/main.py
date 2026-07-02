"""config 容器入口（v241-container-split）

职责：设备配置中心（NETCONF/SSH 配置下发 + 多命令终端 + 批量操作）
数据库：config.db（当前无持久化表，未来加 VPC 元数据）
端口：8000（内部），外部映射 8002
"""
import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware import InternalTokenMiddleware

# 确保数据目录存在
os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
os.makedirs("./logs", exist_ok=True)

from app.database import Base, engine
from app.routers import interface, vlan, execute, batch
from app.utils.logger import setup_logging

setup_logging(log_level=settings.LOG_LEVEL, log_file="./logs/config.log")

SERVICE_NAME = "config"
logger = logging.getLogger("app")
logger.info(f"service_name={SERVICE_NAME} (设备配置中心)")

app = FastAPI(
    title="H3C NetCtrl — config",
    description="设备配置中心：NETCONF/SSH 配置下发 + 终端 + 批量操作",
    version="2.4.1",
)

# CORS（开发环境）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内部 API 鉴权中间件
app.add_middleware(InternalTokenMiddleware)

# 注册路由
app.include_router(interface.router, prefix="/api")
app.include_router(vlan.router, prefix="/api")
app.include_router(execute.router, prefix="/api")
app.include_router(batch.router, prefix="/api")


@app.on_event("startup")
def on_startup():
    """启动时执行数据库迁移（config 容器可能无表，跳过迁移错误）"""
    try:
        from alembic.config import Config
        from alembic import command

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{settings.DB_PATH}")
        command.upgrade(alembic_cfg, "head")
        logging.getLogger("app").info("config 数据库迁移完成")
    except Exception as e:
        logging.getLogger("app").warning(f"config 数据库迁移跳过: {e}")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "config"}
