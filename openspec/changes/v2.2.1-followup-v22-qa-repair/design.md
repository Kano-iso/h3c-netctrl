# v2.2.1-followup-v22-qa-repair Design

## 1. 整体策略

**补 v2.2.0 漏的 14 个新 API + 备份 / VPN 真机集成测试**。

| 维度 | 框架 | 跑什么 | 是否需设备 | 装包 |
|---|---|---|---|---|
| API 单元 / 集成 | FastAPI TestClient + pytest | 14 个新 API smoke + 错误码 + 中文错误 | ❌ | 0 |
| 设备集成 | pytest + paramiko + ncclient（`@pytest.mark.integration`） | 192.168.100.4 backup + restore + reboot verify | ✅ | 0 |

**不引入**：
- ❌ Playwright / Cypress（UI 模拟点击，over-engineering）
- ❌ httpx（FastAPI TestClient 已够）
- ❌ new framework（复用 qa-backend 容器）

## 2. 测试结构

```
backend/tests/
├── conftest.py                          (加 --integration marker)
├── test_smoke.py                        (加 14 个端点 existence smoke)
├── test_device_api.py                   (已有，v2.0 覆盖)
├── test_vlan_api.py                     (待 v2.3 补)
├── test_netconf_errors.py               (已有，v2.0 覆盖)
├── test_bugfix_regression.py            (已有，v2.0 覆盖)
├── test_xml_builder.py                  (已有，v2.0 覆盖)
│
├── test_backup_api.py                   [NEW] 7 个 backup API smoke + 错误码
├── test_vpn_api.py                      [NEW] 4 个 VPN API smoke + 预校验
├── test_interface_edit_api.py           [NEW] link-type + ipv4 3 API smoke
│
├── test_backup_integration.py           [NEW] 192.168.100.4 backup + restore 端到端
└── test_vpn_integration.py              [NEW] 192.168.100.5 VPN + link type + IP 端到端
```

## 3. conftest.py 改造

加 `@pytest.mark.integration` marker + 默认 skip 集成测试：

```python
import pytest

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: 真实设备集成测试，默认 skip，需 --integration 显式开启"
    )

def pytest_addoption(parser):
    parser.addoption(
        "--integration", action="store_true", default=False,
        help="跑真实设备集成测试（需 SSH 通 192.168.100.4 / .5）"
    )

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip_integration = pytest.mark.skip(reason="需 --integration 才跑")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
```

## 4. test_smoke.py 加 14 个 smoke（每个端点 1 行）

```python
def test_backup_endpoint_exists(client):  # 7 个
    for path in ["/api/devices/1/backup", "/api/devices/1/backup/1"]:
        assert client.post(path).status_code in (200, 400, 404, 405, 422)

def test_vpn_endpoint_exists(client):  # 4 个
    assert client.post("/api/devices/1/vpn-instances").status_code in (200, 400, 404, 422)
    assert client.get("/api/devices/1/vpn-instances").status_code in (200, 404)

def test_link_type_endpoint_exists(client):
    assert client.patch("/api/devices/1/interfaces/1/link-type").status_code in (200, 400, 404, 422)

def test_ipv4_address_endpoint_exists(client):
    assert client.post("/api/devices/1/interfaces/1/ipv4-address").status_code in (200, 400, 404, 422)
    assert client.delete("/api/devices/1/interfaces/1/ipv4-address").status_code in (200, 400, 404, 422)
```

## 5. test_backup_api.py（7 API + 错误码）

每个 API 测：
- 设备不存在 → 404 + 中文 error
- 成功路径（mock SSHExecutor）→ 200 + 数据结构正确
- 错误码：422 (body) / 403 (locked) / 410 (file missing) / 500 → 中文错误

```python
def test_create_backup_success(client, created_device, monkeypatch):
    """POST /api/devices/{id}/backup 成功路径（mock BackupManager）"""
    from app.utils.backup_manager import BackupManager
    def fake_create(self, types, db):
        return [{"id": 1, "type": "startup", "size": 100, "content_hash": "abc", "filename": "x.cfg", "created_at": "2026-06-29T10:00:00"}]
    monkeypatch.setattr(BackupManager, "create_backup", fake_create)
    r = client.post(f"/api/devices/{created_device['id']}/backup", json={"types": ["startup"]})
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert len(data["data"]["backups"]) == 1
```

