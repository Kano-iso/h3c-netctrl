"""ctrl 容器入口（v241-container-split）

职责：设备身份中心（device CRUD + 操作日志 + 仪表盘聚合）
数据库：ctrl.db → Device + Log
端口：8000（内部），外部映射 8001
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
from app.routers import device, log, dashboard
from app.routers import ztp
from app.routers import ctrl_internal
from app.utils.logger import setup_logging

setup_logging(log_level=settings.LOG_LEVEL, log_file="./logs/ctrl.log")

SERVICE_NAME = "ctrl"
logger = logging.getLogger("app")
logger.info(f"service_name={SERVICE_NAME} (设备身份中心)")

app = FastAPI(
    title="H3C NetCtrl — ctrl",
    description="设备身份中心：设备 CRUD + 操作日志 + 仪表盘聚合",
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
app.include_router(device.router, prefix="/api")
app.include_router(log.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(ztp.router)
# 内部端点
app.include_router(ctrl_internal.router)


@app.on_event("startup")
def on_startup():
    """启动时执行数据库迁移"""
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{settings.DB_PATH}")
    command.upgrade(alembic_cfg, "head")
    logging.getLogger("app").info("ctrl 数据库迁移完成")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ctrl"}
