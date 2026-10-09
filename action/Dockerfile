FROM ghcr.io/astral-sh/uv:0.11.2@sha256:c4f5de312ee66d46810635ffc5df34a1973ba753e7241ce3a08ef979ddd7bea5 AS uv

FROM python:3.12.14-alpine3.23@sha256:d339953547bb5bc57eb5c1ff3224c40890ce56e494b13a52a574658e5a0f888a AS build

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY packages/attest-core packages/attest-core
COPY packages/attest-collect packages/attest-collect
COPY packages/attest-sign packages/attest-sign
COPY packages/attest-store packages/attest-store
COPY packages/attest-policy packages/attest-policy
COPY packages/attest-cli packages/attest-cli
COPY action/trust action/trust
COPY action/verify_trust_seed.py action/verify_trust_seed.py

ENV UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    OPENSSL_STATIC=0

RUN apk add --no-cache \
        binutils=2.45.1-r0 \
        cargo=1.91.1-r2 \
        gcc=15.2.0-r2 \
        libffi-dev=3.5.2-r0 \
        musl-dev=1.2.5-r23 \
        openssl-dev=3.5.9-r0 \
        pkgconf=2.5.1-r0 \
        rust=1.91.1-r2 \
    && uv sync --frozen --only-group action-build \
    && uv sync --frozen --no-dev --package attest-cli --no-editable --inexact \
        --no-binary-package cryptography \
        --no-build-isolation-package cryptography \
    && uv pip uninstall --python /opt/venv/bin/python maturin setuptools \
    && /opt/venv/bin/python action/verify_trust_seed.py action/trust \
    && find /opt/venv -type f -name '*.so' -exec strip --strip-unneeded {} + \
    && rm -rf \
        /opt/venv/lib/python3.12/site-packages/certifi/tests \
        /opt/venv/lib/python3.12/site-packages/jsonschema/tests \
        /opt/venv/lib/python3.12/site-packages/jsonschema/benchmarks \
        /opt/venv/lib/python3.12/site-packages/jsonschema_specifications/tests \
        /opt/venv/lib/python3.12/site-packages/oras/tests \
        /opt/venv/lib/python3.12/site-packages/pygments \
        /opt/venv/lib/python3.12/site-packages/pygments-2.21.0.dist-info \
        /opt/venv/lib/python3.12/site-packages/referencing/tests \
        /opt/venv/lib/python3.12/site-packages/securesystemslib/_vendor/ed25519/test_data

FROM python:3.12.14-alpine3.23@sha256:d339953547bb5bc57eb5c1ff3224c40890ce56e494b13a52a574658e5a0f888a AS runtime

