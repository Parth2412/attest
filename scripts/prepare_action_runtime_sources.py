"""Prepare the exact public corresponding-source payload for the F-11 image."""

# ruff: noqa: TRY003  # Supply-chain diagnostics are intentionally specific.

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Final, NoReturn

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST: Final[Path] = REPOSITORY_ROOT / "action/runtime-sources.json"
DEFAULT_RECIPE: Final[Path] = REPOSITORY_ROOT / "action/Dockerfile"
DEFAULT_VEX: Final[Path] = REPOSITORY_ROOT / "action/runtime-components.openvex.json"
DOWNLOAD_TIMEOUT_SECONDS: Final[int] = 60
MAX_ARCHIVE_BYTES: Final[int] = 64 * 1024 * 1024
EXPECTED_COMPONENTS: Final[frozenset[str]] = frozenset({"curl", "git"})
EXPECTED_ALGORITHMS: Final[dict[str, int]] = {"sha256": 64, "sha512": 128}


class SourcePreparationError(ValueError):
    """The corresponding-source input violates its closed contract."""


def _fail(message: str) -> NoReturn:
    raise SourcePreparationError(message)


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        _fail(f"{label} must be a non-empty exact string")
    return value


def _components(manifest: Path) -> tuple[Mapping[str, object], ...]:
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SourcePreparationError("runtime source manifest cannot be read") from error
    root = _object(document, "runtime source manifest")
    if set(root) != {"schemaVersion", "components"} or root.get("schemaVersion") != 1:
        _fail("runtime source manifest has an unsupported schema")
    values = root.get("components")
    if not isinstance(values, list) or len(values) != 2:
        _fail("runtime source manifest must contain exactly two components")
    components = tuple(_object(value, "runtime source component") for value in values)
    names = {_text(component.get("name"), "component name") for component in components}
    if names != EXPECTED_COMPONENTS:
        _fail("runtime source manifest must contain exactly curl and git")
    if len(names) != len(components):
        _fail("runtime source manifest repeats a component")
    return tuple(sorted(components, key=lambda component: str(component["name"])))


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(  # noqa: S310  # Closed, reviewed manifest URL.
        url,
        headers={"User-Agent": "attest-runtime-source/1"},
    )
    try:
        with (
            urllib.request.urlopen(  # noqa: S310  # Closed, reviewed manifest URL.
                request,
                timeout=DOWNLOAD_TIMEOUT_SECONDS,
            ) as response,
            destination.open("wb") as output,
        ):
            received = 0
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                if received > MAX_ARCHIVE_BYTES:
                    _fail("runtime source archive exceeds the size limit")
                output.write(chunk)
    except (OSError, urllib.error.URLError) as error:
        raise SourcePreparationError("runtime source archive download failed") from error
    if destination.stat().st_size == 0:
        _fail("runtime source archive is empty")


def _verify_digest(component: Mapping[str, object], archive: Path) -> None:
    name = _text(component.get("name"), "component name")
    archive_contract = _object(component.get("archive"), f"{name} archive")
    digest = _object(archive_contract.get("digest"), f"{name} archive digest")
    algorithm = _text(digest.get("algorithm"), f"{name} digest algorithm")
    expected = _text(digest.get("value"), f"{name} digest value")
    if algorithm not in EXPECTED_ALGORITHMS or len(expected) != EXPECTED_ALGORITHMS[algorithm]:
        _fail(f"{name} archive digest contract is invalid")
    if any(character not in "0123456789abcdef" for character in expected):
        _fail(f"{name} archive digest contract is invalid")
    with archive.open("rb") as stream:
        observed = hashlib.file_digest(stream, algorithm).hexdigest()
    if observed != expected:
        _fail(f"{name} archive digest mismatch")


def _licence(component: Mapping[str, object], archive: Path) -> bytes:
    name = _text(component.get("name"), "component name")
    root = _text(component.get("sourceRoot"), f"{name} source root")
    if PurePosixPath(root).name != root or root in {".", ".."}:
        _fail(f"{name} source root is invalid")
    licence = _object(component.get("licence"), f"{name} licence")
    relative = _text(licence.get("archivePath"), f"{name} licence archive path")
    relative_path = PurePosixPath(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        _fail(f"{name} licence archive path is invalid")
    expected_member = f"{root}/{relative_path.as_posix()}"
    try:
        with tarfile.open(archive, mode="r:xz") as source:
            members = source.getmembers()
            for member in members:
                member_path = PurePosixPath(member.name)
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or not (member.isfile() or member.isdir() or member.issym() or member.islnk())
                ):
                    _fail(f"{name} archive contains an unsafe member")
            matches = [member for member in members if member.name == expected_member]
            if len(matches) != 1 or not matches[0].isfile():
                _fail(f"{name} licence is missing from the source archive")
            stream = source.extractfile(matches[0])
            if stream is None:
                _fail(f"{name} licence cannot be read")
            content = stream.read(MAX_ARCHIVE_BYTES + 1)
    except (OSError, tarfile.TarError) as error:
        raise SourcePreparationError(f"{name} archive cannot be inspected") from error
    if not content or len(content) > MAX_ARCHIVE_BYTES:
        _fail(f"{name} licence has an invalid size")
    return content


