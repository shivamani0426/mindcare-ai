# MindCare AI: encrypted PostgreSQL backup and restore

> **Privacy:** This is a documented, opt-in operation for the authorized project
> administrator. Never copy patient data, database URLs, passwords, unencrypted
> dumps or backup decryption keys into tickets, chat, repository, or CI logs.

## Deadline and hosting risk

The Render PostgreSQL free instance for this project currently lists
**2026-12-12** as its expiration date. Free Render Postgres instances expire
after 30 days, have no managed backups, and are deleted after an additional
14-day upgrade grace period. Confirm the deadline in the Render dashboard.
Do not treat the free tier as durable storage.

Before that deadline: (1) take an encrypted backup; (2) test a restore
in an isolated database; and (3) upgrade to a durable plan or complete a
verified migration. Do NOT create a fresh database and point the live service
to it until records and authorizations have been migrated and audited.

## Requirements on the authorized administrator's computer

- PostgreSQL pg_dump client from PostgreSQL **18 or newer** (server was v18
  at last audit). Older clients cannot dump newer servers.
- PostgreSQL pg_restore client and a throwaway local test database to rehearse.
- The open-source age encryption CLI and a private key kept offline.
- Your own Render external DB connection details from the private dashboard.
  Do not add these connection details to a committed .env file.

On Ubuntu/Linux Mint you can install age from the OS package manager, and
PostgreSQL 18 client from a suitable trusted PostgreSQL package repository.
Check versions with: pg_dump --version, pg_restore --version, age --version.

## 1. Create a private encryption identity (once)

Use a private terminal on your own laptop:

    umask 077
    mkdir -p "$HOME/.config/mindcare"
    age-keygen -o "$HOME/.config/mindcare/backup-identity.txt"
    age-keygen -y "$HOME/.config/mindcare/backup-identity.txt"

Record the **public recipient** (starts with age1) as AGE_RECIPIENT.
Move an encrypted/offline copy of backup-identity.txt to separate safe
storage; losing it makes backups impossible to decrypt. Never commit it.

## 2. Prepare connection details locally

Find the database's **External Database URL / connection fields** in the
Render database dashboard. Use separate PG* environment variables rather
than placing a password-bearing URL on a shell command line:

    export PGHOST='RENDER_EXTERNAL_HOST_FROM_PRIVATE_DASHBOARD'
    export PGPORT='5432'
    export PGDATABASE='DATABASE_NAME_FROM_PRIVATE_DASHBOARD'
    export PGUSER='DATABASE_USER_FROM_PRIVATE_DASHBOARD'
    export AGE_RECIPIENT='age1YOUR_PUBLIC_RECIPIENT'
    read -rs -p 'Database password (hidden): ' PGPASSWORD; echo
    export PGPASSWORD

Do not run backup commands in shared terminals or recorded demos. Use a
network connection permitted by the Render database IP allowlist.

## 3. Run the encrypted backup

From the checked-out repository:

    bash scripts/backup_postgres.sh

Output goes to $HOME/mindcare-backups with owner-only permissions and the
filename mindcare-YYYYMMDDTHHMMSSZ.dump.age. A matching .dump.age.sha256
checksum file is also created, allowing an integrity check after copying the
encrypted archive. Copy **both** files together. The script uses TLS, a pg_dump
custom archive and streaming age encryption. It does not create a temporary
unencrypted dump file or change any live database records.

For a different destination:

    bash scripts/backup_postgres.sh '/path/to/private/backup-folder'

After the command, end the password-bearing shell session, or run:

    unset PGPASSWORD

## 4. Verify and rehearse a restore (MANDATORY before release)

In a private environment with the backup identity, verify the encrypted file
checksum, decrypt the archive in a pipe, and inspect the PostgreSQL archive
structure **without writing an unencrypted copy to disk**:

    bash scripts/verify_postgres_backup.sh \
      '/path/to/backup.dump.age' \
      "$HOME/.config/mindcare/backup-identity.txt"

The companion `.dump.age.sha256` file must be next to the encrypted archive.
The verifier fails if either the checksum or decryption/archive parsing fails.
Successful verification proves the archive is intact and readable; it does NOT
prove that all tables and relationships can be restored. For a complete restore drill, use the new local Docker-based rehearsal.
Install Docker and ensure its active context points to your own local Unix
socket. Do not use remote Docker contexts. The script uses PostgreSQL 18 in
a fresh container with networking disabled, no published ports and temporary
RAM-backed database storage. The container is removed on exit. Run locally
on a trusted machine with sufficient RAM (and encrypted or disabled swap):

    bash scripts/rehearse_postgres_restore.sh \
      '/path/to/backup.dump.age' \
      "$HOME/.config/mindcare/backup-identity.txt"

The script checks the exact encrypted archive checksum, decrypts into
pg_restore, restores in one transaction, and reads representative table
counts. Compare those counts privately against the source snapshot. Never
send counts, records, archives or keys to chat or public CI. If local RAM
is insufficient, arrange an equally isolated encrypted-storage restore
environment with the administrator rather than restoring to production.

The synthetic recovery CI job uses generated dummy data and an ephemeral
key only. Passing CI does not establish that the live database is backed
up, nor that a particular production archive restores successfully.

## 5. Retention and migration

Keep multiple encrypted generations with a copy off the laptop (in a secure
separate location); test that you can recover with the separately stored key.
Set a recurring reminder to take a backup before the expiry deadline, and
again before any production migration. Review data minimization, patient
consent, retention period and deletion requirements before retaining archives.

Upgrade Render Postgres to a plan with managed backups, or use a future
self-hosted dedicated PostgreSQL server with encrypted offsite backups and
recovery checks. A local laptop database is not an always-on production DB
for patients while the laptop is offline.

## 6. After migration: safety checklist

- Test POST login, patient/caregiver registration, all six games, reminders,
  photos, check-ins, approved/revoked caregiver access and video calls.
- Verify all existing patient-linked row counts match the migration source.
- Verify a new database backup and isolated restore again.
- Keep the old database available in a controlled rollback window. Do not
  delete production records as a test.

References: Render free-tier/Postgres backup documentation and PostgreSQL
pg_dump/pg_restore manuals.