RUN apk add --no-cache \
        git=2.52.0-r0 \
        libcrypto3=3.5.9-r0 \
        libgcc=15.2.0-r2 \
        libssl3=3.5.9-r0 \
    && cp /usr/share/zoneinfo/UTC /tmp/attest-UTC \
    && rm -rf \
        /etc/terminfo \
        /usr/lib/libgdbm.so* \
        /usr/lib/libgdbm_compat.so* \
        /usr/lib/libncursesw.so* \
        /usr/lib/libnsl.so* \
        /usr/lib/libpanelw.so* \
        /usr/lib/libreadline.so* \
        /usr/lib/libsqlite3.so* \
        /usr/lib/libtirpc.so* \
        /usr/lib/libapk.so* \
        /usr/lib/libbrotlienc.so* \
        /usr/lib/libcom_err.so* \
        /usr/lib/libexpat.so* \
        /usr/lib/libgssapi_krb5.so* \
        /usr/lib/libgssrpc.so* \
        /usr/lib/libintl.so* \
        /usr/lib/libk5crypto.so* \
        /usr/lib/libkadm5clnt_mit.so* \
        /usr/lib/libkadm5srv_mit.so* \
        /usr/lib/libkdb5.so* \
        /usr/lib/libkeyutils.so* \
        /usr/lib/libkrad.so* \
        /usr/lib/libkrb5.so* \
        /usr/lib/libkrb5support.so* \
        /usr/lib/libpcre2-posix.so* \
        /usr/lib/libverto.so* \
        /usr/lib/krb5 \
        /usr/local/bin/pip \
        /usr/local/bin/pip3 \
        /usr/local/bin/pip3.12 \
        /usr/local/bin/2to3 \
        /usr/local/bin/2to3-3.12 \
        /usr/local/bin/idle \
        /usr/local/bin/idle3 \
        /usr/local/bin/idle3.12 \
        /usr/local/bin/pydoc \
        /usr/local/bin/pydoc3 \
        /usr/local/bin/pydoc3.12 \
        /usr/local/bin/python-config \
        /usr/local/bin/python3-config \
        /usr/local/bin/python3.12-config \
        /usr/local/include \
        /usr/local/lib/pkgconfig \
        /usr/local/lib/python3.12/config-* \
        /usr/local/lib/python3.12/lib-dynload/_crypt.*.so \
        /usr/local/lib/python3.12/lib-dynload/_ctypes_test.*.so \
        /usr/local/lib/python3.12/lib-dynload/_curses.*.so \
        /usr/local/lib/python3.12/lib-dynload/_curses_panel.*.so \
        /usr/local/lib/python3.12/lib-dynload/_dbm.*.so \
        /usr/local/lib/python3.12/lib-dynload/_gdbm.*.so \
        /usr/local/lib/python3.12/lib-dynload/_lsprof.*.so \
        /usr/local/lib/python3.12/lib-dynload/_sqlite3.*.so \
        /usr/local/lib/python3.12/lib-dynload/_test*.*.so \
        /usr/local/lib/python3.12/lib-dynload/_tkinter.*.so \
        /usr/local/lib/python3.12/lib-dynload/_xxinterpchannels.*.so \
        /usr/local/lib/python3.12/lib-dynload/_xxsubinterpreters.*.so \
        /usr/local/lib/python3.12/lib-dynload/_xxtestfuzz.*.so \
        /usr/local/lib/python3.12/lib-dynload/audioop.*.so \
        /usr/local/lib/python3.12/lib-dynload/nis.*.so \
        /usr/local/lib/python3.12/lib-dynload/ossaudiodev.*.so \
        /usr/local/lib/python3.12/lib-dynload/readline.*.so \
        /usr/local/lib/python3.12/lib-dynload/spwd.*.so \
        /usr/local/lib/python3.12/lib-dynload/syslog.*.so \
        /usr/local/lib/python3.12/lib-dynload/xxlimited.*.so \
        /usr/local/lib/python3.12/lib-dynload/xxlimited_35.*.so \
        /usr/local/lib/python3.12/lib-dynload/xxsubtype.*.so \
        /usr/local/lib/python3.12/aifc.py \
        /usr/local/lib/python3.12/bdb.py \
        /usr/local/lib/python3.12/cgi.py \
        /usr/local/lib/python3.12/cgitb.py \
        /usr/local/lib/python3.12/chunk.py \
        /usr/local/lib/python3.12/compileall.py \
        /usr/local/lib/python3.12/crypt.py \
        /usr/local/lib/python3.12/curses \
        /usr/local/lib/python3.12/dbm \
        /usr/local/lib/python3.12/doctest.py \
        /usr/local/lib/python3.12/site-packages/pip \
        /usr/local/lib/python3.12/site-packages/pip-25.0.1.dist-info \
        /usr/local/lib/python3.12/ensurepip \
        /usr/local/lib/python3.12/ftplib.py \
        /usr/local/lib/python3.12/http/server.py \
        /usr/local/lib/python3.12/idlelib \
        /usr/local/lib/python3.12/imghdr.py \
        /usr/local/lib/python3.12/imaplib.py \
        /usr/local/lib/python3.12/lib2to3 \
        /usr/local/lib/python3.12/mailbox.py \
        /usr/local/lib/python3.12/mailcap.py \
        /usr/local/lib/python3.12/nntplib.py \
        /usr/local/lib/python3.12/pdb.py \
        /usr/local/lib/python3.12/pipes.py \
        /usr/local/lib/python3.12/poplib.py \
        /usr/local/lib/python3.12/profile.py \
        /usr/local/lib/python3.12/pstats.py \
        /usr/local/lib/python3.12/pyclbr.py \
        /usr/local/lib/python3.12/pydoc_data \
        /usr/local/lib/python3.12/pydoc.py \
        /usr/local/lib/python3.12/smtplib.py \
        /usr/local/lib/python3.12/sndhdr.py \
        /usr/local/lib/python3.12/socketserver.py \
        /usr/local/lib/python3.12/sqlite3 \
        /usr/local/lib/python3.12/sunau.py \
        /usr/local/lib/python3.12/tabnanny.py \
        /usr/local/lib/python3.12/telnetlib.py \
        /usr/local/lib/python3.12/timeit.py \
        /usr/local/lib/python3.12/tkinter \
        /usr/local/lib/python3.12/trace.py \
        /usr/local/lib/python3.12/turtle.py \
        /usr/local/lib/python3.12/turtledemo \
        /usr/local/lib/python3.12/unittest \
        /usr/local/lib/python3.12/uu.py \
        /usr/local/lib/python3.12/venv \
        /usr/local/lib/python3.12/wsgiref \
        /usr/local/lib/python3.12/xdrlib.py \
        /usr/local/lib/python3.12/xmlrpc \
        /usr/share/apk \
        /usr/share/ca-certificates \
        /usr/share/git-core/templates \
        /usr/share/zoneinfo \
        /sbin/apk \
        /lib/apk \
        /etc/apk \
        /var/cache/apk \
        /var/log/apk.log \
        /usr/bin/scanelf \
        /usr/bin/git-shell \
        /usr/libexec/git-core/git-http-fetch \
        /usr/libexec/git-core/git-http-push \
        /usr/libexec/git-core/git-sh-i18n--envsubst \
        /usr/libexec/git-core/mergetools \
    && mkdir -p /usr/share/zoneinfo \
    && mv /tmp/attest-UTC /usr/share/zoneinfo/UTC

