# Go Daily — Driver app (Android)

Native Android app for drivers: log in, see the assigned vehicle and today's
shifts, start and end a shift, switch the current operation, record fuel or
oil purchases during the shift with a photo of the receipt (reviewed by the
office before they count), and record the vehicle's location automatically
for the whole work shift. It does nothing else.

- Kotlin, Jetpack Compose (Material 3), Arabic RTL UI
- minSdk 26 (Android 8.0), targetSdk 36
- No analytics, no third-party SDKs besides Google Play services location

## Build status — read first

| Part | What it is | Verified where |
|---|---|---|
| `core/` | Pure Kotlin/JVM: API client, offline sync engine, tracking state machine, adaptive sampling, input parsing | **Unit-tested** (65 tests) locally and in CI (`./gradlew -p core test`) |
| `app/` | Android app: Compose UI, foreground location service, SQLite queue, WorkManager sync, Keystore token storage | **Compiles and passes Android lint in CI** (`:app:assembleDebug :app:lintDebug`); no instrumented tests yet |
| On-device behaviour | Background tracking, reboot recovery, OEM battery killers | **Not verified**: needs real phones (see "Device test plan") |

The development sandbox used to write this app cannot reach Google's Maven
repository (`dl.google.com`), so the Android Gradle Plugin and AndroidX
cannot be downloaded there. That is why the testable logic lives in `core/`
(Maven Central only), and why the `android` CI job is the only place `app/`
is compiled and linted. AndroidX/AGP versions in `gradle/libs.versions.toml`
were chosen from known releases but were never resolved in the sandbox; CI
resolves them.

## Run it

Requirements: Android Studio (or the Android SDK command-line tools) and JDK 17.

```bash
cd apps/driver-android
./gradlew -p core test                 # pure logic tests, no Android SDK needed
./gradlew :app:assembleDebug            # debug APK -> app/build/outputs/apk/debug/
./gradlew :app:installDebug             # install on a connected device/emulator
```

API URL: the debug build points at `http://10.0.2.2:8000/api/v1/` (the host
machine as seen from the Android emulator). Override with a Gradle property:

```bash
./gradlew :app:assembleDebug -PgoDailyApiBaseUrl=http://192.168.1.20:8000/api/v1/
./gradlew :app:assembleRelease -PgoDailyApiBaseUrl=https://api.example.com/api/v1/
```

Plain HTTP is allowed **only in debug builds** and only to `10.0.2.2` and
`localhost` (`src/debug/res/xml/network_security_config.xml`). For a LAN dev
server, add its address there. Release builds refuse non-HTTPS base URLs at
build time and trust only system CAs.

Release signing reads an untracked `keystore.properties`
(`storeFile`, `storePassword`, `keyAlias`, `keyPassword`); never commit it.

A driver account is created in the admin web (Users → role *Driver*, linked
to a driver record). Admin and office accounts cannot log in to the mobile
client; the API rejects them.

## How tracking works

```
start shift (server confirms) ──▶ local work context = shift id
        │
        ▼
LocationTrackingService (foreground, type=location, ongoing notification)
  FusedLocationProvider ─▶ dedupe ─▶ sanitize ─▶ SQLite queue (durable)
        │                                   │
        │ adaptive interval                 ▼
        │ (moving 10 s / parked 60 s,   SyncEngine (core)
        │  ×2 on low battery)            events → GPS batches (≤500, stable
        │                                batch id) → queued shift end
        ▼                                   │  idempotent: batch id, point id,
TrackingHealth: permission / location       │  event id, Idempotency-Key
switch / no fixes / offline / backlog       ▼
  → card in the app + notification     POST /driver/tracking/points|events
  → device events for management       POST /driver/shifts/{id}/end
```

- **Only during an authorised shift.** The service runs only while the local
  work context holds an active shift id. It is set when the server confirms
  a started shift (or reports one on refresh) and cleared the moment the
  driver confirms *End shift*, even offline. The server also refuses points
  outside the shift window, so off-shift points are never stored.
- **Prominent disclosure first.** `PermissionScreen` explains what is
  collected, why, and when, before any location permission prompt. Starting
  a shift requires precise location permission. "Allow all the time" and
  battery-optimisation exemption are recommended, not required.
