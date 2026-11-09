"""The Dockerfile pin policy and the release evidence written from it."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import image_inputs


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text()


def test_the_repository_dockerfile_passes() -> None:
    inputs = image_inputs.check(ROOT)
    assert inputs.base_repository == "postgres"
    assert inputs.base_tag == "18-alpine"
    assert inputs.pgvector_version.startswith("v0.8.")


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("postgres:18-alpine@sha256:", "postgres:18@sha256:", "Alpine"),
        ("postgres:18-alpine@sha256:", "postgres:17-alpine@sha256:", "PostgreSQL 18"),
        ("postgres:18-alpine@sha256:", "pgvector/pgvector:18-alpine@sha256:", "official postgres"),
        ("FROM postgres:18-alpine@sha256:", "FROM postgres:18-alpine #sha256:", "FROM must pin"),
        ("ARG PGVECTOR_VERSION=v0.8.7", "ARG PGVECTOR_VERSION=master", "release tag"),
        ("ARG PGVECTOR_COMMIT=f37c13f68b57d2c3472b2214fbcff699d6d34876", "ARG PGVECTOR_COMMIT=f37c13f", "40-character"),
    ],
)
def test_a_loosened_pin_is_refused(old: str, new: str, message: str) -> None:
    assert old in DOCKERFILE
    with pytest.raises(AssertionError, match=message):
        image_inputs.parse(DOCKERFILE.replace(old, new))


def test_a_second_stage_is_refused() -> None:
    with pytest.raises(AssertionError, match="one stage"):
        image_inputs.parse("FROM alpine:3.24@sha256:" + "0" * 64 + "\n" + DOCKERFILE)


@pytest.mark.parametrize(
    ("old", "message"),
    [
        ('test "$(git -C /tmp/pgvector rev-parse HEAD)" = "${PGVECTOR_COMMIT}"', "verified against PGVECTOR_COMMIT"),
        ('OPTFLAGS=""', "march=native"),
        ("apk del --no-network .pgvector-build-deps", "removed in the same layer"),
        ("rm -rf /tmp/pgvector", "source is removed"),
        ("install -D -m 0644 /tmp/pgvector/LICENSE /usr/local/share/licenses/pgvector/LICENSE", "license ships"),
    ],
)
def test_a_weakened_build_recipe_is_refused(old: str, message: str) -> None:
    assert old in DOCKERFILE
    with pytest.raises(AssertionError, match=message):
        image_inputs.check_build_recipe(DOCKERFILE.replace(old, "true"))


def test_a_second_run_layer_is_refused() -> None:
    with pytest.raises(AssertionError, match="exactly one RUN"):
        image_inputs.check_build_recipe(DOCKERFILE + "\nRUN apk del git\n")


def test_versions_carry_the_postgres_release() -> None:
    assert image_inputs.postgres_version("v18.6.0") == "18.6"
    assert image_inputs.postgres_version("18.10.3") == "18.10"
    with pytest.raises(AssertionError):
        image_inputs.postgres_version("v1.0")


def _copy_repo(tmp_path: Path, version: str = "18.6.0") -> Path:
    shutil.copy(ROOT / "Dockerfile", tmp_path / "Dockerfile")
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "x"\nversion = "{version}"\n')
    return tmp_path


def test_the_release_version_must_match_a_pushed_tag(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    assert image_inputs.release_version(root) == "v18.6.0"
    assert image_inputs.release_version(root, ref_name="v18.6.0") == "v18.6.0"
    assert image_inputs.release_version(root, ref_name="main") == "v18.6.0"
    with pytest.raises(AssertionError, match="does not match"):
        image_inputs.release_version(root, ref_name="v18.6.1")


def test_release_writes_checksummed_evidence(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    paths = image_inputs.release("v18.6.0", root)
    assert [path.name for path in paths] == ["image-inputs.json", "THIRD_PARTY_NOTICES.json", "sbom.json"]
    record = json.loads((root / "dist/image-inputs.json").read_text())
    inputs = image_inputs.check(ROOT)
    assert record["postgres"] == "18.6"
    assert record["base_reference"] == inputs.base_reference
    assert record["pgvector_commit"] == inputs.pgvector_commit
    sbom = json.loads((root / "dist/sbom.json").read_text())
    assert sbom["bomFormat"] == "CycloneDX"
    assert {component["name"] for component in sbom["components"]} == {"docker.io/library/postgres", "pgvector"}
    notices = json.loads((root / "dist/THIRD_PARTY_NOTICES.json").read_text())
    assert all(component["license"] == "PostgreSQL" for component in notices["components"])
    for line in (root / "dist/SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((root / "dist" / name).read_bytes()).hexdigest() == digest
    # Deterministic: the same inputs give byte-identical evidence.
    first = (root / "dist/SHA256SUMS").read_text()
    image_inputs.release("v18.6.0", root)
    assert (root / "dist/SHA256SUMS").read_text() == first


def test_main(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert image_inputs.main(["check"]) == 0
    assert "pgvector" in capsys.readouterr().out
    assert image_inputs.main(["base"]) == 0
    assert capsys.readouterr().out.startswith("postgres:18-alpine@sha256:")
    assert image_inputs.main([]) == 2
    assert image_inputs.main(["baseline", "no-such-ref"]) == 0
    assert capsys.readouterr().out.startswith("postgres:18-alpine@sha256:")
    capsys.readouterr()
    assert image_inputs.main(["postgres-version"]) == 0
    assert capsys.readouterr().out.strip().startswith("18.")
    root = _copy_repo(tmp_path)
    monkeypatch.setattr(image_inputs, "ROOT", root)
    monkeypatch.setattr(image_inputs, "release", lambda version, root=root: [root / "dist" / version])
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    assert image_inputs.main(["release"]) == 0
    assert capsys.readouterr().out.strip() == "dist/v18.6.0"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)  # noqa: S603, S607


def test_the_baseline_is_the_base_the_ref_pins(tmp_path: Path) -> None:
    root = _copy_repo(tmp_path)
    released = image_inputs.check(root).base_reference
    _git(root, "init", "-q", "-b", "main")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "base")
    _git(root, "add", "Dockerfile")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "released")
    bumped = "f" * 64
    (root / "Dockerfile").write_text((root / "Dockerfile").read_text().replace(image_inputs.check(root).base_digest, bumped))
    # A Dependabot bump is proven against the base main released, not against itself.
    assert image_inputs.baseline(root, ref="main") == released
    assert image_inputs.check(root).base_digest == bumped
    # A ref that does not exist falls back to this Dockerfile's base.
    assert image_inputs.baseline(root, ref="no-such-ref").endswith(bumped)
