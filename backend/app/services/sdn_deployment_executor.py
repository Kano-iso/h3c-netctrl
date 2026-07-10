"""SdnDeploymentExecutor — 业务配置下发的 NETCONF 执行器

## 职责

读 SdnDeployment.planned_config → NETCONF edit-config → 写回 status

## 架构定位

- 业务下发**只走 backend**：frontend → config 容器 → SdnDeploymentExecutor → NetconfClient → 设备
- ops-toolkit 容器**不参与**业务下发（仅供排错）
- 单 deployment 串行下发（H3C V7 SSH max-session 限制）

## 设备白名单

仅 Leaf-04（192.168.100.5）和 Leaf-05（192.168.100.6）允许下发：
- .2 / .3 是 SDN 参考机器，仅读
- .177 是 test 设备，但下发目标限定 .5/.6

## 失败处理

- 失败立即停（不重试、不自动回滚）
- error 字段记录：失败命令索引 + 原始 NETCONF 错误
- 人工决定是否手动 undo（VPC 创建无 transaction 概念）

## split 容器兼容

- 设备查询走 get_device_with_password（monolith 走本地，split 走 internal API）
- executor 本身在 config 容器
"""
import json
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import SdnDeployment
from app.netconf_client import NetconfClient, classify_netconf_error
from app.utils.device_access import get_device_with_password

logger = logging.getLogger("app")


# 设备白名单：仅 Leaf-04 / Leaf-05（.5 / .6）允许下发
WRITABLE_HOST_SUFFIXES = (".5", ".6")


class SdnDeploymentError(Exception):
    """executor 内部错误（业务可处理的异常）"""
    def __init__(self, error_key, params: Optional[dict] = None, status_code: int = 422):
        super().__init__(error_key)
        self.error_key = error_key
        self.params = params or {}
        self.status_code = status_code


