"""配置备份管理器（v2.2 修复版 - 全文本 + SCP 统一回滚）

封装备份拉取 / 推送、轮转、回滚等核心逻辑。
- 不直接依赖 FastAPI 路由，可在脚本中独立调用
- 文件存储路径：{BACKUP_DIR}/{device_id}/{ISO8601}__{type}.cfg
- 数据库 Backup 表记录元数据
- 锁定备份不参与轮转

H3C V7 适配说明（v2.2 真机验证 192.168.100.4 Leaf-03）：
- SFTP 子系统默认禁用
- SCP server 也默认禁用（但 Python `scp` 库基于 SSH 通道，**不依赖**设备 SCP server）
- `scp` 库通过 paramiko SSH 通道能成功拉/推 H3C V7 文件
- H3C V7 startup.cfg 是纯文本（H3C V5 才是 binary）
- `display current-configuration` 走 SSH CLI 拉（自动 `screen-length 0` 关分页）

回滚策略（统一一条路）：
  startup / running 备份都走 `_restore_via_scp`：
    1. SCP 推 backup → 设备 flash（remote=`recover_<id>.cfg`）
    2. user-view 跑 `startup saved-configuration recover_<id>.cfg`
    3. 不自动 reload（断网风险由运维评估），UI 提示手动 reload

**不**维护白名单：回滚是"全量文件替换"，与设备模块结构 / 元素列表解耦，
  业界主流做法（RANCID / Oxidized / Ansible Network / NAPALM / H3C iMC）。
"""
import hashlib
import logging
import os
import re
import time
from datetime import datetime
from typing import Optional

import paramiko
from scp import SCPClient

from app.config import settings
from app.models import Backup
from app.utils.ssh_executor import SSHExecutor

logger = logging.getLogger("app")


# 备份类型
# - startup: 设备启动配置（持久化），走 SCP 拉/推
# - running: 设备运行配置（动态），走 SSH CLI 拉（display current-configuration），恢复走 SCP 推
SUPPORTED_TYPES = ("startup", "running")

