# Go Daily Fleet Management System --- Claude Code Master Tasks

**Repository:** `ahmedmotaleb/Go-daily`\
**Product:** Go Daily Fleet Control & Operations System\
**Primary market:** Egypt\
**Primary UI language:** Arabic (RTL)\
**Currency:** EGP\
**Timezone:** Africa/Cairo

------------------------------------------------------------------------

## 0. Working Rules --- Read Before Starting

You are the lead engineer for Go Daily. Work through this file **task by
task in order**.

### Mandatory workflow

1.  Inspect the current repository before every task. Never assume the
    previous task is complete.
2.  Do not destructively rewrite working code without a clear reason.
3.  Use a dedicated feature branch and logical commits.
4.  After each task, run the relevant
    tests/lint/typecheck/build/migrations.
5.  Fix failures before moving on.
6.  Never claim a task is complete unless its Definition of Done is
    actually verified.
7.  Update the task checklist in this file as work is completed.
8.  Do not commit `.env`, passwords, API keys, tokens, production
    credentials, or sensitive driver data.
9.  Preserve database history. Use Alembic migrations; never silently
    rebuild a production database.
10. Keep business logic out of UI components and thin API route
    handlers.
11. Do not fabricate GPS, financial, trip, or alert data and present it
    as real.
12. All suspicious activity must be described as **"مراجعة مطلوبة"** or
    **"حالة غير معتادة"**, never as proven theft/fraud.
13. GPS tracking of drivers is for work shifts only, with explicit
    permission/disclosure and appropriate Android foreground/background
    location behavior.
14. Do not automatically merge PRs.
15. Stop and report exact blockers if credentials, infrastructure,
    external APIs, or human decisions are required.

### Target architecture

``` text
/apps
  /admin-web       Next.js + TypeScript + Tailwind
  /api             FastAPI + SQLAlchemy + Alembic
  /driver-android  Android app (added in GPS phase)

/packages
  /shared
  /config

/docs
```

Core: - PostgreSQL is the system of record. - UUID primary keys. - UTC
timestamps internally where appropriate; display in Africa/Cairo. -
Docker / Docker Compose for development. - Arabic-first RTL UI,
future-ready for English. - Backend authorization is mandatory; frontend
hiding is not security.

------------------------------------------------------------------------

# TASK 01 --- Repository Foundation

-   [x] Inspect repository and current branch/status.
-   [x] Establish monorepo structure.
-   [x] Create Next.js admin application with TypeScript/App
    Router/Tailwind.
-   [x] Create FastAPI backend.
-   [x] Configure PostgreSQL.
-   [x] Configure SQLAlchemy 2.x and Alembic.
-   [x] Add Dockerfiles and Docker Compose for `admin-web`, `api`,
    `postgres`.
-   [x] Add `.env.example`.
-   [x] Add root developer commands for
    setup/dev/test/lint/format/migrate/seed.
-   [x] Add `/health` and `/ready`; readiness must check DB
    connectivity.
-   [x] Replace minimal README with real setup documentation.
-   [x] Create `docs/ARCHITECTURE.md` and `docs/ROADMAP.md`.

### Design system

Create reusable tokens: - dark forest green: primary/navigation - bright
lime green: actions/active/GPS indicators - white surfaces - light
neutral dashboard background - dark charcoal text

Avoid generic purple/blue SaaS styling, glassmorphism, excessive
gradients and animation.

### Verify

-   [x] Docker configuration validates/starts where environment permits.
-   [x] API starts.
-   [x] Web app builds.
-   [x] Database migration runs.
-   [x] No secrets committed.

------------------------------------------------------------------------

# TASK 02 --- Authentication, Users & RBAC

Roles: - `SUPER_ADMIN` - `ADMIN` - `OPERATIONS` - `ACCOUNTANT` -
`DRIVER`

Implement: - \[ \] User model: UUID, full_name, phone, optional email,
password_hash, role, is_active, timestamps. - \[ \] Unique phone where
appropriate. - \[ \] Secure password hashing. - \[ \]
Login/logout/current-user flow. - \[ \] Secure token/session strategy. -
\[ \] Inactive-account rejection. - \[ \] Backend RBAC
dependencies/policies. - \[ \] Protected admin routes. - \[ \] Secure
bootstrap admin via environment/command. - \[ \] Audit
authentication-sensitive actions without logging credentials/tokens.

