"""REQ-F11-270/REQ-F11-310 corresponding-source preparation contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PREPARE = REPOSITORY_ROOT / "scripts/prepare_action_runtime_sources.py"
VEX = REPOSITORY_ROOT / "action/runtime-components.openvex.json"
RUNTIME_SOURCES = REPOSITORY_ROOT / "action/runtime-sources.json"


def _archive(path: Path, root: str, licence: bytes, *, unsafe: bool = False) -> None:
    payload = path.parent / "COPYING"
    payload.write_bytes(licence)
    with tarfile.open(path, mode="w:xz") as archive:
        archive.add(payload, arcname=("../COPYING" if unsafe else f"{root}/COPYING"))


def _digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    value.update(path.read_bytes())
    return value.hexdigest()


def _manifest(tmp_path: Path, *, unsafe: bool = False) -> Path:
    git = tmp_path / "git.tar.xz"
    curl = tmp_path / "curl.tar.xz"
    _archive(git, "git-2.52.0", b"git licence\n", unsafe=unsafe)
    _archive(curl, "curl-8.23.0", b"curl licence\n")
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "components": [
            {
                "name": "git",
                "version": "2.52.0",
                "archive": {
                    "filename": "git-2.52.0.tar.xz",
                    "url": git.as_uri(),
                    "digest": {"algorithm": "sha256", "value": _digest(git, "sha256")},
                },
                "sourceRoot": "git-2.52.0",
                "licence": {
                    "archivePath": "COPYING",
                    "spdx": "GPL-2.0-only",
                    "runtimePath": "/usr/share/licenses/git/COPYING",
                },
                "purl": "pkg:generic/git@2.52.0",
                "cpe": "cpe:2.3:a:git-scm:git:2.52.0:*:*:*:*:*:*:*",
            },
            {
                "name": "curl",
                "version": "8.23.0",
                "archive": {
                    "filename": "curl-8.23.0.tar.xz",
                    "url": curl.as_uri(),
                    "digest": {"algorithm": "sha512", "value": _digest(curl, "sha512")},
                },
                "sourceRoot": "curl-8.23.0",
                "licence": {
                    "archivePath": "COPYING",
                    "spdx": "curl",
                    "runtimePath": "/usr/share/licenses/curl/COPYING",
                },
                "purl": "pkg:generic/curl@8.23.0",
                "cpe": "cpe:2.3:a:haxx:curl:8.23.0:*:*:*:*:*:*:*",
            },
        ],
    }
    manifest = tmp_path / "runtime-sources.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    return manifest


def _run(manifest: Path, recipe: Path, destination: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(PREPARE),
            str(destination),
            "--manifest",
            str(manifest),
            "--recipe",
            str(recipe),
            "--vex",
            str(VEX),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.ac("AC-F11-310")
def test_repository_manifest_pins_only_the_fixed_curl_source() -> None:
    encoded = RUNTIME_SOURCES.read_text(encoding="utf-8")
    manifest = json.loads(encoded)
    curl = next(component for component in manifest["components"] if component["name"] == "curl")

    assert curl == {
        "name": "curl",
        "version": "8.23.0",
        "archive": {
            "filename": "curl-8.23.0.tar.xz",
            "url": "https://curl.se/download/curl-8.23.0.tar.xz",
            "digest": {
                "algorithm": "sha512",
                "value": (
                    "69cf0feafdc79fbad007cf2fc977b777ce6ccb05d01afd17b5a42f8bedbfcc342"
                    "fc3a48193faa7f3eafe6800cd7d07948916e8733db1b9de60287ed06219b840"
                ),
            },
        },
        "sourceRoot": "curl-8.23.0",
        "licence": {
            "archivePath": "COPYING",
            "spdx": "curl",
            "runtimePath": "/usr/share/licenses/curl/COPYING",
        },
        "purl": "pkg:generic/curl@8.23.0",
        "cpe": "cpe:2.3:a:haxx:curl:8.23.0:*:*:*:*:*:*:*",
    }
    assert "8.22.0" not in encoded


@pytest.mark.ac("AC-F11-270")
@pytest.mark.ac("AC-F11-310")
def test_runtime_sources_are_hash_locked_complete_and_deterministic(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    recipe = tmp_path / "Dockerfile"
    recipe.write_text("FROM scratch\n", encoding="utf-8")
    first = tmp_path / "first"
    second = tmp_path / "second"

    completed = _run(manifest, recipe, first)
    repeated = _run(manifest, recipe, second)

    assert completed.returncode == 0, completed.stderr
    assert repeated.returncode == 0, repeated.stderr
    expected = {
        "Dockerfile",
        "SOURCE-MANIFEST.json",
        "curl-8.23.0.tar.xz",
        "curl-COPYING",
        "git-2.52.0.tar.xz",
        "git-COPYING",
        "runtime-components.spdx.json",
        "runtime-components.openvex.json",
        "runtime-sources.json",
    }
    assert {path.name for path in first.iterdir()} == expected
    assert {path.name: path.read_bytes() for path in first.iterdir()} == {
        path.name: path.read_bytes() for path in second.iterdir()
    }
    assert (first / "git-COPYING").read_bytes() == b"git licence\n"
    assert (first / "curl-COPYING").read_bytes() == b"curl licence\n"
    source_manifest = json.loads((first / "SOURCE-MANIFEST.json").read_text(encoding="utf-8"))
    assert source_manifest["schemaVersion"] == 1
    assert {entry["path"] for entry in source_manifest["files"]} == expected - {
        "SOURCE-MANIFEST.json"
    }
    sbom = json.loads((first / "runtime-components.spdx.json").read_text(encoding="utf-8"))
    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert {
        (package["name"], package["versionInfo"], package["licenseConcluded"])
        for package in sbom["packages"]
    } == {
        ("curl", "8.23.0", "curl"),
        ("git", "2.52.0", "GPL-2.0-only"),
    }
    assert all(len(package["externalRefs"]) == 2 for package in sbom["packages"])
    assert (first / "runtime-components.openvex.json").read_bytes() == VEX.read_bytes()


@pytest.mark.ac("AC-F11-270")
def test_runtime_source_hash_mismatch_fails_before_extraction(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["components"][0]["archive"]["digest"]["value"] = "0" * 64
    manifest.write_text(json.dumps(document), encoding="utf-8")
    recipe = tmp_path / "Dockerfile"
    recipe.write_text("FROM scratch\n", encoding="utf-8")
    destination = tmp_path / "output"

    completed = _run(manifest, recipe, destination)

    assert completed.returncode == 1
    assert "git archive digest mismatch" in completed.stderr
    assert not destination.exists()


@pytest.mark.ac("AC-F11-270")
def test_runtime_source_licence_extraction_rejects_unsafe_archive(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, unsafe=True)
    recipe = tmp_path / "Dockerfile"
    recipe.write_text("FROM scratch\n", encoding="utf-8")
    destination = tmp_path / "output"

    completed = _run(manifest, recipe, destination)

    assert completed.returncode == 1
    assert "git archive contains an unsafe member" in completed.stderr
    assert not destination.exists()
