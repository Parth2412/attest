"""Validate the exact reviewed F-11 candidate before release promotion."""

# ruff: noqa: TRY003  # Release-specific fail-closed diagnostics are intentional.

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NoReturn

DIGEST: Final[re.Pattern[str]] = re.compile(r"sha256:[0-9a-f]{64}\Z")
IMAGE_REFERENCE: Final[re.Pattern[str]] = re.compile(
    r"^[ \t]*image:[ \t]+docker://ghcr\.io/parth2412/attest@(sha256:[0-9a-f]{64})[ \t]*$",
    re.MULTILINE,
)
EXPECTED_FILES: Final[frozenset[str]] = frozenset(
    {
        "build-metadata.json",
        "context-digest.txt",
        "context-manifest.json",
        "image-digest.txt",
        "manifest.json",
        "provenance.slsa.json",
        "sbom.spdx.json",
    }
)
PLATFORMS: Final[frozenset[str]] = frozenset({"linux/amd64", "linux/arm64"})
MAX_FILE_BYTES: Final[int] = 32 * 1024 * 1024


class CandidateValidationError(ValueError):
    """Candidate evidence differs from the reviewed release contract."""


def _fail(message: str) -> NoReturn:
    raise CandidateValidationError(message)


def _regular_bytes(path: Path) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise CandidateValidationError(f"missing candidate evidence: {path.name}") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        _fail(f"candidate evidence must be a regular file: {path.name}")
    if metadata.st_size <= 0 or metadata.st_size > MAX_FILE_BYTES:
        _fail(f"candidate evidence has an invalid size: {path.name}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise CandidateValidationError(f"candidate evidence cannot be read: {path.name}") from error


def _text(path: Path) -> str:
    try:
        return _regular_bytes(path).decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise CandidateValidationError(f"candidate evidence must be UTF-8: {path.name}") from error


def _json(path: Path) -> object:
    try:
        return json.loads(_text(path))
    except json.JSONDecodeError as error:
        raise CandidateValidationError(
            f"candidate evidence must be valid JSON: {path.name}"
        ) from error


def _digest_text(path: Path, label: str) -> str:
    value = _text(path)
    if not value.endswith("\n") or "\n" in value[:-1] or DIGEST.fullmatch(value[:-1]) is None:
        _fail(f"invalid {label} evidence")
    return value[:-1]


def _manifest_digest(document: dict[str, object]) -> str:
    content = {key: value for key, value in document.items() if key != "contextDigest"}
    encoded = json.dumps(content, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _validate_context(
    evidence: Path,
    current_context_manifest: Path,
    expected_context_digest: str,
) -> None:
    evidence_digest = _digest_text(evidence / "context-digest.txt", "context digest")
    if evidence_digest != expected_context_digest:
        _fail("context digest mismatch")

    evidence_manifest = _json(evidence / "context-manifest.json")
    current_manifest = _json(current_context_manifest)
    if not isinstance(evidence_manifest, dict) or not isinstance(current_manifest, dict):
        _fail("context manifest must be a JSON object")
    if evidence_manifest.get("contextDigest") != expected_context_digest:
        _fail("candidate context manifest digest mismatch")
    if current_manifest.get("contextDigest") != expected_context_digest:
        _fail("current context digest mismatch")
    if _manifest_digest(evidence_manifest) != expected_context_digest:
        _fail("candidate context manifest is not self-consistent")
    if _manifest_digest(current_manifest) != expected_context_digest:
        _fail("current context manifest is not self-consistent")
    if evidence_manifest != current_manifest:
        _fail("final context differs from the reviewed candidate")


def _platforms(manifest: object) -> tuple[frozenset[str], int]:
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 2:
        _fail("candidate image manifest is invalid")
    descriptors = manifest.get("manifests")
    if not isinstance(descriptors, list) or not descriptors:
        _fail("candidate image manifest has no descriptors")
    runnable: set[str] = set()
    attached = 0
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            _fail("candidate image descriptor is invalid")
        platform = descriptor.get("platform")
        if not isinstance(platform, dict):
            _fail("candidate image platform is invalid")
        operating_system = platform.get("os")
        architecture = platform.get("architecture")
        if not isinstance(operating_system, str) or not isinstance(architecture, str):
            _fail("candidate image platform is invalid")
        if operating_system == "unknown" and architecture == "unknown":
            attached += 1
        else:
            runnable.add(f"{operating_system}/{architecture}")
    return frozenset(runnable), attached


def _validate_platform_evidence(path: Path, label: str) -> None:
    document = _json(path)
    if (
        not isinstance(document, dict)
        or set(document) != PLATFORMS
        or any(not isinstance(value, dict) or not value for value in document.values())
    ):
        _fail(f"invalid {label} platform evidence")


def _validate_image(evidence: Path, expected_image_digest: str) -> None:
    evidence_digest = _digest_text(evidence / "image-digest.txt", "image digest")
    if evidence_digest != expected_image_digest:
        _fail("image digest mismatch")

    manifest_bytes = _regular_bytes(evidence / "manifest.json")
    observed_digest = f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}"
    if observed_digest != expected_image_digest:
        _fail("candidate manifest bytes do not match the reviewed image digest")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CandidateValidationError("candidate image manifest must be valid JSON") from error
    runnable, attached = _platforms(manifest)
    if runnable != PLATFORMS or attached < 1:
        _fail("candidate image does not contain the exact platforms and attestations")

    metadata = _json(evidence / "build-metadata.json")
    if (
        not isinstance(metadata, dict)
        or metadata.get("containerimage.digest") != expected_image_digest
    ):
        _fail("build metadata image digest mismatch")
    descriptor = metadata.get("containerimage.descriptor")
    if not isinstance(descriptor, dict) or descriptor.get("digest") != expected_image_digest:
        _fail("build metadata descriptor mismatch")

    _validate_platform_evidence(evidence / "sbom.spdx.json", "SBOM")
    _validate_platform_evidence(evidence / "provenance.slsa.json", "provenance")


def _validate_action_manifest(action_manifest: Path, expected_image_digest: str) -> None:
    manifest = _text(action_manifest)
    matches = IMAGE_REFERENCE.findall(manifest)
    if matches != [expected_image_digest]:
        _fail("Action manifest does not pin the reviewed image digest")


def _validate_directory(evidence: Path) -> None:
    try:
        metadata = evidence.lstat()
        entries = tuple(evidence.iterdir())
    except OSError as error:
        raise CandidateValidationError("candidate evidence directory cannot be read") from error
    if evidence.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        _fail("candidate evidence path must be a directory")
    if {entry.name for entry in entries} != EXPECTED_FILES:
        _fail("candidate evidence directory does not contain the exact release set")
    for entry in entries:
        _regular_bytes(entry)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-directory", required=True, type=Path)
    parser.add_argument("--current-context-manifest", required=True, type=Path)
    parser.add_argument("--action-manifest", required=True, type=Path)
    parser.add_argument("--expected-context-digest", required=True)
    parser.add_argument("--expected-image-digest", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate immutable candidate evidence and the final reviewed source context."""
    arguments = _parser().parse_args(argv)
    if DIGEST.fullmatch(arguments.expected_context_digest) is None:
        sys.stderr.write("candidate evidence error: invalid expected context digest\n")
        return 1
    if DIGEST.fullmatch(arguments.expected_image_digest) is None:
        sys.stderr.write("candidate evidence error: invalid expected image digest\n")
        return 1
    try:
        _validate_directory(arguments.evidence_directory)
        _validate_context(
            arguments.evidence_directory,
            arguments.current_context_manifest,
            arguments.expected_context_digest,
        )
        _validate_image(arguments.evidence_directory, arguments.expected_image_digest)
        _validate_action_manifest(arguments.action_manifest, arguments.expected_image_digest)
    except (CandidateValidationError, OSError) as error:
        sys.stderr.write(f"candidate evidence error: {error}\n")
        return 1
    sys.stdout.write("candidate evidence: validated exact reviewed context and image\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
