"""Fail-bounded keyless Sigstore signing governed by BRD-F06 and ADR-037."""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Never, Protocol, TypeGuard, cast

from sigstore.models import Bundle as SigstoreBundle
from sigstore.models import ClientTrustConfig
from sigstore.oidc import IdentityToken, detect_credential
from sigstore.sign import SigningContext
from sigstore.verify.policy import Identity

from attest_core.constants import DSSE_PAYLOAD_TYPE
from attest_core.models.statement import Statement
from attest_sign.dsse import to_sigstore_statement
from attest_sign.errors import SignError, SignErrorCode, sign_error
from attest_sign.protocols import Bundle, SigningEnvironment

_DEFAULT_ATTEMPT_TIMEOUT = timedelta(seconds=120)
_MAX_PRE_REKOR_ATTEMPTS = 2
_PROCESS_SHUTDOWN_GRACE_SECONDS = 1.0
_PROCESS_POLL_SECONDS = 0.05
_GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"


class _WorkerStage(StrEnum):
    CONFIGURATION = "configuration"
    IDENTITY = "identity"
    FULCIO = "fulcio"
    REKOR = "rekor"


@dataclass(frozen=True, slots=True)
class _StageMessage:
    stage: _WorkerStage


@dataclass(frozen=True, slots=True)
class _SuccessMessage:
    raw: bytes
    identity: str
    issuer: str


@dataclass(frozen=True, slots=True)
class _FailureMessage:
    code: SignErrorCode


type _WorkerMessage = _StageMessage | _SuccessMessage | _FailureMessage


class _SendConnection(Protocol):
    def send(self, value: object) -> None: ...

    def close(self) -> None: ...


class _ReceiveConnection(Protocol):
    def poll(self, timeout: float = 0.0) -> bool: ...

    def recv(self) -> object: ...

    def close(self) -> None: ...


class _Process(Protocol):
    def start(self) -> None: ...

    def is_alive(self) -> bool: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def join(self, timeout: float | None = None) -> None: ...

    def close(self) -> None: ...


class _AttemptTimeoutError(RuntimeError):
    def __init__(self, stage: _WorkerStage | None) -> None:
        self.stage = stage
        super().__init__("isolated signing attempt exceeded its deadline")


class _AmbientIdentityError(ValueError):
    """Signal missing provider context needed to identify the leaf certificate."""


def _certificate_identity(identity_token: IdentityToken, issuer: str) -> str:
    if issuer != _GITHUB_OIDC_ISSUER:
        return identity_token.identity
    workflow_ref = os.environ.get("GITHUB_WORKFLOW_REF")
    if not workflow_ref:
        raise _AmbientIdentityError
    return f"https://github.com/{workflow_ref}"


def _load_trust_config(environment: SigningEnvironment) -> ClientTrustConfig:
    if environment is SigningEnvironment.PRODUCTION:
        return ClientTrustConfig.production()
    if environment is SigningEnvironment.STAGING:
        return ClientTrustConfig.staging()
    raise sign_error("ERR-SIGN-306")


def _sign_once(
    statement: Statement,
    environment: SigningEnvironment,
    emit_stage: Callable[[_WorkerStage], None],
) -> _SuccessMessage:
    """Perform one stage-reported Sigstore operation inside a worker process."""
    try:
        dsse_statement = to_sigstore_statement(statement)
    except Exception:
        raise sign_error("ERR-SIGN-305") from None

    emit_stage(_WorkerStage.IDENTITY)
    try:
        credential = detect_credential()
    except Exception:
        raise sign_error("ERR-SIGN-301") from None
    if credential is None:
        raise sign_error("ERR-SIGN-301")
    try:
        identity_token = IdentityToken(credential)
    except Exception:
        raise sign_error("ERR-SIGN-301") from None

    emit_stage(_WorkerStage.CONFIGURATION)
    try:
        trust_config = _load_trust_config(environment)
        signing_context = SigningContext.from_trust_config(trust_config)
    except SignError:
        raise
    except Exception:
        raise sign_error("ERR-SIGN-306") from None

    emit_stage(_WorkerStage.FULCIO)
    try:
        with signing_context.signer(identity_token) as signer:
            emit_stage(_WorkerStage.REKOR)
            try:
                sigstore_bundle = signer.sign_dsse(dsse_statement)
            except Exception:
                raise sign_error("ERR-SIGN-303") from None
    except SignError:
        raise
    except Exception:
        raise sign_error("ERR-SIGN-302") from None

    try:
        issuer = identity_token.federated_issuer
        identity = _certificate_identity(identity_token, issuer)
        Identity(identity=identity, issuer=issuer).verify(sigstore_bundle.signing_certificate)
        raw = sigstore_bundle.to_json().encode("utf-8")
    except Exception:
        raise sign_error("ERR-SIGN-305") from None

    return _SuccessMessage(raw=raw, identity=identity, issuer=issuer)


