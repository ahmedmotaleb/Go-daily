# Pilot Acceptance Report (U52)

**Status: NOT STARTED — no pilot shift has been run yet.**

This report is filled in during the field pilot. Nothing in it may be marked
as passed without the evidence listed for it: real phones, real shifts and
the records the system kept. Test-suite results and seeded data do not count
as evidence here.

## 1. Pilot setup

| Item | Value |
|---|---|
| Fixed-route / school microbus | _(vehicle code, plate)_ |
| Ride-hailing vehicle | _(vehicle code, plate)_ |
| Drivers | _(names; app account per driver)_ |
| Phones | _(model, Android version, class A/B per `DEVICE_PILOT_TEST_PLAN.md`)_ |
| App version | _(versionName / build)_ |
| Server version | _(commit deployed)_ |
| Pilot dates | _(from – to)_ |
| Reviewers | _(operations, accounts)_ |

Mark both vehicles as pilot vehicles in the admin web under **التجربة الميدانية**.
That page shows each vehicle's day and its daily close (U50/U51), and it is
the main working view during the pilot.

## 2. Acceptance criteria

The acceptance rule:

- **Multiple real shifts.** At least 10 completed shifts per pilot vehicle, on at least 5 different days, including at least one long shift (10 hours or more).
- **Daily close.** Every pilot day must reach «اليوم مكتمل» on the daily close, or have a written explanation for why it did not.

| # | Criterion | Evidence required | Result | Notes / links |
|---|---|---|---|---|
| A1 | Background GPS during whole shifts (screen off, other apps in use) | Shift track per shift: coverage %, gaps (none unexplained); device scenarios P01–P08 | NOT RUN | |
| A2 | Battery use acceptable | Battery % at start and end of each long shift; P15 result | NOT RUN | |
| A3 | Offline recovery: points, shift end, fuel and close-out sent after the internet returns, nothing duplicated | P09–P12, P25–P27; one record per entry on the server | NOT RUN | |
| A4 | Route replay matches the real route | Replay of at least 3 shifts reviewed by operations against the known route | NOT RUN | |
| A5 | Loops and legs detected correctly on the fixed route | Detected loops vs the driver's or supervisor's count for at least 5 shifts | NOT RUN | |
| A6 | GPS vs odometer within tolerance | Odometer reconciliation per shift; every REVIEW case explained | NOT RUN | |
| A7 | Fuel entries complete and correct | Fuel records vs receipts (amount, quantity, time, location) for every pilot shift | NOT RUN | |
| A8 | Fixed-route revenue reconciles | Expected vs recorded collection (`revenue_reconciliation` report) for every pilot day; gaps explained | NOT RUN | |
| A9 | School route runs verified | School runs: planned vs completed, and every missed or incomplete run explained | NOT RUN | |
| A10 | Ride-hailing reconciliation | Platform statement vs recorded ride-hailing shifts and cash for the pilot period | NOT RUN | |
| A11 | Cash handover settles | Close-outs vs collections: nothing left outstanding without a reason (cash board, «حسابي مع الإدارة») | NOT RUN | |
| A12 | Review cases are reasonable | Every case raised during the pilot reviewed; false alarms counted per rule, and thresholds adjusted if needed | NOT RUN | |
| A13 | Usability | Drivers complete start, fuel, close-out and day-off without help after onboarding; feedback recorded | NOT RUN | |
| A14 | Wrong phone clock handled | P28 result | NOT RUN | |
| A15 | No critical data loss | No shift, point batch, fuel entry, close-out or collection lost; compare phone counts with server counts | NOT RUN | |
| A16 | No security issue | Drivers see only their own data; no tokens, passwords or national IDs in logs (log sample reviewed) | NOT RUN | |

Allowed results: NOT RUN / PASS / PASS WITH LIMITATION (state the limitation and who accepted it) / FAIL.

## 3. Daily log

One row per pilot vehicle per day, taken from **التجربة الميدانية**.

| Date | Vehicle | Shifts | Daily close verdict | Missing / review items | Resolved how |
|---|---|---|---|---|---|
| | | | | | |

## 4. Issues found

| # | Date | Description | Severity | Fix / decision | Status |
|---|---|---|---|---|---|
| | | | | | |

## 5. Decision

| | |
|---|---|
| Pilot accepted | _(yes / no / with conditions)_ |
| Conditions | |
| Signed off by | _(name, role, date)_ |

Until this section is signed, U52 stays **REQUIRES REAL-WORLD TEST**, and
the production release gate stays closed.
