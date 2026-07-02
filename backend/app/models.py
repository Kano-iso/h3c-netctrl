from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Task(Base):
    """异步任务记录（v24-feat-async-backup-status）

    存储备份/回滚等耗时操作的异步任务状态。
    - task_type: "backup" | "restore"
    - status: pending → running → success/failed/cancelled
    - progress: 0-100 整数
    - result_json: 任务结果 JSON 字符串（如备份返回的 backups 列表）
    """
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "backup" | "restore"
    device_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=830)
    username: Mapped[str] = mapped_column(String, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(String, nullable=False)
    # 受保护的接口（JSON 字符串列表，存 if_index），配置时会被拦截
    protected_interfaces: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # 一对一关联资产信息
    asset: Mapped["Asset"] = relationship("Asset", back_populates="device", uselist=False, cascade="all, delete-orphan")
    # 一对多关联备份（设备删除时 CASCADE 清理）
    backups: Mapped[list["Backup"]] = relationship("Backup", back_populates="device", cascade="all, delete-orphan")


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, nullable=False)
    device_name: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), unique=True, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=True)
    serial_number: Mapped[str] = mapped_column(String, nullable=True)
    firmware_version: Mapped[str] = mapped_column(String, nullable=True)
    software_package: Mapped[str] = mapped_column(String, nullable=True)
    location: Mapped[str] = mapped_column(String, nullable=True)
    tags: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="unknown")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 反向关联设备
    device: Mapped["Device"] = relationship("Device", back_populates="asset")


class Backup(Base):
    """配置备份记录（v2.2）

    存储设备 startup.cfg / running.cfg 备份元数据，文件本身存 /data/backups/{device_id}/。
    - locked=True 备份不参与轮转（永久保留直到用户主动解锁/删除）
    - 设备删除时 CASCADE 清理（连带删除磁盘文件由 backup.py 路由处理）
    """
    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)  # 容器内绝对路径
    backup_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "startup" | "running"
    size: Mapped[int] = mapped_column(Integer, nullable=False)  # 字节
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256 hex
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    # 反向关联设备
    device: Mapped["Device"] = relationship("Device", back_populates="backups")

    __table_args__ = (
        # 复合索引：按设备 + 时间排序（列表/轮转查询）
        Index("ix_backups_device_created", "device_id", "created_at"),
    )
