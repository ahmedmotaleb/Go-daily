# Go Daily — Driver app device pilot test plan (U01)

This plan checks the driver app on **physical Android phones** before the pilot. Tracking evidence is central to Go Daily, so this is a release gate.

**Gate rule.** The release gate "Mobile driver UX / on-device tracking" stays **open** until this plan has been run on real phones and the results below are filled in from those runs. Emulators, unit tests and CI do not count. Never write a result for a run that did not happen. If a scenario cannot be run, write `NOT RUN` and why.

**Status: not yet executed.** The results log at the end is empty.

## 1. Setup

### Phones

Test at least:

| Class | Why | Examples |
| --- | --- | --- |
| A. Stock or near-stock Android | Baseline Android behaviour | Pixel, Android One, Motorola, Nokia |
| B. Aggressive vendor battery management | Most drivers' phones; these kill background apps | Xiaomi/Redmi/POCO (MIUI/HyperOS), Oppo/Realme (ColorOS), Vivo, Huawei, Samsung (One UI "sleeping apps") |

Cover the oldest Android version the fleet's drivers use (the app supports Android 8.0+) and one recent version (Android 14 or later). Prefer the phone models the pilot drivers actually own.

### Build and accounts

- Debug or release-candidate build of `apps/driver-android` pointed at a **staging** API (Gradle property `goDailyApiBaseUrl`), never production.
- A test driver account and a test vehicle. Do not use a real driver's personal phone number or national ID in test data.
- A staff account with tracking access on the admin web to read the evidence.
- Record the app version (`versionName`/`versionCode` from *Settings → Apps → Go Daily*).

### Before each phone's first run

1. Note the battery level and confirm the phone is not charging during battery measurements.
2. Do **not** exempt the app from battery optimisation yet. Scenario P13 measures the phone's default behaviour first, then with the exemption.
3. Clear the app's data so the run starts from a clean install state.

### Where to read the evidence

| What | Where |
| --- | --- |
| Driver state | The tracking status on the driver app's home header (tap it for *حالة التتبع*: requirement checklist with a fix button for each problem) and the ongoing notification |
| Points and gaps | Admin web → *الورديات* → the shift → card *المسار الفعلي حسب GPS*: *نقاط GPS*, *انقطاعات البيانات*, replay and timeline |
| Device events | The same card's timeline: `TRACKING_STARTED`/`TRACKING_STOPPED`, `SERVICE_RESTARTED`, `PERMISSION_DENIED`/`PERMISSION_GRANTED`, `BACKGROUND_PERMISSION_DENIED`, `LOCATION_DISABLED`/`LOCATION_ENABLED`, `GPS_SIGNAL_LOST`/`GPS_SIGNAL_RESTORED`, `BATTERY_OPTIMIZATION_ENABLED`, `OFFLINE_QUEUE_BACKLOG` |
| Live position | Admin web → *التتبع المباشر* (`/tracking`, live mode; a vehicle counts as online for 120 s after its last point). Replay a finished shift from the same screen (*إعادة المسار*) |
| Review cases | Admin web → *حالات للمراجعة* (long interruptions raise "مراجعة مطلوبة") |
| Battery use | Phone *Settings → Battery → App battery usage* (percentage for Go Daily) plus battery level at start and end |

## 2. Driver states

The driver must always see one of these headlines, in the app and in the notification. They are pinned in `TrackingStatusTest` so the app and this plan use the same words.

| Headline | Meaning | Colour |
| --- | --- | --- |
| التتبع يعمل | Recording and uploading normally | Green |
| جاري رفع المواقع | Online again; points saved while offline are being sent | Green |
| تسجيل بدون إنترنت | No internet; points are saved on the phone | Amber |
| إشارة الموقع ضعيفة | Tracking runs but no recent fix (indoors, tunnel) | Amber |
| الموقع غير متاح | The phone's location switch is off | Red |
| صلاحية الموقع مطلوبة | Location permission missing or revoked | Red |
| التتبع متوقف | A shift is active but tracking is not running | Red |
| الوردية منتهية | No active shift; location is not collected | Grey |

