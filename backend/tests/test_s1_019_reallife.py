"""S1-019 真机生命周期集成测试（默认 skip，需显式准入）。

目标：用真实 `.5 / 192.168.100.5 / SWC / S6850 T7064P15 / LSTN` 走完 S1 后端完整可恢复链路，
并**诚实表达**无下联主机时的最终业务状态（degraded/unknown，绝不伪造业务成功）。

S1-020 修订：不再把 predeploy 阻断断言为 PASS。修复「首次接入自阻断」（`_l2_ready_status` 对
`vsi_up` 无条件必需）后，真机应走完 preview → execute → apply → readback GE1/0/10 AC/xconnect
→ complete → access withdraw → VPC withdraw；无本地绑定 + vsi_up=Down 不再阻断第一个本地 AC。

安全准入（三重门，缺一即 skip）：
  1. `-m integration --integration`（conftest 全局 integration gate）
  2. 环境变量 `S1_019_REAL=1`
  3. 环境变量 `S1_019_REAL_HOST=192.168.100.5`（仅允许 .5，禁止 .6 / 管理口 / GE1/0/1~3）

凭据：`DEVICE_USERNAME` / `DEVICE_PASSWORD` 从 `.env` 注入容器环境，本测试只读不打印；
密码用 conftest 注入的合成 `ENCRYPTION_KEY` 做 Fernet 加解密（进程内自洽），不落盘。

写入边界：
  - 业务写入全部走 backend API/executor（LSTN→SSH22 CLI），不裸写 SSH/paramiko。
  - 设备仅 `.5`；接口仅 `GigabitEthernet1/0/10`；不 save / 不改 startup-config。

标准跑法（唯一、可复用的宿主安全 runner，位于 `openspec/changes/next-s1-backend/qa/`）：
  cd openspec/changes/next-s1-backend/qa
  S1_019_REAL=1 S1_019_REAL_HOST=192.168.100.5 \
    ./run_s1_019_real_lifecycle.sh --integration --cleanup-shared
  # runner 默认拒绝真机：四重门禁（--integration / S1_019_REAL=1 / 精确 .5 / --cleanup-shared）、
  # pytest 前基线核对（共享对象已存在则拒绝承担所有权）、进入可写阶段后 trap 精确兜底清理、
  # 最终 readback 确认回到基线、本机 flock 锁防并发。
  # 本文件（裸 pytest）只是 runner 内部实现，**不承担**共享对象清理（见下方「共享对象」）。

共享对象说明（如实记录）：
  - 本测试自身的 `finally` 只做 VPC withdraw（删 VSI/Vsi-interface/RD）。
  - `sdn_l3vpn` 与 `vxlan tunnel mac-learning disable` 是产品保留的共享对象，本测试**不负责**删除；
    由 runner（进入可写阶段后）按恢复清单精确兜底清理，或由历史轮次的测试外 ops-toolkit 监督清理
    （S1-020 真机运行后两对象确有残留，随后由测试外的 ops-toolkit 精确兜底并最终 readback 干净）。
"""
import json
import os

import pytest

import app.models  # noqa: F401
from app.main import app
from app.models import Device, SdnPortBinding, SdnResourceClaim

REAL_ENABLED = os.environ.get("S1_019_REAL", "0") == "1"
REAL_HOST = os.environ.get("S1_019_REAL_HOST", "")
TARGET_HOST = "192.168.100.5"


def _require_real():
    if not REAL_ENABLED:
        pytest.skip("S1_019_REAL != 1：默认不连真机")
    if REAL_HOST != TARGET_HOST:
        pytest.skip(f"S1_019_REAL_HOST={REAL_HOST!r} != {TARGET_HOST}（仅允许 .5）")


def _ssh_text(ssh, commands):
    out = ssh.execute_commands(commands, delay_ms=300)
    return "\n".join(r.get("output", "") or "" for r in out)