def _signing_worker(
    connection: _SendConnection,
    statement: Statement,
    environment: SigningEnvironment,
) -> None:
    """Run one signing attempt without exposing upstream diagnostics."""
    logging.disable(logging.CRITICAL)
    try:
        message: _SuccessMessage | _FailureMessage = _sign_once(
            statement,
            environment,
            lambda stage: connection.send(_StageMessage(stage)),
        )
    except SignError as error:
        message = _FailureMessage(error.code)
    except Exception:
        message = _FailureMessage("ERR-SIGN-305")

    try:
        connection.send(message)
    except (BrokenPipeError, EOFError, OSError):
        pass
    finally:
        connection.close()


def _terminate_process(process: _Process) -> None:
    if process.is_alive():
        process.terminate()
        process.join(_PROCESS_SHUTDOWN_GRACE_SECONDS)
    if process.is_alive():
        process.kill()
        process.join()


def _receive_message(connection: _ReceiveConnection) -> _WorkerMessage | None:
    try:
        message = connection.recv()
    except (EOFError, OSError):
        return None
    if isinstance(message, _StageMessage | _SuccessMessage | _FailureMessage):
        return message
    return _FailureMessage("ERR-SIGN-305")


def _supervise_process(
    process: _Process,
    connection: _ReceiveConnection,
    timeout: timedelta,
) -> _SuccessMessage:
    """Return a complete child result or terminate the process at its deadline."""
    deadline = time.monotonic() + timeout.total_seconds()
    stage: _WorkerStage | None = None
    terminal: _SuccessMessage | _FailureMessage | None = None

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            while connection.poll():
                message = _receive_message(connection)
                if message is None:
                    break
                if isinstance(message, _StageMessage):
                    stage = message.stage
                elif isinstance(message, _SuccessMessage | _FailureMessage):
                    terminal = message
            if process.is_alive():
                _terminate_process(process)
                raise _AttemptTimeoutError(stage)

        wait = max(0.0, min(_PROCESS_POLL_SECONDS, remaining))
        if connection.poll(wait):
            message = _receive_message(connection)
            if isinstance(message, _StageMessage):
                stage = message.stage
            elif isinstance(message, _SuccessMessage | _FailureMessage):
                terminal = message

        if not process.is_alive():
            process.join()
            while connection.poll():
                message = _receive_message(connection)
                if message is None:
                    break
                if isinstance(message, _StageMessage):
                    stage = message.stage
                elif isinstance(message, _SuccessMessage | _FailureMessage):
                    terminal = message
            if isinstance(terminal, _SuccessMessage):
                return terminal
            if isinstance(terminal, _FailureMessage):
                raise sign_error(terminal.code)
            raise sign_error("ERR-SIGN-305")


def _execute_attempt(
    statement: Statement,
    environment: SigningEnvironment,
    timeout: timedelta,
) -> _SuccessMessage:
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_signing_worker,
        args=(send, statement, environment),
        name="attest-sigstore-sign",
    )
    try:
        try:
            process.start()
        except Exception:
            raise sign_error("ERR-SIGN-306") from None
        finally:
            send.close()
        return _supervise_process(process, receive, timeout)
    finally:
        receive.close()
        if process.is_alive():
            _terminate_process(process)
        process.close()


class _InvalidBundleError(ValueError):
    """Signal one failed serialized-bundle postcondition."""


def _invalid_bundle() -> Never:
    raise _InvalidBundleError


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        _invalid_bundle()
    return cast(dict[str, object], value)


def _non_empty_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        _invalid_bundle()
    return value