Warnings that do not change the headline (background permission, battery optimisation, notifications blocked, large backlog) show as rows under it, each with a button to the right setting.

## 3. Scenarios

Run each scenario on every test phone unless marked otherwise. "Expected" is what the code is designed to do; the run decides whether it does.

| ID | Scenario | Steps | Expected on the phone | Expected evidence on the server |
| --- | --- | --- | --- | --- |
| P01 | Start shift, normal tracking | Log in. Deny location once, then start a shift and grant *While using the app*, then *Allow all the time*. Drive 15 min. | Disclosure before the permission prompt. *التتبع يعمل*. Ongoing notification visible. | Points on the live map within about 1 minute. Points about every 10 s while moving. No gaps. |
| P02 | Screen locked | During a shift, lock the screen for 30 min while driving. | Notification stays. On unlock: *التتبع يعمل*. | Continuous points for the 30 min; no gap. |
| P03 | App in background | Open other apps (maps, WhatsApp, camera) for 30 min while driving. | Same as P02. | Continuous points. |
| P04 | Removed from recents | Swipe Go Daily away from the recent-apps list. Keep driving 15 min. | Notification stays (foreground service survives) or, on some vendors, tracking stops. | Either continuous points, or a gap that ends when the app is reopened, with a `SERVICE_RESTARTED` event. Record which. |
| P05 | Process death | a) Android 13+: stop the app from the task manager's *Active apps*. b) With USB debugging: `adb shell am kill com.godaily.driver` while in background. | a) Tracking stops until the app is opened; reopening shows *التتبع متوقف* with a restart button, or resumes. b) Service restarts, or a "tap to resume" notification appears. | No points lost from before the kill (queue on disk). Gap only while stopped, visible on the timeline. |
| P06 | Reboot mid-shift | a) With *Allow all the time*. b) Without it (*While using the app* only). | a) Tracking resumes after unlock without opening the app. b) Notification asks the driver to open the app; *التتبع متوقف* until they do. | a) Gap only for the reboot time. b) Gap until the app is opened. Both visible on the timeline. |
| P07 | Internet loss and recovery | Turn off mobile data and Wi-Fi (not airplane mode, which can also stop GPS on some phones) for 10 min while driving. Turn them back on. | *تسجيل بدون إنترنت* while off. After reconnecting: *جاري رفع المواقع*, then *التتبع يعمل*. | All points for the 10 min arrive after reconnecting, with their original times. No gap, no duplicates. |
| P08 | Large offline queue | Stay offline for a long drive (2+ hours, or enough for 3,000+ points). Reconnect. | Backlog warning row. App stays responsive. Pending count drops over several minutes. | All points arrive, in order, once each. `OFFLINE_QUEUE_BACKLOG` event on the timeline. |
| P09 | Duplicate retries | During an upload (pending count dropping), toggle mobile data off and on several times. | Upload resumes. | Point count equals what the phone recorded; no duplicate points at the same time. |
| P10 | GPS disabled | Switch the phone's location off for 5 min mid-shift, then on. | *الموقع غير متاح* with *فتح إعدادات الموقع*. Back to *التتبع يعمل* afterwards. | `LOCATION_DISABLED` then `LOCATION_ENABLED` events. A gap of about 5 min, not filled in. |
| P11 | Permission revoked | In system settings, change location permission to *Don't allow*, then back. Also try *Only while using the app*. | *صلاحية الموقع مطلوبة* with *منح إذن الموقع*. With *while using* only: background-permission warning row. | `PERMISSION_DENIED` then `PERMISSION_GRANTED` events. Gap while denied. |
| P12 | Battery saver | Turn on the phone's battery saver for 30 min while driving. | *التتبع يعمل* (interval may double). | Points continue, possibly every 20–30 s. No gap longer than a few minutes. |
| P13 | Vendor battery killer (class B phones) | a) Default vendor settings, app not exempted: 2-hour shift with the screen off most of the time. b) Repeat after exempting the app (battery optimisation off, autostart on, "no restrictions"). | a) Battery-optimisation warning row. Record whether tracking stops. b) *التتبع يعمل* throughout. | a) Record gaps and `SERVICE_RESTARTED` events. b) No gaps. Compare with a). |
| P14 | Poor accuracy | Drive through a tunnel or underground garage; park indoors 10 min; drive between tall buildings. | *إشارة الموقع ضعيفة* after about 2 min without a fix, then back to *التتبع يعمل*. | `GPS_SIGNAL_LOST`/`GPS_SIGNAL_RESTORED` events. Points less accurate than 100 m are kept but flagged and left out of GPS distance. Gaps not filled in. |
| P15 | Long shift | A full real shift (10–12 h) with normal use. | No crash. State correct throughout. | Points across the whole shift. Record total points, gaps and battery use. |
| P16 | Low battery | Let the battery fall below 15 % during a shift (not charging). | Tracking continues (interval may double). Driver can still end the shift. | Points continue at a lower rate. Record battery use per hour. |
| P17 | End shift with unsynced points | Go offline, drive 10 min, end the shift while still offline (enter the end odometer). Reconnect 5 min later. | Tracking stops immediately at end. *الوردية منتهية*. Pending count shown, then drops to zero after reconnecting. | Shift ends with the entered odometer and end time. The 10 min of points arrive after the end request, all inside the shift window. |
| P18 | Notifications blocked (Android 13+) | Deny the notification permission, start a shift. | Notifications-blocked warning row. Tracking still runs. | Points continue. |
| P19 | Stop and park | Park for 5+ min with the engine off during a shift. | *التتبع يعمل*. | Replay shows a stop, not a gap. After about 3 min still, points slow to about one a minute. |