COPY --from=build /opt/venv /opt/venv
COPY action/entrypoint.py /opt/attest/entrypoint.py
COPY --from=build /build/action/trust /opt/attest/trust

RUN <<'PYTHON'
#!/opt/venv/bin/python
import hashlib
import importlib
import pathlib
import py_compile
import shutil
import sys
import zipfile

site_packages = pathlib.Path("/opt/venv/lib/python3.12/site-packages")
system_libgcc = pathlib.Path("/usr/lib/libgcc_s.so.1")
private_libgcc_directories = (
    site_packages / "pydantic_core.libs",
    site_packages / "rfc3161_client.libs",
    site_packages / "rpds_py.libs",
)
private_libgcc_paths = []
for directory in private_libgcc_directories:
    matches = tuple(directory.glob("libgcc_s-*.so.1"))
    if len(matches) != 1 or not matches[0].is_file() or matches[0].is_symlink():
        raise RuntimeError("unexpected private libgcc set")
    private_libgcc_paths.append(matches[0])
if tuple(sorted(site_packages.rglob("libgcc_s*.so*"))) != tuple(
    sorted(private_libgcc_paths)
):
    raise RuntimeError("unexpected private libgcc set")
if not system_libgcc.is_file() or system_libgcc.is_symlink():
    raise RuntimeError("invalid system libgcc")
for private_libgcc in private_libgcc_paths:
    private_libgcc.unlink()
    private_libgcc.symlink_to(system_libgcc)

console_script = pathlib.Path("/opt/venv/bin/attest")
pathlib.Path("/opt/attest/attest-console-script.sha256").write_text(
    f"{hashlib.sha256(console_script.read_bytes()).hexdigest()}\n",
    encoding="ascii",
)

for name in (
    "attest_cli.app",
    "attest_cli.artifacts",
    "attest_cli.commands",
    "attest_cli.config",
    "attest_cli.safe_io",
    "attest_collect",
    "attest_core",
    "attest_policy",
    "attest_sign",
    "attest_store",
):
    importlib.import_module(name)

roots = (
    pathlib.Path("/opt/venv/lib/python3.12/site-packages"),
    pathlib.Path("/usr/local/lib/python3.12"),
)
sources = sorted(
    {
        path.resolve()
        for module in tuple(sys.modules.values())
        if isinstance((file := getattr(module, "__file__", None)), str)
        and (path := pathlib.Path(file)).suffix == ".py"
        and any(path.resolve().is_relative_to(root) for root in roots)
    }
)
for source in sources:
    py_compile.compile(
        source,
        cfile=source.with_suffix(".pyc"),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH,
    )
    source.unlink()

standard_library = pathlib.Path("/usr/local/lib/python3.12")

