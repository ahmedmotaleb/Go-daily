# Go Daily — Upgrades Master Plan

Repository: `ahmedmotaleb/Go-daily`
Purpose: post Tasks 01–32 upgrades before production.
Rule: work on an upgrade branch; do not auto-merge to `main`.

## Global rules
- Inspect and reuse the existing architecture; do not rewrite stable modules unnecessarily.
- Preserve history/audit trails and use migrations for schema changes.
- Never fabricate GPS, financial, fuel, infrastructure, or test evidence.
- Keep Arabic RTL, EGP, Africa/Cairo display time, decimal-safe money.
- GPS only during authorized work shifts with visible tracking status.
- Use neutral anomaly wording: `مراجعة مطلوبة` / `حالة غير معتادة`.
- Add tests for new business rules and run API, web, Android, migrations, lint/typecheck/build.
- Update docs and `docs/UPGRADE_STATUS.md` after every upgrade.
- Real-device/infrastructure tests cannot be marked VERIFIED without real evidence.

## U01 — Real Android GPS Pilot Readiness
Prepare and test: screen locked, background, removed from recents, process death, reboot, internet loss/recovery, offline queue, duplicate retries, GPS disabled, permissions revoked, battery saver/vendor battery killers, poor accuracy, long shift, low battery, and ending shift with unsynced points.
Driver states must clearly show: التتبع يعمل / تسجيل بدون إنترنت / جاري رفع المواقع / الموقع غير متاح / صلاحية الموقع مطلوبة / التتبع متوقف / الوردية منتهية.
Create `docs/DEVICE_PILOT_TEST_PLAN.md` with phone model, Android version, tester/date, scenario, expected/actual result, pass/fail, battery use, GPS points, gaps and notes. Keep release gate open until physical-device evidence exists.

## U02 — GPS Anti-Tampering & Tracking Integrity
Record evidence for GPS disabled, permission revoked, service stopped, prolonged gaps, app restart, detectable reboot, reliable mock-location indicators, impossible jumps, stale submissions, out-of-shift submissions and suspicious timestamp ordering.
Store driver, vehicle, shift, type, server/device time, duration, evidence, severity and review status. Never automatically accuse theft/fraud.

## U03 — GPS Quality Score
Create explainable shift-level GPS quality using coverage duration, gaps, accuracy, stale points, impossible jumps and sync delay. Display ممتاز / جيد / يحتاج مراجعة / بيانات غير كافية and always expose underlying metrics.

## U04 — GPS vs Odometer Reconciliation
For completed shifts calculate GPS km, odometer km, absolute and percentage difference. Configurable tolerance; distinguish missing from suspicious data; preserve original odometer entries; audit corrections.

## U05 — Hardware GPS Tracker Integration Architecture
Provider-neutral future tracker ingestion: device ID, vehicle binding, timestamp, coordinates, speed, heading, ignition/external power if available, raw provider reference; adapter interface, authenticated webhook/API, idempotency, invalid-event quarantine and normalized locations.
Create `docs/HARDWARE_GPS_INTEGRATION.md`. Do not fake a hardware integration.

## U06 — Phone GPS vs Hardware Tracker Reconciliation
Prepare comparison of phone path vs vehicle tracker: time alignment, distance, discrepancies, phone stationary while vehicle moves, movement without active shift. Runtime remains unavailable until hardware exists.

## U07 — Road-Aware Route Intelligence
Replace straight-line-only deviation logic with replaceable routing/map-matching provider architecture: road geometry, distance, snapping where supported, corridor deviation, caching, timeout/failure fallback. Do not hardcode one provider.

## U08 — Route Versioning
Immutable/versioned route definitions with effective dates, stop order, geofences, expected geometry/distance and thresholds. Route edits must never rewrite historical evidence.

## U09 — Smarter Fixed-Route Loop Detection
Improve موقف → جامعة → موقف detection using origin/destination geofences, dwell, minimum travel time, sequence, accuracy threshold, debounce, duplicate prevention, incomplete-leg state and audited manual correction. Preserve legs and complete round trips.