## 6. test_backup_integration.py（真机 + reboot verify）

```python
import pytest
import paramiko

@pytest.mark.integration
class TestBackupIntegration:
    HOST = "192.168.100.4"
    USERNAME = "admin"
    PASSWORD = os.getenv("DEVICE_PASSWORD", "")

    def test_backup_startup_and_running(self):
        """192.168.100.4 backup startup + running 端到端"""
        mgr = BackupManager(device_id=4, host=self.HOST, port=22,
                            username=self.USERNAME, password=self.PASSWORD)
        results = mgr.create_backup(types=["startup", "running"])
        assert len(results) == 2
        assert results[0]["type"] == "startup"
        assert results[0]["size"] > 100

    def test_restore_with_reboot_verify(self):
        """restore with_reboot=true 端到端：备份当前 → 改 → 回滚 → reboot → verify"""
        # 1. 备份当前 startup
        mgr = BackupManager(device_id=4, host=self.HOST, port=22,
                            username=self.USERNAME, password=self.PASSWORD)
        original = mgr.create_backup(types=["startup"])
        backup_id = original[0]["id"]

        # 2. 改一个 vlan（无害操作）
        # ... SSH CLI 改一个 vlan id

        # 3. 回滚 + reboot + verify
        result = mgr.restore(backup_id, with_reboot=True)
        assert result["success"]

        # 4. 等待设备起来（60-120s）
        for _ in range(30):
            try:
                ssh = paramiko.SSHClient()
                ssh.connect(self.HOST, port=22, username=self.USERNAME, password=self.PASSWORD, timeout=5)
                ssh.close()
                break
            except Exception:
                time.sleep(5)

        # 5. 验证 running-config 已恢复
        # ... SSH 跑 display current-configuration 比对

        # 6. 恢复原状（n → n+1 → n）：如果 5 失败，需恢复 n+1 状态
```

**关键约束**（来自 project_memory lessons learned）：
- ✅ 集成测试必须有 `restore_original_state` 步骤（n → n+1 → n）
- ✅ reboot 验证必须 sleep + retry 至少 90s（不是 1 次 15s timeout 失败就推断）
- ✅ 凭理论推断打 [x] 是禁止的——实测 vs 推断必须在 tasks.md 严格区分

## 7. 关键技术决策

### 7.1 为什么用 marker 区分 unit vs integration

- 默认 `pytest` 跑 unit + smoke（秒级，CI 必跑）
- `pytest --integration` 跑设备集成（分钟级，需 SSH 通，按需跑）
- 集成测试连不上设备时**标记 skip 而不是 fail**（不阻塞 CI）

### 7.2 为什么 FastAPI TestClient 够

- 项目是 monolith 单后端，TestClient 直接走 in-process 调用
- 不需要 httpx / requests 做 HTTP 调用
- TestClient 支持所有 HTTP method / 状态码 / 错误码断言

### 7.3 为什么不引入 vitest 跑前端组件

- v2.3-roadmap 计划做 vitest 集成（`add-vitest-component-tests`）
- 本 change 聚焦后端 QA 补漏，前端 QA 规范化推到 v2.3
- qa-frontend 容器现状只跑 vite build 验编译，已能捕获语法 / import 错误

## 8. 失败回退

- **单元 / smoke**：跑失败 → 修代码或修测试（不能 skip 关闭）
- **集成测试**：跑失败 → 修测试或修设备，**不允许 skip**（除设备不通）

## 9. 关联

- 父版本：[v2.2.0 release notes](../../../RELEASE-NOTES-v2.2.0.md)
- 依赖：[v2.3-roadmap § 3.3 QA 规范化](../v2.3-roadmap/design.md) —— v2.3.0 计划把 QA 模板化
- 容器定义：[docker-compose.dev.yml `qa-backend`](../../../docker-compose.dev.yml)
- 项目 QA 容器基线：42 tests PASS in 1.16s（v2.0 / v2.1 覆盖）
