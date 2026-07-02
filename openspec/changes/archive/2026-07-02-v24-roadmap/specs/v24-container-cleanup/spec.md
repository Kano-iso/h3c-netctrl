## ADDED Requirements

### Requirement: 容器清单基线文档
`docs/CONTAINER-INVENTORY.md` 必须存在，作为容器清单的"基线"，含：
- 当前在跑容器（含 `image` + `created` + `status` + `ports`）
- stop 残留容器
- dangling image 列表
- 未用 volume 列表
- 创建日期 + 维护人 + 下次盘点日期

#### Scenario: 文档存在且为基线
- **WHEN** 用户查看 `docs/CONTAINER-INVENTORY.md`
- **THEN** 文件存在，含 4 个章节（在跑 / stop 残留 / dangling image / 未用 volume），每个容器有完整元信息

#### Scenario: 基线与 docker ps -a 输出 100% 一致
- **WHEN** 用户跑 `make container-inventory` 重新生成基线
- **THEN** 脚本输出与 `docs/CONTAINER-INVENTORY.md` 现有内容 100% 一致（无新变化时）或 diff 仅含"新增 / 删除"项

### Requirement: 自动化盘点脚本
`make container-inventory` 脚本必须存在，自动跑 `docker ps -a --format` / `docker images` / `docker volume ls`，输出 markdown 格式到 `docs/CONTAINER-INVENTORY.md`。

#### Scenario: 脚本生成 markdown
- **WHEN** 用户执行 `make container-inventory`
- **THEN** 脚本输出 markdown 内容到 `docs/CONTAINER-INVENTORY.md`，含当前所有容器 / image / volume 状态

#### Scenario: 脚本可重复运行
- **WHEN** 用户连续 2 次跑 `make container-inventory`
- **THEN** 第二次输出与第一次一致（无变化时），或仅含 diff（容器增减时）

### Requirement: 冗余容器清理 SOP
`docs/CONTAINER-CLEANUP-SOP.md` 必须存在，含：
- 哪些容器可安全删除（stale image / stop 容器 / 未用 volume）
- 哪些容器必须保留（frontend / backend / qa-* / ops-toolkit）
- 清理步骤 + 回退方法（删除前先 docker stop + 确认无依赖）

#### Scenario: SOP 文档存在
- **WHEN** 用户查看 `docs/CONTAINER-CLEANUP-SOP.md`
- **THEN** 文档含"可删 / 必须保留"两部分 + 步骤 + 回退方法

#### Scenario: 按 SOP 清理后无残留
- **WHEN** 用户按 SOP 删除 stale image + stop 容器
- **THEN** `docker ps -a` 输出与 SOP 中"必须保留"清单 100% 一致，无多余
