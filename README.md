# GrooveMap PostgreSQL

`ghcr.io/groovemap-music/postgres` is the one PostgreSQL image GrooveMap runs: the official
`postgres:18-alpine` image, unmodified, with [pgvector](https://github.com/pgvector/pgvector)
added. `pg_stat_statements` already ships with PostgreSQL. The same image runs in the dedicated
stack in [groovemap-music/deployment](https://github.com/groovemap-music/deployment) and on a
shared PostgreSQL server that hosts GrooveMap alongside other databases.

## Why it exists

database-schema's vector schema (ADR 0013: `public.artist_embeddings` and the `embedding_pipeline`
role) installs only where pgvector does, and the official image doesn't ship it. The
`pgvector/pgvector` images are Debian (glibc). GrooveMap databases use the libc collation provider
with `en_US.UTF-8`, and glibc and musl order text differently, so a data directory created under
`postgres:18-alpine` would need a full `REINDEX` under them. This image keeps the Alpine base, so the
order of every existing text index is unchanged.

## What is pinned

The Dockerfile is the lock file:

- the base, `postgres:18-alpine`, by manifest digest. It matches the digest deployment reviews for
  its `postgres` service. Dependabot bumps the digest.
- pgvector, by release tag, checked against that tag's commit during the build. A moved tag fails
  the build.

`just check` refuses a Dockerfile that drops either pin, leaves the base, or adds a second build
stage or layer. The base's PostgreSQL release is in the version: `v18.6.0` is PostgreSQL 18.6, and
the last number is this repository's own revision for that release (a base digest or pgvector bump).

## Using it

A server running this image needs:

```text
shared_preload_libraries = 'pg_stat_statements'
pg_stat_statements.track_utility = off   # keeps ALTER ROLE ... PASSWORD out of pg_stat_statements
```

A superuser creates the extensions in the GrooveMap database:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

GrooveMap's role needs no `pg_read_all_stats`. Every GrooveMap service connects as that one login,
and a role sees the full text of its own statements; on a shared server the grant would also show
it other tenants' query text. Turning `track_utility` off does not purge statements already stored,
so afterwards a superuser removes any role-password entries and rotates those passwords:

```sql
SELECT pg_stat_statements_reset(userid, dbid, queryid)
FROM pg_stat_statements WHERE query ~* '\m(password|encrypted)\M';
```

Swapping the image of an existing `postgres:18-alpine` server is an image change only: the data
directory, PostgreSQL release and collation stay the same. `just collation-proof` shows this (below).

## Development

```bash
mise install
just setup
just check            # offline: formatting, lint, the Dockerfile pin policy, types, tests
just image            # build locally (never pushed) and smoke-test a disposable container
just collation-proof  # needs `just image` first; proves collation is unchanged
just release-dry-run  # release evidence in dist/, without publishing
```

`just image` initialises a cluster the way GrooveMap's servers are initialised (libc,
`en_US.UTF-8`). It checks that `vector` and `pg_stat_statements` install, that an HNSW index builds
and answers queries, and that `track_utility=off` keeps `ALTER ROLE ... PASSWORD` out of
`pg_stat_statements`. It also checks that text is ordered by musl's rules, that pgvector's license is
in the image, and that no compiler or git is left behind.

`just collation-proof` initialises a data directory and builds text indexes under the pinned base,
then opens that same directory with the new image. It compares sort order, `lower()` order and index
order over 50,000 mixed-script strings, and runs `amcheck` (`bt_index_parent_check` with
`heapallindexed`). As a control it loads the same rows into Debian's glibc `postgres:18`, whose order
must differ; that shows the probe can detect a collation change.

## Releasing

A pushed `v*` tag runs `.github/workflows/release.yml`, which calls automation's reusable release
workflow. That workflow validates the tag, publishes `ghcr.io/groovemap-music/postgres:<tag>` with
BuildKit SBOM and provenance, and attests the image and the release evidence (`dist/`). Tags must
equal `v` + the `pyproject.toml` version. Tagging needs operator approval.

After a release, deployment and the shared server each review the published digest and pin it.

## License

MIT, see [LICENSE](LICENSE). PostgreSQL and pgvector are under the PostgreSQL License, see
[NOTICE](NOTICE).
