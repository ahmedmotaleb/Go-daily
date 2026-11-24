# Backup / Restore Drill (U39)

**Status: rehearsed on a development database only. The production-like drill (staging server, real backup copy, real size) is still to be done; U39 stays REQUIRES REAL-WORLD TEST until then.**

The procedure is in [`OPERATIONS.md`](OPERATIONS.md) ("Backups", "Restore procedure"). This page records each drill and what it proved. It records only counts, timings and match results: no personal data, no amounts per person, and no secrets or connection strings.

## How to run a drill

On a scratch or staging server, never against the live database:

```bash
# 1. Back up (or take last night's dump from the off-site copy).
BACKUP_KEEP_DAYS=30 scripts/backup-db.sh /var/backups/godaily
# 2. Restore into a NEW database (checksum checked, existing names refused).
scripts/restore-db.sh /var/backups/godaily/godaily-<time>.dump godaily_drill_<date>
# 3. Compare with the source: schema revision, row count of every table,
#    financial totals, newest audit/fuel/shift ids. Exits 1 on any difference.
scripts/verify-restore.sh godaily godaily_drill_<date>
# 4. The application agrees with the restored schema.
DATABASE_URL=postgresql+psycopg://…/godaily_drill_<date> alembic current   # expect "(head)"
DATABASE_URL=postgresql+psycopg://…/godaily_drill_<date> alembic check     # expect no operations
# 5. Restore the matching attachments archive and open a few receipts.
# 6. Drop the drill database and the copied dump when done.
```

Time each step. The total is the recovery time for this database size; compare it with the RTO in [`DISASTER_RECOVERY.md`](DISASTER_RECOVERY.md).

When comparing against a live source that keeps receiving writes, stop writes first, or compare against the source as it was at the dump time, for example a second restore of the same dump.

## Drill log

| Date | Environment | Source size | Backup | Restore | Verify | Result | By |
|---|---|---|---|---|---|---|---|
| 2026-10-30 | development | schema `0011_notifications` | ✓ | ✓ | row counts of the main tables identical | passed | development team |
| 2026-11-08 | development (local PostgreSQL 16) | schema `0020_two_factor`, 43 tables, dump 256 KB | 3.1 s | 1.2 s | `verify-restore.sh`: 53 checks identical (schema revision, row count of all 43 tables, 6 financial totals, newest audit/fuel/shift ids); `alembic current` at head; `alembic check` no differences | passed | development team |

What the 2026-11-08 drill also showed:

- **Negative check:** changing one fuel record's amount by 1 in the restored copy made `verify-restore.sh` report the differing total and exit 1, so a bad restore is detected.
- **Cleanup:** the drill database and dump were deleted afterwards.

## Still required (production-like)

- [ ] Drill on the staging server with a copy of a real-size backup taken by the scheduled job and fetched from the off-site store.
- [ ] Attachments restored and a sample of receipts opened through the admin web.
- [ ] National IDs readable after restore, which proves the same `DATA_ENCRYPTION_KEY` was used.
- [ ] Measured total recovery time recorded and compared with the RTO.
- [ ] Drill repeated quarterly and after major upgrades.
