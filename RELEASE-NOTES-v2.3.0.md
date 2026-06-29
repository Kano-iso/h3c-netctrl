# RELEASE-NOTES-v2.3.0

**版本**: v2.3.0
**日期**: 2026-06-29
**主题**: 修 bug + 健壮性补全（个人轻量级小版本）

---

## 1. 主题

v2.3 不引入新能力（v3.0 VPC / SDN 才加），专注：
- 修 v2.2.0 实战中暴露的 bug
- 补 QA / 测试基础设施
- 为容器解耦（v2.4）做技术储备

## 2. 包含的 Changes（6 个 + 1 个未来）

| Change | 状态 | commit | 备注 |
|---|---|---|---|
| `fix-link-mode-switch` | ✅ 闭环 | `f5c6a12` | 修真机 4 个 bug + 加 NETCONF 查 name |
| `test-backup-rotation-locked` | ✅ 闭环 | `393bff5` | 3 单元测试保护锁定备份不被轮转 |
| `add-ops-toolkit` | ✅ 闭环 | `393bff5` | 容器化运维工具（ping/nc/SSH/ncclient + 5 脚本） |
| `add-integration-test-framework` | ✅ 闭环 | `a900374` | 真机集成测试框架（backup 4 + VPN 6） |
| `add-backup-type-radio-ui` | ✅ 闭环 | `d4d3aad` | UI type radio + 修真 bug |
| `add-vitest-component-tests` | ⏸️ BLOCKED | `35f95a9` | EACCES node_modules，需 sudo chown |
| `v2.4-container-decoupling` | 📋 PROPOSAL | `9e9051a` | 蓝图已留，v2.3 不实施 |

## 3. 收尾时实测发现 + 修复的 bug

### Bug: link-mode 切不生效
- 现象：API 返回 500，设备实际没改
- 根因（4 个）：
  1. `_parse_if_name_for_cli()` 算法错（if_index 数字不能解析为 name）
  2. SSH 端口用 `device.port=830`（NETCONF 端口，invoke_shell 被关）
  3. `r['command']` KeyError（实际是 `r['cmd']`）
  4. `NetconfClient.close()` 不存在（用 `disconnect()`）
- 修：NETCONF 查真实 name + 强制 SSH 22 + 容错 KeyError
- 验证：192.168.100.5 真机 n → n+1(route) → n(bridge) PASS in 11.5s

### Bug: 全量备份 body 不生效
- 现象：前端传 `types:["startup"]`，后端硬编码全备
- 根因：路由用 `body.types` 做校验但 `mgr.create_backup(types=["startup","running"])` 硬编码
- 修：`mgr.create_backup(types=types, db=db)`
- 验证：3 测试用例 PASS（startup / running / 全部 / 错误类型）

## 4. 关键能力清单（用户视角）

| 能力 | v2.2.0 | v2.3.0 |
|---|---|---|
| 接口 link-mode 切换 | ❌ 失败 | ✅ 实战可用 |
| 备份 UI 体验 | 3 份混淆 | ✅ radio 选择 + 中文错误 |
| 备份锁定不被轮转 | 无测试 | ✅ 3 单元测试保护 |
| 运维工具 | 临时命令 | ✅ ops-toolkit 容器 |
| 真机集成测试 | 0 | ✅ 10 case |
| QA 容器 | 已存在 | ✅ 全部使用 |

## 5. 端到端实测状态

| 测试类型 | 数量 | 状态 |
|---|---|---|
| 单元（mock） | 105 | ✅ 2.67s |
| 集成（真机 192.168.100.4/.5） | 11 | ✅ 11.52s（link-mode 11.5s + backup 4 case + VPN 6 case） |
| 前端组件（vitest） | 0 | ⏸️ BLOCKED by env |

## 6. 已知问题 / 限制

| ID | 问题 | 影响 | 解决方案 |
|---|---|---|---|
| #001 | vitest EACCES | 前端组件测试无法运行 | `sudo chown -R $(whoami) node_modules` |
| #002 | ops-toolkit build 慢 | 第一次 build 5+ min | 后续缓存可秒级 |
| #003 | 容器解耦未实施 | monolith 资源争抢 | v2.4 实施 |

## 7. 升级 / 部署注意

- 旧设备：v2.2.0 → v2.3.0 无 schema 变更
- 数据库：SQLite 不变（v2.4 才迁 Postgres）
- 端口：8000（核心）/ 830（NETCONF）/ 22（SSH CLI 用于 link-mode）
- ops-toolkit 容器**默认不启动**（profile: ops）

## 8. 关键 commit 序列

```
393bff5 feat(ops-toolkit): 脚本加进 /usr/local/bin PATH + python 3.10
f5c6a12 fix(link-mode): 真机 NETCONF 查 name + 强制 SSH 22 + 真机集成测试
a900374 docs(openspec): add-integration-test-framework change proposal
d4d3aad feat(backup-ui): 全量备份 type radio + 修真 bug
35f95a9 docs(openspec): add-vitest-component-tests BLOCKED by env
9e9051a docs(openspec): v2.4-container-decoupling proposal
+ 早期: add-interface-l2-l3-switch / test-backup-rotation-locked 等
```

## 9. 关联

- [VERSION-ROADMAP.md](VERSION-ROADMAP.md)
- [RELEASE-NOTES-v2.2.0.md](RELEASE-NOTES-v2.2.0.md)
- [docs/QA-GUIDE.md](docs/QA-GUIDE.md)
- [docs/CONTAINER-DECOUPLING.md](docs/CONTAINER-DECOUPLING.md)
- [openspec/specs/](../specs/)
