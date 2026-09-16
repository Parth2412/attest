"""Validate the closed F-11 Python release artifact set."""

# ruff: noqa: TRY003  # Artifact-specific diagnostics are constructed at each failed invariant.

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import os
import stat
import sys
import tarfile
import tomllib
import zipfile
from collections.abc import Sequence
from email.message import Message
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Final

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
RELEASE_MANIFEST: Final[Path] = REPOSITORY_ROOT / "release/packages.toml"
WHEEL_TAG: Final[str] = "py3-none-any"


class ArtifactValidationError(ValueError):
    """A release artifact does not match the closed source contract."""


def _toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as stream:
            value = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ArtifactValidationError(f"cannot read {path.name}") from error
    return value


def _table(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ArtifactValidationError(f"{label} must be a TOML table")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ArtifactValidationError(f"{label} must be a string array")
    strings = tuple(value)
    if len(strings) != len(set(strings)):
        raise ArtifactValidationError(f"{label} contains a duplicate")
    return strings


def _release_contract() -> tuple[str, tuple[str, ...]]:
    release = _table(_toml(RELEASE_MANIFEST).get("release"), "release")
    version = release.get("version")
    if not isinstance(version, str) or not version:
        raise ArtifactValidationError("release.version must be a non-empty string")
    distributions = _strings(release.get("distributions"), "release.distributions")
    if not distributions:
        raise ArtifactValidationError("release.distributions must not be empty")
    return version, distributions


def _project(distribution: str) -> dict[str, object]:
    package_root = REPOSITORY_ROOT / "packages" / distribution
    return _table(_toml(package_root / "pyproject.toml").get("project"), "project")


def _archive_names(version: str, distributions: Sequence[str]) -> tuple[str, ...]:
    names: list[str] = []
    for distribution in distributions:
        normalized = distribution.replace("-", "_")
        names.extend(
            (
                f"{normalized}-{version}-{WHEEL_TAG}.whl",
                f"{normalized}-{version}.tar.gz",
            )
        )
    return tuple(names)


def _safe_member(name: str) -> None:
    member = PurePosixPath(name)
    if member.is_absolute() or ".." in member.parts or "" in member.parts:
        raise ArtifactValidationError(f"archive contains unsafe member {name!r}")


def _metadata(raw: bytes, label: str) -> Message:
    try:
        message = BytesParser(policy=default).parsebytes(raw)
    except (TypeError, ValueError) as error:
        raise ArtifactValidationError(f"{label} metadata cannot be parsed") from error
    if message.defects:
        raise ArtifactValidationError(f"{label} metadata has parser defects")
    return message


def _metadata_values(message: Message, key: str) -> tuple[str, ...]:
    return tuple(str(value) for value in message.get_all(key, []))


def _validate_metadata(message: Message, distribution: str, project: dict[str, object]) -> None:
    package_root = REPOSITORY_ROOT / "packages" / distribution
    scalar_fields = {
        "Name": project.get("name"),
        "Version": project.get("version"),
        "Summary": project.get("description"),
        "Requires-Python": project.get("requires-python"),
        "Author": "Parth (ZettaCore)",
        "License-Expression": "Apache-2.0",
        "Description-Content-Type": "text/markdown",
    }
    for key, expected in scalar_fields.items():
        if message.get(key) != expected:
            raise ArtifactValidationError(f"{distribution} has invalid {key}")

    expected_dependencies = list(_strings(project.get("dependencies", []), "dependencies"))
    optional_dependencies = _table(
        project.get("optional-dependencies", {}), "optional-dependencies"
    )
    for extra, dependencies in optional_dependencies.items():
        expected_dependencies.extend(
            f"{dependency}; extra == '{extra}'"
            for dependency in _strings(dependencies, f"optional-dependencies.{extra}")
        )
    if sorted(_metadata_values(message, "Requires-Dist")) != sorted(expected_dependencies):
        raise ArtifactValidationError(f"{distribution} has invalid Requires-Dist metadata")

    expected_classifiers = _strings(project.get("classifiers"), "classifiers")
    if _metadata_values(message, "Classifier") != expected_classifiers:
        raise ArtifactValidationError(f"{distribution} has invalid classifiers")

    expected_keywords = ",".join(_strings(project.get("keywords"), "keywords"))
    if message.get("Keywords") != expected_keywords:
        raise ArtifactValidationError(f"{distribution} has invalid keywords")

    urls = _table(project.get("urls"), "urls")
    expected_urls = tuple(f"{label}, {url}" for label, url in urls.items())
    if _metadata_values(message, "Project-URL") != expected_urls:
        raise ArtifactValidationError(f"{distribution} has invalid project URLs")
    if _metadata_values(message, "License-File") != ("LICENSE",):
        raise ArtifactValidationError(f"{distribution} has invalid licence metadata")

    payload = message.get_payload()
    if not isinstance(payload, str):
        raise ArtifactValidationError(f"{distribution} has a non-text description")
    expected_readme = (package_root / "README.md").read_text(encoding="utf-8")
    if payload.strip() != expected_readme.strip():
        raise ArtifactValidationError(f"{distribution} README metadata differs from source")


def _validate_record(archive: zipfile.ZipFile, record_name: str) -> None:
    try:
        rows = list(csv.reader(archive.read(record_name).decode("utf-8").splitlines()))
    except (KeyError, UnicodeError, csv.Error) as error:
        raise ArtifactValidationError("wheel RECORD cannot be parsed") from error
    if any(len(row) != 3 for row in rows):
        raise ArtifactValidationError("wheel RECORD has an invalid row")
    records = {row[0]: (row[1], row[2]) for row in rows}
    names = set(archive.namelist())
    if len(records) != len(rows) or set(records) != names:
        raise ArtifactValidationError("wheel RECORD does not cover every member exactly once")

    for name in sorted(names):
        digest, size = records[name]
        if name == record_name:
            if digest or size:
                raise ArtifactValidationError("wheel RECORD must not hash itself")
            continue
        content = archive.read(name)
        encoded = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
        if digest != f"sha256={encoded.decode('ascii')}" or size != str(len(content)):
            raise ArtifactValidationError(f"wheel RECORD hash mismatch for {name!r}")


def _validate_wheel(path: Path, distribution: str, version: str) -> None:
    normalized = distribution.replace("-", "_")
    dist_info = f"{normalized}-{version}.dist-info"
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ArtifactValidationError(f"{path.name} has duplicate members")
            for info in infos:
                _safe_member(info.filename)
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise ArtifactValidationError(f"{path.name} contains a symbolic link")

            metadata_name = f"{dist_info}/METADATA"
            record_name = f"{dist_info}/RECORD"
            licence_name = f"{dist_info}/licenses/LICENSE"
            required = {metadata_name, record_name, licence_name, f"{dist_info}/WHEEL"}
            if not required <= set(names):
                raise ArtifactValidationError(f"{path.name} is missing required wheel content")
            project = _project(distribution)
            _validate_metadata(
                _metadata(archive.read(metadata_name), path.name), distribution, project
            )
            if archive.read(licence_name) != (REPOSITORY_ROOT / "LICENSE").read_bytes():
                raise ArtifactValidationError(f"{path.name} has invalid licence content")
            wheel_text = archive.read(f"{dist_info}/WHEEL").decode("utf-8")
            if (
                "Root-Is-Purelib: true\n" not in wheel_text
                or f"Tag: {WHEEL_TAG}\n" not in wheel_text
            ):
                raise ArtifactValidationError(f"{path.name} has an invalid compatibility tag")
            _validate_record(archive, record_name)
    except (OSError, UnicodeError, zipfile.BadZipFile) as error:
        raise ArtifactValidationError(f"{path.name} is not a valid wheel") from error


def _tar_bytes(archive: tarfile.TarFile, name: str) -> bytes:
    try:
        member = archive.getmember(name)
        stream = archive.extractfile(member)
    except (KeyError, tarfile.TarError) as error:
        raise ArtifactValidationError(f"source distribution is missing {name!r}") from error
    if not member.isfile() or stream is None:
        raise ArtifactValidationError(f"source distribution member {name!r} is not regular")
    return stream.read()


def _validate_sdist(path: Path, distribution: str, version: str) -> None:
    normalized = distribution.replace("-", "_")
    root = f"{normalized}-{version}"
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                raise ArtifactValidationError(f"{path.name} has duplicate members")
            for member in members:
                _safe_member(member.name)
                if PurePosixPath(member.name).parts[0] != root:
                    raise ArtifactValidationError(f"{path.name} has content outside its root")
                if not (member.isfile() or member.isdir()):
                    raise ArtifactValidationError(f"{path.name} contains an irregular member")

            package_root = REPOSITORY_ROOT / "packages" / distribution
            project = _project(distribution)
            _validate_metadata(
                _metadata(_tar_bytes(archive, f"{root}/PKG-INFO"), path.name),
                distribution,
                project,
            )
            source_files = {
                "LICENSE": REPOSITORY_ROOT / "LICENSE",
                "README.md": package_root / "README.md",
                "pyproject.toml": package_root / "pyproject.toml",
            }
            for member_name, source in source_files.items():
                if _tar_bytes(archive, f"{root}/{member_name}") != source.read_bytes():
                    raise ArtifactValidationError(f"{path.name} {member_name} differs from source")
    except (OSError, tarfile.TarError) as error:
        raise ArtifactValidationError(f"{path.name} is not a valid source distribution") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
    except OSError as error:
        raise ArtifactValidationError(f"cannot hash {path.name}") from error
    return digest.hexdigest()


def _write_hashes(output: Path, artifacts: Sequence[Path]) -> None:
    content = "".join(f"{_sha256(path)}  {path.name}\n" for path in artifacts)
    output_parent = output.parent.resolve()
    try:
        output_parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(output)
    except OSError as error:
        raise ArtifactValidationError(f"cannot write {output.name}") from error


def validate(directory: Path, hash_output: Path | None = None) -> tuple[int, int]:
    """Validate exact wheel/sdist bytes and optionally write their SHA-256 manifest."""
    if not directory.is_dir():
        raise ArtifactValidationError("artifact path must be a directory")
    version, distributions = _release_contract()
    expected_names = _archive_names(version, distributions)
    try:
        actual_names = tuple(sorted(path.name for path in directory.iterdir() if path.is_file()))
    except OSError as error:
        raise ArtifactValidationError("artifact directory cannot be read") from error
    if actual_names != tuple(sorted(expected_names)):
        raise ArtifactValidationError("artifact directory does not contain the exact release set")

    artifacts = tuple(directory / name for name in sorted(expected_names))
    for distribution in distributions:
        normalized = distribution.replace("-", "_")
        _validate_wheel(
            directory / f"{normalized}-{version}-{WHEEL_TAG}.whl",
            distribution,
            version,
        )
        _validate_sdist(
            directory / f"{normalized}-{version}.tar.gz",
            distribution,
            version,
        )
    if hash_output is not None:
        _write_hashes(hash_output, artifacts)
    return len(distributions), len(distributions)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--hash-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate release artifacts without emitting artifact-controlled content."""
    arguments = _parser().parse_args(argv)
    try:
        wheels, source_distributions = validate(arguments.directory, arguments.hash_output)
    except ArtifactValidationError as error:
        print(f"release artifact error: {error}", file=sys.stderr)
        return 1
    print(
        f"release artifacts: validated {wheels} wheels and "
        f"{source_distributions} source distributions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
