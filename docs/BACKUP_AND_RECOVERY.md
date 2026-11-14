# MindCare AI — encrypted PostgreSQL backup and recovery runbook

**Manual, opt-in workflow.** This documents the existing `scripts/backup_postgres.sh` and does not modify production data, create a new database, or turn on a paid service. MindCare stores private patient and family information: treat archives and the corresponding decryption identity as sensitive.

## Before the backup

1. Verify the **existing MindCare Render PostgreSQL** database, its expiry date, and its storage allowance. Never create a replacement database as part of this process.
2. Run from a trusted Linux/macOS workstation with PostgreSQL client `pg_dump` and `age` installed. Do not run backups on the Render web service's ephemeral disk.
3. Prepare an `age` recipient (public key) and preserve its matching **private identity separately** in secure storage. Losing that identity makes the backup unrecoverable.
4. Obtain the database connection parameters in the private Render dashboard. Provide `PGHOST`, `PGDATABASE`, `PGUSER`, and password through secure PostgreSQL client configuration such as a permission-restricted `~/.pgpass` file; optional `PGPORT` as needed. The script enforces TLS via `PGSSLMODE=require`. Do **not** put credentials in source code, GitHub, shell history, screenshots, chat, logs or copied documentation.
5. Never export production credentials or patient data to a developer's publicly shared computer.

## Run a backup

```bash
# Environment values below are placeholder examples, not production secrets.
export PGHOST="your-render-postgres-host"
export PGDATABASE="your-database-name"
export PGUSER="your-database-user"
export AGE_RECIPIENT="age1YOUR_PUBLIC_RECIPIENT"
bash scripts/backup_postgres.sh "$HOME/mindcare-backups"
```

The existing script streams `pg_dump --format=custom` directly into `age` encryption, writes a `.dump.age` file with restrictive permissions, and removes incomplete output on errors. **No unencrypted database dump is intentionally written to disk.** It does not delete old backups, schedule future backups, or upload copies. Confirm the file exists and has a sensible size; this is not a substitute for a restore test.

## Isolated restore drill — never into production

1. Use a separate, disposable PostgreSQL test database and verify its hostname and database name are *not* the production values.
2. On the trusted workstation, decrypt using the private `age` identity and stream into `pg_restore --list` to confirm the archive can be read:

```bash
age --decrypt -i /secure/path/to/age-identity.txt "$HOME/mindcare-backups/YOUR_BACKUP.dump.age" | pg_restore --list >/dev/null
```

3. Restore **only** into the verified disposable test database (command intentionally uses an explicit TEST URL to avoid accidental production restores):

```bash
set -o pipefail
age --decrypt -i /secure/path/to/age-identity.txt "$HOME/mindcare-backups/YOUR_BACKUP.dump.age" | \
  pg_restore --dbname="$TEST_DATABASE_URL" --no-owner --no-acl --exit-on-error
```

4. Privately confirm representative counts and usability of users, caregiver links, family photos, game scores, and reminders. Do not expose real patient data in logs or screenshots. Record whether the drill succeeded, then securely remove the disposable restore environment.

## Operational limits and safeguards

- This is not an automated backup service. Set an appropriate recurring operator procedure and encrypted off-site retention, and periodically **test restores** before depending on the backup.
- Retain the private age identity independently and securely; confirm staff authorization and a documented recovery process. Do not commit identity files or backup archives to Git.
- A `pg_dump` export is a logical snapshot; it does not provide point-in-time recovery. Confirm whether Render's managed plan offers additional restore guarantees.
- The existing database remains untouched by these steps until the operator explicitly runs a restore **against a separate target**.
- Before v1.0.0 release, verify account throttling under load, CSRF and role checks, accessibility with real devices, and mobile-data-to-Wi-Fi video calls. TURN credentials, if needed, belong only in private Render environment settings.
