# Backend Service

See the repository root `README.md` for project overview and usage notes.

## Database Support

The backend can optionally persist owners and devices in SQLite (or any SQLAlchemy
-compatible database). Configure the following environment variables (already present in
the repo `.env` for local development):

- `UBIQUITI_DB_URL` – SQLAlchemy database URL, e.g.
  `sqlite:///app/data/ubiquiti.db`. Remove or clear this value to fall back to the
  in-memory repositories.
- `UBIQUITI_DB_ECHO` – set to `true` to enable SQL echo logging (optional)

Initialize and seed the schema using Just:

```bash
just be-db-init          # creates tables
just be-db-seed          # inserts default owners/devices (skip if already present)

To replace existing rows rather than merging, run:

```bash
uv run --project backend python -m backend.db_setup seed \
  --force \
  --owner-mode replace \
  --device-mode replace
```
```

When no database URL is configured the application transparently falls back to the
in-memory repositories. Set `UBIQUITI_DB_MODE=memory` to explicitly disable the
database-backed adapters if desired.

## Container Usage

A multi-stage Dockerfile is available at `backend/Dockerfile`. Build and run it with the
supplied compose file:

```bash
docker compose up --build
```

The stack exposes the FastAPI backend on port 8000 and persists the SQLite database
under the `backend-data` volume. Seed the database inside the backend container when
needed:

```bash
docker compose exec backend uv run --project . python -m backend.db_setup seed --force
```
