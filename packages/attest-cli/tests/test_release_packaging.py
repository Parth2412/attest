"""Release-package contract tests for F-11."""

from __future__ import annotations

import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any, Final

import pytest

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
RELEASE_MANIFEST: Final[Path] = REPOSITORY_ROOT / "release/packages.toml"
PRODUCT_VERSION: Final[str] = "0.1.0"
PUBLISHED_PACKAGES: Final[tuple[str, ...]] = (
    "attest-core",
    "attest-collect",
    "attest-sign",
    "attest-store",
    "attest-policy",
    "attest-cli",
)
INTERNAL_DEPENDENCIES: Final[dict[str, tuple[str, ...]]] = {
    "attest-core": (),
    "attest-collect": ("attest-core==0.1.0",),
    "attest-sign": ("attest-core==0.1.0",),
    "attest-store": ("attest-core==0.1.0",),
    "attest-policy": ("attest-core==0.1.0",),
    "attest-cli": (
        "attest-core==0.1.0",
        "attest-collect==0.1.0",
        "attest-sign==0.1.0",
        "attest-store==0.1.0",
        "attest-policy==0.1.0",
    ),
}
PROJECT_URLS: Final[dict[str, str]] = {
    "Homepage": "https://github.com/Parth2412/attest",
    "Documentation": "https://github.com/Parth2412/attest/tree/main/docs",
    "Repository": "https://github.com/Parth2412/attest.git",
    "Issues": "https://github.com/Parth2412/attest/issues",
    "Changelog": "https://github.com/Parth2412/attest/blob/main/CHANGELOG.md",
}


def _toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        value: dict[str, Any] = tomllib.load(stream)
    return value


@pytest.mark.ac("AC-F11-140")
def test_release_package_set_and_metadata_are_closed() -> None:
    """REQ-F11-140: only six metadata-complete, mutually pinned projects ship."""
    release = _toml(RELEASE_MANIFEST)["release"]
    assert release == {
        "version": PRODUCT_VERSION,
        "distributions": list(PUBLISHED_PACKAGES),
    }

    root_license = (REPOSITORY_ROOT / "LICENSE").read_bytes()
    for distribution in PUBLISHED_PACKAGES:
        package_root = REPOSITORY_ROOT / "packages" / distribution
        project = _toml(package_root / "pyproject.toml")["project"]
        assert project["name"] == distribution
        assert project["version"] == PRODUCT_VERSION
        assert project["readme"] == "README.md"
        assert project["license"] == "Apache-2.0"
        assert project["license-files"] == ["LICENSE"]
        assert project["authors"] == [{"name": "Parth (ZettaCore)"}]
        assert project["urls"] == PROJECT_URLS
        assert project["classifiers"] == [
            "Development Status :: 3 - Alpha",
            "Environment :: Console",
            "Operating System :: OS Independent",
            "Programming Language :: Python :: 3 :: Only",
            "Programming Language :: Python :: 3.12",
            "Programming Language :: Python :: 3.13",
            "Typing :: Typed",
        ]
        assert project["keywords"] == [
            "ai",
            "attestation",
            "provenance",
            "sigstore",
            "supply-chain",
        ]
        assert (package_root / "README.md").is_file()
        assert (package_root / "LICENSE").read_bytes() == root_license

        internal = tuple(
            dependency
            for dependency in project.get("dependencies", [])
            if dependency.split("==", maxsplit=1)[0] in PUBLISHED_PACKAGES
            or dependency.startswith("attest-")
        )
        assert internal == INTERNAL_DEPENDENCIES[distribution]

    cli_dependencies = _toml(REPOSITORY_ROOT / "packages/attest-cli/pyproject.toml")["project"][
        "dependencies"
    ]
    assert all(not dependency.startswith("attest-export") for dependency in cli_dependencies)


@pytest.mark.ac("AC-F11-140")
def test_built_release_artifacts_match_the_closed_manifest(tmp_path: Path) -> None:
    """REQ-F11-140: every approved wheel and sdist has validated bytes and hashes."""
    artifact_directory = tmp_path / "dist"
    for index, distribution in enumerate(PUBLISHED_PACKAGES):
        command = [
            "uv",
            "build",
            "--package",
            distribution,
            "--out-dir",
            str(artifact_directory),
            "--no-build-logs",
            "--no-create-gitignore",
        ]
        if index == 0:
            command.append("--clear")
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr

    hashes = tmp_path / "SHA256SUMS"
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/validate_release_artifacts.py"),
            str(artifact_directory),
            "--hash-output",
            str(hashes),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "release artifacts: validated 6 wheels and 6 source distributions\n"
    assert len(hashes.read_text(encoding="utf-8").splitlines()) == 12

    wheel = artifact_directory / "attest_core-0.1.0-py3-none-any.whl"
    changed_wheel = tmp_path / wheel.name
    with zipfile.ZipFile(wheel) as source, zipfile.ZipFile(changed_wheel, mode="w") as changed:
        for member in source.infolist():
            content = source.read(member.filename)
            if member.filename == "attest_core/__init__.py":
                content += b"\n"
            changed.writestr(member, content)
    changed_wheel.replace(wheel)

    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/validate_release_artifacts.py"),
            str(artifact_directory),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "wheel RECORD hash mismatch" in result.stderr