@pytest.mark.integration
def test_s1_019_full_lifecycle_real(client, db):
    _require_real()

    username = os.environ.get("DEVICE_USERNAME")
    password = os.environ.get("DEVICE_PASSWORD")
    if not username or not password:
        pytest.fail("DEVICE_USERNAME/DEVICE_PASSWORD 未注入（禁止 admin fallback）")

    from app.utils.crypto import encrypt_password
    from app.utils.ssh_executor import SSHExecutor

    # ── 0. 设备身份交叉确认（只读，走 backend SSHExecutor）──
    ssh = SSHExecutor(TARGET_HOST, 22, username, password, timeout=30)
    ident_text = _ssh_text(ssh, ["display bgp peer l2vpn evpn", "display version"])
    assert "1.1.1.4" in ident_text, f"设备身份不符（期望 Router ID 1.1.1.4）: {ident_text[:200]}"
    assert "S6850" in ident_text, f"设备身份不符（期望 S6850）: {ident_text[:200]}"

    # ── 1. seed 设备（真实凭据，仅内存）──
    device = Device(
        name="SWC",
        host=TARGET_HOST,
        username=username,
        password_encrypted=encrypt_password(password),
        protected_interfaces='["GigabitEthernet1/0/1","GigabitEthernet1/0/2","GigabitEthernet1/0/3","MGE0/0/0"]',
        platform="LSTN",
        sdn_role="evpn_leaf",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    vpc_id = None
    op_id = None
    try:
        # ── 2. tenant + VPC（真实 API，自动分配 VNI/VSI/Vsi-interface）──
        tenant_resp = client.post("/api/sdn/tenants", json={"name": "s1-019-nxt-real"}).json()
        assert tenant_resp["success"] is True, tenant_resp
        tenant_id = tenant_resp["data"]["id"]

        vpc_resp = client.post("/api/sdn/vpcs", json={
            "name": "s1-019-nxt-real", "tenant_id": tenant_id,
            "cidr": "10.19.0.0/24", "gateway_ip": "10.19.0.1",
        }).json()
        assert vpc_resp["success"] is True, vpc_resp
        vpc = vpc_resp["data"]
        vpc_id = vpc["id"]
        assert vpc["vni"] >= 20000 and vpc["vsi_name"].startswith("vpc"), vpc
        vsi_name = vpc["vsi_name"]

        # ── 3. VPC create：deploy 计划 → apply（真实 executor SSH 下发）──
        deploy_resp = client.post(f"/api/sdn/vpcs/{vpc_id}/deploy", json={
            "device_ids": [device.id], "auto_apply": False, "include_port_bindings": False,
        }).json()
        assert deploy_resp["success"] is True, deploy_resp
        create_dep = next(d for d in deploy_resp["data"]["deployments"] if d["action"] == "create")
        apply_resp = client.post(f"/api/sdn/deployments/{create_dep['id']}/apply").json()
        assert apply_resp["success"] is True, apply_resp
        assert apply_resp["data"]["status"] == "success", apply_resp

        # ── 4. 真实 display 采集 + 目标 RD Type-3 作用域证据 ──
        sync_resp = client.post(f"/api/sdn/vpcs/{vpc_id}/devices/{device.id}/validation/sync", json={}).json()
        assert sync_resp["success"] is True, sync_resp
        details = sync_resp["data"]["validation_details"]
        assert details["vsi_exists"]["ok"] is True, details
        assert details["bgp_peer_established"]["ok"] is True, details
        assert details["type3_present"]["ok"] is True, details  # 目标 RD 1:{vni} 块内 [3]
        print(f"[S1-019] create后: vsi_exists=True bgp_peer=True type3_present=True "
              f"vsi_up={details['vsi_up']['ok']} (无 AC 时 VSI State: Down，S1-020 起不再阻断首个 AC)")

        # ── 5. terminal access：preview → execute（S1-020 修复后应成功）──
        port = "GigabitEthernet1/0/10"
        body = {
            "device_id": device.id, "if_index": 10, "interface_name": port,
            "access_vlan": None, "service_instance": 3200, "expected_host_ip": "10.19.0.2",
        }
        preview = client.post(f"/api/sdn/vpcs/{vpc_id}/access-preview", json=body).json()
        assert preview["success"] is True, preview
        assert preview["data"]["predeploy_status"] == "ready", preview
        plan_id = preview["data"]["plan_id"]

        execute = client.post(f"/api/sdn/vpcs/{vpc_id}/access", json={
            **body, "idempotency_key": "s1-019-nxt-real", "plan_id": plan_id, "auto_apply": False,
        }).json()
        assert execute["success"] is True, execute
        op_id = execute["data"]["operation_id"]
        print(f"[S1-019] access execute success: operation_id={op_id}")

        # ── 6. access apply（真实 executor 下发 port_bind，创建 AC）──
        apply_resp = client.post(f"/api/sdn/operations/{op_id}/apply").json()
        assert apply_resp["success"] is True, apply_resp
        assert apply_resp["data"]["status"] == "awaiting_validation", apply_resp
        print(f"[S1-019] access apply success: status={apply_resp['data']['status']}")

        # ── 7. 配置层回读：GE1/0/10 的 service-instance/xconnect AC 实际存在 ──
        rb_text = _ssh_text(ssh, [f"display current-configuration interface {port}"])
        assert f"service-instance 3200" in rb_text, f"回读缺少 service-instance 3200: {rb_text}"
        assert f"xconnect vsi {vsi_name}" in rb_text, f"回读缺少 xconnect vsi {vsi_name}: {rb_text}"
        print("[S1-019] GE1/0/10 AC 回读确认：service-instance 3200 + xconnect vsi 存在")

        # ── 8. access complete（无下联主机 → 诚实 degraded/unknown，不冒充业务成功）──
        complete = client.post(f"/api/sdn/operations/{op_id}/complete", json={"force_validation": True}).json()
        assert complete["success"] is True, complete
        cdata = complete["data"]
        assert cdata["status"] in ("degraded", "unknown", "failed"), cdata
        assert cdata["dimensions"]["business_validation"]["host_observed"] is False, cdata
        print(f"[S1-019] access complete 诚实表达: status={cdata['status']} "
              f"host_observed={cdata['dimensions']['business_validation']['host_observed']}")

        # ── 9. access withdraw（先恢复 GE1/0/10）──
        wd = client.post(f"/api/sdn/operations/{op_id}/withdraw", json={}).json()
        assert wd["success"] is True, wd
        assert wd["data"]["status"] == "withdrawn", wd
        print("[S1-019] access withdraw success（GE1/0/10 已恢复）")

        # ── 10. 回读：GE1/0/10 AC 已撤销 ──
        rb2_text = _ssh_text(ssh, [f"display current-configuration interface {port}"])
        assert "service-instance 3200" not in rb2_text, f"withdraw 后仍残留 service-instance 3200: {rb2_text}"
        assert f"xconnect vsi {vsi_name}" not in rb2_text, f"withdraw 后仍残留 xconnect vsi: {rb2_text}"
        print("[S1-019] withdraw 后 GE1/0/10 回读确认：service-instance/xconnect 已撤销")

    finally:
        # ── 补偿清理：VPC withdraw（真实 executor，删除 VSI/Vsi-interface/RD）──
        # 注意：本测试只负责撤自己创建的 VPC 对象；sdn_l3vpn / vxlan global 两个共享对象
        # 由宿主 runner 兜底清理（裸 pytest 不承担，见 docstring「共享对象」）。
        if vpc_id:
            try:
                wd_vpc = client.post(f"/api/sdn/vpcs/{vpc_id}/withdraw", json={
                    "device_ids": [device.id], "auto_apply": True, "include_port_bindings": True,
                }).json()
                print(f"[S1-019] vpc withdraw: success={wd_vpc.get('success')} "
                      f"deployments={len(wd_vpc.get('data', {}).get('deployments', []))}")
            except Exception as e:  # noqa: BLE001
                print(f"[S1-019] vpc withdraw failed: {e}")

    # ── 11. DB 收尾：无 active/expanding binding、无残留 claim ──
    active_bindings = db.query(SdnPortBinding).filter(SdnPortBinding.status.in_(("active", "expanding"))).count()
    unreleased_claims = db.query(SdnResourceClaim).filter(SdnResourceClaim.released_at.is_(None)).count()
    print(f"[S1-019] 收尾: active_bindings={active_bindings} unreleased_claims={unreleased_claims}")
    assert active_bindings == 0
    assert unreleased_claims == 0
    print("[S1-019] 真机生命周期完成；共享 sdn_l3vpn/vxlan global 由宿主 runner 兜底清理（本测试不负责）")
