#!/usr/bin/env bash
# Restore a Go Daily backup into a NEW database (see docs/OPERATIONS.md).
#
# Never restores over the live database: the target must not exist. After
# checking it, point DATABASE_URL at the restored database and restart.
#
# Usage: scripts/restore-db.sh <dump file> <new database name>
# Connection (server, user, password) from PGHOST/PGPORT/PGUSER/PGPASSWORD
# or ~/.pgpass; the user needs CREATEDB.
set -euo pipefail

file="${1:?usage: restore-db.sh <dump file> <new database name>}"
target="${2:?usage: restore-db.sh <dump file> <new database name>}"

if [[ ! "$target" =~ ^[a-z][a-z0-9_]{0,62}$ ]]; then
  echo "Database name must be lowercase letters, digits and underscores." >&2
  exit 1
fi

if [[ -f "$file.sha256" ]]; then
  (cd "$(dirname "$file")" && sha256sum --check --quiet "$(basename "$file").sha256")
fi

if psql -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '$target'" | grep -q 1; then
  echo "Database '$target' already exists; choose a new name." >&2
  exit 1
fi

createdb "$target"
pg_restore --no-owner --no-privileges --exit-on-error --dbname="$target" "$file"

echo "Restored into '$target'. Checks:"
psql -d "$target" -Atc "SELECT 'schema revision: ' || version_num FROM alembic_version"
for table in users vehicles drivers shifts gps_points fuel_transactions expenses \
  revenue_entries driver_ledger_entries audit_logs attachments; do
  printf '  %-24s %s\n' "$table" "$(psql -d "$target" -Atc "SELECT count(*) FROM $table")"
done
