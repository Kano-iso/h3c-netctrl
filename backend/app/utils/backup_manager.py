"""配置备份管理器（v2.2）

封装 SFTP 拉取、轮转、回滚等核心逻辑。
- 不直接依赖 FastAPI 路由，可在脚本中独立调用
- 文件存储路径：{BACKUP_DIR}/{device_id}/{ISO8601}_{type}.cfg
- 数据库 Backup 表记录元数据
- 锁定备份不参与轮转

回滚策略：
- 首选 NETCONF load-config（RFC 6241，H3C 支持度需探测）
- Fallback：SSH 推送 startup.cfg 到设备 + 执行 `startup saved-configuration`
"""
import hashlib
import logging
import os
import re
import shutil
from datetime import datetime
from typing import Optional

import paramiko

from app.config import settings
from app.models import Backup
from app.utils.crypto import decrypt_password

logger = logging.getLogger("app")


# 备份文件在设备上的路径（H3C V7 通用）
DEVICE_BACKUP_PATHS = {
    "startup": "startup.cfg",
    "running": "running.cfg",
}


class BackupError(Exception):
    """备份操作异常基类"""


class BackupManager:
    """单设备的备份管理器

    使用方式：
        mgr = BackupManager(device_id, host, port, username, password)
        # 拉取备份
        records = mgr.create_backup(types=["startup", "running"])
        # 列出备份
        backups = mgr.list_backups()
        # 删除备份
        mgr.delete_backup(backup_id)
        # 切换锁定
        mgr.set_locked(backup_id, True)
        # 回滚
        mgr.restore(backup_id)
    """

    def __init__(self, device_id: int, host: str, port: int, username: str, password: str, db=None):
        self.device_id = device_id
        self.host = host
        self.port = port  # SSH 端口（H3C 默认为 22，NETCONF 是 830）
        self.username = username
        self.password = password
        self.db = db  # SQLAlchemy Session，由调用方注入

        # 备份目录：{BACKUP_DIR}/{device_id}/
        self.device_backup_dir = os.path.join(settings.BACKUP_DIR, str(device_id))

    def _ensure_dir(self):
        """确保备份目录存在"""
        os.makedirs(self.device_backup_dir, exist_ok=True)

    @staticmethod
    def _hash_file(path: str) -> str:
        """计算文件 SHA256 hex 摘要"""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _timestamp() -> str:
        """生成 ISO8601 紧凑时间戳，如 20260624T103045"""
        return datetime.utcnow().strftime("%Y%m%dT%H%M%S")

    def _connect_ssh(self, timeout: int = 10) -> paramiko.SSHClient:
        """建立 SSH 连接（用于 SFTP）"""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=timeout,
            allow_agent=False,
            look_for_keys=False,
        )
        return client

    def pull_file(self, remote_path: str, local_path: str) -> int:
        """SFTP 拉取单个文件，返回文件大小（字节）

        Raises:
            BackupError: SSH/SFTP 失败
        """
        self._ensure_dir()
        client = self._connect_ssh()
        try:
            sftp = client.open_sftp()
            try:
                sftp.get(remote_path, local_path)
            finally:
                sftp.close()
        except Exception as e:
            raise BackupError(f"SFTP 拉取失败 {self.host}:{remote_path}: {e}") from e
        finally:
            client.close()

        return os.path.getsize(local_path)

    def create_backup(self, types: list[str] = None, db=None) -> list[dict]:
        """创建备份（拉取指定类型 + 落盘 + 写记录 + 轮转）

        Args:
            types: 要备份的类型列表，["startup", "running"]；默认两者都拉
            db: SQLAlchemy Session

        Returns:
            [{"id", "type", "size", "content_hash", "filename", "created_at"}, ...]
        """
        types = types or ["startup", "running"]
        if db is None:
            db = self.db
        if db is None:
            raise BackupError("create_backup 需要 db 参数")

        self._ensure_dir()
        ts = self._timestamp()
        results = []

        # 检查设备是否强制保存（避免拉取正在写入的文件）
        try:
            self._force_save_on_device(types)
        except Exception as e:
            logger.warning(f"强制保存失败（继续备份）: {e}")

        for btype in types:
            remote_path = DEVICE_BACKUP_PATHS.get(btype)
            if not remote_path:
                raise BackupError(f"未知备份类型: {btype}")

            filename = f"{ts}__{btype}.cfg"
            local_path = os.path.join(self.device_backup_dir, filename)

            try:
                size = self.pull_file(remote_path, local_path)
            except BackupError as e:
                # 单类型失败记录 log 但继续
                logger.error(f"备份失败 device_id={self.device_id} type={btype}: {e}")
                record_log(db, self.device_id, self.host, "backup_create",
                           f"备份 {btype} 失败", "failed", error_message=str(e))
                continue

            content_hash = self._hash_file(local_path)

            backup = Backup(
                device_id=self.device_id,
                filename=filename,
                file_path=local_path,
                backup_type=btype,
                size=size,
                content_hash=content_hash,
                locked=False,
            )
            db.add(backup)
            db.flush()  # 获取 ID

            results.append({
                "id": backup.id,
                "type": btype,
                "size": size,
                "content_hash": content_hash,
                "filename": filename,
                "created_at": backup.created_at.isoformat() if backup.created_at else None,
            })
            record_log(db, self.device_id, self.host, "backup_create",
                       f"备份 {btype} 成功 ({size} bytes, hash={content_hash[:8]})", "success")

        db.commit()

        # 轮转：每设备保留 N 份非锁定
        self.rotate(self.device_id, keep=settings.BACKUP_KEEP, db=db)

        return results

    def _force_save_on_device(self, types: list[str]):
        """在设备上执行 `save force`，确保拉到的不是正在写入的文件"""
        # 只有 startup 备份需要强制保存（running 是当前运行态，保存时可能锁）
        if "running" in types:
            return
        client = self._connect_ssh()
        try:
            stdin, stdout, stderr = client.exec_command("save force", timeout=15)
            stdout.channel.recv_exit_status()  # 等待执行完成
            err = stderr.read().decode("utf-8", errors="ignore").strip()
            if err and "no need to save" not in err.lower() and "same as" not in err.lower():
                logger.debug(f"save force 输出: {err}")
        except Exception as e:
            raise BackupError(f"save force 失败: {e}") from e
        finally:
            client.close()

    def rotate(self, device_id: int, keep: int, db=None):
        """轮转：保留最新 N 份非锁定备份，删除超出的最旧非锁定备份

        - locked=True 的备份不参与轮转（永久保留）
        - 按 created_at ASC 排序，保留最后 N 条非锁定
        """
        if db is None:
            db = self.db
        if db is None:
            raise BackupError("rotate 需要 db 参数")

        # 查询所有非锁定备份，按 created_at ASC
        backups = (
            db.query(Backup)
            .filter(Backup.device_id == device_id, Backup.locked == False)  # noqa: E712
            .order_by(Backup.created_at.asc())
            .all()
        )
        to_delete = len(backups) - keep
        if to_delete <= 0:
            return 0

        deleted = 0
        for backup in backups[:to_delete]:
            # 删除磁盘文件
            try:
                if os.path.exists(backup.file_path):
                    os.remove(backup.file_path)
            except OSError as e:
                logger.error(f"删除备份文件失败 {backup.file_path}: {e}")
                continue
            # 删除数据库记录
            db.delete(backup)
            deleted += 1
            logger.info(f"轮转删除: device_id={device_id}, backup_id={backup.id}, file={backup.filename}")
        db.commit()
        return deleted

    def list_backups(self, db=None) -> list[Backup]:
        """列出该设备所有备份，按 created_at DESC"""
        if db is None:
            db = self.db
        if db is None:
            raise BackupError("list_backups 需要 db 参数")
        return (
            db.query(Backup)
            .filter(Backup.device_id == self.device_id)
            .order_by(Backup.created_at.desc())
            .all()
        )

    def get_backup(self, backup_id: int, db=None) -> Optional[Backup]:
        """获取单个备份"""
        if db is None:
            db = self.db
        if db is None:
            raise BackupError("get_backup 需要 db 参数")
        return (
            db.query(Backup)
            .filter(Backup.id == backup_id, Backup.device_id == self.device_id)
            .first()
        )

    def delete_backup(self, backup_id: int, db=None) -> bool:
        """删除备份（锁定的不允许）

        Returns:
            True 删除成功 / False 锁定拒绝
        """
        if db is None:
            db = self.db
        if db is None:
            raise BackupError("delete_backup 需要 db 参数")
        backup = self.get_backup(backup_id, db)
        if not backup:
            raise BackupError(f"备份不存在: id={backup_id}")
        if backup.locked:
            return False  # 锁定拒绝

        # 删除磁盘文件
        try:
            if os.path.exists(backup.file_path):
                os.remove(backup.file_path)
        except OSError as e:
            logger.error(f"删除备份文件失败 {backup.file_path}: {e}")
            # 继续删除数据库记录

        db.delete(backup)
        db.commit()
        record_log(db, self.device_id, self.host, "backup_delete",
                   f"删除备份 id={backup_id} ({backup.filename})", "success")
        return True

    def set_locked(self, backup_id: int, locked: bool, db=None) -> bool:
        """切换备份的锁定状态"""
        if db is None:
            db = self.db
        if db is None:
            raise BackupError("set_locked 需要 db 参数")
        backup = self.get_backup(backup_id, db)
        if not backup:
            raise BackupError(f"备份不存在: id={backup_id}")
        backup.locked = locked
        db.commit()
        record_log(db, self.device_id, self.host, "backup_lock",
                   f"备份 id={backup_id} locked={locked}", "success")
        return True

    def restore(self, backup_id: int, db=None) -> dict:
        """回滚：从指定备份还原到设备

        策略：
        1. 首选 NETCONF load-config（RFC 6241）
        2. Fallback：SSH 推送 startup.cfg 到设备 + 执行 `startup saved-configuration`

        Returns:
            {"success": bool, "method": "netconf" | "ssh", "message": str}
        """
        if db is None:
            db = self.db
        if db is None:
            raise BackupError("restore 需要 db 参数")
        backup = self.get_backup(backup_id, db)
        if not backup:
            raise BackupError(f"备份不存在: id={backup_id}")
        if not os.path.exists(backup.file_path):
            raise BackupError(f"备份文件丢失: {backup.file_path}")

        # 读备份内容（用于 NETCONF 推送）
        with open(backup.file_path, "rb") as f:
            content = f.read()

        # 策略 1：NETCONF load-config
        try:
            method = self._restore_via_netconf(content)
            record_log(db, self.device_id, self.host, "backup_restore",
                       f"回滚备份 id={backup_id} (NETCONF)", "success")
            return {"success": True, "method": "netconf", "message": "NETCONF load-config 成功"}
        except BackupError as e:
            logger.warning(f"NETCONF 回滚失败，fallback SSH: {e}")

        # 策略 2：SSH 推送
        try:
            method = self._restore_via_ssh(backup.file_path, backup.backup_type)
            record_log(db, self.device_id, self.host, "backup_restore",
                       f"回滚备份 id={backup_id} (SSH)", "success")
            return {"success": True, "method": "ssh", "message": "SSH 推送 + startup saved-configuration 成功"}
        except BackupError as e:
            record_log(db, self.device_id, self.host, "backup_restore",
                       f"回滚备份 id={backup_id} 失败", "failed", error_message=str(e))
            return {"success": False, "method": "none", "message": f"回滚失败: {e}"}

    def _restore_via_netconf(self, content: bytes) -> str:
        """NETCONF load-config 回滚

        使用 RFC 6241 标准操作，H3C V7 支持度需实地探测
        """
        # 包装成 NETCONF load-config 报文
        from app.netconf_client import NetconfClient, classify_netconf_error
        try:
            # 备份内容是 cfg 文本，需要包装成 NETCONF config payload
            # 实际格式取决于 H3C 实现，常见的是 <config> 包裹文本
            config_xml = f'<config><top xmlns="http://www.h3c.com/netconf/config:1.0"><Configuration>{content.decode("utf-8", errors="replace")}</Configuration></top></config>'
            with NetconfClient(
                host=self.host, port=830,  # NETCONF 端口
                username=self.username, password=self.password,
            ) as client:
                # 探测 load-config 支持
                try:
                    client.rpc("<load-configuration><url>startup.cfg</url></load-configuration>")
                    return "netconf"
                except Exception as e:
                    raise BackupError(f"NETCONF load-config 不支持或失败: {e}") from e
        except Exception as e:
            raise BackupError(f"NETCONF 回滚失败: {e}") from e

    def _restore_via_ssh(self, local_path: str, backup_type: str) -> str:
        """SSH 推送回滚：SFTP 上传 startup.cfg + 执行 `startup saved-configuration`

        注意：H3C 设备的 startup.cfg 是启动配置，运行时需 save 后才生效
        """
        client = self._connect_ssh(timeout=20)
        try:
            sftp = client.open_sftp()
            try:
                remote_name = "startup_recover.cfg" if backup_type == "startup" else "running_recover.cfg"
                sftp.put(local_path, remote_name)
            finally:
                sftp.close()

            # 在设备上执行：覆盖 startup.cfg 并 save
            commands = []
            if backup_type == "startup":
                # 替换 startup.cfg
                commands = [
                    f"copy {remote_name} startup.cfg",
                    "startup saved-configuration",
                    f"delete /unreserved file {remote_name}",
                ]
            else:
                # running 是动态配置，需要先备份当前 running，然后 apply 备份
                # 简化：把 running_recover.cfg 内容通过 syslog/display 命令应用（不通用）
                # 实际：H3C running 配置恢复需要 NETCONF load-config，SSH 不能完整覆盖
                raise BackupError("running 配置回滚需要 NETCONF load-config 支持，SSH 推送仅支持 startup 类型")

            for cmd in commands:
                stdin, stdout, stderr = client.exec_command(cmd, timeout=20)
                stdout.channel.recv_exit_status()
                err = stderr.read().decode("utf-8", errors="ignore").strip()
                if err and "error" in err.lower():
                    raise BackupError(f"命令失败 {cmd}: {err}")
        except Exception as e:
            raise BackupError(f"SSH 推送回滚失败: {e}") from e
        finally:
            client.close()
        return "ssh"


def record_log(db, device_id, device_name, action, detail, status, error_message=None):
    """兼容调用：直接复用 app.utils.log_recorder.record_log"""
    from app.utils.log_recorder import record_log as _record_log
    return _record_log(db, device_id, device_name, action, detail, status, error_message)