- **Nothing is invented.** Fixes with impossible coordinates are dropped,
  out-of-range optional values (speed, heading, altitude, accuracy) are sent
  as null, repeated fixes are skipped. Gaps stay gaps; the server reports
  them on the replay timeline.
- **Offline first.** Every fix is written to SQLite before any upload.
  Batches keep their id and contents across retries, so the server answers a
  repeated batch from its record instead of ingesting it twice. Rows are
  deleted once acknowledged, so location history does not pile up on the
  phone. Batches the server refuses outright are kept 7 days for diagnosis,
  counted, and never retried.
- **Uploads.** While tracking, the service flushes when 60 points are queued
  or the oldest is 45 s old (the admin live map counts a vehicle as online
  for 120 s). Failures back off exponentially with jitter; regaining a
  validated network clears the backoff. WorkManager uploads whatever is left
  after the shift, after a crash, or after a reboot.
- **Ending a shift with unsynced points.** End shift stops tracking at once,
  stores the end request (odometer, notes, idempotency key) durably, and
  uploads queued points first, then the end. Without internet the driver
  sees "end pending"; it is sent automatically later. The server records the
  end time when it receives the request (the app cannot backdate).
- **Expired login.** Tracking of an active shift continues and points stay
  queued; they upload after the driver logs in again.
- **Driver-visible status** (`core/.../TrackingStatus.kt`): *active*,
  *offline but recording*, *weak GPS signal*, *blocked* (permission or
  location switch), *stopped* (service not running during a shift), *idle*.
  Each problem has Arabic copy and, where possible, a button that opens the
  right settings screen.
- **Problems reach management.** Permission denied/granted, location
  switched off/on, GPS signal lost/restored, battery optimisation on,
  background permission missing, sync backlog, service restarted, tracking
  started/stopped are sent as device events (`/driver/tracking/events`) and
  appear on the shift timeline in the admin web.

## Security

- Session token encrypted with an AES-256-GCM key held in the Android
  Keystore; only ciphertext is stored, in app-private preferences.
- `allowBackup=false` and data-extraction rules exclude preferences and the
  queue database from cloud backup and device transfer.
- HTTPS only in release, system CAs only. No request/response logging (the
  bodies carry the token, password and location).
- IDs used in URL paths are validated so they cannot change the request path.
- No national ID or other sensitive driver data is stored on the phone.
- Fuel entries: the receipt photo comes from the camera (written to the app's
  private cache through a `FileProvider`) or the system photo picker; neither
  needs a camera or storage permission. Photos are shrunk to 1600 px and
  re-encoded as JPEG before upload, which also drops EXIF metadata such as a
  location the camera embedded. Cached photos are deleted when the dialog
  closes. If the upload fails the entry is kept and the driver can retry.
- A fuel entry carries the phone's position only if the tracking service
  recorded a fix in the last two minutes (so only during a shift); otherwise
  none is sent. The dialog tells the driver this.

## Reliability scenarios (Task 29)

| Scenario | What the app does | Verified by |
| --- | --- | --- |
| App process killed or restarted | Queue, in-flight batch id, pending shift end and work context are on disk (SQLite, preferences). A new process resumes the same batch with its original id. The service restarts if Android allows it; otherwise the driver gets a "tap to resume" notification | `SyncReliabilityTest` (restart mid-backlog); device plan 7–8 |
| Device reboot during a shift | `BootReceiver` restarts tracking if "Allow all the time" was granted; otherwise a notification asks the driver to open the app | Device plan 7 |
| Internet lost and back | Every fix goes to SQLite first. Uploads back off with jitter; a validated network clears the backoff. The status shows *offline but recording* | `SyncEngineTest`, `BackoffTest`, `TrackingStatusTest`; device plan 3 |
| Answer lost after the server stored a batch | The batch is resent with the same id; the server answers from its record (no duplicates) | `SyncEngineTest`, `SyncReliabilityTest` (seeded long-shift simulation: every fix exactly once, in order); API `test_tracking.py` |
| Temporary GPS loss | Status *weak GPS signal*; `GPS_SIGNAL_LOST`/`RESTORED` events; gaps stay gaps on the server | `TrackingStatusTest`; device plan 6 |
| Permission denied or revoked, location switched off | Status *blocked* with a button to the right settings screen; events for management; the server's exception engine raises "مراجعة مطلوبة" for long interruptions | `TrackingStatusTest`; API `test_exceptions.py`; device plan 4–5 |
| Battery optimisation / power save | Warning shown to the driver and sent as an event; power save doubles the interval but never stops tracking | `AdaptiveSamplerTest`, `TrackingStatusTest`; device plan (OEM phones) |
| Large offline queue | Uploaded in batches of ≤ 500, at most a few batches per run, so the app stays responsive; a backlog warning goes to management | `SyncEngineTest` (huge backlog); device plan 10 |
| Two uploads at once (service flush and WorkManager) | One sync at a time per process (`Syncer` mutex); requests are idempotent anyway | Code review; `SyncEngineTest` replay cases |
| Shift ended with unsynced fixes | Tracking stops at once; the end request (odometer, idempotency key) is stored and sent after the remaining fixes; the server accepts fixes from inside the shift window after the shift has ended | `SyncEngineTest`, `SyncReliabilityTest`; API `test_late_sync_after_shift_end_is_accepted`; device plan 9 |

