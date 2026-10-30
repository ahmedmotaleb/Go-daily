# Go Daily — Roadmap

Phases follow the master task list ([`GO_DAILY_CLAUDE_MASTER_TASKS.md`](GO_DAILY_CLAUDE_MASTER_TASKS.md)). Status values:

- ✅ done and verified
- 🟡 partial (see notes)
- ⬜ not started
- ⛔ blocked on an external dependency or decision

| # | Phase | Status | Notes |
| --- | --- | --- | --- |
| 01 | Repository foundation | ✅ | Monorepo, API, admin web, Docker, CI, docs |
| 02 | Authentication, users & RBAC | ✅ | Opaque sessions, Argon2id, lockout, RBAC, append-only audit, user management UI |
| 03 | Fleet / vehicles | ✅ | Extensible types, normalised plates, expiry indicators, odometer correction audit |
| 04 | Drivers | ✅ | Encrypted national IDs, app accounts, versioned compensation plans |
| 05 | Driver ↔ vehicle assignment history | ✅ | PRIMARY/RELIEF, DB exclusion constraints, never deleted |
| 06 | Operation types & route definitions | ✅ | Extensible types with behaviour kind; routes with ordered stops/geofence radius |
| 07 | Shifts & operation sessions | ✅ | Lifecycle, single active shift, odometer rules, multiple sessions per shift |
| 08 | Admin dashboard V1 | ✅ | Real KPIs and lists; map/alerts placeholders until GPS phase |
| 09 | Android driver app foundation | 🟡 | Kotlin/Compose app in `apps/driver-android`: login, vehicle, today's shifts, start/end shift, current operation, permission onboarding, Keystore token, Arabic RTL. Pure logic in `core/` is unit-tested (53 tests). The `app/` module compiles and passes Android lint in CI (the dev sandbox cannot reach Google Maven); not tested on a device yet. |
| 10 | Work-shift GPS tracking | 🟡 | Backend complete and tested (idempotent ingestion, shift-window privacy, quality flags, retention). App side: foreground location service, SQLite offline queue, idempotent batch sync, adaptive sampling, driver-visible status, device events. Sync/status/sampling logic unit-tested; device behaviour (background, reboot, OEM battery killers) not yet verified on phones. |
| 11 | Live fleet map & route replay | ✅ | Provider-neutral map (Leaflet impl), live polling, replay, stops, gaps, GPS vs odometer distance |
| 12 | Geofences & fixed-route loop detection | ✅ | Debounced engine, idempotent events, audited admin corrections |
| 13 | School route operations | ✅ | Scheduled runs, GPS-evidenced completion, review/missed states, audited corrections |
| 14 | Ride-hailing operations | ✅ | Manual statement entry (no scraping); approval generates revenue + custody receipts; reconciliation vs recorded shifts, time and distance; statement files attach to the statement. API + admin web tested. |
| 15 | Fuel / CNG / oil ledger | ✅ | Extensible types (CNG, gasoline, diesel, oil); oil kept out of fuel figures; staff entry, review, correction, audit and receipt files in API + admin web; drivers record purchases during the shift in the app (API tested; app compiles and passes lint in CI, not device-tested). The API accepts a receipt photo and location from the app, but the app does not send them yet (Task 29). |
| 16 | General expenses | ✅ | Configurable categories with P&L grouping; review/correction/audit; receipt files; driver-paid costs reimbursed via the driver account. API + admin web tested. |
| 17 | Collections & revenue | ✅ | Single revenue ledger with receipts (cash/electronic, driver/company), outstanding amounts, contract periods, filters and summaries by vehicle/driver/date/kind. API + admin web tested. |
| 18 | Driver financial account & settlement | ✅ | Signed driver ledger (custody, reimbursements, advances, payments, reasoned adjustments), statements, settlements frozen at finalisation and non-overlapping. API + admin web tested. |
| 19 | Vehicle profitability | ✅ | Per-vehicle P&L from approved records with stated allocation rules and incomplete-data warnings; maintenance = approved maintenance records + maintenance-group expenses. API + admin web tested. |
| 20 | Audit & exception detection engine | ✅ | 15 explainable rules (tracking, odometer, fuel, duplicates, revenue) with stored evidence, neutral labels (مراجعة مطلوبة / حالة غير معتادة), dedupe, "no longer detected" marking, audited review workflow (open, under review, escalated, explained, corrected, dismissed, reopen), CLI for scheduling and a "run now" button. API + admin web tested. Rules use recorded data only; route deviation uses straight lines between stops, not roads. |
| 21 | Maintenance | ✅ | Types with default km/day intervals; per-vehicle schedules with overrides and a known baseline; due states (ok / soon / overdue / no baseline); service records with parts/labour/other cost, vendor, downtime, invoices, review lifecycle and corrections; optional link to an oil purchase without counting it twice. API + admin web tested. |
| 22 | Notifications | ✅ | In-app inbox and header bell: document expiry, maintenance due, tracking interruption, important exception cases, daily pending-review summary. Per-user dedupe, severity, automatic clearing when the cause is gone; channel interface for future push/e-mail/WhatsApp/SMS (only a development log channel ships). API + admin web tested. |
| 23 | Reports | ✅ | 12 Arabic reports (daily operations, route loops, school runs, ride-hailing, revenue, expenses, CNG/gasoline/oil, driver statements, vehicle profitability, GPS vs odometer, exceptions, maintenance) with date/vehicle/driver/operation/route/fuel/category filters. Totals are sums of the listed records; each report needs the permissions of its data. CSV export with UTF-8 BOM and formula-injection protection. **No PDF:** not implemented, because reliable Arabic PDF rendering was not verified. API + admin web tested. |
| 24 | Attachments / receipt storage | ✅ | Storage abstraction (local disk or any S3-compatible bucket, chosen by environment; objects private); type sniffed from content (JPEG/PNG/WebP/PDF), size limit, server-generated keys, sha256 duplicate warning, metadata in PostgreSQL, files served only after a permission check on the owning record, soft delete with reason, evidence locked once a record is approved or voided. Local backend verified end to end; S3 backend tested against a mocked S3 (moto), not against a real bucket. |
| 25 | Security hardening | ✅ | Review recorded in `docs/SECURITY.md`. Route-generated RBAC matrix test (every route × every role; login required everywhere; drivers confined to the driver app). Accountants lose live-location access (least privilege). Per-IP login throttle on top of account lockout; API security headers (no-store, nosniff, frame deny, HSTS in production); production CSP for the web; wider log scrubbing (phone, coordinates, cookies, secrets). Dependency audit clean on 2026-10-30. Residual risks listed in the doc. |
| 26 | Data integrity & concurrency | ✅ | Row locks on every financial write path (approve/reject/void/correct/finalise; second reviewer gets 409). Constraint inventory and decisions in `docs/ARCHITECTURE.md` (assignments, shift lifecycle, odometer, GPS/event idempotency, one live ledger/revenue entry per source, settlement overlap, loop dedupe, append-only audit), each with tests. |
| 27 | Observability & backups | ✅ | `docs/OPERATIONS.md`. Request IDs now on every response incl. 500s and shown to users as a follow-up code; error-monitoring hook (no vendor); token-protected Prometheus `/metrics` (HTTP by route template + fleet gauges); `/ready` also fails while migrations are pending; tested `scripts/backup-db.sh` / `restore-db.sh` (restore into a new database only). Fixes: API now refuses to start without `DATA_ENCRYPTION_KEY` outside dev; trusted proxies configurable (was `*`); empty env values mean unset. |
| 28 | PWA & admin UX polish | ⬜ | |
| 29 | Driver app reliability | ⬜ | |
| 30 | End-to-end operational scenarios | ⬜ | |
| 31 | Production deployment preparation | ⬜ | |
| 32 | Final QA & release gate | ⬜ | |

## Pilot rollout

Do not put the whole fleet on an untested release. Pilot first with one fixed-route/school microbus and one ride-hailing vehicle. Validate them over several real shifts for:

- GPS reliability and battery use
- loop detection
- odometer reconciliation
- fuel entry
- collections
- driver usability
- alerts
- financial totals

Expand only after pilot issues are fixed.