Tests: - \[ \] successful login - \[ \] wrong password - \[ \] inactive
user - \[ \] unauthorized request - \[ \] role restrictions

------------------------------------------------------------------------

# TASK 03 --- Fleet / Vehicles

Vehicle fields: - internal code - plate number - vehicle type -
manufacturer - model - model year - color - ownership status - active
status - current odometer - license expiry - insurance expiry - notes -
timestamps

Vehicle types must be extensible; seed: `MICROBUS`, `SEDAN`, `VAN`,
`BUS`, `OTHER`.

Implement: - \[ \] migrations/model/schema/service/API - \[ \]
list/detail/create/edit - \[ \] activate/deactivate - \[ \]
search/filter/pagination - \[ \] Arabic RTL fleet screens - \[ \]
validation and authorization - \[ \] expiry indicators for
license/insurance

Do not permanently bind one driver or one operation type to a vehicle.

------------------------------------------------------------------------

# TASK 04 --- Drivers

Driver is a separate domain profile and may link to a User.

Fields: - full name - phone - optional national ID - license number -
license expiry - employment status - hire date - notes

Prepare compensation configuration for: - fixed salary - daily wage -
revenue percentage - fixed + incentive

Implement: - \[ \] CRUD - \[ \] active/inactive/employment status - \[
\] search/filter - \[ \] license expiry warning - \[ \] Arabic RTL
screens - \[ \] tests

Sensitive IDs must never appear in logs.

------------------------------------------------------------------------

# TASK 05 --- Driver ↔ Vehicle Assignment History

Create historical assignment model rather than `vehicle.driver_id`.

Fields: - driver_id - vehicle_id - starts_at - ends_at nullable -
active - notes - timestamps

Implement: - \[ \] assign driver to vehicle - \[ \] end assignment - \[
\] current assignment - \[ \] history - \[ \] prevent impossible
overlapping active assignments where practical - \[ \] UI from both
driver and vehicle pages - \[ \] tests

Never delete historical assignments just because a new assignment
begins.

------------------------------------------------------------------------

# TASK 06 --- Operation Types & Route Definitions

Initial operation types: - `RIDE_HAILING` --- نقل ذكي - `FIXED_ROUTE`
--- خط ثابت - `SCHOOL_ROUTE` --- دورة مدرسة - `PRIVATE_TRIP` --- رحلة
خاصة - `EMPLOYEE_TRANSPORT` --- نقل موظفين - `OTHER` --- أخرى

A vehicle can perform multiple operation types on the same day.

Create route definitions suitable for fixed operations: - name -
operation type - origin - destination - optional intermediate stops -
active status - expected/typical distance optional - expected operating
window optional - notes

Current real-world pattern must be supported: - موقف ⇄ جامعة repeated
loops - school duty during the same day - smart-transport work on
another vehicle

Do not hardcode one specific university/station into business logic.

------------------------------------------------------------------------

# TASK 07 --- Shift & Operation Sessions

Shift fields should include: - driver - vehicle - start/end time -
start/end odometer - status - operation context - notes

Statuses: `PLANNED`, `ACTIVE`, `COMPLETED`, `CANCELLED`.

Implement: - \[ \] plan shift - \[ \] start - \[ \] end - \[ \] cancel -
\[ \] history - \[ \] active shifts - \[ \] odometer validation - \[ \]
end odometer cannot be lower than start - \[ \] vehicle/driver
consistency checks

A shift may contain multiple operation sessions, e.g.: 1. university
fixed-route service 2. school route 3. another permitted operation

Create an operation-session model so one shift is not forced into one
operation type.

------------------------------------------------------------------------

# TASK 08 --- Admin Dashboard V1

Arabic RTL dashboard using actual DB values.

KPIs: - العربيات النشطة - السائقون النشطون - الورديات النشطة - ورديات
اليوم

