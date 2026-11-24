# Driver App Releases (U42–U44)

How the driver app is built, signed, distributed and kept compatible with the API. Phone setup and the device test plan are in [`DEPLOYMENT.md`](DEPLOYMENT.md) §11 and [`DEVICE_PILOT_TEST_PLAN.md`](DEVICE_PILOT_TEST_PLAN.md).

## 1. Versions

- **`versionCode`** is a whole number that grows with **every** build handed to drivers: 1, 2, 3… It is what the server's version policy compares (§4). Never reuse one.
- **`versionName`** is what people read, as `MAJOR.MINOR.PATCH`:
  - PATCH for fixes;
  - MINOR for new features;
  - MAJOR for changes that need retraining.
- **Setting them:** both come from Gradle properties at build time, so the release commit does not change:

  ```bash
  ./gradlew :app:bundleRelease \
    -PgoDailyVersionCode=12 -PgoDailyVersionName=1.2.0 \
    -PgoDailyApiBaseUrl=https://api.example.com/api/v1/
  ```

- **The phone** shows them at the bottom of the home screen («إصدار التطبيق 1.2.0 (12)»), and the API receives `versionCode` in `X-App-Version` with every request.

## 2. Environments

| | Production | Staging |
|---|---|---|
| Property | (default) or `-PgoDailyEnvironment=production` | `-PgoDailyEnvironment=staging` |
| Application id | `com.godaily.driver` | `com.godaily.driver.staging` (installs next to production) |
| API | `-PgoDailyApiBaseUrl=https://<production API>/api/v1/` | `https://<staging API>/api/v1/` |
| Version name | `1.2.0` | `1.2.0-staging`, and the home screen says «نسخة تجريبية» |

- **HTTPS only:** release builds refuse a non-HTTPS API address.
- **One build, one server:** a staging build never talks to the production API, and the other way round. Staging and production have separate accounts and data (U41).

## 3. Signing and artifact integrity

- **Release key:** generate it once, by its owner, away from the repository:

  ```bash
  keytool -genkeypair -v -keystore godaily-release.jks -alias godaily -keyalg RSA -keysize 4096 -validity 10000
  ```

- **`keystore.properties`** (git-ignored) sits next to `settings.gradle.kts` and points at the keystore:

  ```properties
  storeFile=/secure/path/godaily-release.jks
  storePassword=…
  keyAlias=godaily
  keyPassword=…
  ```

  Without it, release builds are unsigned.
- **Keeping the key safe:** keep two encrypted copies of the keystore and its passwords in the secret store or a password manager, each with a named owner (DISASTER_RECOVERY.md). Losing the key means drivers must uninstall and reinstall, which clears unsent data, unless Play App Signing is used.
- **Never** commit the keystore, its passwords or `keystore.properties`. Never put them in CI logs or images.
- **Google Play:** enrol in Play App Signing. Google holds the app signing key, and the keystore above becomes the upload key, which can be reset if lost.
- **Shrinking:** release builds use R8 (`isMinifyEnabled`, `isShrinkResources`, `proguard-rules.pro`). Test every release build on a phone before handing it out (P01 and the scenarios touched by the release). Shrinking problems only show in release builds.
- **Integrity of each artifact**, recorded in the release notes:

  ```bash
  apksigner verify --print-certs app-release.apk   # signer certificate SHA-256 must match the recorded one
  sha256sum app-release.apk > app-release.apk.sha256
  ```

  Phones reject an update signed with a different key. MDM or manual installs should check the SHA-256.

## 4. API / app compatibility (U44)

The API publishes a version policy through two settings (`versionCode` numbers):

| Setting | Effect |
|---|---|
| `DRIVER_APP_RECOMMENDED_VERSION` | Older apps show «يتوفر إصدار أحدث من التطبيق» on the home screen. Everything keeps working. |
| `DRIVER_APP_MIN_VERSION` | Older apps cannot **start a new shift** (HTTP 426 `app_update_required`, with an Arabic message) and show a red notice. |

- **What is never blocked:** a shift that is already running. GPS points, events, fuel entries, ending the shift and the close-out all keep working for every version, so no driver is cut off mid-shift and queued offline data still arrives.
- **Older builds:** builds from before U44 send no version and count as version 0, which is only relevant once a minimum is set.
- **The status** is in `GET /driver/me` → `app_update`: `version`, `minimum_version`, `recommended_version` and `status` (`OK`, `UPDATE_RECOMMENDED` or `UPDATE_REQUIRED`).

**Evolving the API without breaking active drivers:**

- **Additive only for app endpoints:** add optional fields and new endpoints. Never rename, remove or retype a field the app reads, and never make an optional request field required. The app ignores unknown fields.
- **When a breaking change is unavoidable:**
  1. ship an app that handles both shapes;
  2. raise `DRIVER_APP_RECOMMENDED_VERSION`;
  3. once most phones have updated, raise `DRIVER_APP_MIN_VERSION`, outside working hours, since it only takes effect at the next shift start;
  4. only then change the server.
- **Queued requests:** offline data can arrive days later from an old build, so the server must keep accepting the old shapes of the points, events, fuel and close-out requests until no phone runs that build. Each GPS upload batch records the app version that sent it, which shows which builds are still active.

## 5. Distribution and updates (U43)

| Channel | When | How updates reach phones |
|---|---|---|
| **Company phones with MDM** (recommended) | Pilot and company-owned phones | MDM pushes the signed APK silently, outside shift hours. Check the SHA-256. |
| **Google Play** (closed or internal testing track, then production) | Drivers' own phones, larger fleet | Play updates automatically. Background location needs Play's declaration (prominent disclosure, privacy policy, demo video) and review time. |
| **Direct APK** | Only for the first pilot phones | Hand-install the verified APK and record version and phone. Updates are manual, so use the version policy to remind drivers. |

**Update routine:**

1. Release to staging and test.
2. Install on one or two pilot phones.
3. Roll out.
4. Raise the recommended version.
5. Raise the minimum only when needed.

Before replacing an app by uninstalling, for example after a signing key change, make sure the phone's offline queue is empty: the home card «محفوظ على الهاتف» is gone and no shift end is pending.

## 6. Crash reporting (decision needed)

The app does not yet send crash reports. Choosing a provider is a decision that involves privacy, data location and cost:

- **Google Play's Android vitals:** free, Play distribution only, no code change.
- **Firebase Crashlytics or Sentry:** works for MDM and APK installs, needs an SDK and an account.

Whichever is chosen must:

- send no location, phone number, national ID or tokens;
- be described in the privacy notice;
- be turned on only in release builds.

Until then, crashes are found through the device test plan, driver reports and Android vitals if Play is used.

## 7. Release notes

For each release, add an entry here: version name and code, date, environment, signer certificate SHA-256 (not a secret), APK or AAB SHA-256, changes, and the device scenarios run.

| Version | Code | Date | Environment | Changes | Device tests | APK SHA-256 |
|---|---|---|---|---|---|---|
| 0.1.0 | 1 | — | development builds only | Pilot candidate (not yet released to drivers) | not run (U52) | — |
