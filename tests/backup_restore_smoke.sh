#!/usr/bin/env bash
# Synthetic data only; no production secrets or database connections.
set -euo pipefail
umask 077
work="$(mktemp -d)"
cid=''
cleanup() { if [[ -n "$cid" ]]; then docker rm -fv "$cid" >/dev/null 2>&1 || true; fi; rm -rf -- "$work"; }
trap cleanup EXIT
age-keygen -o "$work/key" 2>/dev/null
recipient="$(age-keygen -y "$work/key")"
cid="$(docker run -d --network none --tmpfs /var/lib/postgresql:rw,nosuid,nodev -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=fixture postgres:18)"
ready=0
for ((i=0;i<60;i++)); do
  if docker exec "$cid" pg_isready -h 127.0.0.1 -U postgres -d fixture >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[[ "$ready" == 1 ]]
docker exec -i -u postgres "$cid" psql -X -v ON_ERROR_STOP=1 -d fixture <<'SQL'
CREATE TABLE "user" (id integer PRIMARY KEY);
CREATE TABLE care_link (id integer PRIMARY KEY, patient_id integer REFERENCES "user"(id));
CREATE TABLE game_result (id integer PRIMARY KEY);
CREATE TABLE reminder (id integer PRIMARY KEY);
CREATE TABLE family_member (id integer PRIMARY KEY);
INSERT INTO "user" VALUES (1);
INSERT INTO care_link VALUES (1,1);
SQL
docker exec -u postgres "$cid" pg_dump -Fc --no-owner --no-acl fixture | age -r "$recipient" -o "$work/fixture.dump.age"
(cd "$work"; sha256sum fixture.dump.age > fixture.dump.age.sha256)
docker rm -fv "$cid" >/dev/null
cid=''
result="$(bash scripts/rehearse_postgres_restore.sh "$work/fixture.dump.age" "$work/key")"
printf '%s\n' "$result"
grep -Eq 'user[[:space:]]*\|[[:space:]]*1' <<< "$result"
grep -Eq 'care_link[[:space:]]*\|[[:space:]]*1' <<< "$result"
grep -q 'Isolated restore succeeded' <<< "$result"
# A corrupt archive must be rejected before the restore starts.
printf 'corrupt' >> "$work/fixture.dump.age"
if bash scripts/rehearse_postgres_restore.sh "$work/fixture.dump.age" "$work/key"; then
  echo 'Corrupt archive was incorrectly accepted' >&2; exit 1
fi
echo 'Synthetic restore and corruption rejection passed.'