Sections: - active vehicles - current driver assignments - active
operations - upcoming license/insurance expiry - recent activity

Add clearly labeled placeholders only for features not yet active: -
`الخريطة المباشرة — سيتم تفعيل التتبع المباشر في مرحلة GPS` -
`التنبيهات التشغيلية — سيتم تفعيلها بعد تشغيل نظام التتبع والتحليل`

No fake moving vehicles or fake revenue.

Navigation: - لوحة التحكم - الأسطول - السائقون - التشغيل - الورديات -
التحصيلات - المصروفات - الصيانة - التقارير - التنبيهات - المستخدمون -
الإعدادات

Future modules may show `قريبًا`.

------------------------------------------------------------------------

# TASK 09 --- Android Driver App Foundation

Create `/apps/driver-android`.

Choose a production-sensible native Android stack, preferably Kotlin +
Jetpack Compose unless the existing repo establishes another justified
standard.

Driver app must be extremely simple and mobile-first.

Implement: - \[ \] secure driver login - \[ \] current assigned
vehicle - \[ \] today's work/shift - \[ \] start shift - \[ \] end
shift - \[ \] current operation - \[ \] permission onboarding - \[ \]
offline-aware networking foundation - \[ \] secure local token storage -
\[ \] clear Arabic UI

Do not implement fake GPS points.

------------------------------------------------------------------------

# TASK 10 --- Continuous Work-Shift GPS Tracking

This is a critical Go Daily requirement.

The driver should NOT manually submit location repeatedly.

After starting an authorized work shift, the Android app tracks location
automatically in the background according to Android platform
requirements.

GPS point must support: - driver - vehicle - shift - timestamp -
latitude/longitude - accuracy - speed if available - heading if
available - source - sync status / server receipt time

Implement: - \[ \] Android foreground location service as required by
Android - \[ \] explicit work-tracking disclosure and permissions - \[
\] tracking only in authorized work context - \[ \] local offline
queue - \[ \] retry/sync after internet returns - \[ \] idempotent
backend ingestion - \[ \] batch upload endpoint - \[ \] server
validation - \[ \] retention-aware DB design - \[ \] battery-conscious
adaptive sampling - \[ \] detect/report permission/location-service
problems - \[ \] driver-visible tracking status

Never silently fabricate missing points.

Document limitations caused by Android power management/device vendors.

------------------------------------------------------------------------

# TASK 11 --- Live Fleet Map & Route Replay

Admin: - \[ \] live/latest vehicle position - \[ \] online/offline/stale
tracking state - \[ \] last GPS update - \[ \] active driver - \[ \]
active shift/operation - \[ \] route polyline for selected shift - \[ \]
timeline - \[ \] stops - \[ \] distance calculated from valid GPS data -
\[ \] historical route replay

Use a replaceable map-provider abstraction. Do not deeply lock business
logic to one map vendor.

Clearly distinguish: - GPS-recorded distance - odometer distance

Do not silently treat either as the other.

------------------------------------------------------------------------

# TASK 12 --- Geofences & Fixed Route Loop Detection

For fixed routes such as موقف ⇄ جامعة:

Create geofence/route-stop support: - origin zone - destination zone -
intermediate zones - configurable radius - expected sequence where
relevant

Implement event detection: - entered stop/geofence - exited - reached
origin - reached destination - completed directional leg - completed
loop

Goal: count repeated university route loops automatically with minimal
driver input.

Protect against noisy GPS: - accuracy threshold - dwell/debounce -
duplicate-event prevention

Provide admin correction capability with audit trail.

------------------------------------------------------------------------

# TASK 13 --- School Route Operations

Support scheduled school duty independently from fixed university loops.

Implement: - \[ \] school-route definition - \[ \] schedule/time
window - \[ \] assigned vehicle/driver - \[ \] route/stops - \[ \]
actual start/end - \[ \] GPS evidence - \[ \] completion state - \[ \]
notes - \[ \] admin correction with audit trail

Architecture should later support multiple schools/contracts without
redesign.

------------------------------------------------------------------------

# TASK 14 --- Ride-Hailing Operations

