# Go Daily — GPS integrity, quality score and odometer reconciliation (U02–U04)

Go Daily records evidence when tracking is interrupted or GPS data looks unusual, and turns it into review cases. A case is a reason to look, never a conclusion. Phones restart, lose signal, run out of battery and have wrong clocks for ordinary reasons. Cases use only the labels **مراجعة مطلوبة** (review required) or **حالة غير معتادة** (unusual case). No rule, summary or label says theft, fraud or tampering, and a test (`test_no_rule_accuses_anyone`) keeps it that way.

## Where the evidence comes from

| Signal | Source | Stored as |
| --- | --- | --- |
| Location switched off / on, permission revoked / granted | Driver app device events | `tracking_events` (device time `occurred_at`, server time `received_at`) |
| Tracking started, stopped, restarted | Driver app device events. Start and restart events carry Android's boot counter (`details.boot_count`) | `tracking_events` |
| Mock location | The phone's own mock-provider flag on each point | `gps_points.is_mock`, quality `MOCK` |
| Impossible jump | Server: the speed needed to reach the point from the previous valid one is above `GPS_MAX_SPEED_KMH` (200) | `gps_points.quality = IMPLAUSIBLE_SPEED` (kept, left out of distance) |
| Late submission | Server: `received_at − recorded_at` per point | `gps_points` |
| Out-of-shift submission | Server refuses points recorded outside the shift window | `gps_upload_batches.rejected_outside_shift` and the time range. **The locations are not stored**, not even as evidence |
| Future timestamps | Server refuses points stamped in the future | `gps_upload_batches.rejected_future`, `future_max_seconds` |
| Phone clock offset | Each batch carries the phone's clock (`device.device_time`) | `gps_upload_batches.device_time` vs `received_at` |
| Batches going back in time | Range of each batch's in-shift points, in arrival order | `gps_upload_batches.first_recorded_at`, `last_recorded_at` |

The app queues points oldest first, so a batch whose points are older than ones already received usually means the phone's clock was changed.

## Rules

All rules run in the exception engine (`python -m app.cli detect-exceptions`, hourly). Each case stores the driver, vehicle, shift, rule (type), device time (`occurred_at` to `occurred_until`, so the duration), server detection time (`detected_at`), evidence, severity and review status. The review workflow, audit trail and dedupe are the existing ones (see `docs/ARCHITECTURE.md`).

| Rule | Label | Raised when | Severity | Threshold setting |
| --- | --- | --- | --- | --- |
| `GPS_DISABLED` | مراجعة مطلوبة | Location off or permission revoked during a shift for longer than the threshold. Evidence includes the device and server times | Medium; high if 60 min+ or never restored | `EXCEPTION_GPS_DISABLED_MINUTES` (5) |
| `GPS_GAP` | حالة غير معتادة | No valid points for longer than the threshold inside a finished shift; notes how far the vehicle moved and which device events fall in the gap | Low; medium if it moved 1 km+ | `EXCEPTION_GPS_GAP_MINUTES` (15) |
| `MOCK_LOCATION` | مراجعة مطلوبة | The phone flagged points as coming from a mock provider | High | — |
| `TRACKING_INTERRUPTED` | مراجعة مطلوبة | Tracking stopped or restarted during a shift and was off longer than the threshold. Time off runs from the "service stopped" event, or the last point before the restart, to the restart (or the end of the shift if it never restarted). A changed boot counter marks a likely reboot | Low; medium if 60 min+ or never restarted | `EXCEPTION_TRACKING_INTERRUPTED_MINUTES` (10) |
| `IMPOSSIBLE_JUMP` | حالة غير معتادة | Points flagged as impossible jumps; up to 5 examples with distance, seconds and implied speed (no coordinates) | Low; medium if 3+ points | `GPS_MAX_SPEED_KMH` (200) |
| `LATE_GPS_UPLOAD` | حالة غير معتادة | Points reached the server more than the threshold after they were recorded. The summary says the phone may have been offline | Low | `EXCEPTION_LATE_UPLOAD_HOURS` (12) |
| `OUT_OF_SHIFT_GPS` | حالة غير معتادة | The phone sent points recorded before the shift started or after it ended. Only the count and time range are kept | Low | — |
| `TIMESTAMP_ANOMALY` | حالة غير معتادة | The phone's clock differed from the server's by more than the threshold, points were stamped in the future, or a batch went back in time by more than the tolerance | Low; medium if 30 min+ off, 30 min+ in the future, or 10 min+ back | `EXCEPTION_CLOCK_SKEW_MINUTES` (5), `EXCEPTION_BACKWARDS_MINUTES` (2) |

Tests: `tests/test_gps_integrity.py` (ingestion evidence, every new rule, normal data raising nothing, engine storage and labels, wording), `tests/test_exceptions.py` (existing GPS rules, dedupe, review workflow).

## What is not detected, and why

- **Rooted phones or apps that hide mock locations.** The app reports only Android's own mock flag. Detecting root or hidden mock apps is unreliable and invasive, so the app does not try.
- **Reboots on phones without a boot counter.** `reboot_detected` is then empty ("unknown"), not "no".
- **Phones that were off.** A phone that is switched off sends nothing. The shift shows a gap (`GPS_GAP`) and, when it comes back, a restart (`TRACKING_INTERRUPTED`).
- **Clock offset on old app versions.** Batches from versions without `device_time` are skipped by the clock check.

