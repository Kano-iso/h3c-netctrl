## ADDED Requirements

### Requirement: ops-toolkit 脚本封装为子命令
ops-toolkit 5 预制脚本（check-host.sh / check-netconf.sh / ssh-test.sh / capture-config.sh / reboot-wait.sh）必须封装为子命令形式（如 `audit-switch.sh <device-name>` 一键替代手动 SSH），接受 `--device` / `--host` / `--port` 等参数。

#### Scenario: 子命令接受设备名
- **WHEN** 用户执行 `docker compose --profile ops run --rm ops-toolkit audit-switch.sh spine-01`
- **THEN** 脚本从 `BACKEND_URL` 查询 `spine-01` 设备 IP + 凭据，自动 SSH 进去执行常用命令（display version / display device / display interface brief）

#### Scenario: 子命令支持直接传 IP
- **WHEN** 用户执行 `audit-switch.sh 192.168.100.4`
- **THEN** 脚本识别为 IP，提示需手动输入凭据（避免明文凭据 hardcode）

### Requirement: 工具回显强制带文档链接
所有 ops-toolkit 5 预制脚本的**末尾输出**必须包含 "📖 文档链接" 段，至少含：
- `📖 用法: <docs-prefix>/ops-toolkit.md#<script-name>`
- `📖 排错 SOP: <docs-prefix>/troubleshooting.md`
- `📖 凭据来源: <docs-prefix>/secrets.md`

`docs-prefix` 默认 `/opt/docs/`，可通过环境变量 `OPS_DOCS_PREFIX` 覆盖（容器外调试用）。

#### Scenario: 脚本执行后回显带文档链接
- **WHEN** 用户执行任意 ops-toolkit 脚本（如 `check-host.sh 192.168.100.4`）并看到主输出
- **THEN** 主输出末尾自动追加"📖 文档链接"段，3 个链接全部出现

#### Scenario: 文档链接指向真实文件
- **WHEN** 用户在容器内 `cat /opt/docs/ops-toolkit.md#check-host`
- **THEN** 文件存在且含 `check-host.sh` 用法说明（与脚本行为一致）

### Requirement: qa 容器入口回显带文档链接
qa-backend / qa-frontend 容器入口（`Dockerfile.qa` `CMD` / `ENTRYPOINT`）必须回显 "📖 QA-GUIDE 链接"，链接到 `docs/QA-GUIDE.md` 的对应章节。

#### Scenario: qa-backend 启动时回显文档
- **WHEN** 用户执行 `docker compose --profile qa run --rm qa-backend`
- **THEN** pytest 输出末尾（或 banner 中）出现 `📖 QA-GUIDE: /opt/docs/QA-GUIDE.md#qa-backend`

#### Scenario: qa-frontend 启动时回显文档
- **WHEN** 用户执行 `docker compose --profile qa run --rm qa-frontend`
- **THEN** 编译/测试输出末尾出现 `📖 QA-GUIDE: /opt/docs/QA-GUIDE.md#qa-frontend`

### Requirement: docs 索引文件统一管理
`docs/ops-toolkit.md` 必须存在，作为 ops-toolkit 5 脚本的"使用 nav"，含：
- 5 脚本各自用法 + 设备命名约定 + 常见错误码解读
- 与 `docs/QA-GUIDE.md` + `docs/CONTAINER-DECOUPLING.md` + `docs/VERSION-ROADMAP.md` 的交叉链接

#### Scenario: 索引文件被脚本链接
- **WHEN** 用户查看任意 ops-toolkit 脚本的回显文档链接
- **THEN** 链接指向 `docs/ops-toolkit.md` 的对应 anchor，anchor 存在且内容详实