For drivers working on smart-transport platforms similar to Uber.

Track: - work shift - vehicle - driver - odometer - GPS distance/time -
platform gross earnings - platform commission/fees - cash collected
where relevant - electronic/platform settlement - tips/adjustments where
relevant - expenses - notes - statement reference/upload metadata

Do not scrape or integrate a platform without an approved/legal API or
explicit supported mechanism.

Start with robust manual statement entry/import architecture.

Create reconciliation views comparing operational activity with entered
platform earnings.

------------------------------------------------------------------------

# TASK 15 --- Fuel, CNG, Oil & Consumables Ledger

Critical requirement: the current microbus may use **CNG + gasoline +
engine oil**.

Types must be extensible: - `CNG` - `GASOLINE` - `DIESEL` -
`ENGINE_OIL` - `OTHER`

Never store fuel costs as fixed columns on Vehicle.

Transaction fields: - vehicle - driver - shift optional - type -
quantity - unit - unit price - total - date/time - odometer -
station/vendor - receipt attachment reference - GPS location when
captured by authorized driver app - notes - creator - timestamps

Implement: - \[ \] driver entry - \[ \] admin/accountant entry - \[ \]
receipt upload architecture - \[ \] edit/correction workflow - \[ \]
audit trail - \[ \] filters/reports - \[ \] validation - \[ \] CNG and
gasoline can both be recorded for the same vehicle/day - \[ \] oil is
separate from fuel efficiency calculations

Do not treat oil as gasoline.

------------------------------------------------------------------------

# TASK 16 --- General Expenses

Expense categories should be configurable.

Examples: - tolls - parking - washing - repairs - tires - parts - fines
where company policy allows recording - miscellaneous operational
expenses

Fields: - vehicle - driver optional - shift/operation optional -
category - amount - date/time - vendor - receipt - notes - payment
method - created/approved by

Implement approval/correction/audit architecture appropriate to
financial records.

------------------------------------------------------------------------

# TASK 17 --- Collections & Revenue

Support different revenue models.

Fixed route: - daily/shift collection - optional per-loop or aggregate
collection - adjustment

School/employee transport: - contract/service revenue allocation
architecture

Private trip: - trip price - received amount - payment method -
outstanding amount

Ride-hailing: - platform earnings and settlement as defined earlier

Implement: - \[ \] revenue ledger - \[ \] cash vs electronic - \[ \]
outstanding amounts - \[ \] correction/audit - \[ \]
vehicle/driver/date/operation reports

Avoid double-counting the same revenue across operation and settlement
records.

------------------------------------------------------------------------

# TASK 18 --- Driver Financial Account & Settlement

Support compensation methods: - fixed monthly salary - daily wage -
percentage of eligible revenue - fixed + incentive

Ledger items: - earnings - advances - bonuses - deductions -
reimbursements - settlements - manual adjustments with reason/audit

Create a clear driver statement: - opening balance - earned - advances -
deductions - paid - closing balance

Financial calculations must use decimal-safe monetary types, never
binary floating point.

Do not silently modify historical settlements when compensation rules
change.

------------------------------------------------------------------------

# TASK 19 --- Vehicle Profitability

Create per-vehicle P&L views.

Inputs: - revenue - CNG - gasoline - diesel if applicable - engine
oil/consumables - maintenance - general expenses - driver cost
allocation - platform commissions - other configured costs

Outputs: - gross revenue - direct operating cost - driver cost - net
operating profit - cost/km - revenue/km - profit/shift - profit by
operation type

Clearly show incomplete-data warnings when records are missing.

Do not manufacture profitability from missing values.

------------------------------------------------------------------------

# TASK 20 --- Audit & Exception Detection Engine

Build explainable rules, not opaque accusations.

Initial signals: - GPS disabled during active shift - unexplained GPS
gap - route deviation - unexpectedly long stop - vehicle moving after
shift - unexpected operating area - GPS distance vs odometer
discrepancy - implausible odometer entry - unusual CNG/gasoline
consumption - fueling far from vehicle location - fueling outside
plausible shift/time - duplicate receipt/transaction indicators where
technically possible - revenue unusually inconsistent with operating
time/distance

