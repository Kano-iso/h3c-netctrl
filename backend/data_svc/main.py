"""data 容器入口（v241-container-split）

职责：数据采集与存储中心（CMDB 资产 + 配置备份 + 异步任务管理）
数据库：data.db → Asset + Backup + Task
端口：8000（内部），外部映射 8003
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
from app.routers import asset, backup
from app.routers import data_internal
from app.utils.logger import setup_logging

setup_logging(log_level=settings.LOG_LEVEL, log_file="./logs/data.log")

SERVICE_NAME = "data"
logger = logging.getLogger("app")
logger.info(f"service_name={SERVICE_NAME} (数据采集与存储中心)")

app = FastAPI(
    title="H3C NetCtrl — data",
    description="数据采集与存储中心：CMDB 资产 + 配置备份 + 异步任务",
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
app.include_router(asset.router, prefix="/api")
app.include_router(backup.router, prefix="/api")
# 内部端点
app.include_router(data_internal.router)


@app.on_event("startup")
def on_startup():
    """启动时执行数据库迁移 + 陈旧资产降级（v2.6.1 fix-asset-stale-status）"""
    from alembic.config import Config
    from alembic import command
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{settings.DB_PATH}")
    command.upgrade(alembic_cfg, "head")
    logging.getLogger("app").info("data 数据库迁移完成")

    # v2.6.1：陈旧 online 资产 → offline（启动时一次，幂等）
    # 复用 app.main.degrade_stale_assets（与 monolith 模式走同一份代码）
    from app.main import degrade_stale_assets
    try:
        degrade_stale_assets()
    except Exception as e:
        # 启动期降级失败不阻塞容器启动（采集按钮仍可手动触发）
        logger.error(f"data 容器启动降级失败: {e}", exc_info=True)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "data"}
