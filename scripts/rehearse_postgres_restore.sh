#!/usr/bin/env bash
# Authorized local recovery drill only. No production connection is possible
# through this script: restore runs in a fresh, network-isolated container.
set -euo pipefail
umask 077
if [[ $# -ne 2 ]]; then
  echo 'Usage: bash scripts/rehearse_postgres_restore.sh ARCHIVE IDENTITY' >&2
  exit 2
fi
archive="$1"
identity="$2"
for tool in docker age sha256sum; do
  command -v "$tool" >/dev/null || { echo "Missing command: $tool" >&2; exit 2; }
done
[[ -f "$archive" && -f "$identity" && -f "$archive.sha256" ]] || {
  echo 'Missing archive, identity or checksum.' >&2; exit 2;
}
# Compare the hash of this exact archive rather than trusting paths in a sidecar.
read -r expected _ < "$archive.sha256"
actual="$(sha256sum < "$archive")"
actual="${actual%% *}"
[[ "$expected" =~ ^[[:xdigit:]]{64}$ && "$actual" == "${expected,,}" ]] || {
  echo 'Encrypted archive checksum mismatch.' >&2; exit 1;
}
# Only a local Docker daemon is permitted. Do not use remote Docker contexts.
[[ -z "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" ]] || {
  echo 'Unset DOCKER_HOST and DOCKER_CONTEXT; use a local Docker daemon.' >&2; exit 2;
}
endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
[[ "$endpoint" == unix:///* ]] || {
  echo 'Docker must use a local Unix socket.' >&2; exit 2;
}
cid=''
cleanup() { if [[ -n "$cid" ]]; then docker rm -fv "$cid" >/dev/null 2>&1 || true; fi; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cid="$(docker run -d --network none --tmpfs /var/lib/postgresql:rw,nosuid,nodev \
  --env POSTGRES_HOST_AUTH_METHOD=trust --env POSTGRES_DB=mindcare_restore postgres:18)"
ready=0
for ((i=0;i<60;i++)); do
  if docker exec "$cid" pg_isready -h 127.0.0.1 -U postgres -d mindcare_restore >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
[[ "$ready" == 1 ]] || { echo 'Isolated PostgreSQL did not start.' >&2; exit 1; }
# Fail closed on decrypt, archive, SQL, or constraint errors. Suppress database
# error output because it could include patient data. Never upload the archive.
if ! age --decrypt --identity "$identity" -- "$archive" |
  docker exec -i -u postgres "$cid" pg_restore --exit-on-error --single-transaction \
    --no-owner --no-acl --dbname=mindcare_restore >/dev/null 2>&1; then
  echo 'Restore failed; disposable database will be removed.' >&2
  exit 1
fi
# Verify required application tables exist and are readable. Counts stay local.
docker exec -i -u postgres "$cid" psql -X -v ON_ERROR_STOP=1 -d mindcare_restore <<'SQL'
SELECT 'user' AS table_name, count(*) FROM public."user"
UNION ALL SELECT 'care_link', count(*) FROM public.care_link
UNION ALL SELECT 'game_result', count(*) FROM public.game_result
UNION ALL SELECT 'reminder', count(*) FROM public.reminder
UNION ALL SELECT 'family_member', count(*) FROM public.family_member;
SQL
docker rm -fv "$cid" >/dev/null
cid=''
echo 'Isolated restore succeeded; disposable container removed.'
echo 'Compare counts privately against the source backup snapshot. Keep the encrypted archive and key separately.'
