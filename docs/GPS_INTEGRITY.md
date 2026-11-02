# Go Daily — GPS integrity evidence (U02)

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