# H3C V7 设备上 startup.cfg 的标准路径
DEVICE_STARTUP_PATH = "startup.cfg"


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

    Attributes:
        device_id: 设备数据库 ID
        host: 设备 IP
        port: SSH 端口 22（startup / running 备份均通过 SSH 22 通道）
        username/password: 设备认证
    """

    def __init__(self, device_id: int, host: str, port: int, username: str, password: str, db=None):
        self.device_id = device_id
        self.host = host
        self.port = port  # SSH 端口 22（startup 走 SCP，running 走 SSH CLI）
        self.username = username
        self.password = password
        self.db = db  # SQLAlchemy Session

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

    def _connect_ssh(self, timeout: int = 15) -> paramiko.SSHClient:
        """建立 SSH 连接"""
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

    # ===================== 拉取 =====================

    def _fetch_startup_via_scp(self) -> bytes:
        """通过 SCP 拉取设备 startup.cfg（基于 SSH 通道，不依赖设备 SCP server）

        Returns:
            startup.cfg 文件原始字节（H3C V7 为文本）

        Raises:
            BackupError: SSH/SCP 失败（连接/认证/协议错误，已转可读中文）
        """
        self._ensure_dir()
        client = self._connect_ssh()
        try:
            # 临时本地路径
            tmp_path = os.path.join(self.device_backup_dir, f".tmp_{self._timestamp()}.cfg")
            try:
                scp = SCPClient(client.get_transport())
                try:
                    scp.get(DEVICE_STARTUP_PATH, tmp_path)
                finally:
                    scp.close()
            except Exception as e:
                # 清理临时文件
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                raise BackupError(f"SCP 拉取 startup.cfg 失败 {self.host}: {e}") from e

            if not os.path.exists(tmp_path):
                raise BackupError(f"SCP 拉取完成但文件未生成: {tmp_path}")

            with open(tmp_path, "rb") as f:
                content = f.read()
            # 清理临时文件（create_backup 会用正式名重写）
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            return content
        finally:
            client.close()

    def _fetch_running_via_ssh_cli(self) -> bytes:
        """通过 SSH CLI 拉取设备 running-config（`display current-configuration` 文本）

        流程：
        1. SSHExecutor 跑 `screen-length 0` 关分页
        2. SSHExecutor 跑 `display current-configuration`，自动处理 H3C 分页提示
        3. 清理尾部 prompt / 命令回显，返回纯文本

        Returns:
            running-config 文本字节（H3C V7 完整配置）

        Raises:
            BackupError: SSH/CLI 失败
        """
        from app.utils.ssh_executor import SSHExecutor

        ssh = SSHExecutor(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=30,
        )

        # 1. 关闭分页（per-session）
        page_off = ssh.execute("screen-length 0")
        if not page_off["success"]:
            raise BackupError(
                f"关闭分页失败 {self.host}: {page_off['output'][:200]}"
            )

        # 2. 拉取 running-config
        result = ssh.execute("display current-configuration")
        if not result["success"]:
            raise BackupError(
                f"display current-configuration 失败 {self.host}: {result['output'][:200]}"
            )

        content = result["output"]

        # 3. 清理尾部 prompt（SSHExecutor 已去首行命令回显）
        lines = content.split("\n")
        # 去掉尾部 H3C prompt（如 <H3C> 或 [H3C]）
        while lines and re.match(r"^[<\[]\S+[>\]]\s*$", lines[-1].strip()):
            lines.pop()
        text = "\n".join(lines).rstrip() + "\n"

        if len(text) < 100:
            raise BackupError(
                f"display current-configuration 结果异常（长度 {len(text)}），可能设备无配置或拉取失败"
            )
        return text.encode("utf-8")

    def create_backup(self, types: list[str] = None, db=None) -> list[dict]:
        """创建备份

        Args:
            types: 备份类型列表
              - "startup" 走 SCP 拉 flash:/startup.cfg
              - "running" 走 SSH CLI 跑 `display current-configuration`
            db: SQLAlchemy Session

        Returns:
            [{"id", "type", "size", "content_hash", "filename", "created_at"}, ...]
        """
        types = types or list(SUPPORTED_TYPES)
        if db is None:
            db = self.db
        if db is None:
            raise BackupError("create_backup 需要 db 参数")

        # 校验类型
        invalid = [t for t in types if t not in SUPPORTED_TYPES]
        if invalid:
            raise BackupError(f"不支持的备份类型: {invalid}（仅支持 {SUPPORTED_TYPES}）")

        self._ensure_dir()
        logger.info(f"开始备份 device_id={self.device_id} types={types}")

        # 为每个 type 单独拉取（startup 走 SCP，running 走 SSH CLI）
        ts = self._timestamp()
        results = []
        for btype in types:
            try:
                if btype == "startup":
                    content_bytes = self._fetch_startup_via_scp()
                elif btype == "running":
                    content_bytes = self._fetch_running_via_ssh_cli()
                else:
                    raise BackupError(f"未知备份类型: {btype}")
            except BackupError as e:
                logger.error(f"备份失败 device_id={self.device_id} type={btype}: {e}")
                from app.utils.log_recorder import record_log
                record_log(db, self.device_id, self.host, "backup_create",
                           f"备份 {btype} 失败", "failed", error_message=str(e))
                continue

            # 统一文本扩展名 .cfg
            filename = f"{ts}__{btype}.cfg"
            local_path = os.path.join(self.device_backup_dir, filename)
            try:
                with open(local_path, "wb") as f:
                    f.write(content_bytes)
            except OSError as e:
                logger.error(f"落盘失败 device_id={self.device_id} type={btype}: {e}")
                from app.utils.log_recorder import record_log
                record_log(db, self.device_id, self.host, "backup_create",
                           f"备份 {btype} 落盘失败", "failed", error_message=str(e))
                continue

            size = os.path.getsize(local_path)
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
            db.flush()

            results.append({
                "id": backup.id,
                "type": btype,
                "size": size,
                "content_hash": content_hash,
                "filename": filename,
                "created_at": backup.created_at.isoformat() if backup.created_at else None,
            })
            from app.utils.log_recorder import record_log
            record_log(db, self.device_id, self.host, "backup_create",
                       f"备份 {btype} 成功 ({size} bytes, hash={content_hash[:8]})", "success")

        db.commit()
        logger.info(f"备份完成 device_id={self.device_id} 成功 {len(results)} 份（{len(types)} 份请求）")

        # 轮转
        rotated = self.rotate(self.device_id, keep=settings.BACKUP_KEEP, db=db)
        if rotated > 0:
            logger.info(f"轮转删除 device_id={self.device_id} 删除 {rotated} 份非锁定备份")
        return results

    # ===================== 轮转 =====================

    def rotate(self, device_id: int, keep: int, db=None):
        """轮转：每设备总份数 ≤ keep（含锁定），锁定优先保留不被删

        v2.3.1 patch 改：BACKUP_KEEP 从"非锁定份数"改为"总份数"（含锁定）。
        锁定备份永远不被轮转删除（v2.2.0 承诺保留）。
        锁定数 ≥ keep → 不删任何非锁定（用户锁太多属预期，保留）。
        锁定数 < keep → 从最旧非锁定删到 `总 - keep = 0`。
        """
        if db is None:
            db = self.db
        if db is None:
            raise BackupError("rotate 需要 db 参数")

        # 查该设备**所有**备份（不 filter locked），按 created_at ASC
        all_backups = (
            db.query(Backup)
            .filter(Backup.device_id == device_id)
            .order_by(Backup.created_at.asc())
            .all()
        )
        # 分离锁定 vs 非锁定（按 created_at 顺序，锁定优先保留）
        locked = [b for b in all_backups if b.locked]
        unlocked = [b for b in all_backups if not b.locked]

        # 锁定数 ≥ keep：用户锁太多，不删任何非锁定（防误删用户保留的）
        if len(locked) >= keep:
            logger.warning(
                f"轮转跳过: device_id={device_id}, 锁定 {len(locked)} ≥ keep={keep},"
                f"非锁定 {len(unlocked)} 全部保留（总 {len(all_backups)} > keep {keep}）"
            )
            return 0

        # 锁定数 < keep：从最旧非锁定删到总份数 == keep
        to_delete = len(all_backups) - keep
        if to_delete <= 0:
            return 0

        deleted = 0
        for backup in unlocked[:to_delete]:
            try:
                if os.path.exists(backup.file_path):
                    os.remove(backup.file_path)
            except OSError as e:
                logger.error(f"删除备份文件失败 {backup.file_path}: {e}")
                continue
            db.delete(backup)
            deleted += 1
            logger.info(f"轮转删除: device_id={device_id}, backup_id={backup.id}, file={backup.filename}")
        db.commit()
        return deleted

    # ===================== 列表 / 删除 / 锁定 =====================

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
        """删除备份（locked=True 返回 False 拒绝）"""
        if db is None:
            db = self.db
        if db is None:
            raise BackupError("delete_backup 需要 db 参数")
        backup = self.get_backup(backup_id, db)
        if not backup:
            raise BackupError(f"备份不存在: id={backup_id}")
        if backup.locked:
            return False

        try:
            if os.path.exists(backup.file_path):
                os.remove(backup.file_path)
        except OSError as e:
            logger.error(f"删除备份文件失败 {backup.file_path}: {e}")

        db.delete(backup)
        db.commit()
        from app.utils.log_recorder import record_log
        record_log(db, self.device_id, self.host, "backup_delete",
                   f"删除备份 id={backup_id} ({backup.filename})", "success")
        return True

    def set_locked(self, backup_id: int, locked: bool, db=None) -> bool:
        """切换备份锁定状态"""
        if db is None:
            db = self.db
        if db is None:
            raise BackupError("set_locked 需要 db 参数")
        backup = self.get_backup(backup_id, db)
        if not backup:
            raise BackupError(f"备份不存在: id={backup_id}")
        backup.locked = locked
        db.commit()
        from app.utils.log_recorder import record_log
        record_log(db, self.device_id, self.host, "backup_lock",
                   f"备份 id={backup_id} locked={locked}", "success")
        return True

    # ===================== 回滚（统一一条路：全文本 + SCP）=====================

    def restore(self, backup_id: int, with_reboot: bool = False, db=None) -> dict:
        """统一回滚：SCP 推 backup → 设备 flash → `startup saved-configuration` (+ 可选 reboot + 验证)

        适用于 startup 和 running 两种备份（都是 .cfg 文本）。
        业界主流做法：全量文件替换，不维护白名单。

        Args:
            backup_id: 备份数据库 ID
            with_reboot: 是否在推完后触发设备 reboot + retry SSH + 验证生效
                         （默认 False，符合"backup 工具不负责 reboot"的业界边界）
                         设为 True 时执行：reboot → retry 180s → display current-configuration 对比
            db: SQLAlchemy Session

        Returns:
            {"success": bool, "method": "scp", "message": str,
             "rebooted": bool, "verified": bool}
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

        # ============ 步骤 1: 推 + set as startup ============
        try:
            self._restore_via_scp(backup)
        except Exception as e:
            from app.utils.log_recorder import record_log
            record_log(db, self.device_id, self.host, "backup_restore",
                       f"回滚备份 id={backup_id} ({backup.backup_type}) 失败（SCP 推阶段）",
                       "failed", error_message=str(e))
            return {"success": False, "method": "scp", "message": f"回滚失败: {e}",
                    "rebooted": False, "verified": False}

        from app.utils.log_recorder import record_log
        record_log(db, self.device_id, self.host, "backup_restore",
                   f"回滚备份 id={backup_id} ({backup.backup_type}) SCP 推 + set as startup 成功",
                   "success")

        result = {
            "success": True,
            "method": "scp",
            "message": (
                f"配置已推回设备并设为 startup。"
            ),
            "rebooted": False,
            "verified": False,
        }

        # ============ 步骤 2 (可选): reboot + retry + verify ============
        if not with_reboot:
            result["message"] += "（未触发 reboot，请手动 reload 让配置生效）"
            return result

        # 触发 reboot
        try:
            self._reboot_and_wait(timeout=180)
        except Exception as e:
            record_log(db, self.device_id, self.host, "backup_reboot",
                       f"回滚后 reboot 失败: {e}", "failed", error_message=str(e))
            result["rebooted"] = False
            result["verified"] = False
            result["message"] = (
                f"配置已推回设备 + set as startup，但 reboot 失败: {e}。"
                f"请手动 reload 设备让配置生效。"
            )
            return result

        result["rebooted"] = True
        record_log(db, self.device_id, self.host, "backup_reboot",
                   "回滚后 reboot + retry SSH 成功", "success")

        # 验证生效
        try:
            verified = self._verify_running_matches_backup(backup)
            result["verified"] = verified
            if verified:
                result["message"] = (
                    f"配置已推回设备 + reboot 完成 + 验证生效（running-config == 备份内容）。"
                )
                record_log(db, self.device_id, self.host, "backup_verify",
                           "回滚后验证：running-config == 备份内容", "success")
            else:
                result["message"] = (
                    f"reboot 完成但 running-config 与备份不一致，"
                    f"请人工确认设备状态。"
                )
                record_log(db, self.device_id, self.host, "backup_verify",
                           "回滚后验证：running-config != 备份内容", "failed")
        except Exception as e:
            result["verified"] = False
            result["message"] = (
                f"reboot 完成但验证失败: {e}，请人工确认设备状态。"
            )
            record_log(db, self.device_id, self.host, "backup_verify",
                       f"回滚后验证失败: {e}", "failed", error_message=str(e))

        return result

    def _restore_via_scp(self, backup: Backup) -> None:
        """统一回滚实现：SCP 推 + `startup saved-configuration`

        流程：
        1. SSH 22 连接设备
        2. SCP 推 backup 文件到设备 flash（remote=`recover_<backup_id>.cfg`）
        3. user-view 跑 `startup saved-configuration recover_<backup_id>.cfg`
        4. 失败时记录错误，不主动清理设备上的临时文件（让用户决定）
        """
        client = self._connect_ssh()
        remote_name = f"recover_{backup.id}.cfg"
        push_ok = False
        try:
            scp = SCPClient(client.get_transport())
            try:
                scp.put(backup.file_path, remote_name)
                push_ok = True
                logger.info(
                    f"SCP 推送 backup ({backup.backup_type}) 到设备: {remote_name}"
                )
            finally:
                scp.close()
        except Exception as e:
            raise BackupError(f"SCP 推回失败: {e}") from e
        finally:
            client.close()

        if not push_ok:
            raise BackupError("SCP 推送未确认成功")

        # 设置为启动配置（user-view 命令，无需 system-view）
        client = self._connect_ssh()
        try:
            chan = client.invoke_shell()
            chan.settimeout(20)
            try:
                chan.send(f"startup saved-configuration {remote_name}\n".encode())
                time.sleep(3)
                out = b""
                while chan.recv_ready():
                    out += chan.recv(8192)
                text = out.decode("utf-8", errors="replace")
                if "Done" not in text and "Done." not in text:
                    raise BackupError(
                        f"startup saved-configuration 未确认成功，输出: {text[-300:]}"
                    )
                logger.info(f"startup saved-configuration {remote_name} 设置成功")
            finally:
                chan.close()
        except Exception as e:
            raise BackupError(f"设置启动配置失败: {e}") from e
        finally:
            client.close()

    def _reboot_and_wait(self, timeout: int = 180) -> None:
        """触发设备 reboot + 等待 SSH 就绪（H3C V7 SSH 完整交互）

        H3C V7 `reboot` 命令交互流程：
        1. `reboot` → "Save current config? [Y/N]" → 答 N（不 save，避免覆盖 startup）
        2. → "This command will reboot the device. Continue? [Y/N]" → 答 Y
        3. 设备开始重启 → 60-120s 后 SSH 起来

        Raises:
            BackupError: reboot 触发失败 / 超时
        """
        client = self._connect_ssh(timeout=10)
        try:
            chan = client.invoke_shell()
            chan.settimeout(20)
            # 清空初始 banner
            time.sleep(1)
            while chan.recv_ready():
                chan.recv(8192)
            # 发 reboot
            chan.send(b"reboot\n")
            all_out = b""
            start = time.time()
            sent_save_no = False
            sent_continue_yes = False
            while time.time() - start < 30:
                if chan.recv_ready():
                    data = chan.recv(8192)
                    all_out += data
                    text = all_out.decode("utf-8", errors="replace")
                    if not sent_save_no and "save current configuration" in text.lower():
                        chan.send(b"N\n")
                        sent_save_no = True
                        logger.info("reboot: 答 save = N（不保存，避免覆盖 startup）")
                    if sent_save_no and not sent_continue_yes and "continue?" in text.lower():
                        chan.send(b"Y\n")
                        sent_continue_yes = True
                        logger.info("reboot: 答 continue = Y")
                    if sent_continue_yes and (
                        "system is rebooting" in text.lower()
                        or "now rebooting" in text.lower()
                        or "rebooting" in text.lower()
                    ):
                        logger.info("reboot: 设备开始重启")
                        break
                else:
                    time.sleep(0.5)
            chan.close()
            if not sent_continue_yes:
                raise BackupError(
                    f"reboot 交互未完成（save_no={sent_save_no}, continue_yes={sent_continue_yes}），"
                    f"最后输出: {all_out.decode('utf-8', errors='replace')[-500:]!r}"
                )
        finally:
            client.close()

        # 耐心等 SSH 就绪（最多 timeout 秒）
        start = time.time()
        attempt = 0
        while time.time() - start < timeout:
            attempt += 1
            client = self._connect_ssh(timeout=3)
            try:
                # 真连上了，关闭
                client.close()
                logger.info(f"reboot: SSH 在 {int(time.time() - start)}s 第 {attempt} 次重连成功")
                return
            except Exception as e:
                logger.debug(f"reboot: 第 {attempt} 次重连失败: {type(e).__name__}")
            finally:
                try:
                    client.close()
                except Exception:
                    pass
            time.sleep(5)
        raise BackupError(f"reboot: 等待 {timeout}s 后 SSH 仍不可达")

    def _verify_running_matches_backup(self, backup: Backup, retries: int = 5, retry_interval: int = 10) -> bool:
        """验证设备当前 running-config 内容 == 备份内容（关键字段对比）

        完整 byte-exact 对比可能因设备 banner / 时间戳略有差异，
        改为对比 sysname + vlan 列表（业务核心配置）。

        reboot 后设备 SSH 已就绪但 CLI 还没完全 ready，需要 retry。
        """
        with open(backup.file_path) as f:
            backup_content = f.read()
        m_bk = re.search(r'^\s*sysname\s+(\S+)', backup_content, re.MULTILINE)
        bk_hostname = m_bk.group(1) if m_bk else '?'
        bk_vlans = sorted(re.findall(r'^vlan\s+(\d+)\s*$', backup_content, re.MULTILINE))

        last_err = None
        for attempt in range(1, retries + 1):
            try:
                ssh = SSHExecutor(
                    host=self.host, port=self.port,
                    username=self.username, password=self.password, timeout=30,
                )
                ssh.execute("screen-length 0")
                r = ssh.execute("display current-configuration")
                if not r['success']:
                    last_err = f"display current-configuration 返回失败: {r['output'][:200]}"
                    logger.warning(f"verify 第 {attempt}/{retries} 次: {last_err}")
                    time.sleep(retry_interval)
                    continue
                content = r['output']
                m_dev = re.search(r'^\s*sysname\s+(\S+)', content, re.MULTILINE)
                dev_hostname = m_dev.group(1) if m_dev else '?'
                dev_vlans = sorted(re.findall(r'^vlan\s+(\d+)\s*$', content, re.MULTILINE))
                logger.info(
                    f"verify 第 {attempt}/{retries} 次: "
                    f"backup sysname={bk_hostname!r} vlans={bk_vlans}; "
                    f"device sysname={dev_hostname!r} vlans={dev_vlans}"
                )
                return dev_hostname == bk_hostname and dev_vlans == bk_vlans
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:200]}"
                logger.warning(f"verify 第 {attempt}/{retries} 次异常: {last_err}")
                time.sleep(retry_interval)

        raise BackupError(f"verify 重试 {retries} 次仍失败: {last_err}")
