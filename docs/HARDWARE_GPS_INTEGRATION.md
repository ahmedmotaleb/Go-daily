# Hardware GPS tracker integration (U05)

**Status: architecture and ingestion code ready; no tracker hardware or provider is in use.** Nothing in the system reads tracker data for operations, review cases or reports yet. No vendor integration is simulated.

## Why

The driver's phone tracks the work shift only. A tracker fitted to the vehicle would report the vehicle itself, on its own power, whether or not a shift is running. That allows two later checks (U06):

- compare the phone path with the vehicle path;
- see vehicle movement outside any shift.

The vehicle tracker reports a vehicle, not a person, and its positions are never mixed into a driver's phone track.

## Data model (`app/models/trackers.py`, migration 0029)

| Table | What it holds |
|---|---|
| `tracker_devices` | A tracker known to the company: provider code + the provider's own device id (unique together), label, active flag. |
| `tracker_bindings` | Which vehicle a tracker was fitted to, from `starts_at` until `ends_at` (open = still fitted). A new binding closes the previous one; a binding can never start before the current one. Events are attributed to the vehicle the tracker was in **at the event's time**. |
| `tracker_raw_events` | Every event received, exactly as sent (`payload`), with `status` ACCEPTED or QUARANTINED and a `reason`. `(provider, provider_event_id)` is unique: a resent event is stored once. |
| `tracker_locations` | Normalised positions of accepted events: vehicle, device, time, latitude/longitude, speed (m/s), heading, ignition and external power when the provider sends them, and a link to the raw event. |

## Ingestion

```
POST /api/v1/trackers/{provider}/events
X-GoDaily-Signature: sha256=<hex HMAC-SHA256 of the raw body with TRACKER_WEBHOOK_SECRET>
```

- **Off by default.** Without `TRACKER_WEBHOOK_SECRET` the endpoint answers 503 `tracker_ingestion_disabled`.
- **Authentication.**
  - A wrong or missing signature gets 401.
  - The endpoint never uses a staff or driver session.
  - The secret is created by its owner in each environment and never committed (ENVIRONMENTS.md).
- **Limits.** Bodies are 256 KB at most. Processing runs off the event loop.
- **Idempotency.** Each event's provider id (or a hash of the event when the provider sends none) is unique per provider. Resending a body changes nothing, and the response counts the duplicates.
- **Adapters** (`app/services/trackers/adapters.py`). An adapter splits a body into events, gives each its provider id and device id, and normalises it (or raises `AdapterError`). An unknown provider gets 404.

  Only the **generic** adapter exists. It reads this documented format:

  ```json
  {"events": [{"event_id": "e-123", "device_id": "TRK-1",
               "recorded_at": "2026-11-23T08:15:00+02:00",
               "lat": 30.0444, "lon": 31.2357,
               "speed_kmh": 36, "heading_deg": 90,
               "ignition": true, "external_power": true}]}
  ```

  A provider can send this directly, or through a small relay in front of it. When a provider is chosen, its own adapter is added next to the generic one: the rest of the system does not change.

### Quarantine

An event is accepted only when every check passes. Otherwise it is kept with its reason, never dropped, and never "fixed": no position is invented or moved.

| Reason | Meaning |
|---|---|
| `INVALID_EVENT` | The adapter could not read it (missing device, time or coordinates; bad format). |
| `INVALID_COORDINATES` | Outside the possible range, or exactly 0,0. |
| `FUTURE_TIME` | More than 5 minutes ahead of the server. |
| `TOO_OLD` | Older than `TRACKER_MAX_EVENT_AGE_DAYS` (30). |
| `UNKNOWN_DEVICE` | Device not registered. |
| `DEVICE_INACTIVE` | Device deactivated. |
| `NO_VEHICLE_BINDING` | Device not fitted to a vehicle at the event's time. |

`POST /api/v1/trackers/events/reprocess` (settings managers, audited) checks again the events quarantined for a device reason (the last three), after the device is registered, activated or fitted.

## Administration (API; no screen yet)

| Endpoint | Permission |
|---|---|
| `GET /trackers/devices` (with the current vehicle) | `tracking:read` |
| `POST /trackers/devices` | `settings:manage` |
| `POST /trackers/devices/{id}/bind` (`vehicle_id`, optional `starts_at`) | `settings:manage` |
| `POST /trackers/devices/{id}/unbind` | `settings:manage` |
| `GET /trackers/events?status=QUARANTINED` (with the Arabic reason) | `tracking:read` |
| `POST /trackers/events/reprocess` | `settings:manage` |

Every device change is audited.

## Privacy and retention

- Tracker positions describe the vehicle at all times, including outside shifts. Fitting trackers needs:
  - management approval;
  - a note in the drivers' privacy notice;
  - the same access rules as tracking.
- `python -m app.cli prune-gps` also deletes tracker positions and raw events older than `GPS_RETENTION_DAYS`.

## Before a real provider goes live

1. **Choose a provider**, with an official API or webhook and its terms accepted. Then write its adapter and tests from its documentation; never from guesses.
2. **Set `TRACKER_WEBHOOK_SECRET`** in staging (or configure the provider's own signing), then register and fit one test device.
3. **Validate on real hardware** and record the evidence in DEVICE_PILOT_TEST_PLAN.md:
   - events arrive and are signed;
   - duplicates are ignored;
   - the clock and time zone are right;
   - positions match the vehicle;
   - ignition and power fields are reported;
   - quarantine reasons are right;
   - load is acceptable at the planned reporting interval.
4. **Only then** use tracker data in operations (U06 comparison, live map, review rules).

Until then the related items stay **BLOCKED / REQUIRES REAL-WORLD TEST**; see UPGRADE_STATUS.md.
