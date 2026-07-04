# add-integration-test-framework Spec Deltas (v242-qa-and-tooling)

> 本 change 在 [add-integration-test-framework](../../specs/add-integration-test-framework/spec.md) 之上 MODIFIED：
> 容器集成测试默认指向 Test-Switch-177。

---

## MODIFIED Requirements

### Requirement: 容器集成测试默认指向 Test-Switch-177

`backend/tests/conftest.py` 的真机 e2e fixture MUST 默认指向 Test-Switch-177 (192.168.100.177)：

- **新增 fixture**：`@pytest.fixture def test_switch_device(): ...` 返回 .177 设备对象
- **现有 fixture 改造**：`split_devices` 列表的默认值改为 `[.177]`，而非 `.4/.5/.100/.177`
- **真机 e2e 标记**：保持 `--integration` 显式启用
- **理由**：qa 反复跑，不污染生产设备

#### Scenario: 真机 e2e 默认指向 .177

- **WHEN** `pytest --integration tests/test_split_integration.py`（不带设备参数）
- **THEN** fixture MUST 默认注入 .177 设备
- **AND** 跑真机 e2e 时只连 .177

#### Scenario: 显式指定多设备

- **WHEN** `pytest --integration --devices=192.168.100.4,192.168.100.5 ...`
- **THEN** fixture MUST 解析为 [.4, .5]（生产设备，需用户显式）
