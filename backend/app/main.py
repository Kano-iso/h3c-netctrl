import os
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# 确保数据目录存在
os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
os.makedirs("./logs", exist_ok=True)

from app.database import Base, engine
from app.routers import device, vlan, log, dashboard, asset, execute, batch, interface, backup
from app.routers import ctrl_internal, data_internal
from app.utils.logger import setup_logging

# 初始化日志系统
setup_logging(log_level=settings.LOG_LEVEL, log_file="./logs/app.log")

# 未来容器解耦预留（v2.1.x patch，未实际拆）
# 当前 monolith 单进程；v2.3 拆 asset / v3.0 加 sdn / 未来 monitor
# 详见 VERSION-ROADMAP.md
SERVICE_NAME = os.getenv("SERVICE_NAME", "core")
logger = logging.getLogger("app")
logger.info(f"service_name={SERVICE_NAME} (future split: core/asset/sdn/monitor)")

app = FastAPI(
    title="H3C NetCtrl",
    description="基于 NETCONF 的 H3C 交换机轻量网控平台",
    version="2.0.0",
)

# CORS 配置（开发环境允许前端访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(device.router, prefix="/api")
app.include_router(vlan.router, prefix="/api")
app.include_router(log.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(asset.router, prefix="/api")
app.include_router(execute.router, prefix="/api")
app.include_router(batch.router, prefix="/api")
app.include_router(interface.router, prefix="/api")
app.include_router(backup.router, prefix="/api")

# 内部端点（v241-container-split，测试用，monolith 模式也注册）
app.include_router(ctrl_internal.router)
app.include_router(data_internal.router)


@app.on_event("startup")
def on_startup():
    """应用启动时通过 Alembic 执行数据库迁移"""
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{settings.DB_PATH}")
    command.upgrade(alembic_cfg, "head")

    logging.getLogger("app").info("数据库迁移完成")


@app.get("/health")
def health_check():
    return {"status": "ok"}
