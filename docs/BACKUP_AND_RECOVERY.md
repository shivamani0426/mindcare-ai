# MindCare AI — PostgreSQL backup and recovery runbook

This is a **manual, opt-in** operational procedure for the existing Render PostgreSQL database. It does **not** replace the database, deploy a new database, or change production code. The data may contain sensitive patient and family information.

## Preparation

1. Confirm the **correct existing** MindCare Render PostgreSQL instance and check the database's expiry and storage limits. Never provision a replacement simply to run this procedure.
2. Use a trusted workstation (not ephemeral Render web-service storage) with PostgreSQL client utilities `pg_dump` and `pg_restore` compatible with the server version.
3. Choose an access-controlled **encrypted** backup destination with enough space. Restrict who can view copies. Do not save backups in GitHub, a public bucket, unencrypted cloud folders, logs, or browser downloads.
4. Retrieve the connection URL through Render's private Database > Connect UI. Export `DATABASE_URL` in your own terminal without writing the credential to source files, shell history, chat or screenshots. An external connection should use TLS, e.g. the provider's supported `sslmode=require` configuration.

## Backup (Linux / macOS)

```bash
# Set DATABASE_URL privately in this shell first; do not paste its value into commands shared publicly.
export BACKUP_DIR="/path/to/your/existing/encrypted/backup-directory"
export MINDCARE_BACKUP_ENCRYPTED_STORAGE=1
bash scripts/backup_postgres.sh
```

The script uses a PostgreSQL **custom-format logical backup**, verifies its archive directory via `pg_restore --list`, creates a SHA-256 checksum, and applies restrictive file permissions. It does not delete old backups or automate database access. A successful archive-list check is **not** proof that every row can be restored.

## Recovery drill (never on production)

1. Prepare an **isolated disposable test database**. Explicitly double-check its URL is **not** MindCare production.
2. Check `sha256sum -c <backup-file>.sha256` from the secure backup folder.
3. Restore to the isolated test database using `pg_restore --dbname=<TEST_DATABASE_URL> --no-owner --no-acl <backup-file>`. This command modifies its target; **never substitute the production URL**.
4. Verify counts and representative records for users, caregiver links, photos, games, reminders, and call records. Do not expose or log any private records. Destroy the disposable database and copies when the drill is finished.
5. Record backup time, operator, checksum check, and restore-drill outcome in an access-controlled operations log.

## Limitations and release checklist

- No schedule or remote encrypted replication is configured; the operator must actually run backups and verify secure off-site retention. A local-only copy is not a sufficient disaster-recovery strategy.
- Do not make backups publicly accessible or store them on the Render free web service's ephemeral disk.
- Configure retention and secure deletion according to the project's data policy; avoid unattended deletion before recovery has been tested.
- Verify the patient consent/privacy model and login throttling separately. Use synthetic accounts for browser tests.
- For video calls, provision TURN secrets only through private Render environment settings and test separate networks. This guide does not provision TURN resources.
