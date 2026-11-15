#!/usr/bin/env bash
# Verify an encrypted MindCare Postgres archive without writing plaintext to disk.
# Read-only against the archive; NEVER connects to the production database.
set -euo pipefail
umask 077

if [[ $# -ne 2 ]]; then
  printf 'Usage: bash scripts/verify_postgres_backup.sh /private/backup.dump.age /private/backup-identity.txt\n' >&2
  exit 2
fi
ARCHIVE="$1"
IDENTITY="$2"
if [[ ! -f "$ARCHIVE" || ! -f "$IDENTITY" || ! -f "$ARCHIVE.sha256" ]]; then
  printf 'Archive, private age identity, or matching SHA-256 file is missing.\n' >&2
  exit 2
fi
for program in age pg_restore sha256sum; do
  if ! command -v "$program" >/dev/null 2>&1; then
    printf 'Missing command: %s\n' "$program" >&2
    exit 2
  fi
done

BACKUP_DIR="$(cd -- "$(dirname -- "$ARCHIVE")" && pwd -P)"
BACKUP_NAME="$(basename -- "$ARCHIVE")"
(
  cd -- "$BACKUP_DIR"
  sha256sum --check -- "$BACKUP_NAME.sha256" >/dev/null
)
printf 'Encrypted archive checksum: verified.\n'
# pg_restore --list checks archive parsing; it is NOT a real restore rehearsal.
age --decrypt --identity "$IDENTITY" -- "$ARCHIVE" | pg_restore --list >/dev/null
printf 'Archive decryption and PostgreSQL table-of-contents parsing: verified.\n'
printf 'NOT YET RESTORE-VERIFIED: run an isolated restore into a disposable database.\n'
