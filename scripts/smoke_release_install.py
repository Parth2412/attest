"""Smoke-test the six installed F-11 Python distributions."""

from __future__ import annotations

import importlib
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Final, NoReturn

PUBLISHED_IMPORTS: Final[dict[str, str]] = {
    "attest-core": "attest_core",
    "attest-collect": "attest_collect",
    "attest-sign": "attest_sign",
    "attest-store": "attest_store",
    "attest-policy": "attest_policy",
    "attest-cli": "attest_cli",
}
EXPECTED_VERSIONS: Final[dict[str, str]] = {
    distribution: "0.1.1" if distribution == "attest-cli" else "0.1.0"
    for distribution in PUBLISHED_IMPORTS
}


def _normalized(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def _fail(message: str) -> NoReturn:
    raise SystemExit(message)


def main() -> int:
    """Verify installed versions, imports, dependency closure, and the CLI entry point."""
    installed_attest = sorted(
        _normalized(distribution.metadata["Name"])
        for distribution in metadata.distributions()
        if distribution.metadata["Name"]
        and _normalized(distribution.metadata["Name"]).startswith("attest-")
    )
    if installed_attest != sorted(PUBLISHED_IMPORTS):
        _fail("clean environment does not contain the exact attest release set")

    for distribution, import_name in PUBLISHED_IMPORTS.items():
        if metadata.version(distribution) != EXPECTED_VERSIONS[distribution]:
            _fail(f"{distribution} has the wrong installed version")
        module = importlib.import_module(import_name)
        module_path = getattr(module, "__file__", None)
        if not isinstance(module_path, str):
            _fail(f"{distribution} has no installed module path")
        source_root = (Path.cwd() / "packages").resolve()
        if Path(module_path).resolve().is_relative_to(source_root):
            _fail(f"{distribution} imported from the repository instead of its wheel")

    cli_requirements = metadata.requires("attest-cli") or []
    if any(
        _normalized(requirement).startswith("attest-export") for requirement in cli_requirements
    ):
        _fail("attest-cli depends on the unpublished attest-export distribution")

    result = subprocess.run(
        [sys.executable, "-m", "attest_cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0 or "Usage:" not in result.stdout:
        _fail("the installed attest CLI help command failed")

    print("release install: six distributions and CLI validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
