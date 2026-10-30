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
| 09 | Android driver app foundation | 🟡 | Kotlin/Compose app in `apps/driver-android`: login, vehicle, today's shifts, start/end shift, current operation, permission onboarding, Keystore token, Arabic RTL. Pure logic in `core/` is unit-tested (53 tests). The `app/` module builds only in CI (the dev sandbox cannot reach Google Maven); not tested on a device yet. |
| 10 | Work-shift GPS tracking | 🟡 | Backend complete and tested (idempotent ingestion, shift-window privacy, quality flags, retention). App side: foreground location service, SQLite offline queue, idempotent batch sync, adaptive sampling, driver-visible status, device events. Sync/status/sampling logic unit-tested; device behaviour (background, reboot, OEM battery killers) not yet verified on phones. |
| 11 | Live fleet map & route replay | ✅ | Provider-neutral map (Leaflet impl), live polling, replay, stops, gaps, GPS vs odometer distance |
| 12 | Geofences & fixed-route loop detection | ✅ | Debounced engine, idempotent events, audited admin corrections |
| 13 | School route operations | ✅ | Scheduled runs, GPS-evidenced completion, review/missed states, audited corrections |
| 14 | Ride-hailing operations | 🟡 | API complete and tested. Manual statement entry (no scraping), approval generates revenue + custody receipts, reconciliation vs recorded shifts/time/distance. Admin web pending. |
| 15 | Fuel / CNG / oil ledger | 🟡 | API complete and tested. Extensible types (CNG, gasoline, diesel, oil); oil kept out of fuel figures; driver-app and staff entry; review/correction/audit. Admin web pending. |
| 16 | General expenses | 🟡 | API complete and tested. Configurable categories with P&L grouping; review/correction/audit; driver-paid costs reimbursed via the driver account. Admin web pending. |
| 17 | Collections & revenue | 🟡 | API complete and tested. Single revenue ledger with receipts (cash/electronic, driver/company), outstanding amounts, contract periods. Admin web pending. |
| 18 | Driver financial account & settlement | 🟡 | API complete and tested. Signed driver ledger (custody, advances, payments, adjustments), statements, settlements frozen at finalisation. Admin web pending. |
| 19 | Vehicle profitability | 🟡 | API complete and tested. Per-vehicle P&L from approved records with explicit allocation rules and incomplete-data warnings. Admin web pending. |
| 20 | Audit & exception detection engine | ⬜ | |
| 21 | Maintenance | ⬜ | |
| 22 | Notifications | ⬜ | |
| 23 | Reports | ⬜ | |
| 24 | Attachments / receipt storage | ⬜ | |
| 25 | Security hardening | ⬜ | |
| 26 | Data integrity & concurrency | ⬜ | |
| 27 | Observability & backups | ⬜ | |
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
