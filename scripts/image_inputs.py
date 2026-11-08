"""Read, check and record the pinned inputs of the GrooveMap PostgreSQL image.

The Dockerfile is this repository's lock file: it pins the official postgres:18-alpine base by
manifest digest and pgvector by release tag and commit. `check` refuses a Dockerfile that loosens
any of those pins; `release` writes the release evidence the reusable release workflow attests
(the inputs record, a third-party notice, a CycloneDX SBOM and SHA256SUMS) from the same values.

Standard library only, so `just check` needs nothing but Python.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# The base must stay the official Alpine (musl) PostgreSQL 18 image: GrooveMap databases use the libc
# collation provider with en_US.UTF-8, and a glibc base would reorder every text index.
BASE_REPOSITORY = "postgres"
BASE_TAG = re.compile(r"18(?:\.\d+)?-alpine(?:3\.\d+)?")
FROM_LINE = re.compile(r"^FROM\s+(?P<repository>[^\s:@]+):(?P<tag>[^\s@]+)@sha256:(?P<digest>[0-9a-f]{64})\s*$", re.MULTILINE)
ARG_LINE = re.compile(r"^ARG\s+(?P<name>[A-Z_]+)=(?P<value>\S+)\s*$", re.MULTILINE)
PGVECTOR_TAG = re.compile(r"v\d+\.\d+\.\d+")
COMMIT = re.compile(r"[0-9a-f]{40}")
VERSION = re.compile(r"v?(?P<postgres>\d+\.\d+)\.(?P<revision>\d+)")


@dataclass(frozen=True)
class ImageInputs:
    base_repository: str
    base_tag: str
    base_digest: str
    pgvector_version: str
    pgvector_commit: str

    @property
    def base_reference(self) -> str:
        return f"{self.base_repository}:{self.base_tag}@sha256:{self.base_digest}"


def parse(dockerfile: str) -> ImageInputs:
    """The pinned inputs, or an AssertionError naming the first missing or loosened pin."""
    froms = list(FROM_LINE.finditer(dockerfile))
    stages = re.findall(r"^FROM\s", dockerfile, re.MULTILINE)
    assert len(stages) == 1, f"the image is one stage FROM the official base; found {len(stages)} FROM lines"
    assert froms, "FROM must pin repository:tag@sha256:<digest>"
    base = froms[0]
    assert base["repository"] == BASE_REPOSITORY, f"the base must be the official {BASE_REPOSITORY} image, not {base['repository']}"
    assert BASE_TAG.fullmatch(base["tag"]), f"the base tag must be PostgreSQL 18 on Alpine (musl), not {base['tag']}"
    args = {match["name"]: match["value"] for match in ARG_LINE.finditer(dockerfile)}
    version = args.get("PGVECTOR_VERSION", "")
    commit = args.get("PGVECTOR_COMMIT", "")
    assert PGVECTOR_TAG.fullmatch(version), f"PGVECTOR_VERSION must be a release tag vX.Y.Z, not {version!r}"
    assert COMMIT.fullmatch(commit), f"PGVECTOR_COMMIT must be a full 40-character commit, not {commit!r}"
    return ImageInputs(BASE_REPOSITORY, base["tag"], base["digest"], version, commit)


def check_build_recipe(dockerfile: str) -> None:
    """The pgvector build verifies the commit, stays portable, and leaves no toolchain behind."""
    runs = [block for block in re.split(r"\n(?=[A-Z]+\s)", dockerfile) if block.startswith("RUN ")]
    assert len(runs) == 1, f"pgvector is built in exactly one RUN layer; found {len(runs)}"
    run = runs[0]
    assert '--branch "${PGVECTOR_VERSION}"' in run, "pgvector must be cloned at PGVECTOR_VERSION"
    assert 'rev-parse HEAD)" = "${PGVECTOR_COMMIT}"' in run, "the clone must be verified against PGVECTOR_COMMIT"
    assert 'OPTFLAGS=""' in run, 'pgvector must build with OPTFLAGS="" (no -march=native)'
    assert "apk add --no-cache --virtual .pgvector-build-deps" in run, "build tools are one virtual package"
    assert "apk del --no-network .pgvector-build-deps" in run, "build tools are removed in the same layer"
    assert "rm -rf /tmp/pgvector" in run, "the pgvector source is removed in the same layer"
    assert "/usr/local/share/licenses/pgvector/LICENSE" in run, "pgvector's license ships in the image"


def check(root: Path = ROOT) -> ImageInputs:
    dockerfile = (root / "Dockerfile").read_text()
    inputs = parse(dockerfile)
    check_build_recipe(dockerfile)
    return inputs


def postgres_version(version: str) -> str:
    """The PostgreSQL major.minor a release version carries: v18.6.0 -> 18.6."""
    match = VERSION.fullmatch(version)
    assert match, f"a release version is vMAJOR.MINOR.REVISION, with MAJOR.MINOR the PostgreSQL release: {version!r}"
    return match["postgres"]


def notices(inputs: ImageInputs) -> dict[str, object]:
    return {
        "image": "ghcr.io/groovemap-music/postgres",
        "license": "MIT",
        "components": [
            {
                "name": "PostgreSQL (official Docker image)",
                "source": f"docker.io/library/{inputs.base_reference}",
                "license": "PostgreSQL",
                "note": "Unmodified base image; its Alpine packages keep their own licenses (see the image's BuildKit SBOM).",
            },
            {
                "name": "pgvector",
                "source": f"https://github.com/pgvector/pgvector/tree/{inputs.pgvector_commit}",
                "version": inputs.pgvector_version,
                "license": "PostgreSQL",
                "license_file": "/usr/local/share/licenses/pgvector/LICENSE",
            },
        ],
    }


def sbom(inputs: ImageInputs, version: str) -> dict[str, object]:
    """A CycloneDX 1.6 SBOM of the inputs this repository adds; BuildKit's SBOM covers the full image."""
    serial = hashlib.sha256(f"{version}:{inputs.base_digest}:{inputs.pgvector_commit}".encode()).hexdigest()
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial[:8]}-{serial[8:12]}-{serial[12:16]}-{serial[16:20]}-{serial[20:32]}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "container",
                "name": "ghcr.io/groovemap-music/postgres",
                "version": version,
                "licenses": [{"license": {"id": "MIT"}}],
            }
        },
        "components": [
            {
                "type": "container",
                "name": "docker.io/library/postgres",
                "version": inputs.base_tag,
                "hashes": [{"alg": "SHA-256", "content": inputs.base_digest}],
                "purl": f"pkg:docker/library/postgres@sha256%3A{inputs.base_digest}?tag={inputs.base_tag}",
                "licenses": [{"license": {"id": "PostgreSQL"}}],
            },
            {
                "type": "library",
                "name": "pgvector",
                "version": inputs.pgvector_version.removeprefix("v"),
                "purl": f"pkg:github/pgvector/pgvector@{inputs.pgvector_version}",
                "licenses": [{"license": {"id": "PostgreSQL"}}],
                "externalReferences": [{"type": "vcs", "url": f"https://github.com/pgvector/pgvector/commit/{inputs.pgvector_commit}"}],
            },
        ],
    }


