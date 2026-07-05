## ADDED Requirements

### Requirement: docker compose up 默认起 3 容器 split 模式

`docker-compose.dev.yml` 中 `ctrl` / `config` / `data` 三个服务 MUST NOT 设置 `profiles` 限制（即默认起）。`backend`（monolith）服务 MUST 加 `profiles: ["core"]`，仅当显式 `docker compose --profile core up` 时启动。

#### Scenario: 默认 docker compose up 起 3 容器

- **WHEN** 执行 `docker compose -f docker-compose.dev.yml up -d`
- **THEN** 启动 `h3c-ctrl` / `h3c-config` / `h3c-data` 3 个容器，`h3c-netctrl-backend` 不启动

#### Scenario: 显式 profile core 起 monolith

- **WHEN** 执行 `docker compose -f docker-compose.dev.yml --profile core up -d`
- **THEN** 启动 `h3c-netctrl-backend` 单容器（monolith 模式）

### Requirement: frontend depends_on 切换为 ctrl

`frontend` 服务的 `depends_on` MUST 从 `backend` 改为 `ctrl`（split 模式下 backend 不起，frontend 应依赖 ctrl 提供的 `/api/devices` 接口）。`depends_on` 仅是启动顺序约束，不强制健康检查。

#### Scenario: frontend 启动前 ctrl 已起

- **WHEN** 执行 `docker compose up -d frontend`
- **THEN** 系统先启动 `h3c-ctrl`，再启动 `h3c-netctrl-frontend`

#### Scenario: core 模式下 frontend 仍能启动

- **WHEN** 执行 `docker compose --profile core up -d frontend`
- **THEN** 系统启动 `h3c-netctrl-backend`（core profile）和 `h3c-netctrl-frontend`，`h3c-ctrl` 不启动（条件依赖）

### Requirement: BREAKING 变更 MUST 在 RELEASE-NOTES 显式标注

`RELEASE-NOTES-v2.5.0.md` MUST 在顶部用 `**BREAKING**` 标注默认模式翻转，并给出 `--profile core` 回退命令。README.md "快速启动" 章节 MUST 更新为 split 模式示例。

#### Scenario: 用户从 v2.4.2.1 升级

- **WHEN** 用户从 v2.4.2.1 升级到 v2.5.0 后执行原脚本 `docker compose up -d`
- **THEN** 默认起 3 容器（行为变化），RELEASE-NOTES 提示用户如需 monolith 用 `--profile core`

### Requirement: Vite proxy 配置 MUST 支持双模式

`frontend/vite.config.js` 的 proxy 配置 MUST 同时支持 split 模式（按路径分发到 ctrl/config/data）和 core 模式（全部转发到 backend:8000）。模式切换由 `VITE_API_MODE` 环境变量控制。

#### Scenario: split 模式按路径分发

- **WHEN** `VITE_API_MODE=split` 时访问 `/api/devices`
- **THEN** Vite proxy 转发到 `http://ctrl:8000`

#### Scenario: core 模式全转发 backend

- **WHEN** `VITE_API_MODE=core` 时访问 `/api/devices`
- **THEN** Vite proxy 转发到 `http://backend:8000`
