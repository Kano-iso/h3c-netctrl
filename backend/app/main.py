import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import device, vlan, log
from app.utils.logger import setup_logging

# 确保数据目录存在
os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
os.makedirs("./logs", exist_ok=True)

# 初始化日志系统
setup_logging(log_level=settings.LOG_LEVEL, log_file="./logs/app.log")

app = FastAPI(
    title="H3C NetCtrl",
    description="基于 NETCONF 的 H3C 交换机轻量网控平台",
    version="1.1.0",
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


@app.on_event("startup")
def on_startup():
    """应用启动时创建数据库表"""
    Base.metadata.create_all(bind=engine)
    import logging
    logging.getLogger("app").info("数据库表已创建/确认")


@app.get("/health")
def health_check():
    return {"status": "ok"}
