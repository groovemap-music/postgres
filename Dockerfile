# syntax=docker/dockerfile:1@sha256:bde3983e9c939224420ddaf6b784cc30e09b035a4dea01f581230c50809f372e
#
# GrooveMap PostgreSQL: the official postgres:18-alpine image, unmodified, plus pgvector.
#
# It stays on Alpine (musl) on purpose. GrooveMap databases use the libc collation provider with
# en_US.UTF-8, and musl and glibc order text differently, so moving to a Debian-based pgvector
# image would silently change the order of every text index and need a full REINDEX. This image
# keeps the base's musl, so a data directory initialised under postgres:18-alpine reads unchanged.
#
# The base is pinned by the manifest digest groovemap-music/deployment reviewed for its postgres
# service; Dependabot's docker ecosystem bumps the tag and digest together.
FROM postgres:18-alpine@sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873

# pgvector, built from source at a release tag and verified against that tag's commit, so a moved
# tag fails the build instead of shipping different code. OPTFLAGS="" drops pgvector's default
# -march=native, which would tie the binary to the build host's CPU. clang21/llvm21 match the
# base's own JIT toolchain (CLANG = clang-21 in its pgxs Makefile.global), so the bitcode it
# installs for JIT inlining is readable. Build tools are added and removed in the same layer.
ARG PGVECTOR_VERSION=v0.8.7
ARG PGVECTOR_COMMIT=f37c13f68b57d2c3472b2214fbcff699d6d34876

RUN apk add --no-cache --virtual .pgvector-build-deps git build-base clang21 llvm21 \
    && git clone --quiet --depth 1 --branch "${PGVECTOR_VERSION}" https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && test "$(git -C /tmp/pgvector rev-parse HEAD)" = "${PGVECTOR_COMMIT}" \
    && make -C /tmp/pgvector OPTFLAGS="" \
    && make -C /tmp/pgvector install \
    && install -D -m 0644 /tmp/pgvector/LICENSE /usr/local/share/licenses/pgvector/LICENSE \
    && rm -rf /tmp/pgvector \
    && apk del --no-network .pgvector-build-deps

ARG BUILD_DATE
ARG VCS_REF
ARG VERSION

LABEL org.opencontainers.image.title="groovemap-postgres" \
      org.opencontainers.image.description="Official postgres:18-alpine with pgvector, for GrooveMap" \
      org.opencontainers.image.licenses="MIT AND PostgreSQL" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="${VERSION}" \
      io.groovemap.pgvector.version="${PGVECTOR_VERSION}" \
      io.groovemap.pgvector.commit="${PGVECTOR_COMMIT}"
