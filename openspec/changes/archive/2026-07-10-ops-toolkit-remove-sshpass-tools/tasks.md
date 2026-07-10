# ops-toolkit-remove-sshpass-tools — Tasks

| # | Task | 状态 | Commit |
|---|------|------|--------|
| 1 | 删 `ops-toolkit/scripts/ssh-test.sh` | ✅ | 36cb92f |
| 2 | 删 `ops-toolkit/scripts/audit-switch.sh` | ✅ | 36cb92f |
| 3 | 修 `vpc-apply.sh:157` 错误注释（"与 capture-config/audit-switch 一致" → "与 vpc-reset/vpc-show 一致"） | ✅ | 36cb92f |
| 4 | 修 `vpc-show.sh:16` 错误注释（"与 audit-switch 一致" → "与 paramiko-batch-exec 一致"） | ✅ | 36cb92f |
| 5 | C 类同步：`.trae/rules/qa规范.md`（7 → 5 脚本） | ✅ | b4aae31 |
| 6 | A 类同步：`README.md`（9 → 7 脚本） | ✅ | b4aae31 |
| 7 | 工具文档：`docs/ops-toolkit.md` 删章节 | ✅ | b4aae31 |
| 8 | 测试文档：`docs/QA-GUIDE.md` 6 → 4 脚本 | ✅ | b4aae31 |
| 9 | 主 spec：`openspec/specs/add-ops-toolkit/spec.md` 删错描述 | ✅ | b4aae31 |
| 10 | perf 文档：`backend/tests/perf/README.md` ssh-test → paramiko-batch-exec | ✅ | b4aae31 |
| 11 | Archive 闭环 | ⏳ | 待执行 |

## 验收

- [x] `ls ops-toolkit/scripts/` 无 ssh-test / audit-switch
- [x] 排除 archive/ 后无残留引用
- [x] 真机勘察确认 paramiko-batch-exec 在 .5 上跑通
