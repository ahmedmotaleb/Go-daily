# Go Daily — Release report (Task 32)

**Date:** 2026-10-30 · **Branch:** `claude/new-session-lpatv5` (draft PR #1, not merged) · **Schema revision:** `0011_notifications`

## Verdict

**Not yet production-ready. Ready for a supervised pilot once the driver app has passed the device test plan on real phones.**

The backend, admin web and the driver app's logic are complete for Tasks 01–32 and verified by automated tests, browser checks and CI. One gate is still open, and only real phones can close it: on-device behaviour of the Android app (background tracking, reboot, vendor battery killers, driver UX). GPS evidence is central to the product, so this gate matters. Everything else on the release checklist is verified (see below).

## Release gate checklist

| Item | Status | Evidence |
| --- | --- | --- |
| All backend tests pass | ✅ | 276 pytest tests on PostgreSQL 16, locally and in CI; ruff, ruff format, mypy (strict) clean |
| Frontend lint passes | ✅ | ESLint + Prettier check, locally and in CI |
| TypeScript typecheck passes | ✅ | `next typegen && tsc`, locally and in CI |
| Frontend production build passes | ✅ | `next build` (standalone), locally and in CI; Docker images build in CI |
| Android build/tests pass | ✅ (debug) | `core`: 65 JVM tests, locally and in CI. `app`: `assembleDebug` + Android lint in CI. A signed release build needs the production keystore (not in the repository) |
| Alembic migrations apply from a clean DB | ✅ | Fresh database → `upgrade head` (11 revisions), `alembic check` clean; every test run also builds the schema from migrations |
| Upgrade path from an existing DB | ✅ | Database at `0006` with users, vehicles, drivers, a completed shift and audit rows → upgraded through `0007`–`0011` with data intact; new features (exception detection, notifications) ran on it |
| Authentication / RBAC | ✅ | `test_auth`, `test_users_rbac`, route-generated RBAC matrix (`test_security`: every route × every role); browser: login, wrong password, user creation, deactivation, logout |
| Vehicle CRUD | ✅ | `test_vehicles`; browser `e2e_fleet` (odometer decrease needs a reason, licence expiry alert) |
| Driver CRUD | ✅ | `test_drivers`; browser (national ID validation and audited reveal, app account, compensation plan) |
| Assignments | ✅ | `test_assignments` (DB exclusion constraint included); browser |
| Shifts | ✅ | `test_shifts`, `test_driver_app`; browser `e2e_shifts` (one active shift per driver, end odometer below start refused) |
| GPS ingestion / retry | ✅ | `test_tracking` (idempotent batches, shift window, late sync); core `SyncEngineTest` + `SyncReliabilityTest` (restart, lost answers, 200-cycle simulation: every fix exactly once) |
| Live / latest position | ✅ | `test_tracking`; browser `e2e_map` |
| Route replay | ✅ | `test_tracking` (gaps and stops, never bridged); browser `e2e_map` |
| Fixed-route loop detection | ✅ | `test_geofence_engine`, `test_route_events_api`, scenario A (3 loops) |
| Fuel / CNG / gasoline / oil ledger | ✅ | `test_finance_costs`; scenarios A and B; fuel report |
| Revenue / expense ledger | ✅ | `test_finance_revenue`, `test_finance_costs`; scenario D (corrections) |
| Driver settlement math | ✅ | `test_finance_settlements` (plans, overlap, freeze at finalisation); driver statements in scenarios A and B |
| Profitability calculations | ✅ | `test_finance_*`; scenarios A (900 − 475 = 425), B, D (850 − 15 = 835) |
| Exception engine | ✅ | `test_exceptions` (15 rules, dedupe, review workflow), scenario C; browser review flow |
| Maintenance | ✅ | `test_maintenance`; browser `e2e_maint` (schedule, record, invoice, approval) |
| Arabic RTL reviewed | ✅ | Screenshots of every module reviewed during development; 19 pages swept at 390 and 768 px (no horizontal overflow); form labels checked on 11 pages. Native-speaker field review is part of the pilot |
| Mobile driver UX reviewed | ❌ | The app compiles and passes lint, but it has **not been run on a phone or emulator** in this environment |
| No secrets committed | ✅ | Pattern scan of all tracked files and all 27 commits (cloud keys, private keys, tokens): none; no `.env`, keystore or certificate files ever added |
| Docs updated | ✅ | README, ARCHITECTURE, ROADMAP, SECURITY, OPERATIONS, DEPLOYMENT, driver app README, this report |
| Backup / restore procedure reviewed | ✅ | `scripts/backup-db.sh` → `scripts/restore-db.sh` round trip rehearsed: checksum verified, restored into a new database, schema revision and row counts identical |

## 1. Completed functionality

| Area | What exists |
| --- | --- |
| Foundation | Monorepo, FastAPI + PostgreSQL API, Next.js admin web (Arabic RTL, installable), Kotlin/Compose driver app, Docker images, CI for all four parts |
| Access | Opaque hashed sessions, Argon2id, lockout and per-IP throttling, RBAC with five roles enforced in the API, append-only audit log |
| Fleet | Vehicles (odometer rules, licence/insurance expiry), drivers (encrypted national IDs with audited reveal), assignment history without overlaps |
| Operations | Operation types, routes with stop geofences, shifts and operation sessions, dashboard |
| Tracking | Driver app with foreground tracking, offline queue, idempotent sync, adaptive sampling and visible status; server ingestion with quality flags, shift-window privacy and retention; live map; route replay |
| Routes | Debounced loop/leg detection with audited manual corrections; school runs that need GPS evidence |
| Finance | One review lifecycle (submit, approve, reject, void, correct-by-replacement) for fuel/CNG/gasoline/oil, expenses, revenue and platform statements; receipts and outstanding amounts; driver ledger (custody, reimbursements, advances, payments); settlements frozen at finalisation; vehicle P&L from approved records with incomplete-data warnings |
| Review | 15 explainable exception rules with stored evidence and neutral labels («مراجعة مطلوبة» / «حالة غير معتادة»), dedupe, audited review workflow |
| Maintenance | Types, per-vehicle km/day schedules, due states, service records with costs, downtime and invoices |
| Attachments | Private storage (local or S3-compatible), content-sniffed types, duplicate-file warnings, evidence locked after approval |
| Notifications | In-app inbox and header bell with dedupe, severity and self-clearing; channel interface for push/e-mail/WhatsApp/SMS |
| Reports | 12 Arabic reports with filters, traceable totals and Excel-friendly CSV |
| Operations support | Request IDs and user-visible follow-up codes, error-monitoring hook, Prometheus metrics, readiness that checks migrations, backup/restore scripts, deployment and operations guides |

## 2. Automated test results (this release)

| Suite | Result | Where |
| --- | --- | --- |
| API (pytest, PostgreSQL 16) | **276 passed** in 27 files: auth 20, exceptions 22, shifts 16, users/RBAC 15, phone/security 15, security matrix 14, vehicles 13, revenue 12, notifications 11, assignments 11, reports 10, integrity 10, geofence 10, settlements 10, costs 10, drivers 10, tracking 9, observability 9, driver app 8, attachments 8, operations 7, maintenance 6, route events 5, health 5, scenarios 4, CLI 4, dashboard 2 | Local and CI (`API (lint, types, tests)`) |
| API static checks | ruff, ruff format, mypy strict: clean | Local and CI |
| Admin web | 27 vitest tests; ESLint, Prettier, `tsc`, production build: clean | Local and CI |
| Driver app core | 65 JVM tests (API client 15, sync engine 11, reliability 2, backoff 4, digits 4, sampler 7, location fix 5, last position 2, receipt image 3, tracking status 12) | Local and CI |
| Driver app module | `assembleDebug` + Android lint | CI only (the sandbox cannot reach Google's Maven repository) |
| Docker images | API and admin web build | CI |
| Dependency audit | pip-audit (119 runtime packages) and `pnpm audit --prod`: no known vulnerabilities | Local, 2026-10-30 |

The suite also passed when run across local midnight (00:02 Cairo time), which flushed out a date assumption in one scenario test. One CI run failed on a flaky test of my own (a log-scrubbing assertion that could match the timestamp); it was fixed in `0abf912`.

## 3. Manual and environment checks

- **Browser end-to-end scripts** against a production build (Playwright, Chromium), all passing:
  - authentication and users;
  - fleet, drivers and assignments;
  - routes and shifts;
  - live map and replay;
  - all finance pages;
  - maintenance and attachments;
  - exception review;
  - notifications and the bell;
  - all 12 reports with CSV download;
  - CSP compliance including the map;
  - responsive sweep.

  Three older scripts first failed on data left by earlier runs (duplicate phone, a vehicle that already had a driver, a stale active shift). They passed after the scripts were made self-contained. No product defects were behind them.
- **Production mode:**
  - without `DATA_ENCRYPTION_KEY` the API refuses to start;
  - with it, `/ready` is green (database and migrations), HSTS is sent, docs are off and `/metrics` requires its token.
- **Compose:** `docker compose config` validates, including tile URLs with braces.
- **Migrations:** fresh database, plus the upgrade from `0006` with data.
- **Backup/restore** drill on the development database.
- **Secret scan** of the tree and full history.

## 4. Known limitations

- **Driver app not device-tested.** Background tracking, reboot recovery, Android 13+ task-manager stops and vendor battery killers (Xiaomi, Oppo, Huawei…) need the device test plan in `apps/driver-android/README.md`.
- Route deviation uses straight lines between route stops, not road geometry. The corridor is generous (2 km) and the rule says so in its evidence.
- Fuel consumption is compared weekly in cost per km against the vehicle's own history (price changes affect it). It is a review hint, not a measurement.
- No PDF reports: reliable Arabic PDF rendering was not verified, so CSV is offered instead.
- The login throttle is per API process; the edge proxy should add a stricter limit (DEPLOYMENT.md).
- The web CSP allows inline scripts (Next.js without nonces).
- No two-factor authentication.
- The lockout message reveals that an account exists.
- The S3 backend is tested against a mocked S3, not a real bucket.
- Exception evidence keeps stop coordinates after raw GPS points are pruned.
- In-process HTTP metrics are per worker.

## 5. External services and configuration still required

| Needed | Why | Reference |
| --- | --- | --- |
| Hosting for two containers + scheduler, domains, TLS | Run the API and web behind HTTPS | DEPLOYMENT.md §1, §5, §6 |
| Managed PostgreSQL 16 with backups/PITR and `btree_gist` | Data | DEPLOYMENT.md §2 |
| `DATA_ENCRYPTION_KEY` (generated once, stored safely) | National ID encryption; the API will not start without it | DEPLOYMENT.md §3–4 |
| Private S3-compatible bucket (or a backed-up volume) | Receipts, statements, invoices | DEPLOYMENT.md §3 |
| Map tile provider and attribution | The live map; the OpenStreetMap default is for light use only | DEPLOYMENT.md §3 |
| Monitoring (Prometheus or similar), uptime checks, optionally Sentry/GlitchTip | Alerts and error reports | OPERATIONS.md |
| Cron or job runner | Exception detection, notifications, pruning, backups | DEPLOYMENT.md §9 |
| Android signing keystore; MDM/APK distribution or a Google Play account with the background-location declaration | Installing the driver app | DEPLOYMENT.md §11 |
| A push/e-mail/WhatsApp/SMS provider, only if wanted | Notifications beyond in-app (a small channel class must be written) | `notification_channels.py` |
| Ride-hailing platforms | None: statements are entered manually; no scraping or unofficial integration | — |

## 6. Security and privacy considerations

- **Location data:**
  - GPS is collected only during an authorised work shift, after an in-app disclosure, with a visible ongoing notification;
  - the server refuses points outside the shift window;
  - raw points are pruned after `GPS_RETENTION_DAYS` (180);
  - accountants no longer have live-location access.

  Publish a driver privacy notice that matches these facts and the retention period.
- **Personal data:**
  - national IDs are encrypted at rest, and revealing one is audited;
  - phone numbers, coordinates, tokens and secrets are scrubbed from logs;
  - API responses are `no-store`.
- **Fairness:** automated cases are labelled «مراجعة مطلوبة» or «حالة غير معتادة», show their evidence and thresholds, and say on every page that they are not proof. Reviews need a written outcome and are audited.
- **Integrity:**
  - financial history is never edited or deleted (void-and-replace);
  - audit rows are protected by database triggers;
  - concurrent reviews are serialised by row locks.
- **Access:**
  - every API route is tied to a permission, checked by a generated test matrix;
  - files are served only after a permission check;
  - drivers can reach only their own driver-app data.
- See SECURITY.md for the full review and residual risks.

## 7. Recommended pilot rollout

1. **Before the pilot:**
   - deploy to a staging environment following DEPLOYMENT.md;
   - run the driver-app device test plan on at least one stock-Android phone and one aggressive-OEM phone (e.g. Xiaomi);
   - fix what it finds;
   - publish the drivers' privacy notice.
2. **Pilot vehicles:** one fixed-route/school microbus and one ride-hailing vehicle, each with its regular driver, for at least 5–10 real shifts.
3. **Configure for the pilot:**
   - route stop coordinates and radii checked on site;
   - compensation plans;
   - the ride-hailing platform;
   - map tiles;
   - scheduled jobs;
   - daily backups with an off-site copy;
   - monitoring alerts.
4. **Validate each day:**
   - GPS continuity (gaps, interruptions, battery use reported by drivers);
   - loop counts against what the driver reports;
   - school runs completed with evidence;
   - odometer against GPS;
   - CNG/gasoline/oil entries against receipts;
   - collections and the driver balance;
   - platform statement reconciliation;
   - exception cases (false positives, so thresholds can be tuned through `EXCEPTION_*`);
   - notifications (useful, not noisy);
   - vehicle P&L against the accountant's own figures.
5. **Review weekly** with operations, finance and the two drivers. Record issues, fix them, and repeat the device checks after app updates.
6. **Expand** to the rest of the fleet in small groups only after the pilot issues are closed and a backup restore has been rehearsed on the production setup.