def _non_negative_integer(value: object) -> int:
    if isinstance(value, bool):
        _invalid_bundle()
    if isinstance(value, str):
        if not value.isascii() or not value.isdecimal():
            _invalid_bundle()
        parsed: object = int(value)
    else:
        parsed = value
    if not isinstance(parsed, int) or parsed < 0:
        _invalid_bundle()
    return parsed


def _bundle_from_success(
    success: _SuccessMessage,
    environment: SigningEnvironment,
) -> Bundle:
    try:
        SigstoreBundle.from_json(success.raw)
        decoded: object = json.loads(success.raw)
        wire = _mapping(decoded)

        envelope = _mapping(wire["dsseEnvelope"])
        _non_empty_string(envelope["payload"])
        if envelope["payloadType"] != DSSE_PAYLOAD_TYPE:
            _invalid_bundle()
        signatures = envelope["signatures"]
        if not isinstance(signatures, list) or len(signatures) != 1:
            _invalid_bundle()

        material = _mapping(wire["verificationMaterial"])
        certificate = _mapping(material["certificate"])
        _non_empty_string(certificate["rawBytes"])
        entries = material["tlogEntries"]
        if not isinstance(entries, list) or len(entries) != 1:
            _invalid_bundle()
        entry = _mapping(entries[0])
        log_index = _non_negative_integer(entry["logIndex"])

        proof = _mapping(entry["inclusionProof"])
        checkpoint = _mapping(proof["checkpoint"])
        _non_empty_string(checkpoint["envelope"])
        _non_empty_string(proof["rootHash"])
        if _non_negative_integer(proof["treeSize"]) < 1:
            _invalid_bundle()
        if not isinstance(proof["hashes"], list):
            _invalid_bundle()

        integrated_value = entry.get("integratedTime")
        integrated_time: datetime | None = None
        has_log_time = False
        if integrated_value is not None:
            seconds = _non_negative_integer(integrated_value)
            inclusion_promise = entry.get("inclusionPromise")
            if seconds > 0 and inclusion_promise is not None:
                has_log_time = bool(_mapping(inclusion_promise))
                if has_log_time:
                    integrated_time = datetime.fromtimestamp(seconds, tz=UTC)

        timestamp_data = _mapping(material["timestampVerificationData"])
        timestamps = timestamp_data["rfc3161Timestamps"]
        has_rfc3161_time = isinstance(timestamps, list) and bool(timestamps)
        if not has_log_time and not has_rfc3161_time:
            _invalid_bundle()

        _non_empty_string(success.identity)
        _non_empty_string(success.issuer)
    except Exception:
        raise sign_error("ERR-SIGN-305") from None

    return Bundle(
        raw=success.raw,
        environment=environment,
        certificate_identity=success.identity,
        certificate_issuer=success.issuer,
        log_index=log_index,
        log_integrated_time=integrated_time,
    )


def _is_positive_timeout(value: object) -> TypeGuard[timedelta]:
    return isinstance(value, timedelta) and value > timedelta(0)


class SigstoreSigner:
    """Use an isolated ambient-identity Sigstore worker (REQ-F06-030/120)."""

    def __init__(
        self,
        *,
        environment: SigningEnvironment,
        attempt_timeout: timedelta = _DEFAULT_ATTEMPT_TIMEOUT,
    ) -> None:
        """Configure one explicit environment and hard deadline (REQ-F06-070/120)."""
        if not isinstance(environment, SigningEnvironment):
            raise sign_error("ERR-SIGN-306")
        if not _is_positive_timeout(attempt_timeout):
            raise sign_error("ERR-SIGN-306")
        self._environment = environment
        self._attempt_timeout = attempt_timeout

    def sign(self, statement: Statement) -> Bundle:
        """Sign without credential or key inputs (REQ-F06-090/100)."""
        if not isinstance(statement, Statement):
            raise sign_error("ERR-SIGN-305")

        attempts = 0
        while attempts < _MAX_PRE_REKOR_ATTEMPTS:
            attempts += 1
            try:
                success = _execute_attempt(
                    statement,
                    self._environment,
                    self._attempt_timeout,
                )
            except _AttemptTimeoutError as error:
                if error.stage is _WorkerStage.REKOR or attempts >= _MAX_PRE_REKOR_ATTEMPTS:
                    raise sign_error("ERR-SIGN-304") from None
                continue
            return _bundle_from_success(success, self._environment)

        raise sign_error("ERR-SIGN-304")  # pragma: no cover - loop is statically bounded