Every event needs: - type - severity - evidence - detected_at -
vehicle/driver/shift links - status - reviewer - review notes -
resolution

Arabic labels: - `مراجعة مطلوبة` - `حالة غير معتادة`

Never label an anomaly as proven theft.

Allow: - open - under review - explained - corrected - dismissed -
escalated

All reviewer actions should be audited.

------------------------------------------------------------------------

# TASK 21 --- Maintenance

Implement: - maintenance types - service records - odometer/date based
schedules - upcoming maintenance - overdue maintenance -
parts/labor/vendor/cost - attachments - vehicle downtime - notes

Examples: - engine oil change - filters - brakes - tires - scheduled
service

Do not confuse engine-oil purchase entries with completed oil-change
maintenance. Allow linking where appropriate.

------------------------------------------------------------------------

# TASK 22 --- Notifications

Notification foundation for: - license expiry - insurance expiry -
maintenance due - GPS tracking interruption - unusual operational
event - settlement/review workflow where useful

Implement in-app notifications first.

Design provider abstraction for future push/email/WhatsApp/SMS without
hardcoding one vendor.

Avoid notification spam; use deduplication and severity.

------------------------------------------------------------------------

# TASK 23 --- Reports

Arabic reports with filters for: - date range - vehicle - driver -
operation type - route - expense/fuel type

Reports: - daily operations - fixed-route loops - school routes -
ride-hailing - revenue - expenses - CNG/gasoline/oil - driver
statements - vehicle profitability - GPS/odometer discrepancy -
exceptions - maintenance

Exports: - CSV - PDF only if implemented reliably and Arabic renders
correctly

Report totals must be backed by source records.

------------------------------------------------------------------------

# TASK 24 --- Attachments / Receipt Storage

Create storage abstraction for: - fuel receipts - expense receipts -
platform statements - maintenance invoices - relevant vehicle documents

Requirements: - safe file type/size validation - unique object keys -
metadata in PostgreSQL - no public bucket assumption - signed/private
access architecture - provider configurable by environment -
deletion/correction policy with audit considerations

Do not hardcode Cloudinary as a mandatory dependency.

------------------------------------------------------------------------

# TASK 25 --- Security Hardening

Review: - authentication - authorization - IDOR - mass assignment -
input validation - upload security - CORS - rate limiting where
appropriate - token handling - logging - dependency vulnerabilities -
error leakage - audit integrity

Add tests for role boundaries.

Ensure drivers cannot access other drivers' private/financial data
unless explicitly permitted.

Ensure accountant/operations permissions follow least privilege.

------------------------------------------------------------------------

# TASK 26 --- Data Integrity & Concurrency

Add database constraints and transactional protection for: - active
driver/vehicle assignments - shift lifecycle - odometer monotonicity
where appropriate - duplicate GPS batches - duplicate financial
submissions - settlement finalization - loop detection duplication -
audit record creation

Use idempotency for mobile retry-sensitive writes.

Document concurrency decisions.

------------------------------------------------------------------------

# TASK 27 --- Observability & Backups

Implement production-ready foundation: - structured application logs -
request correlation IDs - error monitoring integration point -
health/readiness checks - metrics integration point - database backup
documentation - restore procedure documentation

Never log GPS auth tokens, passwords, national IDs, or other unnecessary
sensitive values.

------------------------------------------------------------------------

# TASK 28 --- PWA & Admin UX Polish

Admin web: - installable PWA where appropriate - responsive
desktop/tablet/mobile - proper loading/empty/error states - Arabic RTL
correctness - accessible forms - consistent validation - search/filter
persistence where useful - confirmation for destructive/financial
actions - Go Daily brand tokens and logo integration

Prioritize operational clarity over decorative UI.

------------------------------------------------------------------------

# TASK 29 --- Driver App Reliability

Test and improve: - app process restart - device reboot behavior where
allowed/appropriate - loss/recovery of internet - temporary GPS loss -
denied/revoked permission - Android battery optimization - large offline
queue - duplicate sync - shift ending with unsynced points

