# Go Daily — Production deployment (Task 31)

This guide prepares a deployment; it does not perform one. Every value below is a placeholder: no real credentials belong in this repository. Read [`SECURITY.md`](SECURITY.md) and [`OPERATIONS.md`](OPERATIONS.md) alongside it.

## 1. Topology

```text
Drivers' phones ──HTTPS──▶ api.example.com ─┐
Office browsers ─HTTPS──▶ admin.example.com ┤  reverse proxy (TLS, rate limits, body size)
                                            │
                     ┌──────────────────────┴───────────────┐
                     ▼                                      ▼
            admin-web (Next.js, :3000) ──server-side──▶ api (FastAPI/Uvicorn, :8000)
                                                            │
                         ┌──────────────────────────────────┼──────────────────┐
                         ▼                                  ▼                  ▼
                 PostgreSQL 16 (managed)       object storage (S3-compatible)   scheduler
                 backups + PITR                 private bucket, versioning      CLI jobs
```

- Browsers talk only to the admin web. It calls the API from its server with the user's session token, which is kept in an `httpOnly` cookie.
- The driver app calls the API directly at `https://api.example.com/api/v1/`.
- Only the reverse proxy is reachable from the internet. The API and admin web listen on a private network or on localhost. PostgreSQL is never public.

Any platform that runs two containers, a managed PostgreSQL and a scheduler works: a VPS with Docker Compose, Railway/Render/Fly, or Kubernetes. Pick one where Cairo latency is acceptable and backups are managed.

## 2. Requirements

