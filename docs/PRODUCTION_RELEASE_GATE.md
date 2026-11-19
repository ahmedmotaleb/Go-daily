# Production Release Gate V2 (U53)

**Verdict: NOT READY FOR PRODUCTION.** Gates 3–10, 12–15 and 17 below are still open. Every one of them needs real infrastructure, real phones, real shifts or a management decision; none can be closed from the repository alone. The system is a **pilot candidate**: run the pilot (U50–U52) first.

Rule: production goes live only when **every** gate is ✅ with the evidence linked, or management accepts an open gate in writing. Acceptance names the person, the date, the risk and the mitigation. Nothing is marked ✅ without evidence.

| # | Gate | Status | Evidence / what is missing | Owner |
|---|---|---|---|---|
| 1 | CI green on the release commit | ✅ for the current branch head | GitHub Actions on PR #1: API (lint, types, tests, migrations up/down), admin web (lint, types, tests, build), driver app (core tests, Android build, lint). Re-check on the exact release commit. | Development |
| 2 | Migrations tested | ✅ in CI and locally | 0001–0021 apply to a clean database and downgrade cleanly in CI. The restore drill confirmed the schema at head and `alembic check` clean (BACKUP_RESTORE_DRILL.md). | Development |
| 3 | Staging deployed | ⬜ open | No staging environment yet. Provision it per ENVIRONMENTS.md: its own database, bucket, Redis, secrets and accounts. Deploy the release and run the smoke test. | Operations / development |
| 4 | Physical Android test passed | ⬜ open | DEVICE_PILOT_TEST_PLAN.md scenarios P01–P28 on at least one class A and one class B phone. Not run (no phones available to development). | Operations |
| 5 | GPS pilot passed | ⬜ open | PILOT_ACCEPTANCE_REPORT.md criteria A1–A6 over real shifts. All NOT RUN. | Operations |
| 6 | Real object storage validated | ⬜ open (U29 BLOCKED) | Needs a real S3-compatible bucket and credentials. Validate upload and retrieval, signed URL expiry, unauthorized rejection, type and size limits, deletion and backups. | Operations |
| 7 | Backup and restore passed (production-like) | ⬜ open | Rehearsed only on a development database (BACKUP_RESTORE_DRILL.md). Repeat on staging with a real-size off-site backup, attachments and readable national IDs, and measure the RTO. | Operations |
| 8 | Monitoring active | ⬜ open | Metrics, error counters and alert rules are ready (`/metrics`, `ops/monitoring/alerts.yml`, OPERATIONS.md "Alerts"). A Prometheus/Alertmanager (or provider) setup scraping production does not exist yet. Validate the rules with `promtool`. | Operations |
| 9 | Alert drill successful | ⬜ open | Stop the API on staging and confirm `GoDailyApiDown` reaches the on-call person. Repeat for storage errors. | Operations |
| 10 | Android signing ready | ⬜ open | Release keystore not created. Keystore owner, custody and Play App Signing decision (DRIVER_APP_RELEASE.md §3). First signed build verified with `apksigner`. | Management / development |
| 11 | Security risks accepted or fixed | ⚠️ partly | Fixed in this branch: two-factor login (U31), shared rate limits (U32), no account-existence leaks (U33), nonce CSP (U34), startup guard against development defaults (U41). Open: residual risks in SECURITY.md "Residual risks"; the CSP exception for style attributes; crash reporting not chosen. Needs a written review and acceptance. | Management |
| 12 | 2FA policy decided | ⬜ decision | Code ready; `TWOFA_ENFORCE` is off by default. Decide that it is mandatory for SUPER_ADMIN and ADMIN (recommended), enrol them, then set `TWOFA_ENFORCE=true`. | Management |
| 13 | Routing and map providers configured | ⬜ open | Map tiles use the configured tile server (`MAP_TILE_URL`, `MAP_TILE_ATTRIBUTION`). Choose a provider with a production licence (OpenStreetMap's public tiles are not for production use). There is no routing provider; routes use straight-line corridors between stops (documented). | Management / development |
| 14 | Privacy and retention approved | ⬜ decision | GPS only during shifts with visible tracking status and prominent disclosure; national IDs encrypted; GPS retention `GPS_RETENTION_DAYS` (180); audit kept. The privacy notice, retention periods and driver consent wording need approval (and Play's background location declaration if Play is used). | Management |
| 15 | Pilot report approved | ⬜ open | PILOT_ACCEPTANCE_REPORT.md must be filled and signed (U52). | Management |
| 16 | Disaster recovery targets and owners | ⚠️ proposed | DISASTER_RECOVERY.md proposes RPO/RTO and roles; people and targets to be approved. | Management |
| 17 | Environments separated | ⬜ open | ENVIRONMENTS.md checklist: production secrets created by their owners, none in CI, `APP_ENV` set; the startup guard refuses development defaults. | Operations |

Legend: ✅ passed with evidence · ⚠️ partly done or proposed · ⬜ open.

## Order of work

Most gates depend on the same few steps. A sensible order:

1. **Provision staging (gates 3 and 17), then use it for:**
   - storage validation (6);
   - the production-like restore drill (7);
   - monitoring and the alert drill (8, 9).
2. **Create the signing key (10)** and build the staging app.
3. **Run the device test plan (4)**, then the pilot (5, 15) on two vehicles with «التجربة الميدانية».
4. **Management decisions** in parallel: 2FA (12), map provider (13), privacy and retention (14), DR owners (16), security acceptance (11).
5. **Re-check gate 1** on the final release commit, then deploy production following DEPLOYMENT.md §12.

## Sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| Operations | | | |
| Finance | | | |
| Management | | | |