## Privacy

- Nothing is collected outside a work shift. Points from outside the shift are refused, and only their count and time range are kept.
- Integrity evidence holds times, counts, distances and speeds, not extra locations. Closed cases older than `GPS_RETENTION_DAYS` lose any coordinates through `prune-gps` (see `docs/SECURITY.md`).
- The boot counter is the only new value read from the phone. It identifies neither the phone nor the driver.

## GPS quality score (U03)

Every shift's GPS page (admin web → shift → *المسار الفعلي حسب GPS*) shows a quality grade and all the numbers behind it. The API returns it as `quality` on `GET /api/v1/shifts/{id}/track` (`app/services/gps_quality.py`).

| Grade | Meaning |
| --- | --- |
| ممتاز | Every check is within its "excellent" threshold |
| جيد | At least one check is only within its "good" threshold |
| يحتاج مراجعة | At least one check is beyond "good" |
| بيانات غير كافية | Shift not started, shorter than `GPS_QUALITY_MIN_MINUTES` (15), or fewer than `GPS_QUALITY_MIN_POINTS` (10) valid points. Nothing is estimated |

The grade is the **worst** check, so one weak area is never averaged away. While a shift is running, the figures are "so far".

| Check | Definition | Excellent | Good |
| --- | --- | --- | --- |
| تغطية مدة الوردية | Share of the shift not inside a gap longer than `GPS_GAP_SECONDS` (300 s). Same definition as the GPS-vs-odometer rule | ≥ 95 % | ≥ 80 % |
| أطول انقطاع | Longest gap between valid points (or from the shift start/to its end) | ≤ 10 min | ≤ 30 min |
| الدقة المعتادة | Median reported accuracy of all points | ≤ 20 m | ≤ 50 m |
| نقاط منخفضة الدقة | Share of points less accurate than `GPS_MAX_ACCURACY_M` (100 m) | ≤ 5 % | ≤ 15 % |
| قفزات غير ممكنة | Points flagged as impossible jumps | 0 | ≤ 2 |
| نقاط من مصدر وهمي | Points the phone flagged as mock | 0 | 0 |
| نقاط وصلت متأخرة | Share of points received more than `GPS_QUALITY_STALE_MINUTES` (10) after recording | ≤ 10 % | ≤ 50 % |

Always shown as well: shift duration, points and valid points, number of gaps, median and 95th-percentile sync delay (time from recording to reaching the server), and the number of late points.

A low grade means the GPS record is weak for that shift: distances and route checks for it deserve less weight. It is not a judgement of the driver. Phones, buildings, tunnels and network coverage all affect it.

Old shifts whose raw points were deleted after `GPS_RETENTION_DAYS` show "بيانات غير كافية".

Tests: `tests/test_gps_quality.py` (each grade, worst-check rule, stale points, insufficient data), `tests/test_tracking.py` (the API returns the quality with its checks), `src/lib/gps-quality.test.ts` (labels).

## GPS vs odometer reconciliation (U04)

For each **completed** shift Go Daily compares the odometer distance (end − start reading) with the GPS distance (sum of consecutive valid points; gaps longer than `GPS_GAP_SECONDS` are not bridged). One function does this (`app/services/odometer_reconciliation.py`) for the shift page, the report and the review rule, so they always agree.

| Result | When |
| --- | --- |
| ضمن الحد المسموح | Both distances available and the difference is within the allowance |
| فرق يحتاج مراجعة | Both available, GPS coverage sufficient, difference beyond the allowance. Raises a `GPS_ODOMETER_MISMATCH` review case |
| قراءة العداد ناقصة | A start or end reading is missing |
| تغطية GPS غير كافية | Fewer than 2 valid points, or coverage below `EXCEPTION_ODOMETER_MIN_GPS_COVERAGE_PCT` (80 %) |
| الوردية لم تنتهِ | The shift is still running (not compared) |

Missing data is never treated as a difference: the numbers are still shown, but no review case is raised and the page says the comparison is not meaningful.

- **Figures:** odometer km, GPS km, signed difference (odometer − GPS), absolute difference, difference as a percentage of the odometer distance, the allowance and the GPS coverage.
- **Allowance:** the larger of `EXCEPTION_ODOMETER_TOLERANCE_KM` (5 km) and `EXCEPTION_ODOMETER_TOLERANCE_PCT` (25 %) of the larger distance. Both are environment settings.
- **Corrections:** staff correct readings on the shift page with a required reason. Each correction is an audit entry with the old and new value. The reading as first entered is kept in `original_start_odometer_km` / `original_end_odometer_km` and is never overwritten by later corrections. The shift page shows "مصححة؛ الأصلية …" under a corrected reading, and the report has a "قراءة مصححة" column. Migration 0013 recovered the originals of shifts corrected earlier from their first audit entry.
- **Where:** the shift GPS card (*مطابقة العداد مع GPS*), the report *مطابقة العداد وGPS* (`gps_odometer`, with counts by result and CSV export), and review cases.

Tests: `tests/test_odometer_reconciliation.py` (each result, missing vs suspicious, the rule only for real differences, corrections keep the first reading and are audited, report), `tests/test_shifts.py::test_odometer_correction_is_audited`.
