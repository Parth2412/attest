"""Regression contracts for previously published Python release verification."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PATCH_RELEASE_MANIFEST: Final[Path] = REPOSITORY_ROOT / "release/patches/0.1.3.toml"
PUBLISHED_VERIFIER: Final[Path] = REPOSITORY_ROOT / "scripts/verify_published_release.py"


def _published_fixture(root: Path) -> tuple[Path, Path]:
    artifacts = root / "release-assets"
    index = root / "index" / "pypi"
    public_files = root / "public-files"
    artifacts.mkdir()
    public_files.mkdir()
    distributions = (
        "attest-core",
        "attest-collect",
        "attest-sign",
        "attest-store",
        "attest-policy",
        "attest-cli",
    )
    for distribution in distributions:
        normalized = distribution.replace("-", "_")
        files = (
            (f"{normalized}-0.1.0-py3-none-any.whl", "bdist_wheel"),
            (f"{normalized}-0.1.0.tar.gz", "sdist"),
        )
        urls: list[dict[str, object]] = []
        for filename, package_type in files:
            content = filename.encode()
            (artifacts / filename).write_bytes(content)
            public_file = public_files / filename
            public_file.write_bytes(content)
            urls.append(
                {
                    "filename": filename,
                    "packagetype": package_type,
                    "digests": {"sha256": hashlib.sha256(content).hexdigest()},
                    "size": len(content),
                    "url": public_file.as_uri(),
                    "yanked": False,
                }
            )
        endpoint = index / distribution / "0.1.0"
        endpoint.mkdir(parents=True)
        (endpoint / "json").write_text(
            json.dumps({"info": {"name": distribution, "version": "0.1.0"}, "urls": urls}),
            encoding="utf-8",
        )
    return artifacts, root / "index"


def _verify_published(
    artifacts: Path,
    index: Path,
    *distributions: str,
    version: str = "0.1.0",
    manifest: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        sys.executable,
        str(PUBLISHED_VERIFIER),
        str(artifacts),
        "--version",
        version,
        "--index-base-url",
        index.as_uri(),
        "--attempts",
        "1",
        "--delay-seconds",
        "0",
    ]
    if manifest is not None:
        arguments.extend(("--manifest", str(manifest)))
    for distribution in distributions:
        arguments.extend(("--distribution", distribution))
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.ac("AC-F11-190")
def test_published_release_verifier_accepts_exact_cli_patch(tmp_path: Path) -> None:
    artifacts = tmp_path / "release-assets"
    endpoint = tmp_path / "index" / "pypi" / "attest-cli" / "0.1.3"
    public_files = tmp_path / "public-files"
    artifacts.mkdir()
    endpoint.mkdir(parents=True)
    public_files.mkdir()
    records: list[dict[str, object]] = []
    for filename, package_type in (
        ("attest_cli-0.1.3-py3-none-any.whl", "bdist_wheel"),
        ("attest_cli-0.1.3.tar.gz", "sdist"),
    ):
        content = filename.encode()
        (artifacts / filename).write_bytes(content)
        public_file = public_files / filename
        public_file.write_bytes(content)
        records.append(
            {
                "filename": filename,
                "packagetype": package_type,
                "digests": {"sha256": hashlib.sha256(content).hexdigest()},
                "size": len(content),
                "url": public_file.as_uri(),
                "yanked": False,
            }
        )
    (endpoint / "json").write_text(
        json.dumps({"info": {"name": "attest-cli", "version": "0.1.3"}, "urls": records}),
        encoding="utf-8",
    )

    result = _verify_published(
        artifacts,
        tmp_path / "index",
        version="0.1.3",
        manifest=PATCH_RELEASE_MANIFEST,
    )

    assert result.returncode == 0, result.stderr
    assert "published release: verified 1 distributions and 2 artifacts" in result.stdout


@pytest.mark.ac("AC-F11-170")
def test_published_release_verifier_rejects_an_unsafe_patch_manifest(tmp_path: Path) -> None:
    artifacts = tmp_path / "release-assets"
    artifacts.mkdir()
    manifest = tmp_path / "unsafe.toml"
    manifest.write_text(
        '[release]\nversion = "0.1.1"\ndistributions = ["../attest-cli"]\n',
        encoding="utf-8",
    )

    result = _verify_published(
        artifacts,
        tmp_path / "index",
        version="0.1.1",
        manifest=manifest,
    )

    assert result.returncode == 1
    assert "release package manifest contains an invalid distribution name" in result.stderr


@pytest.mark.ac("AC-F11-140")
def test_published_release_verifier_accepts_exact_public_artifacts(tmp_path: Path) -> None:
    artifacts, index = _published_fixture(tmp_path)
    result = _verify_published(artifacts, index)
    assert result.returncode == 0, result.stderr
    assert "published release: verified 6 distributions and 12 artifacts" in result.stdout


@pytest.mark.ac("AC-F11-140")
def test_published_release_verifier_accepts_strict_bootstrap_subset(tmp_path: Path) -> None:
    artifacts, index = _published_fixture(tmp_path)
    result = _verify_published(artifacts, index, "attest-core", "attest-collect", "attest-sign")
    assert result.returncode == 0, result.stderr
    assert "published release: verified 3 distributions and 6 artifacts" in result.stdout


@pytest.mark.ac("AC-F11-140")
@pytest.mark.parametrize(
    "distributions",
    [("attest-core", "attest-core"), ("attest-export",)],
)
def test_published_release_verifier_rejects_invalid_bootstrap_subset(
    tmp_path: Path,
    distributions: tuple[str, ...],
) -> None:
    artifacts, index = _published_fixture(tmp_path)
    result = _verify_published(artifacts, index, *distributions)
    assert result.returncode == 1
    assert "requested distributions are not a unique release-package subset" in result.stderr


@pytest.mark.ac("AC-F11-140")
def test_published_release_verifier_rejects_a_public_hash_mismatch(tmp_path: Path) -> None:
    artifacts, index = _published_fixture(tmp_path)
    document_path = index / "pypi/attest-cli/0.1.0/json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["urls"][0]["digests"]["sha256"] = "0" * 64
    document_path.write_text(json.dumps(document), encoding="utf-8")
    result = _verify_published(artifacts, index)
    assert result.returncode == 1
    assert "public artifact hash mismatch" in result.stderr


@pytest.mark.ac("AC-F11-170")
def test_published_release_verifier_rejects_tampered_downloaded_bytes(tmp_path: Path) -> None:
    artifacts, index = _published_fixture(tmp_path)
    document = json.loads((index / "pypi/attest-cli/0.1.0/json").read_text(encoding="utf-8"))
    Path(document["urls"][0]["url"].removeprefix("file://")).write_bytes(b"tampered")

    result = _verify_published(artifacts, index)

    assert result.returncode == 1
    assert "downloaded public artifact mismatch" in result.stderr


@pytest.mark.ac("AC-F11-140")
def test_published_release_verifier_rejects_published_export(tmp_path: Path) -> None:
    artifacts, index = _published_fixture(tmp_path)
    endpoint = index / "pypi/attest-export"
    endpoint.mkdir(parents=True)
    (endpoint / "json").write_text(
        json.dumps({"info": {"name": "attest-export", "version": "0.1.0"}}),
        encoding="utf-8",
    )
    result = _verify_published(artifacts, index)
    assert result.returncode == 1
    assert "attest-export must remain unpublished" in result.stderr
