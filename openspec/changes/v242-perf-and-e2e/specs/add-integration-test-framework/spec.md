# v242-perf-and-e2e Spec Deltas

> 本 change 在 [add-integration-test-framework](../../specs/add-integration-test-framework/spec.md) 之上 MODIFIED：
> 性能压测 + split 模式真机 e2e。

---

## MODIFIED Requirements

### Requirement: locust 性能压测 .177 NETCONF / SSH

`backend/tests/perf/locustfile.py` MUST 提供 100 并发接口查询 + 50 并发备份压测能力：

- **目标设备**：Test-Switch-177 (192.168.100.177, id=7) **唯一**
- **绝对不压**：.4 / .5 / .100 / .177 之外的设备
- **路径**：
  - 100 并发接口：locust → backend (monolith) → NETCONF 真链路到 .177
  - 50 并发备份：locust → backend (data 容器，split 模式) → SSH/SCP 真链路到 .177
- **阈值**：
  - 接口查询 P99 < 5s
  - 备份 P99 < 30s
  - 失败率 < 1%
  - SSH 并发连接 < 50
  - 设备 CPU < 80%
- **装包**：`locust==2.31.0`（~10MB）
- **场景脚本**：`backend/tests/perf/scenarios/100_concurrent_interfaces.sh` + `50_concurrent_backup.sh`

#### Scenario: 100 并发接口压测达标

- **WHEN** 跑 `locust -u 100 -r 10 --run-time 60s --headless --host http://backend:8000`（场景：GET /api/devices/7/interfaces）
- **THEN** P99 MUST < 5s
- **AND** 失败率 MUST < 1%
- **AND** .177 SSH 连接数 MUST < 50

#### Scenario: 50 并发备份压测达标

- **WHEN** 跑 `locust -u 50 -r 5 --run-time 60s --headless`（场景：POST /api/devices/7/backup）
- **THEN** P99 MUST < 30s
- **AND** 失败率 MUST < 1%

#### Scenario: 压测前设备可达性检查

- **WHEN** 跑压测脚本
- **THEN** MUST 先调 `ops-toolkit check-host.sh --device test` 验 .177 可达
- **AND** 不通 MUST exit 1（不强行压）

### Requirement: split 模式真机 e2e 4 设备 8 场景

`backend/tests/test_split_e2e_real.py` MUST 跑 4 设备 × 8 场景 split 模式端到端测试，**无 monkeypatch**：

- **测试设备**：.4 / .5 / .100 / .177（4 台）
- **8 场景**（与 v241-supplement 一致，真链路版）：
  1. 设备列表（`GET /api/devices`，split 走 ctrl 真 HTTP）
  2. 接口列表（`GET /api/devices/{id}/interfaces`，config 真 NETCONF 到设备）
  3. running 备份（`POST /api/devices/{id}/backup`，data 真 SCP）
  4. 全量异步备份（`POST /api/backups-async`，split 端到端真链路）
  5. 设备删除清理（`DELETE /api/devices/{id}` + 验 data cleanup 真调）
  6. Dashboard 聚合（`GET /api/dashboard`，ctrl 跨容器真调 data）
  7. **故障注入：docker stop data → config 改 .177 接口仍成功**（真停容器）
  8. **故障注入：docker stop ctrl → config 返明确中文错误**（真停容器）
- **fixture**：
  - `split_3containers`：检查 3 容器都 up，否则 skip
  - `real_4_devices`：返回 [4, 5, 100, 177] 设备 id
- **状态恢复**：每个 case 跑完恢复设备原状（n → n+1 → n）
- **故障恢复**：场景 7/8 跑完 `docker start data` / `docker start ctrl` 恢复

#### Scenario: split 模式 4 设备 8 场景全 PASS

- **WHEN** 跑 `pytest tests/test_split_e2e_real.py -m integration -v`（4 设备全可达）
- **THEN** 8 场景 MUST 全 PASS
- **AND** 备份文件 / device 列表恢复到测试前状态

#### Scenario: 设备不通时 skip

- **WHEN** 1+ 设备不可达（SSH / NETCONF 失败）
- **THEN** 该 case MUST `pytest.skip("设备不可达")`，不阻塞其他 case

#### Scenario: 故障注入容错真机版

- **WHEN** 跑场景 7：真 `docker stop data` 后调 config 接口
- **THEN** config MUST 仍返回 200（不依赖 data）
- **AND** 跑场景 8：真 `docker stop ctrl` 后调 config 接口
- **THEN** config MUST 返回明确中文错误"设备查询失败: 内部 API 调用失败..."
- **AND** 故障恢复（`docker start data/ctrl`）后所有场景再跑仍全 PASS
