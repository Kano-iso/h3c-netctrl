## ADDED Requirements

### Requirement: Project directory structure
The project SHALL follow the directory structure defined in design.md, with `backend/`, `frontend/`, `data/`, `logs/` as top-level directories. All source code, configuration, and deployment files SHALL be organized within this structure.

#### Scenario: Directory structure is complete
- **WHEN** the project is initialized
- **THEN** all directories (`backend/app/`, `backend/app/routers/`, `backend/app/utils/`, `frontend/`, `data/`, `logs/`) exist with `__init__.py` files in Python packages

### Requirement: Docker development environment
The project SHALL provide `docker-compose.dev.yml` and `Dockerfile.dev` that define a backend container (Python 3.10 + FastAPI + ncclient) and a frontend container (Nginx). The backend container SHALL mount source code for hot-reload, and SQLite data SHALL persist to `./data/dev.db` on the host.

#### Scenario: One-command environment startup
- **WHEN** developer runs `make dev` or `docker-compose -f docker-compose.dev.yml up -d --build`
- **THEN** both backend and frontend containers start successfully, backend API is accessible, and frontend page is served by Nginx

#### Scenario: Source code hot-reload
- **WHEN** developer modifies backend Python source code while containers are running
- **THEN** the backend service automatically reloads without manual container restart

#### Scenario: Data persistence across restarts
- **WHEN** containers are stopped and restarted with `docker-compose -f docker-compose.dev.yml down` then `up -d`
- **THEN** SQLite database file `./data/dev.db` retains all previously stored data

### Requirement: Environment variable management
The project SHALL provide `.env.example` listing all required environment variables with placeholder values. The `.env` file SHALL be listed in `.gitignore`. Environment variables SHALL include `LOG_LEVEL`, `ENCRYPTION_KEY`, `DB_PATH`, and backend service port.

#### Scenario: Environment template exists
- **WHEN** a new developer clones the repository
- **THEN** `.env.example` exists with all required variable names and placeholder values

#### Scenario: .env is not committed
- **WHEN** developer has a local `.env` file
- **THEN** git status does not show `.env` as an untracked file

### Requirement: Makefile automation
The project SHALL provide a Makefile with targets: `dev`, `dev-rebuild`, `stop`, `logs`, `backup`, `clean`. Each target SHALL execute the corresponding docker-compose or utility command as defined in the project flow specification.

#### Scenario: Make dev starts environment
- **WHEN** developer runs `make dev`
- **THEN** development containers start in detached mode

#### Scenario: Make logs shows backend output
- **WHEN** developer runs `make logs`
- **THEN** real-time backend container logs are displayed

### Requirement: Git initialization
The project SHALL have a `.gitignore` that excludes `data/`, `logs/`, `.env`, `__pycache__/`, `*.pyc`, `.venv/`, and `backups/`. The initial commit SHALL include all scaffold files.

#### Scenario: Sensitive files are ignored
- **WHEN** developer runs `git status` after creating `data/dev.db` or `.env`
- **THEN** these files do not appear in the output

### Requirement: Backend dependencies
The backend SHALL declare all Python dependencies in `requirements.txt`, including at minimum: `fastapi`, `uvicorn`, `ncclient`, `sqlalchemy`, `cryptography`, `pydantic`, `python-dotenv`.

#### Scenario: Dependencies install correctly
- **WHEN** `pip install -r requirements.txt` is executed in the backend container
- **THEN** all packages install without errors and the FastAPI application can start
