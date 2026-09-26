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

ENV UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never

RUN apk add --no-cache binutils=2.45.1-r0 \
    && uv sync --frozen --no-dev --package attest-cli --no-editable \
    && find /opt/venv -type f -name '*.so' -exec strip --strip-unneeded {} + \
    && rm -rf \
        /opt/venv/lib/python3.12/site-packages/certifi/tests \
        /opt/venv/lib/python3.12/site-packages/jsonschema/tests \
        /opt/venv/lib/python3.12/site-packages/jsonschema_specifications/tests \
        /opt/venv/lib/python3.12/site-packages/oras/tests \
        /opt/venv/lib/python3.12/site-packages/referencing/tests \
        /opt/venv/lib/python3.12/site-packages/securesystemslib/_vendor/ed25519/test_data

FROM python:3.12.14-alpine3.23@sha256:d339953547bb5bc57eb5c1ff3224c40890ce56e494b13a52a574658e5a0f888a

RUN apk add --no-cache git=2.52.0-r0 \
    && rm -rf \
        /usr/local/bin/pip \
        /usr/local/bin/pip3 \
        /usr/local/bin/pip3.12 \
        /usr/local/lib/python3.12/site-packages/pip \
        /usr/local/lib/python3.12/site-packages/pip-25.0.1.dist-info \
        /usr/local/lib/python3.12/ensurepip \
        /usr/local/lib/python3.12/idlelib \
        /usr/local/lib/python3.12/lib2to3 \
        /usr/local/lib/python3.12/pydoc_data \
        /usr/local/lib/python3.12/tkinter \
        /usr/local/lib/python3.12/turtledemo

COPY --from=build /opt/venv /opt/venv
COPY action/entrypoint.py /opt/attest/entrypoint.py

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/opt/venv/bin:/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    PYTHONSAFEPATH=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

ENTRYPOINT ["/opt/venv/bin/python", "-I", "/opt/attest/entrypoint.py"]
