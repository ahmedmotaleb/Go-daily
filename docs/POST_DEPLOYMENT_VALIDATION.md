# Post-deployment validation report (U54)

**Status: template.** No deployment has been validated yet: there is no staging or production environment (PRODUCTION_RELEASE_GATE.md, gates 3 and 17). Copy this file to `docs/reports/DEPLOYMENT_VERIFICATION_<environment>_<YYYY-MM-DD>.md` for each deployment and fill it in. **Never mark a check ✅ without the evidence**: a screenshot, a log extract, a command output, a record id. A check that could not be run is ⬜ with the reason.

Use test accounts and test vehicles only. Do not record real drivers' national IDs, phone numbers, passwords or tokens in the report.

## Deployment

| Item | Value |
|---|---|
| Environment | staging / production |
| Date and time (Cairo) | |
| Release commit (API, web, driver app) | |
| Migration head after deploy (`alembic current`) | |
| Pre-deploy backup (file, size, checksum) | |
| Deployed by | |
| Validated by (not the deployer, where possible) | |

## Checks

Legend: ✅ passed with evidence · ❌ failed (open an issue, decide rollback) · ⬜ not run (reason).

### 1. Platform

| # | Check | How | Expected | Result | Evidence |
|---|---|---|---|---|---|
| 1.1 | Liveness | `GET /health` | 200 | | |
| 1.2 | Readiness | `GET /ready` | 200; database, migrations at head, storage | | |
| 1.3 | Startup guard | API log at start | No development defaults refused or warned (U41) | | |
| 1.4 | HTTPS and headers | `curl -I` the web and the API | HSTS, CSP with nonce, no `X-Powered-By` | | |
| 1.5 | Time zone | Dashboard date; a record's time | Africa/Cairo shown; UTC stored | | |

### 2. Login and RBAC

| # | Check | How | Expected | Result | Evidence |
|---|---|---|---|---|---|
| 2.1 | Admin login with 2FA | Test SUPER_ADMIN | TOTP asked when `TWOFA_ENFORCE=true` (gate 12) | | |
| 2.2 | Wrong password | 5 attempts | Generic message, lockout, event on «أحداث الأمان» | | |
| 2.3 | Role limits | Log in as OPERATIONS and ACCOUNTANT | Menus and API follow the role; a forbidden URL gives 403 and is audited | | |
| 2.4 | Re-authentication | Change a policy | `/confirm` asked when the session is older than the window (U35) | | |
| 2.5 | Driver app login | Test driver on a test phone | Logs in; staff accounts refused on the app | | |

### 3. Fleet and assignments

| # | Check | How | Expected | Result | Evidence |
|---|---|---|---|---|---|
| 3.1 | Vehicles and drivers | Open lists and one record of each | Data present; national ID masked | | |
| 3.2 | Assignment | Assign the test driver to the test vehicle | Saved and audited; conflicts refused | | |

### 4. Shifts and GPS

| # | Check | How | Expected | Result | Evidence |
|---|---|---|---|---|---|
| 4.1 | Start a shift on the phone | Odometer photo, start | Shift ACTIVE; tracking notification visible | | |
| 4.2 | GPS ingestion | Drive 10 minutes | Points arrive; «التتبع المباشر» shows the vehicle with fresh time | | |
| 4.3 | Offline and replay | Airplane mode 5 minutes, then back | Queued points upload; no duplicates; gap shown, not filled | | |
| 4.4 | Loops (fixed route) | Drive the test route | Legs and loops detected on the shift page | | |
| 4.5 | End and close-out | End shift, close-out with cash | Shift COMPLETED; close-out on «تحصيل نقدية السائقين» | | |
| 4.6 | Replay | Shift page map | Track, stops and gaps match the drive | | |

### 5. Fuel and receipts

| # | Check | How | Expected | Result | Evidence |
|---|---|---|---|---|---|
| 5.1 | Fuel from the phone | Entry with receipt photo | Record SUBMITTED; photo in storage; signed URL opens and expires | | |
| 5.2 | Review | Approve as accountant | Reimbursement on the driver account if driver-paid | | |
| 5.3 | Plausibility | Open the record | Checks shown; no false certainty | | |

### 6. Revenue, expenses and settlement

| # | Check | How | Expected | Result | Evidence |
|---|---|---|---|---|---|
| 6.1 | Revenue | Fixed-route collection for the test shift | Approved; appears in reconciliation | | |
| 6.2 | Expense | One expense with receipt | Approved; in profitability | | |
| 6.3 | Ride-hailing import | Small test CSV (U19) | Preview, import, rollback works | | |
| 6.4 | Settlement | Draft → review → approve → record payment (U20) | Ledger entries correct; payment only recorded | | |

### 7. Review cases, reports, notifications

| # | Check | How | Expected | Result | Evidence |
|---|---|---|---|---|---|
| 7.1 | Detection | `python -m app.cli detect-exceptions` | Runs cleanly; cases worded «مراجعة مطلوبة» | | |
| 7.2 | Reports | Open three reports, download CSV | Figures match records; Arabic CSV opens correctly | | |
| 7.3 | Notifications | `python -m app.cli generate-notifications` | In-app notifications created; external channel if configured | | |

### 8. Backup and monitoring

| # | Check | How | Expected | Result | Evidence |
|---|---|---|---|---|---|
| 8.1 | Scheduled backup | Check the last run | File present off-site, size and checksum logged | | |
| 8.2 | Restore spot check | Restore last backup to a scratch database | Migrations at head; record counts plausible (BACKUP_RESTORE_DRILL.md) | | |
| 8.3 | Metrics | Scrape `/metrics` with the token | Values present; 404 without the token | | |
| 8.4 | Alerts | Alert rules loaded in the monitoring system | `GoDailyApiDown` and others active (gate 8) | | |
| 8.5 | Errors | Error tracker or logs for 30 minutes | No new 5xx; no sensitive values in logs | | |

## Outcome

| Item | Value |
|---|---|
| Checks passed / failed / not run | |
| Failures and decisions (fix forward, rollback, accept with owner and date) | |
| Test data cleaned up (shifts, records voided with reason «اختبار ما بعد النشر») | |
| Verdict | **Validated** only if every check passed or each exception is accepted in writing |

| Role | Name | Date | Signature |
|---|---|---|---|
| Operations | | | |
| Development | | | |
| Management | | | |
