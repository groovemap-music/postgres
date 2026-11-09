#!/usr/bin/env bash
# Proves the image leaves collation unchanged: initialises a cluster and builds text indexes under
# the base image main pins (the released one; on a base bump, the previous base), then opens the SAME data directory under the new image and
# compares text ordering (sort, lower(), index order) and runs amcheck with heapallindexed. As a
# control it loads the same rows into Debian's glibc postgres:18, whose ordering must differ, so
# the probe is shown to tell the two libcs apart. Disposable: removes its containers and volume.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
# The proof starts from the base main already pins (COLLATION_BASELINE_REF), so a base bump is read
# against the previous base, not against itself. On main, or without that ref, it is the current base.
old="${BASELINE_IMAGE:-$(python3 "${root}/scripts/image_inputs.py" baseline "${COLLATION_BASELINE_REF:-origin/main}")}"
new="${IMAGE:-groovemap-postgres:local}"
control="${CONTROL_IMAGE:-postgres:18}"
out="${COLLATION_PROOF_DIR:-${root}/dist/collation-proof}"
volume="groovemap-postgres-collation-$$"
mkdir -p "${out}"

cleanup() {
    docker rm --force --volumes "${volume}-old" "${volume}-new" "${volume}-control" >/dev/null 2>&1 || true
    docker volume rm --force "${volume}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

start() {
    local name=$1 image=$2
    shift 2
    docker run --detach --name "${name}" --env POSTGRES_PASSWORD=probe --env POSTGRES_DB=groovemap \
        --env POSTGRES_INITDB_ARGS="--locale-provider=libc --locale=en_US.UTF-8" "$@" "${image}" >/dev/null
    for _ in $(seq 90); do
        docker exec "${name}" psql -U postgres -d groovemap -Atc 'SELECT 1' >/dev/null 2>&1 && return 0
        sleep 1
    done
    docker logs "${name}" >&2
    return 1
}
run_sql() { docker exec -i "$1" psql -X -v ON_ERROR_STOP=1 -U postgres -d groovemap -q; }
data=(--volume "${volume}:/var/lib/postgresql/data" --env PGDATA=/var/lib/postgresql/data/pgdata)

echo "== ${old}: initdb, load, index"
start "${volume}-old" "${old}" "${data[@]}"
run_sql "${volume}-old" < "${root}/sql/collation-seed.sql"
run_sql "${volume}-old" < "${root}/sql/collation-probe.sql" | tee "${out}/old.txt"
docker stop --timeout 30 "${volume}-old" >/dev/null

echo "== ${new}: the same data directory"
start "${volume}-new" "${new}" "${data[@]}"
run_sql "${volume}-new" < "${root}/sql/collation-probe.sql" | tee "${out}/new.txt"

echo "== control ${control}: the same rows on glibc"
start "${volume}-control" "${control}"
run_sql "${volume}-control" < "${root}/sql/collation-seed.sql"
run_sql "${volume}-control" < "${root}/sql/collation-probe.sql" | tee "${out}/control.txt"

if ! diff <(grep -v '^server=' "${out}/old.txt") <(grep -v '^server=' "${out}/new.txt"); then
    echo "FAIL: ordering or index checks differ between ${old} and ${new}" >&2
    exit 1
fi
if diff -q <(grep _md5= "${out}/old.txt") <(grep _md5= "${out}/control.txt") >/dev/null; then
    echo "FAIL: the glibc control ordered text like musl, so this probe cannot detect a collation change" >&2
    exit 1
fi
echo "ok: collation unchanged from ${old}; amcheck clean; the glibc control differs as expected"
