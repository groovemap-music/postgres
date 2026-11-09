# Changelog

## v18.6.1

- Base image bumped to postgres:18-alpine@sha256:123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395
  (Alpine 3.24.4; still PostgreSQL 18.6), from 77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873
  (Alpine 3.24.2). pgvector v0.8.7 unchanged. The collation proof ran against the previous base: indexes built
  under 77f5851 read identically under the new image and amcheck is clean, so an existing data directory needs
  no REINDEX. The collation proof now always baselines on the base main pins (27b1c26).

## v18.6.0

- First release: the official postgres:18-alpine (PostgreSQL 18.6, Alpine 3.24,
  sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873) plus pgvector v0.8.7
  (f37c13f68b57d2c3472b2214fbcff699d6d34876), built from source with the base's clang-21 toolchain.