## U10 — Automatic Expected Revenue per Loop
Configurable expected revenue per loop/leg and optional passenger-count × fare model. Calculate detected loops, expected revenue, actual collection, difference and percentage. Threshold alerts must say `فرق تحصيل — مراجعة مطلوبة`, not theft.

## U11 — Passenger Count Architecture
Optional future passenger counts from driver, supervisor, ticketing or hardware. Store source/confidence. Never infer exact passenger count from GPS.

## U12 — School Route Verification
Track scheduled/actual start/end, required/reached stops, GPS evidence, route completion/deviation/delay and audited correction. Status: مكتملة / مكتملة بتأخير / غير مكتملة / تحتاج مراجعة.

## U13 — Fuel Efficiency Intelligence
Gasoline/diesel: km/litre, L/100km, EGP/km. CNG: configurable unit, km/unit, EGP/km. Calculate by shift/day/week/month/vehicle. Keep engine oil outside fuel-efficiency metrics.

## U14 — Vehicle Fuel Baselines
Rolling vehicle baselines compared with historical/recent averages and operation type where enough data exists. Require minimum sample size and incomplete-data handling. Alert: `استهلاك غير معتاد — مراجعة مطلوبة`.

## U15 — Refueling Plausibility
Check assignment, shift time, odometer, GPS proximity when available, quantity, prior events and duplicate indicators. Detect implausible location/time, decreasing odometer, unusual quantity and rapid repeated refuels. Configurable thresholds.

## U16 — Fuel Station/Vendor Intelligence
Station/vendor master records with name, location, fuel types, transaction history, average/historical prices and receipts. Allow trusted geofences later without blocking legitimate new stations.

## U17 — Oil & Service Reconciliation
Oil purchase != oil change. Link oil purchase to maintenance/service when applicable; store quantity/specification, service date/odometer and next target.

## U18 — Revenue Reconciliation Engine
One view combining fixed-route expected/actual collections, ride-hailing gross/commission/electronic/cash, private trips, school/employee allocation and approved adjustments. Prevent double counting and show completeness warnings.

## U19 — Ride-Hailing Statement Import
CSV import first: configurable mapping, preview, validation, duplicate detection, batch ID, rollback/void and reconciliation to driver/vehicle/shift. No scraping; direct integration only through approved APIs.

## U20 — Driver Settlement Automation
Draft settlement from fixed salary, daily wage, percentage, fixed+incentive, bonuses, advances, deductions and reimbursements.
Workflow: Draft → Reviewed → Approved → Paid. No automatic payment; audited overrides; historical calculation inputs immutable.

## U21 — Cash Accountability
Optional cash custody: collected, expected, handed over, timestamp, receiver, difference and evidence. Status: لم يتم التسليم / تم التسليم / فرق يحتاج مراجعة.

## U22 — Vehicle Profitability V2
Revenue, commissions, driver cost, fuel, oil/service, maintenance, other expenses and net profit by vehicle/operation/route/shift/day/week/month. Add cost/km, revenue/km, profit/km, profit/shift and profit/loop with completeness warnings.

## U23 — Operations Control Center
Dashboard: active vehicles, driver, operation, latest/live position, GPS freshness, shift start, loop count, school status, collections, fuel and open review cases. Never fabricate live data.

## U24 — Vehicle Daily Timeline
Unified timeline: assignment, shift, operation changes, GPS gaps, arrivals/loops, school duty, fuel, expenses, collections, maintenance and review cases.

## U25 — Driver Daily Timeline
Assigned vehicle, shifts, GPS state, operations, financial entries, advances/settlements and review cases. Enforce strict RBAC.

## U26 — Exception Engine V2
Configurable explainable rules for GPS gaps/permissions/jumps/deviation/unexpected movement, odometer mismatch, movement outside shift, overlapping assignment, fuel anomalies, duplicate receipts, expected-vs-actual revenue, ride-hailing mismatch, cash differences, missed school stops, incomplete routes and abnormal stops.
Every alert must show reason, threshold, observed value, evidence and review action.

