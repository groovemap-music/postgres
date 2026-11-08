set shell := ["bash", "-euo", "pipefail", "-c"]

image_tag := "groovemap-postgres:local"

default:
    @just --list

setup:
    uv sync --dev --frozen

format:
    uv run ruff format .

format-check:
    uv run ruff format --check .

lint:
    uv run ruff check .
    uv run python scripts/image_inputs.py check

typecheck:
    uv run mypy

test:
    uv run pytest --cov --cov-report=term-missing --cov-report=xml

coverage: test

# Offline and credential-free: formatting, lint, the Dockerfile pin policy, types and tests.
check: format-check lint typecheck test

audit:
    uv run pip-audit

# Python dev tooling only; the image's own components are recorded in dist/THIRD_PARTY_NOTICES.json.
license-check:
    uv run pip-licenses --fail-on "GPL-2.0-only;GPL-3.0-only;AGPL-3.0-only"

secret-scan:
    gitleaks git --redact --no-banner
    gitleaks dir . --redact --no-banner

# The release evidence (inputs record, notices, SBOM, SHA256SUMS) without building or publishing.
build:
    uv run python scripts/image_inputs.py release

# Builds the image locally (never pushed) and smoke-tests it on a disposable container.
image:
    IMAGE={{image_tag}} bash scripts/smoke-image.sh

install-check: image

# Opens a data directory initialised under the pinned base with the locally built image and proves
# text ordering and amcheck are unchanged. Needs Docker and `just image` first; disposable.
collation-proof:
    IMAGE={{image_tag}} bash scripts/collation-proof.sh

release-dry-run: check build
    cd dist && sha256sum --check SHA256SUMS 2>/dev/null || shasum -a 256 --check SHA256SUMS
