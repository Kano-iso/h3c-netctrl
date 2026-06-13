## 1. Project Scaffold

- [x] 1.1 Create project directory structure (backend/app/, backend/app/routers/, backend/app/utils/, frontend/, data/, logs/) with __init__.py files
- [x] 1.2 Create backend/requirements.txt with all Python dependencies (fastapi, uvicorn, ncclient, sqlalchemy, cryptography, pydantic, python-dotenv)
- [x] 1.3 Create .env.example with all required environment variables (LOG_LEVEL, ENCRYPTION_KEY, DB_PATH, BACKEND_PORT)
- [x] 1.4 Create .gitignore excluding data/, logs/, .env, __pycache__/, *.pyc, .venv/, backups/
- [x] 1.5 Create backend/Dockerfile.dev (Python 3.10, install requirements, mount source, uvicorn hot-reload)
- [x] 1.6 Create frontend/nginx.conf (serve static files, proxy /api to backend)
- [x] 1.7 Create docker-compose.dev.yml (backend + frontend containers, volume mounts for source/data/logs)
- [x] 1.8 Create Makefile with targets: dev, dev-rebuild, stop, logs, backup, clean
- [x] 1.9 Initialize git repo and create initial commit

## 2. Backend Core

- [x] 2.1 Create backend/app/config.py — load environment variables via pydantic Settings
- [ ] 2.2 Create backend/app/database.py — SQLAlchemy engine, session factory, base model
- [ ] 2.3 Create backend/app/models.py — Device SQLAlchemy model with all fields
- [ ] 2.4 Create backend/app/schemas.py — Pydantic request/response models for device and VLAN
- [ ] 2.5 Create backend/app/utils/crypto.py — Fernet encrypt/decrypt functions using ENCRYPTION_KEY
- [ ] 2.6 Create backend/app/main.py — FastAPI app init, include routers, startup event to create tables

## 3. Device Management

- [ ] 3.1 Create backend/app/routers/device.py — GET /api/device, POST /api/device, PUT /api/device endpoints
- [ ] 3.2 Implement device creation with password encryption before storage
- [ ] 3.3 Implement device update with re-encryption if password changes
- [ ] 3.4 Implement GET /api/device returning device info without password_encrypted
- [ ] 3.5 Create backend/app/netconf_client.py — NETCONF connection manager with context manager pattern
- [ ] 3.6 Implement POST /api/device/test — NETCONF connection test with precise error classification (unreachable, refused, auth fail, session fail)

## 4. VLAN Management

- [ ] 4.1 Implement NETCONF get-config for VLAN query — construct H3C-compatible RPC, parse response XML to extract vlan_id and name
- [ ] 4.2 Implement NETCONF edit-config for VLAN creation — construct H3C-compatible RPC with merge operation
- [ ] 4.3 Implement NETCONF edit-config for VLAN name modification — construct H3C-compatible RPC with merge on existing VLAN
- [ ] 4.4 Implement NETCONF edit-config for VLAN deletion — construct H3C-compatible RPC with delete operation
- [ ] 4.5 Create backend/app/routers/vlan.py — GET /api/vlans, POST /api/vlans, PUT /api/vlans/{vlan_id}, DELETE /api/vlans/{vlan_id}
- [ ] 4.6 Implement VLAN input validation (vlan_id 1-4094, name required, duplicate check)
- [ ] 4.7 Implement unified error handling — catch NETCONF errors, device errors, and return readable Chinese messages

## 5. Logging System

- [ ] 5.1 Create backend/app/utils/logger.py — configure Python logging with LOG_LEVEL from env, dual output to stdout and file
- [ ] 5.2 Add INFO-level logging to all device and VLAN operations (action, target, outcome)
- [ ] 5.3 Add DEBUG-level logging to netconf_client.py — log full request/response XML with password masking
- [ ] 5.4 Add ERROR-level logging with full stack trace for all exceptions

## 6. Frontend UI

- [ ] 6.1 Create frontend/index.html — single-page layout with Bootstrap CDN, device info section, VLAN table, error area
- [ ] 6.2 Create frontend/js/api.js — unified API call function with error handling and loading state
- [ ] 6.3 Create frontend/js/device.js — device info display, device form, connection test button logic
- [ ] 6.4 Create frontend/js/vlan.js — VLAN table rendering, refresh, create/edit modal, delete confirmation
- [ ] 6.5 Create frontend/css/style.css — minimal custom styles for error display, loading states
- [ ] 6.6 Implement global error display area — red text, auto-dismiss after 5 seconds
- [ ] 6.7 Implement loading state — disable buttons and show spinner during API calls

## 7. Integration & Verification

- [ ] 7.1 Verify docker-compose dev environment starts cleanly with `make dev`
- [ ] 7.2 Verify device CRUD and connection test through API
- [ ] 7.3 Verify VLAN CRUD through API with H3C simulator
- [ ] 7.4 Verify frontend page loads and all interactions work end-to-end
- [ ] 7.5 Verify DEBUG mode logs NETCONF XML payloads correctly
- [ ] 7.6 Verify data persistence across container restarts
