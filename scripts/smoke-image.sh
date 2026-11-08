#!/usr/bin/env bash
# Builds the image locally (never pushed) and asserts what GrooveMap relies on, on a fresh cluster
# initialised the way GrooveMap's servers are (libc provider, en_US.UTF-8):
# pgvector and pg_stat_statements install and work, track_utility=off keeps utility statements
# (ALTER ROLE ... PASSWORD) out of pg_stat_statements, text orders by musl's rules, pgvector's
# license ships, and no build toolchain is left behind. Removes its container on every exit.
set -euo pipefail

image="${IMAGE:-groovemap-postgres:local}"
container="groovemap-postgres-smoke-$$"
cleanup() { docker rm --force --volumes "${container}" >/dev/null 2>&1 || true; }
trap cleanup EXIT

if [[ "${SKIP_BUILD:-}" != 1 ]]; then
    docker build --tag "${image}" --build-arg VERSION="local" .
fi

docker run --detach --name "${container}" \
    --env POSTGRES_PASSWORD=smoke --env POSTGRES_DB=groovemap \
    --env POSTGRES_INITDB_ARGS="--locale-provider=libc --locale=en_US.UTF-8" \
    "${image}" -c shared_preload_libraries=pg_stat_statements -c pg_stat_statements.track_utility=off >/dev/null

for _ in $(seq 60); do
    docker exec "${container}" psql -U postgres -d groovemap -Atc 'SELECT 1' >/dev/null 2>&1 && break
    sleep 1
done

# The release version's MAJOR.MINOR is the PostgreSQL release the base actually ships.
want_postgres="$(python3 scripts/image_inputs.py postgres-version)"
have_postgres="$(docker exec "${container}" psql -U postgres -d groovemap -Atc 'SHOW server_version' | cut -d' ' -f1)"
if [[ "${have_postgres}" != "${want_postgres}" ]]; then
    echo "the image runs PostgreSQL ${have_postgres}, but pyproject's version says ${want_postgres}" >&2
    exit 1
fi

actual="$(docker exec -i "${container}" psql -X -v ON_ERROR_STOP=1 -U postgres -d groovemap -Atq <<'SQL'
SELECT string_agg(name, ',' ORDER BY name) FROM pg_available_extensions WHERE name IN ('vector', 'pg_stat_statements');
CREATE EXTENSION vector;
CREATE EXTENSION pg_stat_statements;
SELECT '[1,2,3]'::vector <-> '[1,2,5]'::vector;
CREATE TABLE smoke (id int, embedding vector(3));
INSERT INTO smoke SELECT g, ARRAY[g, g * 2, g % 7]::real[]::vector FROM generate_series(1, 500) g;
CREATE INDEX ON smoke USING hnsw (embedding vector_cosine_ops);
SET enable_seqscan = off;
SELECT count(*) FROM (SELECT id FROM smoke ORDER BY embedding <=> '[3,1,2]' LIMIT 5) nearest;
SELECT current_setting('pg_stat_statements.track_utility');
ALTER ROLE postgres PASSWORD 'never-recorded';
SELECT count(*) FROM pg_stat_statements WHERE query ILIKE '%never-recorded%' OR query ILIKE '%ALTER ROLE%';
SELECT datlocprovider::text || ' ' || datcollate FROM pg_database WHERE datname = current_database();
SELECT ('a' < 'B')::text || ' ' || ('Z' < 'a')::text || ' ' || ('é' < 'f')::text;
SQL
)"
expected="pg_stat_statements,vector
2
5
off
0
c en_US.UTF-8
false true false"
if [[ "${actual}" != "${expected}" ]]; then
    printf 'smoke mismatch\n--- expected\n%s\n--- actual\n%s\n' "${expected}" "${actual}" >&2
    exit 1
fi

docker exec "${container}" test -s /usr/local/share/licenses/pgvector/LICENSE
if docker exec "${container}" sh -c 'command -v git || command -v clang-21 || command -v gcc || command -v make'; then
    echo "a build tool was left in the image" >&2
    exit 1
fi
echo "ok: ${image} has pgvector and pg_stat_statements, track_utility off, musl en_US.UTF-8 ordering, no toolchain"
