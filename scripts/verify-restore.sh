#!/usr/bin/env bash
# Compare a restored database with its source (U39 backup/restore drill).
#
# Prints only counts, totals and identifiers of the newest rows; never
# personal data, amounts per person, coordinates or secrets. Exits non-zero
# when anything differs, so a drill (or a scheduled check) can alert on it.
#
# Usage: scripts/verify-restore.sh <source database> <restored database>
# Connection from PGHOST/PGPORT/PGUSER/PGPASSWORD or ~/.pgpass.
set -euo pipefail

src="${1:?usage: verify-restore.sh <source db> <restored db>}"
dst="${2:?usage: verify-restore.sh <source db> <restored db>}"

# One line per check, the same query on both databases.
summary() {
  local db="$1"
  psql -d "$db" -Atqc "SELECT 'schema revision ' || version_num FROM alembic_version"
  # Row count of every application table.
  psql -d "$db" -Atqc "
    SELECT format('rows %s %s', table_name,
      (xpath('/row/c/text()',
        query_to_xml(format('SELECT count(*) AS c FROM %I', table_name), false, true, '')))[1]::text)
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    ORDER BY table_name"
  # Financial totals (decimal sums, never per person).
  psql -d "$db" -Atqc "
    SELECT 'total fuel ' || coalesce(sum(total_amount), 0) FROM fuel_transactions
    UNION ALL SELECT 'total expenses ' || coalesce(sum(amount), 0) FROM expenses
    UNION ALL SELECT 'total revenue ' || coalesce(sum(amount), 0) FROM revenue_entries
    UNION ALL SELECT 'total ledger ' || coalesce(sum(amount), 0) FROM driver_ledger_entries
    UNION ALL SELECT 'total closeouts ' || coalesce(sum(collection_amount), 0) FROM shift_closeouts
    UNION ALL SELECT 'total collections ' || coalesce(sum(amount), 0) FROM cash_collections"
  # Newest rows, by id only.
  psql -d "$db" -Atqc "
    SELECT 'newest audit ' || coalesce((SELECT id::text FROM audit_logs ORDER BY occurred_at DESC, id DESC LIMIT 1), '-')
    UNION ALL SELECT 'newest fuel ' || coalesce((SELECT id::text FROM fuel_transactions ORDER BY created_at DESC, id DESC LIMIT 1), '-')
    UNION ALL SELECT 'newest shift ' || coalesce((SELECT id::text FROM shifts ORDER BY created_at DESC, id DESC LIMIT 1), '-')"
}

a="$(mktemp)"
b="$(mktemp)"
trap 'rm -f "$a" "$b"' EXIT
summary "$src" >"$a"
summary "$dst" >"$b"

checks="$(wc -l <"$a")"
if diff -u --label "$src" --label "$dst" "$a" "$b"; then
  echo "OK: $checks checks identical (schema, row counts of every table, financial totals, newest rows)."
  grep -E '^(schema|total)' "$b"
else
  echo "MISMATCH: the restored database differs from the source (see above)." >&2
  exit 1
fi
