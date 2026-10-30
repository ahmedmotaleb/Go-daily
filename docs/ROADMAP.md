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
| 06 | Operation types & route definitions | ⬜ | |
| 07 | Shifts & operation sessions | ⬜ | |
| 08 | Admin dashboard V1 | ⬜ | |
| 09 | Android driver app foundation | ⬜ | |
| 10 | Work-shift GPS tracking | ⬜ | |
| 11 | Live fleet map & route replay | ⬜ | |
| 12 | Geofences & fixed-route loop detection | ⬜ | |
| 13 | School route operations | ⬜ | |
| 14 | Ride-hailing operations | ⬜ | |
| 15 | Fuel / CNG / oil ledger | ⬜ | |
| 16 | General expenses | ⬜ | |
| 17 | Collections & revenue | ⬜ | |
| 18 | Driver financial account & settlement | ⬜ | |
| 19 | Vehicle profitability | ⬜ | |
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
