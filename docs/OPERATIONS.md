# Go Daily — Operations (Task 27)

How to watch the system, find a failing request, and back up and restore data. Deployment itself is in [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Logs

- The API writes one JSON object per line to stdout (`LOG_JSON=true`). Collect stdout with the platform's log service or `docker compose logs`.
- Every request produces one `request` line with method, path (never the query string), status and `duration_ms`.
- Each line carries `request_id`. The ID comes from the caller's `X-Request-ID` (64 printable characters at most), or is generated, and is returned in the response header on every status, 500 included.
- The admin web sends a new request ID with each API call. When the API fails (5xx), the user sees **"رمز المتابعة"** with the first 12 characters. Search the logs for that prefix to find the request and its traceback.
- Never logged: passwords and hashes, tokens and `Authorization` headers, cookies, idempotency keys, encryption and storage secrets, national IDs, phone numbers, coordinates. These keys are scrubbed even if code passes them by mistake.
- Background jobs log one line per failed rule or generator (`exception_rule_failed`, `notification_generator_failed`). The CLI exits with code 1, so schedulers can alert on it.

## Error monitoring

`app/core/monitoring.py` is the integration point. Unhandled API errors and failing background rules call `capture_exception(exc, component=..., ...)`. By default nothing beyond the log line happens.

To use a service such as Sentry or GlitchTip, register a reporter at startup, for example in `app/main.py`:

```python
import sentry_sdk
from app.core import monitoring

sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], send_default_pii=False, traces_sample_rate=0)
monitoring.register(lambda exc, ctx: sentry_sdk.capture_exception(exc))
```

Reporters receive the exception and only non-sensitive context: `component`, `path`, `request_id`, `name`. A failing reporter is logged and ignored. Keep `send_default_pii=False`, because request bodies can contain personal data.

The admin web's own server errors appear in its stdout (`docker compose logs admin-web`).

## Health and readiness

| Endpoint | Meaning | Use |
| --- | --- | --- |
| `GET /health` | The process is up (no dependencies checked) | Container liveness; the Docker `HEALTHCHECK` uses it |
| `GET /ready` | Database reachable **and** schema at the revision this build expects | Load balancer readiness and post-deploy check. Returns 503 with `{"migrations": "pending"}` until `alembic upgrade head` has run |

## Metrics

`GET /metrics` serves Prometheus text format when `METRICS_TOKEN` is set. Scrape it with `Authorization: Bearer <token>`. Without the token, or with a wrong one, it answers 404.

| Metric | Type | Notes |
| --- | --- | --- |
| `godaily_http_requests_total{method,route,status}` | counter | Labelled by route template (`/api/v1/fuel/{tx_id}`), never raw IDs; status class `2xx`…`5xx` |
| `godaily_http_request_duration_seconds` | histogram | Per route template |
| `godaily_active_shifts` | gauge | |
| `godaily_tracking_vehicles{state}` | gauge | Vehicles in an active shift: `ONLINE`, `STALE`, `OFFLINE` |
| `godaily_gps_points_received_5m` | gauge | Ingestion is flowing |
| `godaily_open_exceptions{severity}` | gauge | Cases still needing review |
| `godaily_exception_run_age_seconds` | gauge | Time since the last detection run; alert if it exceeds 2 hours |
| `godaily_exception_run_failed_rules` | gauge | Alert if above 0 |
| `godaily_pending_financial_reviews` | gauge | |

HTTP counters are kept per worker process. Fleet gauges are read from the database at scrape time.

Suggested alerts:
- `/ready` not 200 for 2 minutes;
- 5xx rate above 1% for 10 minutes;
- `godaily_gps_points_received_5m == 0` while `godaily_active_shifts > 0` for 15 minutes;
- exception runs stale or failing;
- backup job failing (see below).

## Scheduled jobs

Listed in the README ("Scheduled jobs"): `detect-exceptions` hourly, `generate-notifications` hourly after it, `prune-gps` and `prune-idempotency` daily, and the database backup below. Each exits non-zero on failure.

## Backups

What needs backing up:

1. **PostgreSQL**: all operational, financial and audit data.
2. **Attachments**: receipts, statements and invoices.
   - With `STORAGE_BACKEND=local`, back up the `attachments-data` volume (`/app/var/attachments`).
   - With S3, enable bucket versioning and a lifecycle rule; files are never overwritten (keys are unique) and only soft-deleted in the database.
3. **Secrets**, stored outside the server (password manager or the platform's secret store): `DATA_ENCRYPTION_KEY` and database credentials. **Without `DATA_ENCRYPTION_KEY`, stored national IDs cannot be decrypted, even from a good backup.**

### Database

Prefer the hosting provider's managed backups with point-in-time recovery (PITR) when available. Daily snapshots plus WAL retention of 7–30 days are reasonable. In addition, or on a self-managed server, take logical dumps:

```bash
# Uses PGHOST/PGPORT/PGUSER/PGDATABASE and PGPASSWORD or ~/.pgpass (nothing secret in argv).
BACKUP_KEEP_DAYS=30 scripts/backup-db.sh /var/backups/godaily
```

The script writes `godaily-<UTC time>.dump` (pg_dump custom format) and its `.sha256`, and refuses to keep an unreadable archive (`pg_restore --list`). It deletes dumps older than `BACKUP_KEEP_DAYS` and prints the file path.

With Docker Compose, either run it from the host against the published port, or dump inside the container:

```bash
docker compose exec -T postgres pg_dump -U godaily --format=custom godaily > godaily-$(date -u +%Y%m%dT%H%M%SZ).dump
```

Recommended:
- daily at a quiet hour (e.g. 03:00 Cairo time);
- copy each dump off the server (object storage in another account or region, with encryption at rest);
- alert when the job fails or produces no file;
- keep dumps at least as long as financial records must be retrievable.

### Attachments (local storage)

```bash
docker run --rm -v go-daily_attachments-data:/data -v /var/backups/godaily:/backup alpine \
  tar czf /backup/attachments-$(date -u +%Y%m%dT%H%M%SZ).tgz -C /data .
```

Run it after the database dump, so that every attachment row has its file. Files added in between only mean some files exist without a row, which is harmless.

## Restore procedure

Restores never overwrite the live database. They go into a new database, which is checked and then switched to.

1. **Stop writes.** Scale the API to zero or put the site in maintenance, so nothing is lost between the restore point and the switch.
2. **Restore into a new database:**

   ```bash
   scripts/restore-db.sh /var/backups/godaily/godaily-20261030T030000Z.dump godaily_restored_20261030
   ```

   The script verifies the checksum, refuses an existing database name or an unsafe one, restores with `--exit-on-error`, and prints the schema revision and row counts of the main tables.
3. **Check:**
   - the schema revision matches the release (or run `alembic upgrade head` against the restored database if the release is newer);
   - the row counts are plausible;
   - the latest shifts, fuel records and audit entries are where you expect them.
4. **Restore attachments** (local storage): extract the matching archive into the volume. With S3, restore deleted object versions only if needed.
5. **Switch:**
   - point `DATABASE_URL` at the restored database;
   - keep the same `DATA_ENCRYPTION_KEY`;
   - start the API;
   - confirm `GET /ready` is 200;
   - log in, open a vehicle, a driver (including the national ID) and a recent financial record.
6. **Keep the old database** until the restored one has been used successfully for a few days. Then drop it.

For a managed provider's PITR, restore to a new instance at the chosen time, then follow steps 3–6.

### Restore drill

Rehearse at least quarterly, and after major upgrades, on a scratch server: restore last night's dump with steps 2–3 and record how long it took. The procedure was rehearsed on 2026-10-30 against the development database: backup, checksum, restore into a new database, schema revision `0011_notifications`, and row counts identical to the source. A restore is only proven once it has been rehearsed.
