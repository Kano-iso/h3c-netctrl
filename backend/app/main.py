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
from app.routers import sdn
from app.routers import sdn_access
from app.routers import sdn_assurance
from app.routers import ztp
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
# v3.0 SDN/VPC 路由（monolith 模式也注册，便于前端 monolith 跑能用 sdn 端点）
app.include_router(sdn.router)  # sdn router 自带 prefix=/api/sdn
app.include_router(sdn_access.router)  # S1 终端接入端点，自带 prefix=/api/sdn
app.include_router(sdn_assurance.router)  # S3-001 VPC 保障（策略 + 只读评估），prefix=/api/sdn
app.include_router(ztp.router)

# 内部端点（v241-container-split，测试用，monolith 模式也注册）
app.include_router(ctrl_internal.router)
app.include_router(data_internal.router)


def degrade_stale_assets() -> int:
    """降级陈旧 online 资产为 offline（v2.6.1 fix-asset-stale-status）

    SQL: `UPDATE assets SET status='offline' WHERE status='online'
          AND updated_at < datetime('now', '-' || :hours || ' hours')`

    幂等：已降级行不再满足 `status='online'`，重复调用影响行数 = 0。

    Returns:
        受影响行数（0 = 无 stale 资产 / 已降级过 / 功能关闭）

    Raises:
        仅在数据库异常时抛（不吞错误，遵循"快速失败"原则）
    """
    if not settings.ASSET_STALE_ENABLED:
        logger.info("degrade_stale_assets: ASSET_STALE_ENABLED=False，跳过降级")
        return 0
    from sqlalchemy import text
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "UPDATE assets SET status='offline' "
                "WHERE status='online' "
                "AND updated_at < datetime('now', '-' || :hours || ' hours')"
            ),
            {"hours": settings.ASSET_STALE_HOURS},
        )
        affected = result.rowcount
    logger.info(
        f"degrade_stale_assets: 降级完成，hours={settings.ASSET_STALE_HOURS} "
        f"affected={affected}"
    )
    return affected


@app.on_event("startup")
def on_startup():
    """应用启动时通过 Alembic 执行数据库迁移"""
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{settings.DB_PATH}")
    command.upgrade(alembic_cfg, "head")

    logging.getLogger("app").info("数据库迁移完成")

    # v2.6.1 fix-asset-stale-status: 仅 data 容器（split 模式）跑陈旧降级
    # monolith 模式默认 SERVICE_NAME=core，跳过（避免误降级共用库）
    if SERVICE_NAME == "data":
        try:
            degrade_stale_assets()
        except Exception as e:
            # 启动期降级失败不阻塞容器启动（采集按钮仍可手动触发）
            logger.error(f"data 容器启动降级失败: {e}", exc_info=True)


@app.get("/health")
def health_check():
    return {"status": "ok"}
