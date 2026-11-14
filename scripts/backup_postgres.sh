#!/usr/bin/env bash
# Opt-in encrypted backup of the currently configured PostgreSQL database.
# The script never transmits patient records to GitHub or ChatGPT.
set -euo pipefail
umask 077

# Required env vars: PGHOST, PGDATABASE, PGUSER and AGE_RECIPIENT.
for key in PGHOST PGDATABASE PGUSER AGE_RECIPIENT; do
  if [[ ! -v "$key" ]]; then
    printf 'Set %s before running the backup.\n' "$key" >&2
    exit 2
  fi
done
if [[ -z "$PGHOST" || -z "$PGDATABASE" || -z "$PGUSER" || -z "$AGE_RECIPIENT" ]]; then
  printf 'Missing PGHOST, PGDATABASE, PGUSER or AGE_RECIPIENT.\n' >&2
  exit 2
fi
for program in pg_dump age; do
  if ! command -v "$program" >/dev/null 2>&1; then
    printf 'Missing command: %s\n' "$program" >&2
    exit 2
  fi
done
if [[ "$PGHOST" == /* ]]; then
  printf 'Use a TCP PGHOST, not a Unix socket.\n' >&2
  exit 2
fi

# Remote Render Postgres requires TLS. PGPORT is optional (5432 by default).
export PGSSLMODE=require
DEST="$HOME/mindcare-backups"
if [[ "$#" -ge 1 ]]; then DEST="$1"; fi
mkdir -p -- "$DEST"
chmod 700 -- "$DEST"
STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
TARGET="$DEST/mindcare-$STAMP.dump.age"
PART="$TARGET.incomplete.$$"
if [[ -e "$TARGET" ]]; then
  printf 'Backup already exists: %s\n' "$TARGET" >&2
  exit 2
fi
cleanup() { rm -f -- "$PART"; }
trap cleanup EXIT

printf 'Exporting encrypted archive; no plaintext dump will be saved to disk.\n'
# pg_dump custom format is portable and restorable via pg_restore.
# pipefail means a failed export or encryption cannot be reported as success.
pg_dump --format=custom --no-owner --no-acl --no-password |
  age --recipient "$AGE_RECIPIENT" --output "$PART"
mv -- "$PART" "$TARGET"
trap - EXIT
printf 'Encrypted backup created: %s\n' "$TARGET"
printf 'Keep the private age identity in a separate secure location.\n'
