# spec: add-integration-test-framework

## 能力

真机集成测试框架（profile: integration，--integration 显式启用）。

## 范围

### 框架
- conftest.py `--integration` marker
- pytest_collection_modifyitems 默认 skip 集成测试
- 显式 `--integration` 参数启用

### 集成测试用例
- **backup（4 case）** — 192.168.100.4
  - backup startup
  - backup running
  - 锁定不被轮转
  - 列表 API 包含新备份
- **VPN（6 case）** — 192.168.100.5
  - VPN 实例创建
  - 接口绑定 VPN
  - 接口解绑 VPN（v2.2.1 修的预校验）
  - VPN 列表
  - VPN 删除
  - 异常：接口不存在

## 设计决策

- **不污染数据库**：每个 case 创建/清理独立设备
- **不影响 dev/prod**：不 reboot 设备
- **真机不可达时 skip**：不 fail
- **复用一个真实设备**：192.168.100.4 (backup) + 192.168.100.5 (VPN)

## 验收标准

- [x] `pytest --integration` 跑通
- [x] 设备不可达时 skip 不 fail
- [x] 测试设备最后状态恢复（n → n+1 → n）

## 关联 change
- `openspec/changes/archive/2026-06-29-add-integration-test-framework/`
- `backend/tests/test_backup_integration.py`
- `backend/tests/test_vpn_integration.py`
- `backend/tests/conftest.py`
