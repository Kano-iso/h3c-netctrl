# add-integration-test-framework

## Why

v2.2.0 备份/接口功能上线后多次发现"API 单元测试 PASS 但真机不工作"：
- link-mode 切：单元 PASS，真机失败（H3C V7 端口、NETCONF/SSH 协议差异）
- VPN 绑定：单元 PASS，真机失败（unbind 预校验缺失）
- 备份回滚：单元 PASS，真机失败（reboot 等待不足）

**问题**：单元测试用 mock 设备，无法覆盖协议/时序/设备差异。

## What Changes

新增真机集成测试框架 + 10 个 case：

### 1. conftest.py `--integration` marker
- pytest_collection_modifyitems 默认 skip 集成测试
- `--integration` 参数显式启用（防止 CI 误跑）

### 2. backup 集成测试（4 case）— `tests/test_backup_integration.py`
- 192.168.100.4 backup startup 端到端
- 192.168.100.4 backup running 端到端
- 锁定不会被轮转（与 test_backup_rotation.py 单元测试互补）
- 备份列表 API 包含新备份

### 3. VPN 集成测试（6 case）— `tests/test_vpn_integration.py`
- 192.168.100.5 VPN 实例创建
- 接口绑定 VPN
- 接口解绑 VPN（v2.2.1 修的预校验）
- VPN 列表
- VPN 删除
- 异常：接口不存在

## Verification

```bash
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
# 默认模式：100 passed + 11 skipped (集成测试 skip)
# 启用集成：pytest --integration tests/test_*_integration.py
```

## 约束
- 集成测试不污染数据库：每个 case 创建/清理独立设备
- 不影响 dev/prod 容器
- 真机不可达时 skip（不 fail）
- 不 reboot 设备（避免网络中断）

## Files Changed
- `backend/tests/conftest.py`（新增 --integration marker）
- `backend/tests/test_backup_integration.py`（4 case）
- `backend/tests/test_vpn_integration.py`（6 case）
