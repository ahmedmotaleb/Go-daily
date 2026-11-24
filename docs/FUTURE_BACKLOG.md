# Future backlog (U55)

**Documented only. Nothing here is implemented, and nothing may be implemented without written management approval.** Each item lists what exists today to build on, what it needs first, and the risks to weigh. An approved item becomes its own upgrade with the usual delivery rules: migrations, tests, documentation, and real-world evidence before it is called verified.

| # | Item | What exists to build on | Needs first (blockers) | Risks and rules |
|---|---|---|---|---|
| B1 | **Ride-hailing platform APIs** | CSV statement import (U19) with mapping, duplicate detection and rollback; reconciliation with recorded shifts. | An official partner API and written terms from each platform; credentials kept in the secret store. | No scraping or unofficial endpoints, ever. API data still lands as SUBMITTED statements for review. |
| B2 | **WhatsApp / SMS notifications** | Notification channels interface (`notification_channels.py`); in-app notifications with severity and dedupe; notification rules in the policies (U48). | A WhatsApp Business or SMS provider contract; approved templates; drivers' consent to messages. | Cost per message; no national IDs, amounts or locations in message bodies; opt-out handling. |
| B3 | **Ticketing** | Revenue entries per session; expected revenue per loop (U10); passenger counts reserve the `TICKETING` source (U11). | A ticketing provider or device choice; fare rules per route; cash-handling policy. | Fare disputes; offline sales on the vehicle; reconciliation with cash close-outs. |
| B4 | **QR / NFC** (boarding, attendance, fuel cards) | Attachments and receipts; driver app offline queue (U45). | A defined use case (which check-in, by whom); hardware for NFC. | Spoofing (screenshots of QR codes); privacy of passengers' data. |
| B5 | **Fuel level sensors** | Fuel efficiency (U13), baselines (U14), plausibility (U15), stations (U16). | Sensor hardware and a provider integration (through the U05 tracker pipeline or its own adapter). | Sensor calibration per tank; readings are evidence to review, never automatic theft findings. |
| B6 | **CAN / OBD data** (odometer, engine hours, faults) | Odometer reconciliation (U04); maintenance due by km (U17); tracker ingestion pipeline (U05). | Compatible telematics units; a provider; per-model data mapping. | Vehicle warranty; data volume; the odometer from the vehicle must not overwrite driver-entered readings silently: both are kept. |
| B7 | **Physical GPS trackers** | Ingestion architecture ready (U05) and phone-vs-tracker comparison (U06), with webhook off by default. | Provider choice and adapter from its documentation; devices fitted; validation on real vehicles (HARDWARE_GPS_INTEGRATION.md). | Tracking outside shifts needs management approval and the drivers' privacy notice. |
| B8 | **Passenger counters** | Passenger counts with source and confidence (U11), `HARDWARE` source reserved. | Counter hardware and its integration; validation against manual counts. | Counts are evidence with confidence, never exact truth; no images of passengers stored. |
| B9 | **Predictive maintenance** | Maintenance history, schedules and due list (Task 21, U17); fuel efficiency trends. | Enough history per vehicle (at least a year) and a decided method. | Predictions are suggestions; scheduled maintenance stays the rule. No black-box decisions. |
| B10 | **Route optimisation** | Routes with versions (U08), road-aware geometry ready (U07), loops and timings. | A routing provider (release gate 13); real demand data (passenger counts). | Changes to fixed routes affect licences and customers; humans decide. |
| B11 | **Customer / contract portal** | Contract revenue spread over periods; school runs (U12); reports. | Customer accounts model, separate authentication, legal terms. | Strict tenant isolation; no driver personal data or GPS outside the customer's own service. |
| B12 | **School-parent tracking** | School runs and their verification (U12); live tracking. | Child-safety and privacy approval; consent from parents and schools; a separate public-facing app or portal. | Highest privacy sensitivity: only the child's own run, only during the run, delayed or coarse positions, full audit. |
| B13 | **Payroll integration** | Settlement workflow with recorded payments (U20); driver ledger. | The payroll system and its import format; HR approval. | Payments stay recorded, not executed, until a bank or payroll integration is approved; reconciliation of every transfer. |

## How an item gets approved

1. Management names an owner and the business reason.
2. Development writes a short design: data, integration, privacy and cost.
3. Legal and privacy review where the item touches passengers, children or drivers' data.
4. Written approval (who, date). Then the item enters `GO_DAILY_UPGRADES_MASTER.md` as a new upgrade.
