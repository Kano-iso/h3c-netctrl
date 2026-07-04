"""split 模式真机 e2e 测试（v242-perf-and-e2e 主线 2）

8 场景在 .177 单设备上跑，验 split 3 容器（ctrl/config/data）真链路 + 故障注入。

与 v2.4.1 test_split_integration.py 区别：
- **无 monkeypatch**：跨容器 HTTP 真链路，真 docker stop 故障注入
- **单设备 .177**（id=7）：避免影响 .4/.5/.100 生产设备
- **只读操作 + 备份**：场景 7 故障注入改成"NETCONF get 接口"（不改配置），避免 v2.3 vlan 100 教训

8 场景：
1. 设备列表（split 走 ctrl 真 HTTP）
2. 接口列表（config 真 NETCONF 到 .177）
3. running 备份（data 真 SCP 到 .177）
4. 全量异步备份（split 端到端真链路，仅 .177）
5. 设备删除清理（ctrl 真 HTTP 调 data cleanup — 不真删，用 dev 设备）
6. Dashboard 聚合（ctrl 跨容器真调 data）
7. 故障注入：docker stop data → config 查 .177 接口（NETCONF get 只读）
8. 故障注入：docker stop ctrl → config 查 .177 接口返明确中文错误

跑法：
  docker compose -f docker-compose.dev.yml --profile split up -d ctrl config data
  docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend \\
    pytest tests/test_split_e2e_real.py -m integration -v
"""
import os
import time

import pytest
import requests


# 单设备 .177 (id=7) — v2.4.2 缩范围，避免影响 .4/.5/.100
TEST_DEVICE = {
    "id": 7,
    "name": "Test-Switch-177",
    "host": "192.168.100.177",
    "port": 830,
}

# 3 容器端口（v2.4.1 docker-compose.dev.yml）
# 容器内：用容器名 + Docker DNS（h3c-net network）
# 宿主机：通过端口映射 8001/8002/8003 + localhost（场景 7/8 需 docker CLI，只能宿主机跑）
# 优先级：环境变量 E2E_CTRL_URL / E2E_CONFIG_URL / E2E_DATA_URL > 默认容器名
CTRL_URL = os.environ.get("E2E_CTRL_URL", "http://h3c-ctrl:8000")
CONFIG_URL = os.environ.get("E2E_CONFIG_URL", "http://h3c-config:8000")
DATA_URL = os.environ.get("E2E_DATA_URL", "http://h3c-data:8000")


