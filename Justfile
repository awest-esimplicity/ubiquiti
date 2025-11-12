set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# Default recipe lists available commands.
default:
    just --list

# Run the backend unit test suite via uv/pytest.
be-test:
    UBIQUITI_DB_MODE=memory UBIQUITI_DB_URL="" uv run --project backend pytest

# Lock all devices belonging to the provided owner.
be-lock owner:
    uv run --project backend ubiquiti --owner {{owner}}

# Unlock all devices belonging to the provided owner.
be-unlock owner:
    uv run --project backend ubiquiti --owner {{owner}} --unlock

# List UniFi devices managed by the controller.
be-list-devices:
    uv run --project backend ubiquiti --list-devices

# List currently active client devices.
be-list-active:
    uv run --project backend ubiquiti --list-active

# List active clients that are not registered in devices.py.
be-list-non-registered-active:
    uv run --project backend ubiquiti --list-non-registered-active

# Launch the FastAPI backend (defaults to localhost:8000).
be-start host="127.0.0.1" port="8000":
    uv run --project backend uvicorn backend.app:app --host {{host}} --port {{port}}

# Launch the FastAPI backend with reload for development.
be-dev host="127.0.0.1" port="8000":
    uv run --project backend uvicorn backend.app:app --host {{host}} --port {{port}} --reload

# Launch the Streamlit UI on the chosen port (defaults to 8501).
be-ui port="8501":
    uv run --project backend streamlit run streamlit_app.py --server.port {{port}}

# Launch the Streamlit UI with live reload on save.
be-ui-dev port="8501":
    uv run --project backend streamlit run streamlit_app.py --server.port {{port}} --server.runOnSave true

# Refresh the MAC vendor cache used for lookup.
be-update-vendors:
    uv run --project backend python -c "from mac_vendor_lookup import MacLookup; MacLookup().update_vendors()"

# Initialize the SQL database schema.
be-db-init:
    uv run --project backend python -m backend.db_setup init

# Seed the SQL database with default owners and devices.
be-db-seed force="false":
	if [ "{{force}}" = "true" ]; then \
		uv run --project backend python -m backend.db_setup seed --force; \
	else \
		uv run --project backend python -m backend.db_setup seed; \
	fi

# Run Ruff lint checks on the backend codebase.
be-ruff:
    uv run --project backend ruff check backend/src backend/tests streamlit_app.py

# Run Ruff lint checks with autofix enabled.
be-ruff-fix:
    uv run --project backend ruff check --fix backend/src backend/tests streamlit_app.py

# Format backend code with Ruff.
be-format:
    uv run --project backend ruff format backend/src backend/tests streamlit_app.py

# Type-check the backend package with MyPy.
be-mypy:
    uv run --project backend mypy backend

# -------------------------------
# Docker helpers
# -------------------------------

be-dc-up:
    docker compose up --build

be-dc-down:
    docker compose down --remove-orphans

be-dc-logs:
    docker compose logs --follow

# -------------------------------
# Frontend commands (Astro React)
# -------------------------------

fe-install:
    cd frontend && npm install

fe-dev:
    cd frontend && npm run dev

fe-build:
    cd frontend && npm run build

fe-preview:
    cd frontend && npm run preview

fe-format:
    cd frontend && npm run format

fe-format-check:
    cd frontend && npm run format:check

fe-lint:
    cd frontend && npm run lint

fe-lint-fix:
    cd frontend && npm run lint:fix

fe-typecheck:
    cd frontend && npm run typecheck

fe-astro-check:
    cd frontend && npm run astro:check

fe-test:
    cd frontend && npm run test

fe-test-watch:
    cd frontend && npm run test:watch

fe-test-coverage:
    cd frontend && npm run test:coverage

fe-e2e:
    cd frontend && npm run e2e

fe-e2e-ci:
    cd frontend && npm run e2e:ci
