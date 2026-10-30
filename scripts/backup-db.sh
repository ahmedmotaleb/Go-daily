#!/usr/bin/env bash
# PostgreSQL backup for Go Daily (see docs/OPERATIONS.md).
#
# Connection comes from the standard libpq variables (PGHOST, PGPORT, PGUSER,
# PGDATABASE) and the password from PGPASSWORD or ~/.pgpass, so no secret
# appears in the process list.
#
# Usage: scripts/backup-db.sh [backup_dir]
#   BACKUP_KEEP_DAYS  delete dumps older than this (default 30)
set -euo pipefail

dir="${1:-./backups}"
keep_days="${BACKUP_KEEP_DAYS:-30}"
: "${PGDATABASE:?set PGDATABASE (and PGHOST/PGUSER, password via PGPASSWORD or ~/.pgpass)}"

umask 077
mkdir -p "$dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="$dir/godaily-$stamp.dump"

# Custom format: compressed, restorable table by table, verifiable.
pg_dump --format=custom --no-owner --no-privileges --file="$file.partial"
# Refuse to keep an unreadable archive.
pg_restore --list "$file.partial" >/dev/null
mv "$file.partial" "$file"
(cd "$dir" && sha256sum "$(basename "$file")" >"$(basename "$file").sha256")

find "$dir" -maxdepth 1 -name 'godaily-*.dump*' -mtime +"$keep_days" -delete
echo "$file"