runtime_archive_roots = (
    "OpenSSL",
    "_yaml",
    "annotated_doc",
    "annotated_types",
    "anyio",
    "attest_cli",
    "attest_collect",
    "attest_core",
    "attest_policy",
    "attest_sign",
    "attest_store",
    "attr",
    "attrs",
    "certifi",
    "cffi",
    "dns",
    "email_validator",
    "h11",
    "httpcore",
    "httpx",
    "idna",
    "jsonschema",
    "jsonschema_specifications",
    "jwt",
    "markdown_it",
    "mdurl",
    "oras",
    "platformdirs",
    "pyasn1",
    "pycparser",
    "pydantic",
    "referencing",
    "rekor_types",
    "requests",
    "rfc8785",
    "rich",
    "shellingham",
    "sigstore",
    "sigstore_models",
    "structlog",
    "tuf",
    "typer",
    "typing_inspection",
    "urllib3",
)
runtime_archive = site_packages / "attest-runtime.zip"
with zipfile.ZipFile(
    runtime_archive,
    mode="w",
    compression=zipfile.ZIP_STORED,
) as archive:
    for name in runtime_archive_roots:
        root = site_packages / name
        if not root.is_dir() or any(root.rglob("*.so")):
            raise RuntimeError(f"unsafe runtime archive root: {name}")
        for path in sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        ):
            metadata = zipfile.ZipInfo(
                path.relative_to(site_packages).as_posix(),
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            metadata.compress_type = zipfile.ZIP_STORED
            metadata.create_system = 3
            metadata.external_attr = 0o100644 << 16
            archive.writestr(metadata, path.read_bytes())
for name in runtime_archive_roots:
    shutil.rmtree(site_packages / name)
(site_packages / "attest-runtime-archive.pth").write_text(
    f"{runtime_archive}\n",
    encoding="utf-8",
)

archive_path = standard_library.parent / "python312.zip"
archive_members = sorted(
    path
    for path in standard_library.rglob("*")
    if path.is_file()
    and "__pycache__" not in path.parts
    and path.suffix in {".py", ".pyc"}
)
with zipfile.ZipFile(
    archive_path,
    mode="w",
    compression=zipfile.ZIP_DEFLATED,
    compresslevel=9,
) as archive:
    for path in archive_members:
        metadata = zipfile.ZipInfo(
            path.relative_to(standard_library).as_posix(),
            date_time=(1980, 1, 1, 0, 0, 0),
        )
        metadata.compress_type = zipfile.ZIP_DEFLATED
        metadata.create_system = 3
        metadata.external_attr = 0o100644 << 16
        archive.writestr(metadata, path.read_bytes(), compresslevel=9)
for path in archive_members:
    path.unlink()
for root in roots:
    for cache in sorted(root.rglob("__pycache__"), reverse=True):
        shutil.rmtree(cache)
for metadata_root in sorted(site_packages.glob("*.dist-info")):
    for path in sorted(metadata_root.iterdir()):
        if (
            path.name == "METADATA"
            or path.name == "licenses"
            or path.name.startswith(("LICENSE", "COPYING", "NOTICE"))
        ):
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
for directory in sorted(standard_library.rglob("*"), reverse=True):
    if directory.is_dir():
        try:
            directory.rmdir()
        except OSError:
            pass
PYTHON

FROM scratch AS system-lib
COPY --from=runtime /usr/lib /usr/lib

FROM runtime AS system-git-files
RUN destination=/split \
    && mkdir -p \
        "${destination}/usr/bin" \
        "${destination}/usr/libexec/git-core" \
    && cp /usr/bin/git "${destination}/usr/bin/git" \
    && ln -s git "${destination}/usr/bin/git-receive-pack" \
    && ln -s git "${destination}/usr/bin/git-upload-pack" \
    && cp \
        /usr/libexec/git-core/git-remote-http \
        "${destination}/usr/libexec/git-core/git-remote-http" \
    && ln -s \
        git-remote-http \
        "${destination}/usr/libexec/git-core/git-remote-https"

FROM scratch AS system-git
COPY --from=system-git-files /split/ /

FROM runtime AS system-core-files
RUN destination=/split \
    && mkdir -p \
        "${destination}/bin" \
        "${destination}/etc/ssl/certs" \
        "${destination}/lib" \
        "${destination}/usr/share/zoneinfo" \
    && mkdir -m 1777 "${destination}/tmp" \
    && cp /bin/busybox "${destination}/bin/busybox" \
    && ln -s /bin/busybox "${destination}/bin/sh" \
    && cp \
        /etc/alpine-release \
        /etc/group \
        /etc/passwd \
        "${destination}/etc/" \
    && ln -s ../usr/lib/os-release "${destination}/etc/os-release" \
    && cp \
        /etc/ssl/certs/ca-certificates.crt \
        "${destination}/etc/ssl/certs/ca-certificates.crt" \
    && ln -s certs/ca-certificates.crt "${destination}/etc/ssl/cert.pem" \
    && cp \
        /etc/ssl/ct_log_list.cnf \
        /etc/ssl/openssl.cnf \
        "${destination}/etc/ssl/" \
    && cp -a \
        /lib/ld-musl-*.so.1 \
        /lib/libc.musl-*.so.1 \
        "${destination}/lib/" \
    && cp \
        /usr/share/zoneinfo/UTC \
        "${destination}/usr/share/zoneinfo/UTC"

FROM scratch AS system-core
COPY --from=system-core-files /split/ /

FROM runtime AS python-lib
RUN rm -rf \
        /usr/local/lib/python3.12 \
        /usr/local/lib/python312.zip

FROM scratch AS python-dynload
COPY --from=runtime \
    /usr/local/lib/python3.12/lib-dynload \
    /usr/local/lib/python3.12/lib-dynload

FROM scratch AS python-rest
COPY --from=runtime /usr/local/bin /usr/local/bin
COPY --from=runtime /usr/local/share /usr/local/share
COPY --from=runtime /usr/local/lib/python312.zip /usr/local/lib/python312.zip
COPY --from=runtime \
    /usr/local/lib/python3.12/LICENSE.txt \
    /usr/local/lib/python3.12/LICENSE.txt
COPY --from=runtime /usr/local/lib/python3.12/ctypes /usr/local/lib/python3.12/ctypes
COPY --from=runtime /usr/local/lib/python3.12/email /usr/local/lib/python3.12/email
COPY --from=runtime \
    /usr/local/lib/python3.12/site-packages \
    /usr/local/lib/python3.12/site-packages

FROM runtime AS venv-crypto
RUN destination=/split/opt/venv/lib/python3.12/site-packages \
    && mkdir -p "${destination}" \
    && cp -a \
        /opt/venv/lib/python3.12/site-packages/_cffi_backend.*.so \
        /opt/venv/lib/python3.12/site-packages/cryptography \
        "${destination}/"

FROM runtime AS venv-rfc3161
RUN destination=/split/opt/venv/lib/python3.12/site-packages \
    && mkdir -p "${destination}" \
    && cp -a \
        /opt/venv/lib/python3.12/site-packages/rfc3161_client \
        /opt/venv/lib/python3.12/site-packages/rfc3161_client.libs \
        "${destination}/"

FROM runtime AS venv-pydantic
RUN destination=/split/opt/venv/lib/python3.12/site-packages \
    && mkdir -p "${destination}" \
    && cp -a \
        /opt/venv/lib/python3.12/site-packages/pydantic_core \
        /opt/venv/lib/python3.12/site-packages/pydantic_core.libs \
        "${destination}/"

FROM runtime AS venv-rest
RUN rm -rf \
        /opt/venv/lib/python3.12/site-packages/_cffi_backend.*.so \
        /opt/venv/lib/python3.12/site-packages/cryptography \
        /opt/venv/lib/python3.12/site-packages/pydantic_core \
        /opt/venv/lib/python3.12/site-packages/pydantic_core.libs \
        /opt/venv/lib/python3.12/site-packages/rfc3161_client \
        /opt/venv/lib/python3.12/site-packages/rfc3161_client.libs

# Balance the runtime across Docker's three concurrent layer downloads.
FROM scratch AS pull-a
COPY --from=system-lib / /
COPY --from=venv-pydantic /split/ /
COPY --from=python-lib /usr/local/lib /usr/local/lib

FROM scratch AS pull-b
COPY --from=venv-crypto /split/ /
COPY --from=venv-rfc3161 /split/ /
COPY --from=python-rest / /
COPY --from=system-git / /

FROM scratch AS pull-c
COPY --from=venv-rest /opt/venv /opt/venv
COPY --from=python-dynload / /
COPY --from=system-core / /

FROM scratch
COPY --from=pull-a / /
COPY --from=pull-b / /
COPY --from=pull-c / /
COPY --from=runtime /opt/attest /opt/attest

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/opt/venv/bin:/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    PYTHONSAFEPATH=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

ENTRYPOINT ["/opt/venv/bin/python", "-I", "/opt/attest/entrypoint.py"]
