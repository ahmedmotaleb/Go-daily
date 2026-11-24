# Disaster Recovery (U40)

What to do when something is lost or compromised: the database, attachments, a server, credentials or a release.

- **How-to steps:** backup and restore steps are in [`OPERATIONS.md`](OPERATIONS.md); deployment and rollback are in [`DEPLOYMENT.md`](DEPLOYMENT.md).
- **Drill record:** the drill evidence is in [`BACKUP_RESTORE_DRILL.md`](BACKUP_RESTORE_DRILL.md).

**Status:** the targets and owners below are **proposals**. Management must approve them and name the people before production (U53). Until then, nothing here is a commitment.

## 1. Targets (proposed)

| | Target | Why it is achievable |
|---|---|---|
| **RPO**, data loss tolerated (database) | ≤ 15 minutes with managed PITR; ≤ 24 hours with daily dumps only | PITR replays WAL to any minute. Daily `backup-db.sh` dumps are the fallback. |
| **RPO** (attachments) | ≤ 24 hours (local volume); 0 with S3 versioning | Files are never overwritten (unique keys) and only soft-deleted in the database. |
| **RPO** (driver phones) | 0 for queued GPS points, shift ends, fuel entries and close-outs | Phones queue them and resend with the same ids after the server is back (U45). Resends never duplicate. |
| **RTO**, time to restore service | ≤ 4 hours | The drill restored a development database in seconds. A real-size restore must be measured on staging; the total RTO is dominated by provisioning and DNS. |

Measure the real numbers in the production-like drill (U39) and update this table.

## 2. Roles (to be named)

| Role | Responsibility | Person / backup |
|---|---|---|
| Incident lead | Declares the incident, decides restore vs wait, communicates | _(to be named)_ |
| Technical lead | Runs the restore or rollback, checks data | _(to be named)_ |
| Operations contact | Tells drivers and dispatch what to do (keep the app open; shifts continue offline) | _(to be named)_ |
| Finance contact | Confirms collections, close-outs and fuel totals after a restore | _(to be named)_ |
| Secret owner | Holds and rotates credentials (DEPLOYMENT.md §4) | _(to be named)_ |

## 3. Scenarios

### Database lost or corrupted

1. Stop writes: scale the API to zero, or put the site in maintenance.
2. **Restore into a new database:**
   - **Managed PITR:** restore to a new instance at the last good minute.
   - **Otherwise:** run `scripts/restore-db.sh <latest dump> <new name>`.
3. Run `scripts/verify-restore.sh` against a second restore of the same dump if the source is gone. Check the newest records against what dispatch and finance remember. Then run `alembic current` (expect head).
4. Point `DATABASE_URL` at the restored database. Keep the same `DATA_ENCRYPTION_KEY`. Start the API and confirm `/ready`.
5. **Drivers' phones** resend what they queued after the restore point (points, shift ends, fuel, close-outs) without duplicates.
6. **Re-entry:** entries made in the admin web after the restore point are lost and must be re-entered from paper or receipts. Finance lists what changed since the backup time.

### Attachments lost

- **S3 with versioning:** restore deleted or overwritten object versions.
- **Local volume:** extract the latest attachments archive into the volume.
- **Missing files:** rows whose file is missing show "ملف المرفق غير متاح". Ask for a copy of the receipt where it matters.

### Server lost (host failure, provider outage)

1. Provision a new host from DEPLOYMENT.md. Images are rebuilt from the tagged release commit.
2. Restore the database and attachments as above, then restore the secrets from the secret store.
3. Point DNS at the new host and check TLS. Then run the smoke test (DEPLOYMENT.md §12).

### Credentials leaked or a staff member with access leaves

Rotate in this order, and log each rotation (who, when, which secret; never the value):

1. **Database password:**
   - create a new role password;
   - update `DATABASE_URL`;
   - restart;
   - revoke the old one.
2. **S3 keys:**
   - issue a new key limited to the bucket;
   - update the settings;
   - restart;
   - delete the old key.
3. **`METRICS_TOKEN`:** new token in the API settings and the monitoring server.
4. **User sessions:**
   - deactivate the departed user;
   - reset passwords where needed, which ends their sessions;
   - reset two-factor login for anyone whose phone was lost (U31).
5. **Android signing key:** a leak needs Play App Signing key reset procedures (U42). Never commit signing material.
6. **`DATA_ENCRYPTION_KEY`:** rotation means re-encrypting national IDs with a migration script and both keys. Plan it; do not change the key on its own, or stored IDs become unreadable.

### Bad release

Roll back as in DEPLOYMENT.md §12:

- **Application only:** redeploy the previous image tags; migrations are additive.
- **Bad migration:** restore the pre-deploy backup into a new database and redeploy the previous images.
- **Driver app:** keep the previous signed APK. Make sure a phone's offline queue is empty before reinstalling.

## 4. Incident checklist

- [ ] Declare the incident and note the start time; name the incident lead.
- [ ] Stop writes if data may be damaged.
- [ ] Tell operations: drivers keep the app open; points and entries are queued on the phone.
- [ ] Choose restore or rollback; write down the restore point.
- [ ] Restore into a **new** database; verify (`verify-restore.sh`, `alembic current`, sample records).
- [ ] Switch, then check `/ready`, login, a vehicle page, a recent fuel record and a close-out.
- [ ] Watch 5xx rate and GPS ingestion for 30 minutes (alerts in `ops/monitoring/alerts.yml`).
- [ ] Finance reconciles collections and close-outs around the restore point.
- [ ] Rotate any exposed credential.
- [ ] Keep the old database until the restored one has worked for a few days.
- [ ] Write the post-incident note: timeline, data lost (if any), measured RPO/RTO, what to change.