## 4. What counts as a pass

- The phone shows the expected headline within about 2 minutes of the change.
- The server shows the expected points, gaps and events. A gap is acceptable only when the scenario causes it (location off, permission denied, reboot without background permission, task-manager stop) and the gap is visible to management. Unexplained gaps fail the scenario.
- No duplicate points, no points outside the shift window, no points invented to fill a gap.
- No crash or ANR.
- Where the expected result says "record which" (P04, P13a), the scenario passes if the behaviour is recorded and visible to management. The result decides what drivers are told in onboarding.

The gate can close when every scenario has passed on at least one class A and one class B phone, or has a documented limitation that operations has accepted in writing (with the mitigation, for example "drivers on brand X must enable autostart").

## 5. Results log

Copy the table for each phone. One row per scenario run. Leave rows empty until the run happens.

- **Battery use**: battery % at start and end, and the app's % in the phone's battery usage screen.
- **GPS points**: the admin shift page's *نقاط GPS* for the scenario's time window.
- **Gaps**: count and longest duration from *انقطاعات البيانات*.
- Attach screenshots (app state, admin replay) to the pilot issue or PR, not to the repository. Crop or blur anything showing a driver's home location or personal details.

### Phone 1

| Phone model | Android version | Tester | Date | Scenario | Expected result | Actual result | Pass/Fail | Battery use | GPS points | Gaps | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | P01 | See §3 | | | | | | |
| | | | | P02 | See §3 | | | | | | |
| | | | | P03 | See §3 | | | | | | |
| | | | | P04 | See §3 | | | | | | |
| | | | | P05 | See §3 | | | | | | |
| | | | | P06 | See §3 | | | | | | |
| | | | | P07 | See §3 | | | | | | |
| | | | | P08 | See §3 | | | | | | |
| | | | | P09 | See §3 | | | | | | |
| | | | | P10 | See §3 | | | | | | |
| | | | | P11 | See §3 | | | | | | |
| | | | | P12 | See §3 | | | | | | |
| | | | | P13 | See §3 | | | | | | |
| | | | | P14 | See §3 | | | | | | |
| | | | | P15 | See §3 | | | | | | |
| | | | | P16 | See §3 | | | | | | |
| | | | | P17 | See §3 | | | | | | |
| | | | | P18 | See §3 | | | | | | |
| | | | | P19 | See §3 | | | | | | |

### Phone 2

Copy the Phone 1 table.

## 6. Sign-off

| Role | Name | Date | Decision |
| --- | --- | --- | --- |
| Operations | | | |
| Technical owner | | | |

Record accepted limitations here with their mitigation.
