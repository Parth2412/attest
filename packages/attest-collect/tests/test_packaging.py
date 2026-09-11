"""ADR-034 package-metadata and lazy-import tests."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _metadata(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        value: dict[str, Any] = tomllib.load(stream)
    return value


def test_pygit2_is_optional_for_collect_and_store_but_pinned_for_ci() -> None:
    for package in ("attest-collect", "attest-store"):
        metadata = _metadata(REPOSITORY_ROOT / "packages" / package / "pyproject.toml")
        assert "pygit2==1.20.0" not in metadata["project"]["dependencies"]
        assert metadata["project"]["optional-dependencies"]["pygit2"] == ["pygit2==1.20.0"]
    root = _metadata(REPOSITORY_ROOT / "pyproject.toml")
    assert "pygit2==1.20.0" in root["dependency-groups"]["dev"]


def test_importing_collect_does_not_import_pygit2() -> None:
    command = "import sys, attest_collect; raise SystemExit('pygit2' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", command],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
