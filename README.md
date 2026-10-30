# Go Daily — Fleet Control & Operations System

Go Daily is a fleet management and operations platform for a transport company in Egypt. It covers vehicles, drivers, shifts, work-shift GPS tracking, fixed-route and school operations, ride-hailing work, fuel (CNG / gasoline / oil), expenses, revenue, driver settlements and per-vehicle profitability.

- **Primary UI language:** Arabic (RTL), with English planned later
- **Currency:** EGP
- **Timezone:** Africa/Cairo for display. Timestamps are stored in UTC.

> Status: under active development. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for what exists and [`docs/GO_DAILY_CLAUDE_MASTER_TASKS.md`](docs/GO_DAILY_CLAUDE_MASTER_TASKS.md) for the task checklist.

## Repository layout

```text
apps/
  api/             FastAPI + SQLAlchemy 2 + Alembic (Python 3.12)
  admin-web/       Next.js 16 (App Router) + TypeScript + Tailwind CSS v4
  driver-android/  Android driver app (Kotlin, Compose) — see its README
packages/
  config/          Shared tsconfig and Go Daily design tokens
  shared/          Shared TypeScript constants (roles, Arabic labels)
docs/              Architecture, roadmap, deployment and operations docs
```

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.12+ | managed by [uv](https://docs.astral.sh/uv/) |
| uv | 0.5+ | Python dependency manager |
| Node.js | 22+ | |
| pnpm | 10+ | `npm i -g pnpm` |
| PostgreSQL | 16 | local install or Docker |
| Docker + Compose v2 | optional | runs the full stack |

## Quick start (Docker)

```bash
cp .env.example .env          # edit POSTGRES_PASSWORD etc.
docker compose up --build -d  # postgres -> migrate -> api -> admin-web
```

- Admin web: <http://localhost:3000>
- API: <http://localhost:8000> (interactive docs at `/docs` outside production)
- Health: `GET /health` (liveness), `GET /ready` (checks database connectivity)

Then create the first administrator (see [First administrator](#first-administrator)).

## Local development (without Docker for the apps)

1. Start PostgreSQL and create a database and user that match `DATABASE_URL` in `.env`. Create a separate test database for `TEST_DATABASE_URL`. You can also run only the database in Docker: `docker compose up -d postgres`.
2. Install dependencies and apply migrations:

   ```bash
   make setup     # creates .env if missing, installs Python + Node deps
   make migrate   # alembic upgrade head
   make seed      # idempotent reference data only (no fake operational data)
   ```

3. Run the apps with auto-reload:

   ```bash
   make dev       # API on :8000 and admin web on :3000
   ```

## Developer commands

Run `make help` for the full list.

| Command | What it does |
| --- | --- |
| `make setup` | Install dependencies, create `.env` from the example |
| `make dev` | Run API and admin web with auto-reload |
| `make up` / `make down` | Start or stop the Docker stack |
| `make migrate` | Apply Alembic migrations |
| `make migration m="..."` | Autogenerate a new migration, then review it |
| `make seed` | Seed reference data (idempotent) |
| `make bootstrap-admin` | Create the first `SUPER_ADMIN` from env vars |
| `make detect-exceptions` | Run the exception rules now (also schedule it, see below) |
| `make test` | API tests (pytest, real PostgreSQL) and web unit tests (vitest) |
| `make lint` | Ruff, ESLint, Prettier check |
| `make typecheck` | mypy (strict) and `tsc` |
| `make format` | Auto-format Python and TypeScript |
| `make build` | Production build of the admin web |
| `make check` | Everything CI runs |

## First administrator

Accounts are never created with default passwords. Create the first `SUPER_ADMIN` once, from environment variables:

```bash
BOOTSTRAP_ADMIN_PHONE=01000000000 BOOTSTRAP_ADMIN_PASSWORD='a-long-unique-password' make bootstrap-admin
# Docker:
docker compose run --rm -e BOOTSTRAP_ADMIN_PHONE=... -e BOOTSTRAP_ADMIN_PASSWORD=... api python -m app.cli bootstrap-admin
```

The command refuses to run if a `SUPER_ADMIN` already exists. Remove the password from the environment afterwards.

## Scheduled jobs

Run these from the server's scheduler (cron, systemd timer or the hosting platform's job runner). All are safe to repeat.

| Command | Suggested schedule | Purpose |
| --- | --- | --- |
| `python -m app.cli detect-exceptions` | hourly | Runs the review rules over the last 3 days (`--days N` to change). Re-running never duplicates cases. Exit code 1 if a rule failed. |
| `python -m app.cli prune-gps` | daily | Deletes raw GPS points of finished shifts older than `GPS_RETENTION_DAYS`. |
| `python -m app.cli prune-idempotency` | daily | Deletes expired idempotency records. |

With Docker: `docker compose run --rm api python -m app.cli detect-exceptions`.

## Testing

API tests run against a real PostgreSQL database (`TEST_DATABASE_URL`) because the schema uses PostgreSQL features. **The test run drops and recreates the `public` schema of that database**, so never point it at a database you care about. The schema is built by running the Alembic migrations, so every test run also checks the migration chain.

```bash
make test
```

## Configuration

All configuration comes from environment variables. See [`.env.example`](.env.example) for the full list with comments. Never commit `.env` files or real credentials.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): system design, conventions and key decisions
- [`docs/ROADMAP.md`](docs/ROADMAP.md): phases and current status
- [`docs/GO_DAILY_CLAUDE_MASTER_TASKS.md`](docs/GO_DAILY_CLAUDE_MASTER_TASKS.md): the engineering task checklist

## Principles

- PostgreSQL is the system of record. Use migrations and never rebuild a database silently.
- The backend enforces authorization. Hiding something in the frontend is not security.
- GPS, financial, trip and alert data are never fabricated.
- Automated findings are labelled **"مراجعة مطلوبة"** (review required) or **"حالة غير معتادة"** (unusual case), never as proven theft or fraud.
- Drivers are tracked only during authorized work shifts, with explicit disclosure.
