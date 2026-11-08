# Repository instructions

- This repository publishes one image, ghcr.io/groovemap-music/postgres: the official
  postgres:18-alpine plus pgvector. Add nothing else to it without an operator decision.
- Stay on Alpine (musl) and PostgreSQL 18. GrooveMap databases use the libc collation provider with
  en_US.UTF-8; a glibc base or a major upgrade changes text ordering and is a migration, not a bump.
- The Dockerfile is the lock file: the base by manifest digest, pgvector by tag and commit.
  `just check` refuses a loosened pin.
- Run `just check` before proposing a change, and `just image` plus `just collation-proof` for any
  change to the Dockerfile.
- Tagging, publishing and releasing need operator approval. Publication happens only through the
  tag-gated release workflow; never push an image by hand.