def release(version: str, root: Path = ROOT, dist: Path | None = None) -> list[Path]:
    """Write the release evidence into dist/ and return the files SHA256SUMS covers."""
    inputs = check(root)
    record = {"version": version, "postgres": postgres_version(version), "base_reference": inputs.base_reference, **asdict(inputs)}
    out = dist or root / "dist"
    out.mkdir(parents=True, exist_ok=True)
    written = {
        "image-inputs.json": record,
        "THIRD_PARTY_NOTICES.json": notices(inputs),
        "sbom.json": sbom(inputs, version),
    }
    paths = []
    for name, content in written.items():
        path = out / name
        path.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n")
        paths.append(path)
    sums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in paths)
    (out / "SHA256SUMS").write_text(sums)
    return paths


def release_version(root: Path = ROOT, ref_name: str | None = None) -> str:
    """The release version: pyproject's, which a pushed tag (GITHUB_REF_NAME) must equal."""
    version = "v" + tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    postgres_version(version)
    if ref_name and ref_name.startswith("v"):
        assert ref_name == version, f"tag {ref_name} does not match pyproject version {version}"
    return version


def main(argv: list[str]) -> int:
    if argv[:1] == ["check"]:
        inputs = check()
        print(f"ok: {inputs.base_reference} + pgvector {inputs.pgvector_version} ({inputs.pgvector_commit})")
        return 0
    if argv == ["release"]:
        for path in release(release_version(ref_name=os.environ.get("GITHUB_REF_NAME"))):
            print(path.relative_to(ROOT))
        return 0
    if argv[:1] == ["base"]:
        print(check().base_reference)
        return 0
    if argv == ["postgres-version"]:
        print(postgres_version(release_version()))
        return 0
    print("usage: image_inputs.py check | base | postgres-version | release", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
