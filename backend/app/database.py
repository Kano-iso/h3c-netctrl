from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


engine = create_engine(
    f"sqlite:///{settings.DB_PATH}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    # v2.6.1 fix-backup-data-integrity Task 3c: 设为 False，commit 后实例属性
    # 不会 expire，避免长任务（task_manager、BackupManager.create_backup 循环）
    # commit 后访问属性触发隐式 reload（reload 失败可能 ObjectDeletedError）
    expire_on_commit=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


def get_db():
    """获取数据库 session 的依赖注入函数"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
