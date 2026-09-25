"""S1-027/S2-018 合成数据 seed（隔离 SQLite；仅测试合成值，无任何生产凭据/数据）。

在 launcher 于 uvicorn 之前对 STACK_QA_DIR/db.sqlite 执行：建表 + 写入合成
EVPN Leaf / tenant / 已部署 VPC / 新鲜验证快照（业务端口可用、predeploy ready）。
设备 host 用 TEST-NET（192.0.2.0/24）合成地址——即使误触发真实连接也会失败暴露。

S2-018 追加：第二台 evpn_leaf（Leaf-Spare，无任何记录 → not_targeted、覆盖缺口）
+ 一台非 EVPN 设备（Access-QA，sdn_role=access → 排除、不进 scope 分母），
形成「同一 VPC 覆盖 1/2」的 S2 真实栈验收基线。
"""

import json
import os
from datetime import timedelta

from app.database import SessionLocal
import app.models  # noqa: F401  确保全部模型注册到 metadata
from app.models import Device, SdnDeployment, SdnTenant, SdnValidationSnapshot, SdnVpc
from app.utils.crypto import encrypt_password


def seed() -> None:
    # 表结构由 uvicorn 启动时 alembic upgrade head 建立（launcher 先起后端再 seed）
    db = SessionLocal()
    try:
        # 幂等清空本 seed 拥有域（只清合成实体，不留半状态）
        for model in (SdnValidationSnapshot, SdnDeployment, SdnVpc, SdnTenant, Device):
            db.query(model).delete()
        db.commit()

        device = Device(
            name="Leaf-Stack",
            host="192.0.2.10",  # TEST-NET 合成地址
            username="qa",
            password_encrypted=encrypt_password("stack-qa-synthetic"),
            protected_interfaces="[]",
            platform="LSTN",
            sdn_role="evpn_leaf",
        )
        spare = Device(
            name="Leaf-Spare",
            host="192.0.2.11",  # TEST-NET 合成地址（未覆盖 Leaf）
            username="qa",
            password_encrypted=encrypt_password("stack-qa-synthetic"),
            protected_interfaces="[]",
            platform="LSTN",
            sdn_role="evpn_leaf",
        )
        access = Device(
            name="Access-QA",
            host="192.0.2.20",  # TEST-NET 合成地址（非 EVPN）
            username="qa",
            password_encrypted=encrypt_password("stack-qa-synthetic"),
            protected_interfaces="[]",
            platform="LSTN",
            sdn_role="access",
        )
        db.add_all([device, spare, access])
        db.flush()

        tenant = SdnTenant(name="stack-qa", rd="65000:1", import_rt="65000:1", export_rt="65000:1", l3_vni=10001)
        db.add(tenant)
        db.flush()

        vpc = SdnVpc(
            tenant_id=tenant.id,
            name="stack-vpc",
            cidr="10.1.0.0/24",
            gateway_ip="10.1.0.1",
            gateway_mac="00:00:5e:00:01:01",
            vni=10001,
            vsi_name="vsi-stack",
            vsi_interface=1,
            vlan_id=100,
            status="deployed",
            version=0,
        )
        db.add(vpc)
        db.flush()

        dep = SdnDeployment(
            vpc_id=vpc.id, device_id=device.id, action="create", unit="vpc-create-all",
            planned_config="[]", status="success",
        )
        db.add(dep)
        db.commit()
        db.refresh(dep)
        # CR8: 持久化 config 完成时间（真实 executor 在 I/O 成功后写入）
        dep.config_completed_at = dep.created_at
        db.commit()

        snap = SdnValidationSnapshot(
            vpc_id=vpc.id,
            device_id=device.id,
            validation_result="active",
            collection_started_at=dep.config_completed_at + timedelta(seconds=1),
            collection_completed_at=dep.config_completed_at + timedelta(seconds=2),
            snapshot_data=json.dumps({
                "commands": {
                    "display bgp peer l2vpn evpn": {"success": True, "output": "Peer: State: Established", "error": None},
                    f"display l2vpn vsi name {vpc.vsi_name} verbose": {"success": True, "output": f"VSI Name: {vpc.vsi_name}\n VSI State: Up", "error": None},
                    f"display current-configuration interface Vsi-interface{vpc.vsi_interface}": {"success": True, "output": f"interface Vsi-interface{vpc.vsi_interface}\n l3-vni {tenant.l3_vni}", "error": None},
                    "display bgp l2vpn evpn": {"success": True, "output": "Route Type: [3]", "error": None},
                }
            }, ensure_ascii=False),
            validation_details=json.dumps({
                "vsi_exists": {"ok": True}, "vsi_up": {"ok": True}, "type3_present": {"ok": True},
                "raw_has_error": {"ok": True}, "bgp_peer_established": {"ok": True},
                "vsi_interface_exists": {"ok": True}, "l3_vni_present": {"ok": True},
            }, ensure_ascii=False),
        )
        db.add(snap)
        # 非 EVPN 设备带观测记录 → 走 projection 的 excluded（排除、不计入 scope 分母），
        # S2-018 让「非 EVPN 已排除」计数可见；快照内容不影响排除判定。
        access_snap = SdnValidationSnapshot(
            vpc_id=vpc.id,
            device_id=access.id,
            validation_result="active",
            collection_started_at=dep.config_completed_at + timedelta(seconds=3),
            collection_completed_at=dep.config_completed_at + timedelta(seconds=4),
            snapshot_data=json.dumps({"commands": {}}, ensure_ascii=False),
            validation_details=json.dumps({}, ensure_ascii=False),
        )
        db.add(access_snap)
        db.commit()
        print(f"SEED_OK leaf_id={device.id} spare_id={spare.id} access_id={access.id} tenant_id={tenant.id} vpc_id={vpc.id} db={os.environ.get('DB_PATH', '')}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
