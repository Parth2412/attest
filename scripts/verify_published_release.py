"""Verify the exact F-11 distribution set against the public package index."""

# ruff: noqa: TRY003  # Publication-specific fail-closed diagnostics are intentional.

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Final, NoReturn

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
RELEASE_MANIFEST: Final[Path] = REPOSITORY_ROOT / "release/packages.toml"
PYPI_BASE_URL: Final[str] = "https://pypi.org"
FORBIDDEN_DISTRIBUTION: Final[str] = "attest-export"
WHEEL_TAG: Final[str] = "py3-none-any"
MAX_RESPONSE_BYTES: Final[int] = 8 * 1024 * 1024


class PublishedReleaseError(ValueError):
    """The public release differs from the reviewed local artifacts."""


def _fail(message: str) -> NoReturn:
    raise PublishedReleaseError(message)


def _normalized(value: str) -> str:
    return value.lower().replace("_", "-").replace(".", "-")


def _release_contract() -> tuple[str, tuple[str, ...]]:
    try:
        with RELEASE_MANIFEST.open("rb") as stream:
            document = tomllib.load(stream)
        release = document["release"]
        version = release["version"]
        distributions = release["distributions"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise PublishedReleaseError("release package manifest cannot be read") from error
    if (
        not isinstance(version, str)
        or not version
        or not isinstance(distributions, list)
        or len(distributions) != 6
        or not all(isinstance(item, str) and item for item in distributions)
        or len(distributions) != len(set(distributions))
        or FORBIDDEN_DISTRIBUTION in distributions
    ):
        _fail("release package manifest is not the closed six-package set")
    return version, tuple(distributions)


def _expected_files(version: str, distributions: tuple[str, ...]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for distribution in distributions:
        normalized = distribution.replace("-", "_")
        expected[f"{normalized}-{version}-{WHEEL_TAG}.whl"] = "bdist_wheel"
        expected[f"{normalized}-{version}.tar.gz"] = "sdist"
    return expected


def _artifact_hashes(directory: Path, expected: dict[str, str]) -> dict[str, str]:
    try:
        metadata = directory.lstat()
        entries = tuple(directory.iterdir())
    except OSError as error:
        raise PublishedReleaseError("release artifact directory cannot be read") from error
    if directory.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        _fail("release artifact path must be a directory")

    actual_names = {entry.name for entry in entries if entry.is_file() and not entry.is_symlink()}
    missing = set(expected).difference(actual_names)
    if missing:
        _fail(f"release artifact directory is missing: {sorted(missing)}")
    unexpected_archives = {
        name
        for name in actual_names
        if (name.endswith(".whl") or name.endswith(".tar.gz"))
        and name not in expected
        and not name.endswith("-source.tar.gz")
    }
    if unexpected_archives:
        _fail(f"release artifact directory has unexpected archives: {sorted(unexpected_archives)}")

    hashes: dict[str, str] = {}
    for name in expected:
        path = directory / name
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
            _fail(f"release artifact must be a non-empty regular file: {name}")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _validated_base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        _fail("package index base URL is invalid")
    if parsed.scheme == "https":
        if not parsed.hostname:
            _fail("package index HTTPS URL has no host")
    elif parsed.scheme == "file":
        if parsed.netloc or not parsed.path.startswith("/"):
            _fail("package index file URL is invalid")
    else:
        _fail("package index base URL must use HTTPS")
    return value.rstrip("/")


def _endpoint(base_url: str, distribution: str) -> str:
    return f"{base_url}/pypi/{urllib.parse.quote(distribution, safe='')}/json"


def _read_endpoint(url: str) -> dict[str, object] | None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as error:
            raise PublishedReleaseError("package index fixture cannot be read") from error
    else:
        request = urllib.request.Request(  # noqa: S310  # URL scheme validated before this call.
            url,
            headers={"Accept": "application/json", "User-Agent": "attest-release-verifier/0.1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310  # nosec B310
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise PublishedReleaseError(f"package index returned HTTP {error.code}") from error
        except (OSError, urllib.error.URLError) as error:
            raise PublishedReleaseError("package index request failed") from error
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        _fail("package index response has an invalid size")
    try:
        document = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PublishedReleaseError("package index response is not valid JSON") from error
    if not isinstance(document, dict):
        _fail("package index response must be a JSON object")
    return document


def _file_records(document: dict[str, object], version: str) -> tuple[dict[str, object], ...]:
    urls = document.get("urls")
    releases = document.get("releases")
    if not isinstance(urls, list) or not isinstance(releases, dict):
        _fail("package index response has invalid release records")
    version_records = releases.get(version)
    if not isinstance(version_records, list) or urls != version_records:
        _fail("package index current and version release records differ")
    if not all(isinstance(item, dict) for item in urls):
        _fail("package index release record is invalid")
    return tuple(urls)


def _validate_distribution(
    distribution: str,
    version: str,
    document: dict[str, object],
    expected_types: dict[str, str],
    local_hashes: dict[str, str],
) -> None:
    info = document.get("info")
    if (
        not isinstance(info, dict)
        or _normalized(str(info.get("name", ""))) != distribution
        or info.get("version") != version
    ):
        _fail(f"public metadata mismatch for {distribution}")

    prefix = distribution.replace("-", "_") + f"-{version}"
    expected_names = {name for name in expected_types if name.startswith(prefix)}
    records = _file_records(document, version)
    observed_names = {record.get("filename") for record in records}
    if observed_names != expected_names or len(records) != 2:
        _fail(f"public artifact set mismatch for {distribution}")
    for record in records:
        filename = record.get("filename")
        if not isinstance(filename, str):
            _fail(f"public artifact name is invalid for {distribution}")
        digests = record.get("digests")
        if (
            record.get("packagetype") != expected_types[filename]
            or record.get("yanked") is not False
            or not isinstance(digests, dict)
            or digests.get("sha256") != local_hashes[filename]
        ):
            _fail(f"public artifact hash mismatch for {filename}")


def _load_public_documents(
    base_url: str,
    distributions: tuple[str, ...],
    attempts: int,
    delay_seconds: float,
) -> dict[str, dict[str, object]]:
    last_error: PublishedReleaseError | None = None
    for attempt in range(1, attempts + 1):
        try:
            documents: dict[str, dict[str, object]] = {}
            for distribution in distributions:
                document = _read_endpoint(_endpoint(base_url, distribution))
                if document is None:
                    _fail(f"public distribution is unavailable: {distribution}")
                documents[distribution] = document
        except PublishedReleaseError as error:
            last_error = error
            if attempt < attempts:
                time.sleep(delay_seconds)
        else:
            return documents
    if last_error is None:
        _fail("public package verification did not run")
    raise last_error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_directory", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--index-base-url", default=PYPI_BASE_URL)
    parser.add_argument("--attempts", type=int, default=30)
    parser.add_argument("--delay-seconds", type=float, default=10.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Compare the public package release with the exact locally reviewed artifacts."""
    arguments = _parser().parse_args(argv)
    if arguments.attempts < 1 or arguments.delay_seconds < 0:
        sys.stderr.write("published release error: retry settings are invalid\n")
        return 1
    try:
        version, distributions = _release_contract()
        if arguments.version != version:
            _fail("requested version differs from the release package manifest")
        base_url = _validated_base_url(arguments.index_base_url)
        expected_types = _expected_files(version, distributions)
        local_hashes = _artifact_hashes(arguments.artifact_directory, expected_types)
        documents = _load_public_documents(
            base_url,
            distributions,
            arguments.attempts,
            arguments.delay_seconds,
        )
        for distribution in distributions:
            _validate_distribution(
                distribution,
                version,
                documents[distribution],
                expected_types,
                local_hashes,
            )
        if _read_endpoint(_endpoint(base_url, FORBIDDEN_DISTRIBUTION)) is not None:
            _fail("attest-export must remain unpublished")
    except (PublishedReleaseError, OSError) as error:
        sys.stderr.write(f"published release error: {error}\n")
        return 1
    sys.stdout.write(
        f"published release: verified {len(distributions)} distributions "
        f"and {len(expected_types)} artifacts\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
