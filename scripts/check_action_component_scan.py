"""Enforce the F-11 upstream Git/curl component vulnerability gate."""

# ruff: noqa: TRY003  # Gate-specific fail-closed diagnostics are intentional.

from __future__ import annotations

import argparse
import json
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, NoReturn

MAX_FILE_BYTES: Final[int] = 32 * 1024 * 1024
EXPECTED_COMPONENTS: Final[dict[str, tuple[str, str, str]]] = {
    "pkg:generic/curl@8.22.0": (
        "curl",
        "8.22.0",
        "cpe:2.3:a:haxx:curl:8.22.0:*:*:*:*:*:*:*",
    ),
    "pkg:generic/git@2.52.0": (
        "git",
        "2.52.0",
        "cpe:2.3:a:git-scm:git:2.52.0:*:*:*:*:*:*:*",
    ),
}
EXPECTED_VEX: Final[dict[str, object]] = {
    "@context": "https://openvex.dev/ns/v0.2.0",
    "@id": "https://github.com/Parth2412/attest/vex/ADR-062",
    "author": "https://github.com/Parth2412/attest",
    "timestamp": "2026-10-13T00:00:00Z",
    "version": 1,
    "statements": [
        {
            "vulnerability": {"@id": "CVE-2026-62960"},
            "products": [{"@id": "pkg:generic/git@2.52.0"}],
            "status": "not_affected",
            "justification": "vulnerable_code_not_present",
            "impact_statement": (
                "The advisory requires Git for Windows UNC/SMB path handling; this artifact is "
                "built for Linux with musl and contains no Windows compatibility code."
            ),
        }
    ],
}


class ComponentScanError(ValueError):
    """Component evidence or scanner output violates the closed gate."""


def _fail(message: str) -> NoReturn:
    raise ComponentScanError(message)


def _json(path: Path, label: str) -> object:
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            _fail(f"{label} must be a regular file")
        if metadata.st_size <= 0 or metadata.st_size > MAX_FILE_BYTES:
            _fail(f"{label} has an invalid size")
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ComponentScanError(f"{label} is not valid JSON") from error


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        _fail(label)
    return value


def _validate_sbom(path: Path) -> None:
    document = _mapping(_json(path, "component SBOM"), "invalid component SBOM")
    packages = document.get("packages")
    if document.get("spdxVersion") != "SPDX-2.3" or not isinstance(packages, list):
        _fail("invalid component SBOM")
    observed: dict[str, tuple[str, str, str]] = {}
    for value in packages:
        package = _mapping(value, "invalid component SBOM")
        references = package.get("externalRefs")
        if not isinstance(references, list):
            _fail("invalid component SBOM")
        locators = {
            reference.get("referenceType"): reference.get("referenceLocator")
            for value in references
            if isinstance(value, dict)
            for reference in (value,)
        }
        purl = locators.get("purl")
        cpe = locators.get("cpe23Type")
        name = package.get("name")
        version = package.get("versionInfo")
        if (
            not isinstance(purl, str)
            or not isinstance(cpe, str)
            or not isinstance(name, str)
            or not isinstance(version, str)
        ):
            _fail("invalid component SBOM")
        if purl in observed:
            _fail("invalid component SBOM")
        observed[purl] = (name, version, cpe)
    if observed != EXPECTED_COMPONENTS:
        _fail("invalid component SBOM")


def _validate_vex(path: Path) -> frozenset[tuple[str, str]]:
    document = _json(path, "component VEX")
    if document != EXPECTED_VEX:
        _fail("invalid component VEX")
    return frozenset({("CVE-2026-62960", "pkg:generic/git@2.52.0")})


def _validate_report(document: object) -> list[Mapping[str, object]]:
    report = _mapping(document, "invalid Grype component report")
    matches = report.get("matches")
    source = report.get("source")
    descriptor = report.get("descriptor")
    if (
        not isinstance(matches, list)
        or not isinstance(source, dict)
        or not isinstance(descriptor, dict)
    ):
        _fail("invalid Grype component report")
    target = source.get("target")
    configuration = descriptor.get("configuration")
    database = descriptor.get("db")
    if (
        source.get("type") != "sbom-file"
        or not isinstance(target, str)
        or not target.endswith("/runtime-components.spdx.json")
        or descriptor.get("name") != "grype"
        or descriptor.get("version") != "0.107.0"
        or not isinstance(configuration, dict)
        or not isinstance(configuration.get("match"), dict)
        or not isinstance(configuration["match"].get("stock"), dict)
        or configuration["match"]["stock"].get("using-cpes") is not True
        or not isinstance(database, dict)
        or not isinstance(database.get("status"), dict)
        or database["status"].get("valid") is not True
        or not isinstance(database["status"].get("built"), str)
        or not isinstance(database["status"].get("from"), str)
    ):
        _fail("invalid Grype component report")
    if any(not isinstance(match, dict) for match in matches):
        _fail("invalid Grype component report")
    return matches


def _evaluate(
    matches: list[Mapping[str, object]],
    exclusions: frozenset[tuple[str, str]],
) -> tuple[int, int, int, int]:
    critical = 0
    fixable_high = 0
    unfixable_high = 0
    ignored = 0
    for match in matches:
        vulnerability = _mapping(match.get("vulnerability"), "invalid Grype component report")
        artifact = _mapping(match.get("artifact"), "invalid Grype component report")
        vulnerability_id = vulnerability.get("id")
        severity = vulnerability.get("severity")
        purl = artifact.get("purl")
        name = artifact.get("name")
        fix = vulnerability.get("fix")
        if (
            not isinstance(vulnerability_id, str)
            or not isinstance(severity, str)
            or not isinstance(purl, str)
            or purl not in EXPECTED_COMPONENTS
            or name != EXPECTED_COMPONENTS[purl][0]
            or not isinstance(fix, dict)
            or not isinstance(fix.get("state"), str)
            or not isinstance(fix.get("versions"), list)
            or any(not isinstance(version, str) for version in fix["versions"])
        ):
            _fail("invalid Grype component report")
        if (vulnerability_id, purl) in exclusions:
            ignored += 1
            continue
        normalized = severity.upper()
        if normalized == "CRITICAL":
            critical += 1
        elif normalized == "HIGH":
            if fix["state"] == "fixed" or fix["versions"]:
                fixable_high += 1
            else:
                unfixable_high += 1
    return critical, fixable_high, unfixable_high, ignored


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--sbom", required=True, type=Path)
    parser.add_argument("--vex", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate exact scanner inputs and enforce the unchanged vulnerability threshold."""
    arguments = _parser().parse_args(argv)
    try:
        _validate_sbom(arguments.sbom)
        exclusions = _validate_vex(arguments.vex)
        matches = _validate_report(_json(arguments.report, "Grype component report"))
        critical, fixable_high, unfixable_high, ignored = _evaluate(matches, exclusions)
    except ComponentScanError as error:
        sys.stderr.write(f"component security gate error: {error}\n")
        return 2
    summary = (
        f"critical={critical}, fixable high={fixable_high}, "
        f"unfixed high={unfixable_high}, ignored by VEX={ignored}"
    )
    if critical or fixable_high:
        sys.stderr.write(f"component security gate failed: {summary}\n")
        return 1
    sys.stdout.write(f"component security gate passed: {summary}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
