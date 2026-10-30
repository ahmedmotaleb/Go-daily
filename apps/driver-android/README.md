# Go Daily — Driver app (Android)

Native Android app for drivers: log in, see the assigned vehicle and today's
shifts, start and end a shift, switch the current operation, record fuel or
oil purchases during the shift (reviewed by the office before they count),
and record the vehicle's location automatically for the whole work shift.
It does nothing else.

- Kotlin, Jetpack Compose (Material 3), Arabic RTL UI
- minSdk 26 (Android 8.0), targetSdk 36
- No analytics, no third-party SDKs besides Google Play services location

## Build status — read first

| Part | What it is | Verified where |
|---|---|---|
| `core/` | Pure Kotlin/JVM: API client, offline sync engine, tracking state machine, adaptive sampling, input parsing | **Unit-tested** (53 tests) locally and in CI (`./gradlew -p core test`) |
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