## U27 — Severity & Escalation
Info/Low/Medium/High based on current evidence, financial magnitude and operational impact. Repeated history alone must not prove current wrongdoing.

## U28 — Investigation Workspace
One screen combining map/path, GPS timeline, odometer, fuel, revenue, shift, route, attachments and related events. Actions: تحت المراجعة / تم التوضيح / تم التصحيح / مرفوض كإنذار / تم التصعيد. Require notes for material resolutions.

## U29 — Real Object Storage Validation
Create `docs/OBJECT_STORAGE_VALIDATION.md`. Validate a real S3-compatible environment: upload/retrieve receipt, signed URL expiry, unauthorized rejection, type/size validation, deletion/correction and backup considerations. Never commit credentials.

## U30 — Receipt Image Reliability
Android camera/gallery/file picker, compression, orientation, upload progress, retry, offline pending and failed states. Preserve originals according to policy. No OCR unless separately approved.

## U31 — Admin 2FA
TOTP 2FA for privileged roles, secure secret storage, QR enrollment, recovery codes, reset/disable audit and re-authentication for sensitive changes. Never log TOTP secrets.

## U32 — Distributed Login Rate Limiting
Replace/augment per-process throttling with Redis-compatible distributed limits for login, 2FA and sensitive auth endpoints. Document backend-failure behavior.

## U33 — Authentication Privacy
Reduce account-existence leakage in login/lockout/password-reset responses while retaining internal audit evidence.

## U34 — CSP Hardening
Reduce unsafe-inline usage with nonce/hash strategy where feasible; production-test Next.js/maps/assets and document any remaining exception.

## U35 — Sensitive Action Re-Authentication
Require recent authentication/2FA for privileged-role changes, security resets, large settlement approvals and other high-risk actions. Configurable thresholds.

## U36 — Security Event Dashboard
Authorized admins: failed-login spikes, lockouts, 2FA resets, suspicious auth patterns, useful permission-denied events and security configuration warnings. No secrets or national IDs.

## U37 — Production Monitoring & Alerting
Replaceable monitoring integration for API errors/latency, DB health, migration mismatch, storage failures, GPS ingestion/queue backlog, background jobs and notification failures. Alerts must be actionable and low-noise.

## U38 — Operational Metrics
Metrics: active shifts, GPS points/min, rejected points, stale vehicles, sync latency, queue depth, loop detections, open cases, fuel/revenue submissions and API latency/errors. Never use coordinates as metric labels.

## U39 — Production-Like Backup/Restore Drill
Backup, verify, restore to clean DB, verify counts/critical finance/audit/migrations and measure recovery time. Record evidence without secrets/data leakage.

## U40 — Disaster Recovery
Create `docs/DISASTER_RECOVERY.md`: RPO/RTO, DB/object recovery, credential rotation, server loss, rollback, responsibilities and incident checklist.

## U41 — Environments
Separate development/staging/production DB, storage, secrets and configuration. Safe migration path and staging validation. Never reuse production secrets in CI.

## U42 — Android Release Pipeline
Signed release process, secure keystore documentation, version policy, release notes, staging/prod API configuration, R8/ProGuard where appropriate, crash reporting and artifact integrity. Never commit signing keys.

## U43 — Driver App Update Strategy
Document managed distribution (Play/internal/approved enterprise). Show app version and support backend minimum/recommended version policy.

## U44 — API/App Compatibility
Minimum supported app version, recommended version, graceful API evolution and no breaking change to active drivers mid-shift.

## U45 — Offline Financial Entry Reliability
Fuel/expense/collection local queue with unique client IDs, idempotency, retry, pending/synced/failed states and conflict handling. Never duplicate financial records on retry.

## U46 — Clock Integrity
Store server receive time + device event time, detect major skew, preserve submitted time, use authoritative server time for workflow decisions where appropriate, display Egypt local time.

## U47 — Versioned Company Policies
Authorized, audited, versioned configuration for GPS gap/stale/stop/deviation thresholds, fuel/revenue anomalies, receipt rules and settlement approval thresholds.