def _spdx(components: tuple[Mapping[str, object], ...], manifest_bytes: bytes) -> bytes:
    namespace_digest = hashlib.sha256(manifest_bytes).hexdigest()
    packages: list[dict[str, object]] = []
    for component in components:
        name = _text(component.get("name"), "component name")
        version = _text(component.get("version"), f"{name} version")
        archive = _object(component.get("archive"), f"{name} archive")
        digest = _object(archive.get("digest"), f"{name} archive digest")
        licence = _object(component.get("licence"), f"{name} licence")
        algorithm = _text(digest.get("algorithm"), f"{name} digest algorithm")
        packages.append(
            {
                "SPDXID": f"SPDXRef-Package-{name}",
                "name": name,
                "versionInfo": version,
                "downloadLocation": _text(archive.get("url"), f"{name} archive URL"),
                "filesAnalyzed": False,
                "checksums": [
                    {
                        "algorithm": algorithm.upper(),
                        "checksumValue": _text(digest.get("value"), f"{name} digest value"),
                    }
                ],
                "licenseConcluded": _text(licence.get("spdx"), f"{name} SPDX licence"),
                "licenseDeclared": _text(licence.get("spdx"), f"{name} SPDX licence"),
                "copyrightText": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": _text(component.get("purl"), f"{name} purl"),
                    },
                    {
                        "referenceCategory": "SECURITY",
                        "referenceType": "cpe23Type",
                        "referenceLocator": _text(component.get("cpe"), f"{name} CPE"),
                    },
                ],
            }
        )
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "attest-action-runtime-components",
        "documentNamespace": (
            "https://github.com/Parth2412/attest/runtime-components/" + namespace_digest
        ),
        "creationInfo": {
            "created": "1970-01-01T00:00:00Z",
            "creators": ["Tool: attest-prepare-action-runtime-sources"],
        },
        "packages": packages,
        "relationships": [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": package["SPDXID"],
            }
            for package in packages
        ],
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()


def _source_manifest(directory: Path) -> bytes:
    files = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            _fail(f"corresponding source contains an unsafe path: {path.name}")
        content = path.read_bytes()
        files.append(
            {
                "path": path.name,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    document = {"schemaVersion": 1, "digestAlgorithm": "sha256", "files": files}
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()


def _prepare(destination: Path, manifest: Path, recipe: Path, vex: Path) -> None:
    if destination.exists() or destination.is_symlink():
        _fail("corresponding-source destination already exists")
    try:
        manifest_bytes = manifest.read_bytes()
        recipe_bytes = recipe.read_bytes()
        vex_metadata = vex.lstat()
        vex_bytes = vex.read_bytes()
    except OSError as error:
        raise SourcePreparationError("runtime source contract cannot be read") from error
    if (
        not manifest_bytes
        or not recipe_bytes
        or not vex_bytes
        or vex.is_symlink()
        or not stat.S_ISREG(vex_metadata.st_mode)
        or len(vex_bytes) > MAX_ARCHIVE_BYTES
    ):
        _fail("runtime source contract is empty")
    components = _components(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        (temporary / "runtime-sources.json").write_bytes(manifest_bytes)
        (temporary / "Dockerfile").write_bytes(recipe_bytes)
        (temporary / "runtime-components.openvex.json").write_bytes(vex_bytes)
        for component in components:
            name = _text(component.get("name"), "component name")
            archive_contract = _object(component.get("archive"), f"{name} archive")
            filename = _text(archive_contract.get("filename"), f"{name} archive filename")
            if PurePosixPath(filename).name != filename:
                _fail(f"{name} archive filename is invalid")
            archive = temporary / filename
            _download(_text(archive_contract.get("url"), f"{name} archive URL"), archive)
            _verify_digest(component, archive)
            (temporary / f"{name}-COPYING").write_bytes(_licence(component, archive))
        (temporary / "runtime-components.spdx.json").write_bytes(_spdx(components, manifest_bytes))
        (temporary / "SOURCE-MANIFEST.json").write_bytes(_source_manifest(temporary))
        temporary.replace(destination)
    except (OSError, SourcePreparationError):
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--recipe", type=Path, default=DEFAULT_RECIPE)
    parser.add_argument("--vex", type=Path, default=DEFAULT_VEX)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Prepare and validate the complete corresponding-source directory."""
    arguments = _parser().parse_args(argv)
    try:
        _prepare(arguments.destination, arguments.manifest, arguments.recipe, arguments.vex)
    except (OSError, SourcePreparationError) as error:
        sys.stderr.write(f"runtime source error: {error}\n")
        return 1
    sys.stdout.write("runtime source: prepared exact Git and curl correspondence\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