| Component | Requirement |
| --- | --- |
| PostgreSQL | **Version 16** (CI and the compose file use 16; 13+ is the hard minimum for trusted `btree_gist` and `gen_random_uuid()`). The `btree_gist` extension must be allowed (migration `0003` runs `CREATE EXTENSION IF NOT EXISTS btree_gist`; managed providers allow it). Server time zone UTC (the app converts to `Africa/Cairo`). Daily backups with point-in-time recovery, 7–30 days. |
| Database role | One application role that owns the schema, so migrations can create tables, indexes and triggers. Not a superuser. Use a separate read-only role for ad-hoc reporting if needed. |
| Connections | `DATABASE_POOL_SIZE` (5) + `DATABASE_MAX_OVERFLOW` (10) per API worker; the image runs 2 workers. Keep the total under the plan's connection limit, or put PgBouncer (transaction mode) in front. |
| API | Python 3.12 image from `apps/api/Dockerfile` (target `runtime`), non-root, 512 MB RAM is enough for a small fleet. |
| Admin web | Node 22 standalone image from `apps/admin-web/Dockerfile`, non-root, 256–512 MB RAM. |
| Storage | S3-compatible bucket (AWS S3, Cloudflare R2, MinIO, DigitalOcean Spaces…), private, with versioning, or a persistent volume for `STORAGE_BACKEND=local` on a single server. |
| TLS | Certificates for both hostnames (Let's Encrypt via the proxy is fine). |
| Scheduler | Cron, systemd timers or the platform's job runner, to run the CLI jobs in section 9. |

## 3. Environment variables

Defaults live in `apps/api/app/core/config.py` and `.env.example`. **Empty values mean "not set"** (`VAR=` falls back to the default).

### API (and the `migrate` job)

| Variable | Production value | Notes |
| --- | --- | --- |
| `APP_ENV` | `production` | Turns off OpenAPI docs, enables HSTS, requires the encryption key |
| `DATABASE_URL` | `postgresql://USER:PASSWORD@HOST:5432/DB?sslmode=require` | `postgres://` and `postgresql://` are normalised to the psycopg driver |
| `DATA_ENCRYPTION_KEY` | Fernet key (secret) | **Required.** The API refuses to start without it. Generate once: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Losing it makes stored national IDs unreadable; changing it requires re-encrypting them |
| `CORS_ORIGINS` | `https://admin.example.com` | Comma-separated. The driver app does not need CORS |
| `FORWARDED_ALLOW_IPS` | The proxy's address (e.g. `10.0.0.5`) | Uvicorn trusts `X-Forwarded-For` only from here. **Never `*`** if the API port can be reached directly |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `true` | JSON lines on stdout |
| `METRICS_TOKEN` | Random 32+ chars (secret) | Enables `GET /metrics`. Leave empty to disable |
| `STORAGE_BACKEND` | `s3` (or `local` on a single server) | |
| `STORAGE_S3_BUCKET`, `STORAGE_S3_REGION`, `STORAGE_S3_PREFIX` | Your bucket | The prefix keeps environments apart in one bucket (e.g. `prod/`) |
| `STORAGE_S3_ENDPOINT_URL` | Only for non-AWS providers | e.g. the R2 or MinIO endpoint |
| `STORAGE_S3_ACCESS_KEY_ID` / `STORAGE_S3_SECRET_ACCESS_KEY` | Secret, scoped to the bucket | Leave empty to use the platform's role or instance credentials |
| `ATTACHMENT_MAX_BYTES` | `10485760` | Keep the proxy body limit slightly above it |
| `SESSION_TTL_HOURS_ADMIN` / `_DRIVER`, `SESSION_IDLE_TIMEOUT_HOURS` | 12 / 720 / 72 | |
| `LOGIN_MAX_FAILED_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`, `LOGIN_RATE_LIMIT`, `LOGIN_RATE_WINDOW_SECONDS` | 5, 15, 60, 300 | The per-IP limit covers the whole office (admin logins come from the web server) |
| `GPS_RETENTION_DAYS` | 180 | Raw points of finished shifts older than this are pruned. Match your privacy notice |
| `EXCEPTION_*` | Defaults | Review thresholds. Set `EXCEPTION_OPERATING_AREAS` (`lat,lng,radius_km;...`) to enable the out-of-area rule |
| `NOTIFICATION_CHANNELS`, `NOTIFICATION_CHANNEL_MIN_SEVERITY` | Empty, `CRITICAL` | In-app notifications always work; extra channels need code (see `notification_channels.py`) |
| `BOOTSTRAP_ADMIN_PHONE` / `_PASSWORD` / `_NAME` | **Only for the one-time bootstrap**, then remove | See section 8 |

### Admin web

| Variable | Production value | Notes |
| --- | --- | --- |
| `API_INTERNAL_URL` | `http://api:8000` (private address) | Server-side only; never exposed to browsers |
| `SESSION_COOKIE_SECURE` | `true` | Required behind HTTPS (also the default when `NODE_ENV=production`) |
| `MAP_TILE_URL` | HTTPS tile template from your map provider | The OpenStreetMap default is for light use only; a fleet's live map needs a provider (MapTiler, Stadia, Thunderforest…) or its own tile server |
| `MAP_TILE_ATTRIBUTION`, `MAP_TILE_MAX_ZOOM` | As the provider requires | Attribution is a licence condition |

### Driver app (build time)

| Setting | Where | Notes |
| --- | --- | --- |
| `goDailyApiBaseUrl` | `-PgoDailyApiBaseUrl=https://api.example.com/api/v1/` or `gradle.properties` | Release builds refuse non-HTTPS URLs |
| Signing | `apps/driver-android/keystore.properties` (`storeFile`, `storePassword`, `keyAlias`, `keyPassword`) | Untracked. Keep the keystore and passwords in the secret store: losing the key prevents updates |

## 4. Secrets

- Keep every secret in the platform's secret store or environment settings, or in a password manager plus a root-only `.env` file on a single server: `DATABASE_URL` password, `DATA_ENCRYPTION_KEY`, `METRICS_TOKEN`, S3 keys, Android signing material. Never put them in the repository, in images, or in CI logs.
- `.env`, `keystore.properties` and backups are git-ignored. Images receive secrets only at runtime (the Dockerfiles take an optional BuildKit secret `extra_ca` for build-time CAs, which never lands in a layer).
- Give each secret one owner and write down where it lives. Rotate S3 keys and the metrics token yearly or when staff leave. `DATA_ENCRYPTION_KEY` cannot be rotated without re-encrypting national IDs.
- Least privilege for infrastructure: an S3 key limited to the bucket (and prefix), and a database role that is not a superuser.

## 5. Reverse proxy and HTTPS

The proxy terminates TLS, forwards client IPs, limits request size and rate-limits login. Example with nginx (Caddy works too):

```nginx
limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;

server {
    listen 443 ssl http2;
    server_name api.example.com;
    # ssl_certificate ... (e.g. certbot)
    client_max_body_size 11m;              # attachments are capped at 10 MB by the API

    location = /api/v1/auth/login {
        limit_req zone=login burst=10 nodelay;
        proxy_pass http://127.0.0.1:8000;
        include proxy_params;
    }
    location = /metrics {                  # monitoring only
        allow 10.0.0.0/8; deny all;
        proxy_pass http://127.0.0.1:8000;
    }
    location / {
        proxy_pass http://127.0.0.1:8000;
        include proxy_params;              # Host, X-Real-IP, X-Forwarded-For, X-Forwarded-Proto
        proxy_read_timeout 60s;
    }
}

server {
    listen 443 ssl http2;
    server_name admin.example.com;
    client_max_body_size 11m;              # receipts go through the web's server actions
    location / {
        proxy_pass http://127.0.0.1:3000;
        include proxy_params;
    }
}

server { listen 80; server_name api.example.com admin.example.com; return 301 https://$host$request_uri; }
```

- Set `FORWARDED_ALLOW_IPS` on the API to the proxy's address, so audit IPs and the login throttle see real clients.
- Keep `/docs` off in production (it is, with `APP_ENV=production`).
- The API sends HSTS in production. Add it at the proxy for the admin hostname too, once HTTPS works everywhere.

## 6. Deploying the API and the admin web

The CI workflow builds both images on every push (`Docker images build`). For production:

1. Build and tag images with the commit SHA (immutable tags; never deploy `latest`): `apps/api` target `runtime`, and `apps/admin-web`.
2. Push them to a private registry.
3. Run them with the environment above:
   - **API:** `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --workers 2` (the image's default). Liveness is `GET /health`; readiness is `GET /ready`, which also checks migrations.
   - **Admin web:** `node apps/admin-web/server.js` (the image's default) on port 3000. Liveness is `GET /healthz`.
4. Single-server option: `compose.yaml` runs PostgreSQL, the one-shot `migrate` job, the API and the web, bound to localhost behind the proxy. For production, set `APP_ENV=production`, the secrets and `SESSION_COOKIE_SECURE=true` in `.env`, and prefer a managed database (remove the `postgres` service and point `DATABASE_URL` at it).

## 7. Migrations

Alembic owns the schema. Never edit tables by hand, and never rebuild a production database.

1. **Back up first:** take a provider snapshot, or run `scripts/backup-db.sh` (OPERATIONS.md).
2. **Run migrations once, before the new API serves traffic:** `alembic upgrade head`, as a one-off job with the new image and the API environment (the compose `migrate` service does exactly this).
3. **Deploy the new API and web.** The new API's `/ready` returns 503 (`migrations: pending`) until step 2 has run, so a load balancer will not route to it early.
4. **Check:** `/ready` 200, log in, open a few records.

Migrations so far only add tables, columns, indexes and constraints. Write new ones as "expand, then contract": add first; remove only in a later release, after nothing reads the old shape. This keeps the previous release working against the new schema, which makes rollback possible. `alembic downgrade` exists for development; in production, prefer restoring the pre-migration backup.

## 8. First-time setup

1. Provision the database, bucket, secrets and DNS. Configure the proxy.
2. Run migrations (section 7). They also seed reference data: vehicle types, operation types, fuel types, expense categories, maintenance types. `python -m app.cli seed` is idempotent if run again.
3. Create the first administrator once:
   `BOOTSTRAP_ADMIN_PHONE=01XXXXXXXXX BOOTSTRAP_ADMIN_PASSWORD='long-unique-password' python -m app.cli bootstrap-admin`.
   The command refuses if a super admin already exists. **Remove both variables afterwards.**
4. Sign in to the admin web and create staff users (operations, accountant) with the least role each needs. Then add vehicles, drivers (with app accounts), assignments, routes with stop coordinates and radii, compensation plans and platforms.
5. Set up the scheduled jobs (section 9), backups and monitoring (section 10).
6. Build the driver app for production (section 11) and install it on the pilot phones.

## 9. Scheduled jobs

Run with the API image and environment, for example from cron on a single server:

```cron
# m  h  dom mon dow  command (UTC)
5    *  *   *   *    docker compose run --rm api python -m app.cli detect-exceptions
15   *  *   *   *    docker compose run --rm api python -m app.cli generate-notifications
30   1  *   *   *    docker compose run --rm api python -m app.cli prune-gps
40   1  *   *   *    docker compose run --rm api python -m app.cli prune-idempotency
0    1  *   *   *    PGHOST=... PGUSER=... PGDATABASE=... /opt/godaily/scripts/backup-db.sh /var/backups/godaily
```

All jobs are safe to repeat. They exit non-zero on failure, so alert on that.

## 10. Monitoring

- Scrape `GET /metrics` with `Authorization: Bearer $METRICS_TOKEN` from the monitoring network only. Suggested alerts are in OPERATIONS.md: readiness, 5xx rate, GPS ingestion while shifts are active, stale or failing exception runs, failing backups.
- Uptime checks on `https://api.example.com/health` and `https://admin.example.com/healthz`.
- Error reporting: register a reporter in `app/core/monitoring.py` (Sentry or GlitchTip example in OPERATIONS.md) with `send_default_pii=False`.
- Ship logs to the platform's log store. They are JSON, and secrets and personal fields are already scrubbed.

## 11. Driver app

1. `./gradlew :app:assembleRelease -PgoDailyApiBaseUrl=https://api.example.com/api/v1/` (or `bundleRelease` for the Play Store), signed with the keystore from section 3.
2. Distribution:
   - **Company phones (recommended for the pilot):** install the signed APK directly or through MDM.
   - **Google Play:** background location needs Play's declaration (an in-app prominent disclosure exists; a demo video and a privacy policy are also required). Expect review time.
3. On each phone:
   - grant precise location and "Allow all the time";
   - exempt the app from battery optimisation, and on Xiaomi, Oppo or Huawei also enable vendor autostart (see https://dontkillmyapp.com);
   - keep notifications on.
4. Run the device test plan in `apps/driver-android/README.md` before the pilot.

## 12. Rollout and rollback

**Release steps:**
1. CI green on the release commit.
2. Back up the database.
3. Run migrations.
4. Deploy the API.
5. Deploy the web.
6. Smoke test:
   - `/ready` 200;
   - login;
   - dashboard;
   - a vehicle page;
   - a report with CSV download;
   - one driver-app login on a test account;
   - `detect-exceptions` runs cleanly.
7. Watch the 5xx rate and GPS ingestion for 30 minutes.

**Rollback:**
- **Application only:** redeploy the previous image tags for the API and web. Because migrations are additive (section 7), the previous release runs on the newer schema.
- **A migration broke data or cannot run on the old code:**
  1. stop the API;
  2. restore the pre-deploy backup into a new database (`scripts/restore-db.sh`, OPERATIONS.md);
  3. point `DATABASE_URL` at it;
  4. deploy the previous images.

  Writes made after the backup are lost, so keep the deploy window short and announce it to drivers. Their phones queue GPS and shift ends offline and upload them afterwards.
- **Driver app:** keep the previous signed APK; reinstalling it over a newer one requires uninstalling first, which clears the offline queue. Make sure the queue is empty before rolling back a phone.

**Pilot first:** follow "Pilot Rollout Recommendation" in the master task list and the release report. Start with one fixed-route or school microbus and one ride-hailing vehicle for several real shifts before adding the fleet.