## U48 — Master Data Management
Admin for operation types, routes, stations/vendors, expense categories, consumables, maintenance types and relevant notification rules. Prefer deactivate/archive over destructive deletion.

## U49 — Data Quality Dashboard
Find missing ending odometer, fuel without odometer, unreconciled revenue, stale assignments, routes missing geofences, missing vehicle documents, unsynced GPS and unresolved corrections. Clearly separate missing data from suspicious data.

## U50 — Pilot Command Center
Dedicated view for one fixed-route/school microbus and one ride-hailing vehicle: driver, shift, tracking, GPS quality/distance, loops/operation, fuel, revenue, expenses, settlement and review cases.

## U51 — Pilot Daily Close
For each pilot vehicle verify shift ended, GPS synced, ending odometer, operations, fuel, expenses, revenue, cash handover and review cases. Output: اليوم مكتمل / بيانات ناقصة / يحتاج مراجعة.

## U52 — Pilot Acceptance
Create `docs/PILOT_ACCEPTANCE_REPORT.md`. Multiple real shifts must validate background GPS, battery, offline recovery, replay, loops, GPS-vs-odometer, fuel, fixed-route revenue, school route, ride-hailing reconciliation, usability, no critical data loss/security issue.

## U53 — Production Release Gate V2
Required before production: CI green, migrations tested, staging deployed, physical Android test passed, GPS pilot passed, real storage validated, backup/restore passed, monitoring active, alert drill successful, Android signing ready, security risks accepted/fixed, 2FA policy decided, routing/map providers configured, privacy/retention approved, pilot report approved.
Never mark production-ready with mandatory gates open.

## U54 — Post-Deployment Validation
Verify login/RBAC, fleet, shifts, GPS ingestion/live/replay/loops, fuel/receipts, revenue/expenses/settlement, exceptions, reports, backup and monitoring. Produce deployment verification report.

## U55 — Future Backlog (do not implement without approval)
Approved ride-hailing APIs, WhatsApp/SMS, ticketing, QR/NFC, fuel sensors, CAN/OBD, physical GPS trackers, passenger counters, predictive maintenance, route optimization, customer/contract portal, school-parent tracking and payroll integration.

# Execution Order

### Phase A — Pilot Critical
U01, U02, U03, U04, U09, U10, U12, U13, U14, U15, U18, U23, U24, U26, U28, U45, U46, U50, U51, U52.

### Phase B — Production Critical
U29, U31, U32, U33, U34, U37, U38, U39, U40, U41, U42, U43, U44, U47, U49, U53.

### Phase C — Intelligence & Scale
U05, U06, U07, U08, U11, U16, U17, U19, U20, U21, U22, U25, U27, U30, U35, U36, U48, U54, U55.

# Claude Code Delivery Protocol
For every upgrade:
1. Read this plan and current architecture/docs.
2. Inspect existing code before editing.
3. Implement the smallest safe change.
4. Add/update tests.
5. Run relevant verification and migrations.
6. Fix failures before proceeding.
7. Update docs.
8. Commit clearly and push to the upgrade branch.
9. Update `docs/UPGRADE_STATUS.md`.
10. Do not merge to `main`.

`docs/UPGRADE_STATUS.md` should include:
| Upgrade | Status | Commit | Tests | Notes |
|---|---|---|---|---|

Statuses: NOT STARTED / IN PROGRESS / BLOCKED / CODE COMPLETE / VERIFIED / REQUIRES REAL-WORLD TEST.

# Final objective
Go Daily must reliably answer: where each working vehicle is; current driver/operation; GPS health/gaps; GPS vs odometer distance; university loops; school completion; expected vs actual collections; CNG/gasoline/oil; fuel efficiency and plausibility; expenses; driver settlement; vehicle profit; cash difference; which cases need review and why; whether data is missing vs unusual; whether tracking survives locked screen/offline conditions; and whether every pilot/production gate has real evidence.

Optimize for trustworthy operational evidence, financial correctness, driver usability, privacy, security and real-world reliability — not feature count.