Failures are never hidden. The driver sees one of *active*, *offline but recording*, *weak GPS signal*, *blocked*, *stopped* or *idle*. Management sees device events on the shift timeline, the live map's tracking state, "tracking interrupted" notifications and review cases from the exception engine.

## Android power management — known limitations

Android and phone vendors restrict background work, and some of it cannot be
fixed from inside the app:

- **Foreground service required.** Background location on Android 8+ is
  throttled to a few fixes per hour, so tracking runs as a foreground service
  with an ongoing notification. If the driver blocks notifications
  (Android 13+), the service still runs but the notification is hidden; the
  app warns about it.
- **Starting tracking needs the app in the foreground.** Android 12+ refuses
  to start a foreground service from the background. Tracking therefore
  starts when the driver starts the shift in the app. If the process dies and
  Android does not restart the service, the driver gets a "tap to resume"
  notification.
- **Reboots.** After a reboot during a shift, tracking resumes automatically
  only with "Allow all the time" location permission (Android 10+ rule for
  starting location services from the background). Without it the driver
  must open the app.
- **Vendor battery killers.** Xiaomi (MIUI/HyperOS), Huawei (EMUI), Oppo/Realme
  (ColorOS), Vivo (Funtouch), Samsung ("sleeping apps") and others may kill
  the app despite the foreground service. Drivers must exempt Go Daily from
  battery optimisation and, on some brands, enable "autostart" or "no
  restrictions" in vendor settings. The app links to the standard battery
  setting; vendor screens differ and are not automated. See
  https://dontkillmyapp.com for per-brand steps.
- **Force-stop / swipe-away "stop" in the task manager** (Android 13+ lets
  users stop foreground services) stops tracking until the app is opened
  again. The gap is visible to management on the shift timeline, and the app
  shows *stopped*.
- **Doze / power save.** Low battery or power-save mode doubles the sampling
  interval (never stops it). Deep Doze can still delay fixes on some devices.
- **GPS quality** depends on the phone and surroundings (tunnels, garages,
  dense buildings). The app reports weak signal instead of guessing.
- **Clock.** Point times come from the location fix; the server rejects
  points stamped in the future and flags implausible jumps.

## Device test plan (not yet executed)

Run on at least one stock-Android phone and one aggressive-OEM phone
(e.g. Xiaomi), with the debug build against a staging API:

1. Log in; deny location; confirm *Start shift* routes to the disclosure and
   the permission prompt.
2. Start a shift; confirm the notification, points on the admin live map
   within ~1 minute, and the *active* state.
3. Airplane mode for 10 minutes while driving; confirm *offline but
   recording*, then automatic upload and no duplicate points after
   reconnecting.
4. Revoke location in system settings mid-shift; confirm *blocked* in the
   app and a `PERMISSION_DENIED` event on the shift timeline.
5. Switch location off; confirm *blocked* and `LOCATION_DISABLED`.
6. Park for 5+ minutes; confirm the interval drops to 60 s and the replay
   shows a stop, not a gap.
7. Reboot mid-shift with and without "Allow all the time".
8. Swipe the app away; stop it from the Android 13+ task manager.
9. End the shift offline; confirm tracking stops immediately and the end and
   remaining points arrive when back online.
10. Leave 3,000+ points queued (long offline drive); confirm the backlog
    drains over several runs without the app freezing.
