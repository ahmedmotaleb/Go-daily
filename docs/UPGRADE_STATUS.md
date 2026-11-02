# Go Daily — Upgrade status

Tracks [`GO_DAILY_UPGRADES_MASTER.md`](GO_DAILY_UPGRADES_MASTER.md). Work happens on the branch `claude/new-session-lpatv5` (draft PR #1); nothing is merged to `main` automatically.

**Statuses**
- NOT STARTED, IN PROGRESS, BLOCKED.
- CODE COMPLETE: implemented and covered by automated tests.
- REQUIRES REAL-WORLD TEST: code is ready but needs phones, infrastructure or pilot data.
- VERIFIED: only with real evidence (devices, staging, pilot), never from automated tests alone.

| Upgrade | Status | Commit | Tests | Notes |
|---|---|---|---|---|
| U01 — Real Android GPS Pilot Readiness | REQUIRES REAL-WORLD TEST | 0613936 | Core 67 incl. `TrackingStatusTest` (exact labels, uploading, permission vs location off); app compile + lint in CI | Phase A. Driver headlines now exactly التتبع يعمل / جاري رفع المواقع / تسجيل بدون إنترنت / الموقع غير متاح / صلاحية الموقع مطلوبة / التتبع متوقف / الوردية منتهية (+ إشارة الموقع ضعيفة) in app and notification. [`DEVICE_PILOT_TEST_PLAN.md`](DEVICE_PILOT_TEST_PLAN.md) written, **not executed**: needs physical phones. Release gate stays open. |
| U02 — GPS Anti-Tampering & Tracking Integrity | CODE COMPLETE | d611fd5 | API `test_gps_integrity.py` (11) + existing GPS rules; core `SyncEngineTest`/`OkHttpDriverApiTest` (device clock); migration 0012 up/down/check | Phase A. Five new review rules in the exception engine (tracking interrupted + likely reboot, impossible jumps, late uploads, out-of-shift submissions, timestamp anomalies); ingestion keeps rejection counts/time ranges and the phone clock per batch, never out-of-shift locations; app sends `device_time` and the boot counter. Neutral labels only, pinned by a test. Real-phone behaviour (boot counter, restarts) still part of [`DEVICE_PILOT_TEST_PLAN.md`](DEVICE_PILOT_TEST_PLAN.md). See [`GPS_INTEGRITY.md`](GPS_INTEGRITY.md). |
| U03 — GPS Quality Score | CODE COMPLETE | 5d89fdc | API `test_gps_quality.py` (6) + track endpoint assertion; web `gps-quality.test.ts`; web lint/format/types/build | Phase A. Explainable per-shift grade ممتاز / جيد / يحتاج مراجعة / بيانات غير كافية = worst of 7 checks (coverage, longest gap, median accuracy, low-accuracy share, impossible jumps, mock points, stale share) with published thresholds; all metrics incl. sync delay shown on the shift GPS card. See [`GPS_INTEGRITY.md`](GPS_INTEGRITY.md#gps-quality-score-u03). Thresholds need calibration with pilot data. |
| U04 — GPS vs Odometer Reconciliation | CODE COMPLETE | 3545c0b | API `test_odometer_reconciliation.py` (7) + rule/report/shift suites; migration 0013 up/down/check and backfill checked on a DB copy; web tests; browser check of the shift page (desktop + mobile) | Phase A. One reconciliation function for shift page, report and review rule: GPS km, odometer km, signed/absolute/% difference, allowance (env-configurable), coverage. Missing odometer / insufficient GPS are reported as missing, never as a difference. First-entered readings kept on correction (`original_*_odometer_km`), corrections audited. Also fixed mirrored ≥/≤ in Arabic threshold text. See [`GPS_INTEGRITY.md`](GPS_INTEGRITY.md#gps-vs-odometer-reconciliation-u04). |
| U05 — Hardware GPS Tracker Integration Architecture | NOT STARTED | — | — | Phase C. |
| U06 — Phone GPS vs Hardware Tracker Reconciliation | NOT STARTED | — | — | Phase C. |
| U07 — Road-Aware Route Intelligence | NOT STARTED | — | — | Phase C. |
| U08 — Route Versioning | NOT STARTED | — | — | Phase C. |
| U09 — Smarter Fixed-Route Loop Detection | CODE COMPLETE | — | API `test_geofence_engine.py` (+5) and `test_route_events_api.py` (+1); migration 0014 up/down/check; web `route-legs.test.ts` | Phase A. Minimum leg travel time (`ROUTE_MIN_LEG_MINUTES`), `LEG_INCOMPLETE` (returned to start / session ended) and `LEG_REJECTED` (too fast) kept as evidence and never counted; per-leg evidence (duration, terminals, intermediate stops, route order); detection parameters moved to settings; sessions and the loops report show incomplete legs. Existing debounce, accuracy filter, dedupe, legs/loops and audited manual correction preserved. Needs calibration on real routes. See ARCHITECTURE §6. |
| U10 — Automatic Expected Revenue per Loop | NOT STARTED | — | — | Phase A. |
| U11 — Passenger Count Architecture | NOT STARTED | — | — | Phase C. |
| U12 — School Route Verification | NOT STARTED | — | — | Phase A. |
| U13 — Fuel Efficiency Intelligence | NOT STARTED | — | — | Phase A. |
| U14 — Vehicle Fuel Baselines | NOT STARTED | — | — | Phase A. |
| U15 — Refueling Plausibility | NOT STARTED | — | — | Phase A. |
| U16 — Fuel Station/Vendor Intelligence | NOT STARTED | — | — | Phase C. |
| U17 — Oil & Service Reconciliation | NOT STARTED | — | — | Phase C. |
| U18 — Revenue Reconciliation Engine | NOT STARTED | — | — | Phase A. |
| U19 — Ride-Hailing Statement Import | NOT STARTED | — | — | Phase C. |
| U20 — Driver Settlement Automation | NOT STARTED | — | — | Phase C. |
| U21 — Cash Accountability | NOT STARTED | — | — | Phase C. |
| U22 — Vehicle Profitability V2 | NOT STARTED | — | — | Phase C. |
| U23 — Operations Control Center | NOT STARTED | — | — | Phase A. |
| U24 — Vehicle Daily Timeline | NOT STARTED | — | — | Phase A. |
| U25 — Driver Daily Timeline | NOT STARTED | — | — | Phase C. |
| U26 — Exception Engine V2 | NOT STARTED | — | — | Phase A. |
| U27 — Severity & Escalation | NOT STARTED | — | — | Phase C. |
| U28 — Investigation Workspace | NOT STARTED | — | — | Phase A. |
| U29 — Real Object Storage Validation | NOT STARTED | — | — | Phase B. |
| U30 — Receipt Image Reliability | NOT STARTED | — | — | Phase C. |
| U31 — Admin 2FA | NOT STARTED | — | — | Phase B. |
| U32 — Distributed Login Rate Limiting | NOT STARTED | — | — | Phase B. |
| U33 — Authentication Privacy | NOT STARTED | — | — | Phase B. |
| U34 — CSP Hardening | NOT STARTED | — | — | Phase B. |
| U35 — Sensitive Action Re-Authentication | NOT STARTED | — | — | Phase C. |
| U36 — Security Event Dashboard | NOT STARTED | — | — | Phase C. |
| U37 — Production Monitoring & Alerting | NOT STARTED | — | — | Phase B. |
| U38 — Operational Metrics | NOT STARTED | — | — | Phase B. |
| U39 — Production-Like Backup/Restore Drill | NOT STARTED | — | — | Phase B. |
| U40 — Disaster Recovery | NOT STARTED | — | — | Phase B. |
| U41 — Environments | NOT STARTED | — | — | Phase B. |
| U42 — Android Release Pipeline | NOT STARTED | — | — | Phase B. |
| U43 — Driver App Update Strategy | NOT STARTED | — | — | Phase B. |
| U44 — API/App Compatibility | NOT STARTED | — | — | Phase B. |
| U45 — Offline Financial Entry Reliability | NOT STARTED | — | — | Phase A. |
| U46 — Clock Integrity | NOT STARTED | — | — | Phase A. |
| U47 — Versioned Company Policies | NOT STARTED | — | — | Phase B. |
| U48 — Master Data Management | NOT STARTED | — | — | Phase C. |
| U49 — Data Quality Dashboard | NOT STARTED | — | — | Phase B. |
| U50 — Pilot Command Center | NOT STARTED | — | — | Phase A. |
| U51 — Pilot Daily Close | NOT STARTED | — | — | Phase A. |
| U52 — Pilot Acceptance | NOT STARTED | — | — | Phase A. |
| U53 — Production Release Gate V2 | NOT STARTED | — | — | Phase B. |
| U54 — Post-Deployment Validation | NOT STARTED | — | — | Phase C. |
| U55 — Future Backlog (do not implement without approval) | NOT STARTED | — | — | Phase C. Backlog only: not implemented without approval. |
