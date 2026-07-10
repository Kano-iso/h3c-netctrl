# ops-toolkit-remove-sshpass-tools — 清理过时的 sshpass 系列工具

## Why

v3.0 启动期真机勘察发现：`ssh-test.sh` / `audit-switch.sh` 都用 `sshpass + 原生 ssh` 实现，**不兼容 H3C V7 老设备的 ssh-rsa host key**（OpenSSH 7.4+ 默认禁用 ssh-rsa）。在 .5 设备上实测全部 fail：

```
$ audit-switch --device leaf-04
[1/3] display version → Unable to negotiate ... no matching host key type found. Their offer: ssh-rsa
[2/3] display device → 同上
[3/3] display interface brief → 同上
```

两个脚本形同摆设——既不能用于 .5（v3.0 SDN/VPC 唯一可用真机），也不能用于 .177（Test-Switch-177）。继续保留只会误导用户以为可用。

**正解**：H3C V7 SSH 兼容性已由 `paramiko-batch-exec.sh`（复用 backend `SSHExecutor` 内部 kex 兼容）解决。所有 SSH 交互场景统一走 paramiko 系列。

## What Changes

**删工具**（commit `36cb92f`）：
- `ops-toolkit/scripts/ssh-test.sh` — 删
- `ops-toolkit/scripts/audit-switch.sh` — 删

**修错误注释**（commit `36cb92f`）：
- `ops-toolkit/scripts/vpc-apply.sh:157` — "与 capture-config / audit-switch 一致" → "与 vpc-reset / vpc-show 一致"（它们都是 paramiko 模式）
- `ops-toolkit/scripts/vpc-show.sh:16` — "与 audit-switch 一致" → "与 paramiko-batch-exec 一致"（audit-switch 是 sshpass，注释与实现不符）

**文档联动同步**（commit `b4aae31`）：
- `.trae/rules/qa规范.md`（C 类）— 7 脚本 → 5 脚本
- `README.md`（A 类）— 9 个 → 7 个排错脚本
- `docs/ops-toolkit.md` — 删 ssh-test / audit-switch 章节
- `docs/QA-GUIDE.md` — 6 脚本 → 4 脚本
- `openspec/specs/add-ops-toolkit/spec.md` — 删 ssh-test 错误描述行
- `backend/tests/perf/README.md` — ssh-test 示例 → paramiko-batch-exec

## 不在本 change 范围

- **不动 archive/ 下历史文档**（按 B 类"archive 保留历史"原则）
- **不动 RELEASE-NOTES-***（B 类发版说明不维护）
- **不动 docs/REVIEW-***（B 类 review 不维护）
- **不修 capture-config.sh / reboot-wait.sh**（虽然也用 sshpass，但功能上 capture-config 走 scp 拉 startup.cfg，reboot-wait 是 reboot 流程，**待后续真机验证是否同样受 kex 影响再决定**——避免一次性过度清理）

## 影响范围

| 工具 | 数量 | 备注 |
|---|---|---|
| 删脚本 | 2 个 | ssh-test.sh, audit-switch.sh |
| 改注释 | 2 处 | vpc-apply.sh, vpc-show.sh 错误引用 |
| 改文档 | 6 个 | A 类 1 + C 类 1 + 主 spec 1 + 工具文档 2 + perf 1 |

## 验收标准

- [x] `ops-toolkit/scripts/` 下无 ssh-test.sh / audit-switch.sh
- [x] `grep -r "ssh-test\|audit-switch" --exclude-dir=archive --exclude-dir=.git` 排除 archive/RELEASE-NOTES/REVIEW 后无结果
- [x] C 类 / A 类 / 主 spec 同步更新
- [x] vpc-apply / vpc-show 错误注释修正
- [x] 真机勘察确认（paramiko-batch-exec.sh 在 .5 上跑通，ssh-test/audit-switch 不再被需要）

## 关联 commit

- `36cb92f` — chore(ops-toolkit): remove ssh-test/audit-switch + fix vpc-* wrong comments
- `b4aae31` — docs: remove ssh-test/audit-switch references