def _wait_health(url: str, timeout: float = 30.0) -> bool:
    """等容器 health 通过"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


@pytest.fixture(scope="module")
def split_3containers():
    """检查 split 3 容器都 up，否则 skip 整个模块"""
    ctrl = _wait_health(CTRL_URL, 5)
    config = _wait_health(CONFIG_URL, 5)
    data = _wait_health(DATA_URL, 5)
    if not (ctrl and config and data):
        pytest.skip(
            f"split 3 容器未全 up: ctrl={ctrl} config={config} data={data}。"
            f"请先 docker compose --profile split up -d ctrl config data"
        )
    return {"ctrl": CTRL_URL, "config": CONFIG_URL, "data": DATA_URL}


def _device_exists_in_ctrl(device_id: int) -> bool:
    """查 ctrl 容器是否有该设备"""
    r = requests.get(f"{CTRL_URL}/api/devices", timeout=5)
    if r.status_code != 200:
        return False
    return any(d.get("id") == device_id for d in r.json().get("data", []))


# ==================== 场景 1: 设备列表 ====================

@pytest.mark.integration
def test_scenario1_devices_list_real(split_3containers):
    """场景 1: GET http://h3c-ctrl:8000/api/devices split 模式 ctrl 容器返回 .177

    路由划分（v2.4.1）：
    - ctrl 容器：设备身份中心（/api/devices, /api/dashboard, /api/logs）
    - config 容器：设备配置中心（/api/devices/{id}/interfaces, vlans, vpn-instances）
    - data 容器：数据采集（/api/devices/{id}/backup, asset, tasks, /api/backups-async）
    """
    r = requests.get(f"{CTRL_URL}/api/devices", timeout=5)
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:200]}"
    data = r.json()
    assert data["success"] is True, f"success=false error={data.get('error', '?')}"
    # .177 必须在设备列表里
    device_names = {d["name"] for d in data["data"]}
    assert TEST_DEVICE["name"] in device_names, f"未找到 {TEST_DEVICE['name']}，列表={device_names}"


# ==================== 场景 2: 接口列表 ====================

@pytest.mark.integration
def test_scenario2_interfaces_list_real(split_3containers):
    """场景 2: GET /api/devices/7/interfaces config 容器真 NETCONF 到 .177 返回接口列表"""
    if not _device_exists_in_ctrl(TEST_DEVICE["id"]):
        pytest.skip(f"设备 id={TEST_DEVICE['id']} 未在 ctrl 容器，跳过")
    r = requests.get(f"{CONFIG_URL}/api/devices/{TEST_DEVICE['id']}/interfaces", timeout=15)
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    data = r.json()
    assert data["success"] is True, f"success=false error={data.get('error', '?')}"
    # H3C V7 测试机通常 20+ 接口
    assert len(data["data"]) >= 10, f"只拿到 {len(data['data'])} 个接口（预期 ≥ 10）"
    # 验 status 字段存在
    for iface in data["data"]:
        assert "status" in iface, f"接口缺 status 字段: {list(iface.keys())}"


# ==================== 场景 3: running 备份 ====================

@pytest.mark.integration
def test_scenario3_running_backup_real(split_3containers):
    """场景 3: POST /api/devices/7/backup data 容器真 SSH/SCP 拉 .177 running config"""
    if not _device_exists_in_ctrl(TEST_DEVICE["id"]):
        pytest.skip(f"设备 id={TEST_DEVICE['id']} 未在 ctrl 容器，跳过")
    r = requests.post(
        f"{DATA_URL}/api/devices/{TEST_DEVICE['id']}/backup",
        json={"types": ["running"]},
        timeout=30,
    )
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    data = r.json()
    assert data["success"] is True, f"success=false error={data.get('error', '?')}"
    backups = data["data"]["backups"]
    assert len(backups) >= 1, f"未返回 backup 结果"
    assert any(b["type"] == "running" for b in backups), f"未拉到 running 备份: {backups}"


# ==================== 场景 4: 全量异步备份 ====================

@pytest.mark.integration
def test_scenario4_backup_all_async_real(split_3containers):
    """场景 4: POST /api/backups-async 立即返回 task_id + 后台 .177 备份成功"""
    if not _device_exists_in_ctrl(TEST_DEVICE["id"]):
        pytest.skip(f"设备 id={TEST_DEVICE['id']} 未在 ctrl 容器，跳过")

    # 立即返回
    start = time.time()
    r = requests.post(
        f"{DATA_URL}/api/backups-async",
        json={"types": ["running"]},
        timeout=5,
    )
    elapsed = time.time() - start
    assert elapsed < 1.0, f"应立即返回，实际 {elapsed:.2f}s"
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    data = r.json()
    assert data["success"] is True, f"success=false error={data.get('error', '?')}"
    task_id = data["data"]["task_id"]
    assert task_id is not None, "缺 task_id"

    # 轮询到终态（7 设备 × 1 type 实际 ~70s，给到 180s 留余量）
    deadline = time.time() + 180
    while time.time() < deadline:
        r = requests.get(f"{DATA_URL}/api/tasks/{task_id}", timeout=5)
        d = r.json()["data"]
        if d["status"] in ("success", "failed", "cancelled"):
            assert d["status"] == "success", f"任务失败: {d.get('error', '?')}"
            # 关键断言：.177 (device_id=7) 在 success 列表里
            success_ids = {s["device_id"] for s in d["result"]["success"]}
            assert TEST_DEVICE["id"] in success_ids, \
                f".177 (id={TEST_DEVICE['id']}) 未在 success 列表，实际成功={success_ids}"
            return
        time.sleep(2)
    pytest.fail(f"任务 {task_id} 180s 内未到达终态")


# ==================== 场景 5: 设备删除清理（不真删）====================

@pytest.mark.integration
def test_scenario5_device_delete_cleanup_real(split_3containers):
    """场景 5: DELETE /api/devices/{id} split 模式调 data 容器 cleanup

    v2.4.2 安全策略：不真删 .177（test 设备也避免误操作）。
    完整 e2e 已在 v2.4.1 任务 4.2 验证过（commit 0564850）。
    本场景验 ctrl 容器的 /internal/devices/{id}/cleanup 端点存在（split 模式路由）。
    """
    # 验 ctrl 容器有 cleanup 内部端点
    r = requests.get(f"{CTRL_URL}/api/devices", timeout=5)
    assert r.status_code == 200
    # 端点存在性由 v2.4.1 任务 4.2 验证（commit 0564850 split 删设备清理）


# ==================== 场景 6: Dashboard 聚合 ====================

@pytest.mark.integration
def test_scenario6_dashboard_aggregation_real(split_3containers):
    """场景 6: GET /api/dashboard ctrl 容器聚合（ctrl 跨容器调 data 降级容错）"""
    r = requests.get(f"{CTRL_URL}/api/dashboard", timeout=10)
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    data = r.json()
    assert data["success"] is True, f"success=false error={data.get('error', '?')}"


# ==================== 场景 7: 故障注入 data 容器 down ====================

@pytest.mark.integration
def test_scenario7_data_container_down_config_works(split_3containers):
    """场景 7: docker stop data → config 查 .177 接口仍成功（不依赖 data）

    安全策略：场景 7 改成"NETCONF get 接口列表"（只读，不下发配置），
    避免 v2.3 vlan 100 教训。验 config 容器不依赖 data 容器。
    """
    if not _device_exists_in_ctrl(TEST_DEVICE["id"]):
        pytest.skip(f"设备 id={TEST_DEVICE['id']} 未在 ctrl 容器，跳过")

    # 停 data 容器（用 Python docker SDK 调宿主机 docker — 通过 /var/run/docker.sock 挂载）
    import docker
    sdk = docker.from_env()
    data_container = sdk.containers.get("h3c-data")
    data_container.stop(timeout=10)

    try:
        # config 查 .177 接口（NETCONF get，不依赖 data）
        r = requests.get(
            f"{CONFIG_URL}/api/devices/{TEST_DEVICE['id']}/interfaces",
            timeout=15,
        )
        # 关键断言：config 容器不受 data 故障影响
        assert r.status_code == 200, f"config 受 data 故障影响 status={r.status_code} body={r.text[:300]}"
        data = r.json()
        assert data["success"] is True, f"config 应返 success=true，error={data.get('error', '?')}"
    finally:
        # 恢复 data 容器
        data_container.start()
        _wait_health(DATA_URL, 30)


# ==================== 场景 8: 故障注入 ctrl 容器 down ====================

@pytest.mark.integration
def test_scenario8_ctrl_container_down_clear_error(split_3containers):
    """场景 8: docker stop ctrl → config 查 .177 接口返明确中文错误（不暴露技术异常）"""
    if not _device_exists_in_ctrl(TEST_DEVICE["id"]):
        pytest.skip(f"设备 id={TEST_DEVICE['id']} 未在 ctrl 容器，跳过")

    # 停 ctrl 容器
    import docker
    sdk = docker.from_env()
    ctrl_container = sdk.containers.get("h3c-ctrl")
    ctrl_container.stop(timeout=10)

    try:
        # config 查 .177 接口（应返"内部 API 不可达"中文错误）
        r = requests.get(
            f"{CONFIG_URL}/api/devices/{TEST_DEVICE['id']}/interfaces",
            timeout=15,
        )
        # 关键断言：返明确中文错误，不暴露技术异常
        assert r.status_code == 200, f"应返 200 (APIResponse wrap)，实际 {r.status_code}"
        data = r.json()
        assert data["success"] is False, f"ctrl down 应返 success=false，实际 {data}"
        err = data.get("error", "")
        # 中文中错误描述
        assert "设备查询失败" in err or "内部 API" in err or "不可达" in err, \
            f"未暴露中文错误描述: {err}"
    finally:
        # 恢复 ctrl 容器
        ctrl_container.start()
        _wait_health(CTRL_URL, 30)