class SdnDeploymentExecutor:
    """业务配置下发执行器

    Usage:
        executor = SdnDeploymentExecutor()
        deployment = executor.execute(db, deployment_id=1)
    """

    def __init__(self):
        pass

    def execute(self, db: Session, deployment_id: int) -> SdnDeployment:
        """执行 deployment 下发

        流程：
        1. 查 deployment + 校验（status == 'pending'、action == 'create'）
        2. 查 device + 解密密码 + 校验 host 白名单
        3. 解析 planned_config JSON
        4. NetconfClient context manager 串行 edit_config
        5. 写回 status（success / failed + error）

        Args:
            db: SQLAlchemy Session
            deployment_id: SdnDeployment.id

        Returns:
            SdnDeployment（已写回 status / error，commit 到 DB）

        Raises:
            SdnDeploymentError: 校验失败（status / action / device / JSON）
            异常会冒泡到 router 层，router 转 APIResponse
        """
        # 1. 查 deployment
        deployment = db.query(SdnDeployment).filter(SdnDeployment.id == deployment_id).first()
        if not deployment:
            raise SdnDeploymentError(
                "SDN_DEPLOYMENT_NOT_FOUND",
                params={"id": deployment_id},
                status_code=404,
            )

        # 2. 校验 status
        if deployment.status != "pending":
            raise SdnDeploymentError(
                "SDN_DEPLOYMENT_NOT_PENDING",
                params={"id": deployment_id, "status": deployment.status},
                status_code=409,
            )

        # 3. 校验 action（本 change 仅支持 create）
        if deployment.action != "create":
            raise SdnDeploymentError(
                "SDN_DEPLOYMENT_ACTION_NOT_SUPPORTED",
                params={"action": deployment.action},
                status_code=422,
            )

        # 4. 查 device + 校验
        device, password, device_err = get_device_with_password(db, deployment.device_id)
        if device_err is not None:
            # 设备不存在
            raise SdnDeploymentError(
                "SDN_DEVICE_NOT_FOUND",
                params={"id": deployment.device_id},
                status_code=404,
            )
        if not password:
            raise SdnDeploymentError(
                "SDN_DEVICE_NOT_WRITABLE",
                params={"name": device.name, "host": device.host},
                status_code=422,
            )

        # 5. 校验 host 白名单
        if not self._is_writable_host(device.host):
            raise SdnDeploymentError(
                "SDN_DEVICE_NOT_WRITABLE",
                params={"name": device.name, "host": device.host},
                status_code=422,
            )

        # 6. 解析 planned_config
        try:
            commands = self._parse_planned_config(deployment.planned_config)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # 标记 failed
            deployment.status = "failed"
            deployment.error = f"planned_config 格式错误: {e}"
            db.commit()
            db.refresh(deployment)
            logger.error(f"sdn deploy: deployment {deployment_id} planned_config 解析失败: {e}")
            raise SdnDeploymentError(
                "SDN_PLANNED_CONFIG_INVALID",
                params={"id": deployment_id, "error": str(e)},
                status_code=500,
            )

        # 7. 串行 NETCONF edit_config
        try:
            self._apply_commands(
                commands=commands,
                host=device.host,
                port=device.port,
                username=device.username,
                password=password,
            )
        except Exception as e:
            # 失败：记录 error + status=failed
            error_msg = classify_netconf_error(e) if hasattr(e, '__class__') else str(e)
            deployment.status = "failed"
            deployment.error = f"配置下发失败: {error_msg}"
            db.commit()
            db.refresh(deployment)
            logger.error(f"sdn deploy: deployment {deployment_id} NETCONF 失败: {error_msg}")
            # 业务视为已尝试下发（不是校验错），返回 200 + status=failed 由 router 处理
            return deployment

        # 8. 成功
        deployment.status = "success"
        deployment.error = None
        db.commit()
        db.refresh(deployment)
        logger.info(f"sdn deploy: deployment {deployment_id} 成功下发 {len(commands)} 条命令")
        return deployment

    @staticmethod
    def _is_writable_host(host: str) -> bool:
        """设备 host 后缀校验：仅 .5 / .6 允许下发"""
        if not host:
            return False
        return any(host.endswith(suffix) for suffix in WRITABLE_HOST_SUFFIXES)

    @staticmethod
    def _parse_planned_config(planned_config: Optional[str]) -> List[dict]:
        """解析 planned_config JSON 字符串 → List[{mode, command}]

        Raises:
            json.JSONDecodeError: JSON 格式错
            ValueError: 命令格式错
        """
        if not planned_config:
            raise ValueError("planned_config 为空")
        commands = json.loads(planned_config)
        if not isinstance(commands, list):
            raise ValueError("planned_config 不是 list")
        for i, cmd in enumerate(commands):
            if not isinstance(cmd, dict):
                raise ValueError(f"第 {i + 1} 条不是 dict")
            if "command" not in cmd:
                raise ValueError(f"第 {i + 1} 条缺少 command 字段")
            if not isinstance(cmd.get("command"), str):
                raise ValueError(f"第 {i + 1} 条 command 不是 str")
        return commands

    @staticmethod
    def _apply_commands(
        commands: List[dict],
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> None:
        """串行 NETCONF edit_config 下发

        简化方案（v1）：每条命令单独发一次 edit_config
        - 优点：单条失败立即停，错误定位准
        - 缺点：每条 ~0.5s SSH 开销

        未来 v2 优化：批量 <config> 一次下发
        """
        # H3C 命名空间
        h3c_ns = "http://www.h3c.com/netconf/config:1.0"

        with NetconfClient(host, port, username, password) as client:
            for i, cmd in enumerate(commands, 1):
                mode = cmd.get("mode", "merge")
                command_text = cmd["command"]
                # 构造 edit_config XML（单条命令）
                # H3C 接受 CLI 文本通过 <Configuration> 节点（v3.0 简化方案）
                config_xml = (
                    f'<config xmlns="{h3c_ns}">'
                    f'<Configuration>'
                    f'{command_text}'
                    f'</Configuration>'
                    f'</config>'
                )
                logger.debug(f"sdn deploy: [{i}/{len(commands)}] {command_text[:50]}")
                try:
                    client.edit_config(config_xml)
                except Exception as e:
                    # 立即停 + 抛出
                    logger.error(f"sdn deploy: 第 {i}/{len(commands)} 条失败: {e}")
                    raise