Driver must see whether tracking is: - active - temporarily offline but
recording - permission blocked - stopped

Do not hide tracking failures from management or driver.

------------------------------------------------------------------------

# TASK 30 --- End-to-End Operational Scenarios

Create automated/integration tests where practical for:

### Scenario A --- Fixed route microbus

Driver starts shift → microbus starts university route → GPS records
repeated station/university movement → loop events detected → CNG
purchase entered → gasoline purchase also entered → school operation
begins later → shift ends → odometer reconciled → collections entered →
vehicle daily result available.

### Scenario B --- Ride-hailing

Driver starts shift → GPS tracking active → platform operation recorded
→ platform earnings/fees entered → gasoline/CNG expense as applicable →
shift ends → driver/vehicle financial summary available.

### Scenario C --- GPS interruption

Active shift → location stops unexpectedly → tracking gap generated →
`مراجعة مطلوبة` → manager reviews evidence → records resolution.

### Scenario D --- Financial correction

Expense/revenue entered incorrectly → authorized correction → original
history remains traceable → report reflects corrected accounting result.

------------------------------------------------------------------------

# TASK 31 --- Production Deployment Preparation

Do not deploy blindly.

Prepare: - production environment variable documentation - secure secret
strategy - PostgreSQL production requirements - migration deployment
procedure - HTTPS/reverse proxy expectations - backup strategy - admin
web deployment - API deployment - Android environment configuration -
map/storage provider configuration - monitoring configuration - rollback
plan

Create `docs/DEPLOYMENT.md`.

No real credentials in repository.

------------------------------------------------------------------------

# TASK 32 --- Final QA & Release Gate

Before declaring production-ready:

-   [ ] all backend tests pass
-   [ ] frontend lint passes
-   [ ] TypeScript typecheck passes
-   [ ] frontend production build passes
-   [ ] Android build/tests pass
-   [ ] Alembic migrations apply from clean DB
-   [ ] upgrade path from existing DB tested
-   [ ] authentication/RBAC verified
-   [ ] vehicle CRUD verified
-   [ ] driver CRUD verified
-   [ ] assignments verified
-   [ ] shifts verified
-   [ ] GPS ingestion/retry verified
-   [ ] live/latest position verified
-   [ ] route replay verified
-   [ ] fixed-route loop detection verified
-   [ ] fuel/CNG/gasoline/oil ledger verified
-   [ ] revenue/expense ledger verified
-   [ ] driver settlement math verified
-   [ ] profitability calculations verified
-   [ ] exception engine verified
-   [ ] maintenance verified
-   [ ] Arabic RTL reviewed
-   [ ] mobile driver UX reviewed
-   [ ] no secrets committed
-   [ ] docs updated
-   [ ] backup/restore procedure reviewed

Create a final release report listing: 1. completed functionality 2.
automated test results 3. manual checks 4. known limitations 5. external
services still requiring configuration 6. security/privacy
considerations 7. recommended pilot rollout steps

------------------------------------------------------------------------

# Pilot Rollout Recommendation

Do not immediately put the entire fleet on an untested release.

Pilot with: 1. one fixed-route/school microbus 2. one ride-hailing
vehicle

Validate for several real work shifts: - GPS reliability - battery
usage - route/loop detection - odometer reconciliation -
CNG/gasoline/oil entry - collections - driver usability - alerts -
financial totals

Only expand after pilot issues are fixed.

------------------------------------------------------------------------

# Definition of the Product

The final Go Daily system should let management answer, from evidence:

-   Where is each working vehicle?
-   Which driver has it?
-   What operation is it performing?
-   What route did it actually travel?
-   How many fixed-route loops were completed?
-   Was the school duty completed?
-   How many kilometers did GPS record?
-   What did the odometer report?
-   How much CNG, gasoline and oil was used?
-   What other expenses occurred?
-   How much revenue was collected?
-   What does Go Daily owe the driver / what has been settled?
-   What is the profitability of each vehicle?
-   Which operational records require management review?

Build toward those answers without fabricating data, destroying audit
history, or treating automated anomalies as proof of misconduct.
