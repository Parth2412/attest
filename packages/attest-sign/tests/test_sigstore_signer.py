"""Acceptance tests for bounded keyless Sigstore signing."""

from __future__ import annotations

import json
import multiprocessing
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Never, cast

import pytest
from sigstore.models import Bundle as SigstoreBundle
from sigstore.oidc import IdentityToken

from attest_core import Statement
from attest_sign import Bundle, SigningEnvironment, SigstoreSigner
from attest_sign import sigstore_signer as module
from attest_sign.errors import SignError, sign_error


def _bundle_wire(*, integrated_time: str | None = None) -> dict[str, object]:
    entry: dict[str, object] = {
        "integratedTime": "0",
        "logIndex": "42",
        "kindVersion": {"kind": "hashedrekord", "version": "0.0.2"},
        "inclusionProof": {
            "checkpoint": {"envelope": "checkpoint"},
            "rootHash": "cm9vdA==",
            "treeSize": "43",
            "hashes": [],
        },
    }
    timestamps: list[dict[str, str]] = [{"signedTimestamp": "dGltZXN0YW1w"}]
    if integrated_time is not None:
        entry["integratedTime"] = integrated_time
        entry["inclusionPromise"] = {"signedEntryTimestamp": "c2V0"}
        timestamps = []
    return {
        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "verificationMaterial": {
            "certificate": {"rawBytes": "Y2VydA=="},
            "tlogEntries": [entry],
            "timestampVerificationData": {"rfc3161Timestamps": timestamps},
        },
        "dsseEnvelope": {
            "payload": "cGF5bG9hZA==",
            "payloadType": "application/vnd.in-toto+json",
            "signatures": [{"sig": "c2ln"}],
        },
    }


def _success(raw: bytes | None = None) -> module._SuccessMessage:
    return module._SuccessMessage(
        raw=raw or json.dumps(_bundle_wire()).encode(),
        identity="https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/main",
        issuer="https://token.actions.githubusercontent.com",
    )


class _CaptureConnection:
    def __init__(self) -> None:
        self.messages: list[object] = []
        self.closed = False

    def send(self, value: object) -> None:
        self.messages.append(value)

    def close(self) -> None:
        self.closed = True


class _BrokenConnection(_CaptureConnection):
    def send(self, value: object) -> None:
        del value
        raise BrokenPipeError


class _QueueConnection:
    def __init__(self, messages: list[object]) -> None:
        self.messages = messages
        self.closed = False

    def poll(self, timeout: float = 0.0) -> bool:
        del timeout
        return bool(self.messages)

    def recv(self) -> object:
        return self.messages.pop(0)

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, *, alive: bool = False, start_failure: bool = False) -> None:
        self.alive = alive
        self.start_failure = start_failure
        self.started = False
        self.terminated = False
        self.killed = False
        self.joined: list[float | None] = []
        self.closed = False

    def start(self) -> None:
        if self.start_failure:
            raise RuntimeError
        self.started = True

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.alive = False

    def join(self, timeout: float | None = None) -> None:
        self.joined.append(timeout)

    def close(self) -> None:
        self.closed = True


class _FakeMultiprocessingContext:
    def __init__(
        self,
        process: _FakeProcess,
        receive: _QueueConnection,
        send: _CaptureConnection,
    ) -> None:
        self.process = process
        self.receive = receive
        self.send = send
        self.process_arguments: dict[str, object] | None = None

    def Pipe(self, *, duplex: bool) -> tuple[_QueueConnection, _CaptureConnection]:  # noqa: N802
        assert duplex is False
        return self.receive, self.send

    def Process(self, **kwargs: object) -> _FakeProcess:  # noqa: N802
        self.process_arguments = kwargs
        return self.process


class _FakeToken:
    identity = "repo:Org/Repo:pull_request"
    federated_issuer = "https://token.actions.githubusercontent.com"


class _FakeBundle:
    signing_certificate = object()

    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def to_json(self) -> str:
        return self._raw.decode()


class _FakeIdentityPolicy:
    observed: tuple[str, str, object] | None = None

    def __init__(self, *, identity: str, issuer: str) -> None:
        self._identity = identity
        self._issuer = issuer

    def verify(self, certificate: object) -> None:
        type(self).observed = (self._identity, self._issuer, certificate)


class _FakeUpstreamSigner:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls = 0

    def sign_dsse(self, statement: object) -> _FakeBundle:
        del statement
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return _FakeBundle(json.dumps(_bundle_wire()).encode())


class _FakeContext:
    def __init__(
        self,
        upstream: _FakeUpstreamSigner,
        *,
        enter_failure: Exception | None = None,
    ) -> None:
        self.upstream = upstream
        self.enter_failure = enter_failure
        self.signer_calls: list[tuple[object, dict[str, object]]] = []

    @contextmanager
    def signer(self, token: object, **kwargs: object) -> Iterator[_FakeUpstreamSigner]:
        self.signer_calls.append((token, kwargs))
        if self.enter_failure is not None:
            raise self.enter_failure
        yield self.upstream


def _install_successful_boundary(
    monkeypatch: pytest.MonkeyPatch,
    context: _FakeContext,
) -> None:
    class FakeSigningContext:
        @classmethod
        def from_trust_config(cls, trust_config: object) -> _FakeContext:
            assert trust_config == "staging-trust"
            return context

    monkeypatch.setattr(module, "_load_trust_config", lambda environment: "staging-trust")
    monkeypatch.setattr(module, "detect_credential", lambda: "secret-ambient-token")
    monkeypatch.setattr(module, "IdentityToken", lambda credential: _FakeToken())
    monkeypatch.setattr(module, "SigningContext", FakeSigningContext)
    monkeypatch.setattr(module, "Identity", _FakeIdentityPolicy)
    monkeypatch.setattr(module, "to_sigstore_statement", lambda statement: object())
    monkeypatch.setenv(
        "GITHUB_WORKFLOW_REF",
        "Org/Repo/.github/workflows/attest.yml@refs/heads/main",
    )


@pytest.mark.ac("AC-F06-030")
@pytest.mark.ac("AC-F06-080")
@pytest.mark.ac("AC-F06-110")
def test_one_context_signs_with_ambient_identity_and_validates_certificate(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
    tmp_path: Path,
) -> None:
    """REQ-F06-030/080/110: ambient keyless signing uses one in-memory context."""
    upstream = _FakeUpstreamSigner()
    context = _FakeContext(upstream)
    _install_successful_boundary(monkeypatch, context)
    stages: list[module._WorkerStage] = []

    result = module._sign_once(statement, SigningEnvironment.STAGING, stages.append)

    assert [stage.value for stage in stages] == ["identity", "configuration", "fulcio", "rekor"]
    assert len(context.signer_calls) == 1
    assert isinstance(context.signer_calls[0][0], _FakeToken)
    assert context.signer_calls[0][1] == {}
    assert upstream.calls == 1
    expected_identity = "https://github.com/Org/Repo/.github/workflows/attest.yml@refs/heads/main"
    assert result.identity == expected_identity
    assert result.issuer == _FakeToken.federated_issuer
    assert _FakeIdentityPolicy.observed == (
        expected_identity,
        _FakeToken.federated_issuer,
        _FakeBundle.signing_certificate,
    )
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.ac("AC-F06-040")
def test_missing_ambient_identity_is_noninteractive_and_actionable(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
) -> None:
    """REQ-F06-040: missing ambient OIDC fails without opening an interactive flow."""
    monkeypatch.setattr(module, "_load_trust_config", lambda environment: object())
    monkeypatch.setattr(module, "detect_credential", lambda: None)

    with pytest.raises(SignError) as captured:
        module._sign_once(statement, SigningEnvironment.STAGING, lambda stage: None)

    assert captured.value.code == "ERR-SIGN-301"
    assert "id-token: write" in captured.value.remediation
    assert captured.value.__cause__ is None
    assert not hasattr(module, "Issuer")


@pytest.mark.ac("AC-F06-060")
def test_rekor_failure_returns_only_sanitized_error(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
    tmp_path: Path,
) -> None:
    """REQ-F06-060: a Rekor failure cannot return or write a bundle."""
    secret = "ghs_this_must_never_escape"
    upstream = _FakeUpstreamSigner(failure=RuntimeError(secret))
    context = _FakeContext(upstream)
    _install_successful_boundary(monkeypatch, context)

    with pytest.raises(SignError) as captured:
        module._sign_once(statement, SigningEnvironment.STAGING, lambda stage: None)

    assert captured.value.code == "ERR-SIGN-303"
    assert secret not in str(captured.value)
    assert captured.value.__cause__ is None
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.parametrize(
    ("boundary", "expected_code"),
    [("configuration", "ERR-SIGN-306"), ("fulcio", "ERR-SIGN-302")],
)
def test_upstream_failures_map_at_the_public_stage(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
    boundary: str,
    expected_code: str,
) -> None:
    """REQ-F06-120/130: stage errors are stable and contain no upstream diagnostic."""
    secret = "eyJhbGciOiJub25lIn0.secret.signature"
    if boundary == "configuration":
        monkeypatch.setattr(module, "detect_credential", lambda: "secret-ambient-token")
        monkeypatch.setattr(module, "IdentityToken", lambda credential: _FakeToken())

        def fail_config(environment: SigningEnvironment) -> Never:
            del environment
            raise RuntimeError(secret)

        monkeypatch.setattr(module, "_load_trust_config", fail_config)
    else:
        context = _FakeContext(
            _FakeUpstreamSigner(),
            enter_failure=RuntimeError(secret),
        )
        _install_successful_boundary(monkeypatch, context)

    with pytest.raises(SignError) as captured:
        module._sign_once(statement, SigningEnvironment.STAGING, lambda stage: None)

    assert captured.value.code == expected_code
    assert secret not in str(captured.value)
    assert captured.value.__cause__ is None


@pytest.mark.parametrize(
    ("boundary", "expected_code"),
    [
        ("statement", "ERR-SIGN-305"),
        ("credential", "ERR-SIGN-301"),
        ("token", "ERR-SIGN-301"),
        ("configuration", "ERR-SIGN-306"),
        ("certificate", "ERR-SIGN-305"),
        ("github-context", "ERR-SIGN-305"),
    ],
)
def test_additional_boundary_failures_are_stable(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
    boundary: str,
    expected_code: str,
) -> None:
    """REQ-F06-040/100/130: every adapter boundary fails with a stable code."""
    context = _FakeContext(_FakeUpstreamSigner())
    _install_successful_boundary(monkeypatch, context)

    def fail() -> Never:
        raise RuntimeError("private")

    if boundary == "statement":
        monkeypatch.setattr(module, "to_sigstore_statement", lambda statement: fail())
    elif boundary == "credential":
        monkeypatch.setattr(module, "detect_credential", fail)
    elif boundary == "token":
        monkeypatch.setattr(module, "IdentityToken", lambda credential: fail())
    elif boundary == "configuration":

        def fail_configuration(environment: SigningEnvironment) -> Never:
            del environment
            raise sign_error("ERR-SIGN-306")

        monkeypatch.setattr(module, "_load_trust_config", fail_configuration)
    elif boundary == "github-context":
        monkeypatch.delenv("GITHUB_WORKFLOW_REF")
    else:

        class RejectIdentity:
            def __init__(self, *, identity: str, issuer: str) -> None:
                del identity, issuer

            def verify(self, certificate: object) -> Never:
                del certificate
                fail()

        monkeypatch.setattr(module, "Identity", RejectIdentity)

    with pytest.raises(SignError) as captured:
        module._sign_once(statement, SigningEnvironment.STAGING, lambda stage: None)

    assert captured.value.code == expected_code
    assert "private" not in str(captured.value)
    assert captured.value.__cause__ is None


def test_non_github_identity_uses_sigstore_token_identity() -> None:
    """REQ-F06-110: other ambient providers retain Sigstore's detected identity."""

    class OtherProviderToken:
        identity = "builder@example.com"

    token = cast(IdentityToken, OtherProviderToken())

    assert module._certificate_identity(token, "https://accounts.google.com") == token.identity


@pytest.mark.ac("AC-F06-050")
@pytest.mark.ac("AC-F06-100")
def test_bundle_postconditions_accept_both_signed_time_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-F06-050/100: a complete v1- or v2-style bundle result is accepted."""
    monkeypatch.setattr(SigstoreBundle, "from_json", lambda raw: object())

    v2 = module._bundle_from_success(_success(), SigningEnvironment.STAGING)
    v1 = module._bundle_from_success(
        _success(json.dumps(_bundle_wire(integrated_time="1700000000")).encode()),
        SigningEnvironment.STAGING,
    )

    assert isinstance(v2, Bundle)
    assert v2.log_index == 42
    assert v2.log_integrated_time is None
    assert v1.log_integrated_time == datetime.fromtimestamp(1700000000, tz=UTC)


def _remove_dsse(wire: dict[str, object]) -> None:
    wire.pop("dsseEnvelope")


def _remove_certificate(wire: dict[str, object]) -> None:
    cast(dict[str, object], wire["verificationMaterial"]).pop("certificate")


def _remove_log_entry(wire: dict[str, object]) -> None:
    cast(dict[str, object], wire["verificationMaterial"])["tlogEntries"] = []


def _remove_inclusion_proof(wire: dict[str, object]) -> None:
    material = cast(dict[str, object], wire["verificationMaterial"])
    entry = cast(list[dict[str, object]], material["tlogEntries"])[0]
    entry.pop("inclusionProof")


def _remove_checkpoint(wire: dict[str, object]) -> None:
    material = cast(dict[str, object], wire["verificationMaterial"])
    entry = cast(list[dict[str, object]], material["tlogEntries"])[0]
    cast(dict[str, object], entry["inclusionProof"]).pop("checkpoint")


def _remove_signed_time(wire: dict[str, object]) -> None:
    material = cast(dict[str, object], wire["verificationMaterial"])
    cast(dict[str, object], material["timestampVerificationData"])["rfc3161Timestamps"] = []


def _empty_payload(wire: dict[str, object]) -> None:
    cast(dict[str, object], wire["dsseEnvelope"])["payload"] = ""


def _replace_payload_type(wire: dict[str, object]) -> None:
    cast(dict[str, object], wire["dsseEnvelope"])["payloadType"] = "text/plain"


def _remove_signatures(wire: dict[str, object]) -> None:
    cast(dict[str, object], wire["dsseEnvelope"])["signatures"] = []


def _boolean_log_index(wire: dict[str, object]) -> None:
    material = cast(dict[str, object], wire["verificationMaterial"])
    cast(list[dict[str, object]], material["tlogEntries"])[0]["logIndex"] = True


def _invalid_log_index(wire: dict[str, object]) -> None:
    material = cast(dict[str, object], wire["verificationMaterial"])
    cast(list[dict[str, object]], material["tlogEntries"])[0]["logIndex"] = "+42"


def _negative_log_index(wire: dict[str, object]) -> None:
    material = cast(dict[str, object], wire["verificationMaterial"])
    cast(list[dict[str, object]], material["tlogEntries"])[0]["logIndex"] = -1


def _zero_tree_size(wire: dict[str, object]) -> None:
    material = cast(dict[str, object], wire["verificationMaterial"])
    entry = cast(list[dict[str, object]], material["tlogEntries"])[0]
    cast(dict[str, object], entry["inclusionProof"])["treeSize"] = "0"


def _invalid_proof_hashes(wire: dict[str, object]) -> None:
    material = cast(dict[str, object], wire["verificationMaterial"])
    entry = cast(list[dict[str, object]], material["tlogEntries"])[0]
    cast(dict[str, object], entry["inclusionProof"])["hashes"] = {}


@pytest.mark.ac("AC-F06-100")
@pytest.mark.parametrize(
    "mutate",
    [
        _remove_dsse,
        _remove_certificate,
        _remove_log_entry,
        _remove_inclusion_proof,
        _remove_checkpoint,
        _remove_signed_time,
        _empty_payload,
        _replace_payload_type,
        _remove_signatures,
        _boolean_log_index,
        _invalid_log_index,
        _negative_log_index,
        _zero_tree_size,
        _invalid_proof_hashes,
    ],
)
def test_incomplete_bundle_never_crosses_the_signer_boundary(
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    """REQ-F06-100: every required bundle postcondition fails closed."""
    monkeypatch.setattr(SigstoreBundle, "from_json", lambda raw: object())
    wire = _bundle_wire()
    mutate(wire)

    with pytest.raises(SignError) as captured:
        module._bundle_from_success(
            _success(json.dumps(wire).encode()),
            SigningEnvironment.STAGING,
        )

    assert captured.value.code == "ERR-SIGN-305"
    assert captured.value.__cause__ is None


@pytest.mark.ac("AC-F06-100")
def test_bundle_postconditions_reject_invalid_top_level_and_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-F06-100: structure and reported identity must both be usable."""
    monkeypatch.setattr(SigstoreBundle, "from_json", lambda raw: object())

    invalid_results = (
        _success(b"[]"),
        module._SuccessMessage(
            raw=json.dumps(_bundle_wire()).encode(),
            identity="",
            issuer="https://token.actions.githubusercontent.com",
        ),
    )
    for success in invalid_results:
        with pytest.raises(SignError) as captured:
            module._bundle_from_success(success, SigningEnvironment.STAGING)
        assert captured.value.code == "ERR-SIGN-305"


def test_trust_configuration_maps_each_explicit_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-F06-070: each explicit environment selects only its matching root."""

    class FakeClientTrustConfig:
        @classmethod
        def production(cls) -> str:
            return "production-root"

        @classmethod
        def staging(cls) -> str:
            return "staging-root"

    monkeypatch.setattr(module, "ClientTrustConfig", FakeClientTrustConfig)
    production = next(item for item in SigningEnvironment if item.value == "production")

    assert cast(str, module._load_trust_config(production)) == "production-root"
    assert cast(str, module._load_trust_config(SigningEnvironment.STAGING)) == "staging-root"
    with pytest.raises(SignError) as captured:
        module._load_trust_config(cast(SigningEnvironment, "invalid"))
    assert captured.value.code == "ERR-SIGN-306"


@pytest.mark.parametrize(
    ("terminal", "expected_code"),
    [
        (module._FailureMessage("ERR-SIGN-302"), "ERR-SIGN-302"),
        (object(), "ERR-SIGN-305"),
        (None, "ERR-SIGN-305"),
    ],
)
def test_supervisor_maps_worker_terminal_states(
    terminal: object | None,
    expected_code: str,
) -> None:
    """REQ-F06-120/130: worker failures and crashes cross as project codes only."""
    messages = [] if terminal is None else [terminal]
    process = _FakeProcess()
    connection = _QueueConnection(messages)

    with pytest.raises(SignError) as captured:
        module._supervise_process(process, connection, timedelta(seconds=1))

    assert captured.value.code == expected_code
    assert process.joined == [None]


def test_supervisor_returns_only_a_complete_success() -> None:
    """REQ-F06-100/120: stage messages precede one complete terminal result."""
    expected = _success()
    connection = _QueueConnection([module._StageMessage(module._WorkerStage.FULCIO), expected])
    process = _FakeProcess()

    actual = module._supervise_process(process, connection, timedelta(seconds=1))

    assert actual is expected
    assert process.joined == [None]


def test_forced_process_shutdown_escalates_to_kill() -> None:
    """REQ-F06-120: an uncooperative worker is killed after its grace period."""
    process = _FakeProcess(alive=True)

    module._terminate_process(process)

    assert process.terminated
    assert process.killed
    assert process.joined == [module._PROCESS_SHUTDOWN_GRACE_SECONDS, None]


def test_execute_attempt_owns_and_closes_its_process_resources(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
) -> None:
    """REQ-F06-120: the process wrapper starts, supervises, and closes one worker."""
    expected = _success()
    process = _FakeProcess()
    receive = _QueueConnection([])
    send = _CaptureConnection()
    context = _FakeMultiprocessingContext(process, receive, send)
    monkeypatch.setattr(multiprocessing, "get_context", lambda method: context)
    monkeypatch.setattr(
        module,
        "_supervise_process",
        lambda child, connection, timeout: expected,
    )

    actual = module._execute_attempt(
        statement,
        SigningEnvironment.STAGING,
        timedelta(seconds=1),
    )

    assert actual is expected
    assert process.started
    assert process.closed
    assert receive.closed
    assert send.closed
    assert context.process_arguments == {
        "target": module._signing_worker,
        "args": (send, statement, SigningEnvironment.STAGING),
        "name": "attest-sigstore-sign",
    }


def test_execute_attempt_maps_process_start_failure(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
) -> None:
    """REQ-F06-120/130: process initialization failure is coded and cleaned up."""
    process = _FakeProcess(start_failure=True)
    receive = _QueueConnection([])
    send = _CaptureConnection()
    context = _FakeMultiprocessingContext(process, receive, send)
    monkeypatch.setattr(multiprocessing, "get_context", lambda method: context)

    with pytest.raises(SignError) as captured:
        module._execute_attempt(
            statement,
            SigningEnvironment.STAGING,
            timedelta(seconds=1),
        )

    assert captured.value.code == "ERR-SIGN-306"
    assert process.closed
    assert receive.closed
    assert send.closed


def test_public_signer_validates_input_and_returns_validated_bundle(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
) -> None:
    """REQ-F06-100: the public operation rejects invalid input and validates success."""
    signer = SigstoreSigner(environment=SigningEnvironment.STAGING)
    with pytest.raises(SignError) as captured:
        signer.sign(cast(Statement, object()))
    assert captured.value.code == "ERR-SIGN-305"

    monkeypatch.setattr(module, "_execute_attempt", lambda *arguments: _success())
    monkeypatch.setattr(SigstoreBundle, "from_json", lambda raw: object())

    result = signer.sign(statement)

    assert result.environment is SigningEnvironment.STAGING
    assert result.log_index == 42


@pytest.mark.ac("AC-F06-120")
def test_timeout_retries_only_before_rekor(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
) -> None:
    """REQ-F06-120: pre-Rekor gets two attempts; Rekor gets exactly one."""
    attempts: list[module._WorkerStage] = []

    def timeout_before_rekor(
        supplied: Statement,
        environment: SigningEnvironment,
        timeout: timedelta,
    ) -> Never:
        del supplied, environment, timeout
        attempts.append(module._WorkerStage.FULCIO)
        raise module._AttemptTimeoutError(module._WorkerStage.FULCIO)

    monkeypatch.setattr(module, "_execute_attempt", timeout_before_rekor)
    signer = SigstoreSigner(
        environment=SigningEnvironment.STAGING,
        attempt_timeout=timedelta(milliseconds=10),
    )

    with pytest.raises(SignError) as captured:
        signer.sign(statement)
    assert captured.value.code == "ERR-SIGN-304"
    assert len(attempts) == 2

    attempts.clear()

    def timeout_at_rekor(
        supplied: Statement,
        environment: SigningEnvironment,
        timeout: timedelta,
    ) -> Never:
        del supplied, environment, timeout
        attempts.append(module._WorkerStage.REKOR)
        raise module._AttemptTimeoutError(module._WorkerStage.REKOR)

    monkeypatch.setattr(module, "_execute_attempt", timeout_at_rekor)
    with pytest.raises(SignError) as captured:
        signer.sign(statement)
    assert captured.value.code == "ERR-SIGN-304"
    assert len(attempts) == 1


@pytest.mark.ac("AC-F06-120")
def test_supervisor_terminates_a_hanging_process() -> None:
    """REQ-F06-120: the real process boundary cannot survive its deadline."""
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=time.sleep, args=(5,))
    process.start()
    send.close()

    try:
        with pytest.raises(module._AttemptTimeoutError):
            module._supervise_process(
                process,
                receive,
                timedelta(milliseconds=50),
            )
        assert not process.is_alive()
    finally:
        receive.close()
        if process.is_alive():
            process.kill()
            process.join()
        process.close()


@pytest.mark.ac("AC-F06-130")
def test_worker_discards_exception_text_and_token_like_values(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """REQ-F06-130: child-process failures expose only stable project codes."""
    secret = "ghs_FAKE_0123456789abcdefghijklmnopqrstuvwxyz"

    def fail_once(
        supplied: Statement,
        environment: SigningEnvironment,
        emit_stage: object,
    ) -> Never:
        del supplied, environment, emit_stage
        raise RuntimeError(secret)

    monkeypatch.setattr(module, "_sign_once", fail_once)
    connection = _CaptureConnection()

    module._signing_worker(connection, statement, SigningEnvironment.STAGING)

    captured = capsys.readouterr()
    rendered = repr(connection.messages) + captured.out + captured.err
    assert connection.closed
    assert connection.messages == [module._FailureMessage("ERR-SIGN-305")]
    assert secret not in rendered


def test_worker_preserves_only_codes_and_tolerates_a_closed_parent(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
) -> None:
    """REQ-F06-130: known failures remain coded even if the parent pipe closes."""

    def fail_with_code(
        supplied: Statement,
        environment: SigningEnvironment,
        emit_stage: object,
    ) -> Never:
        del supplied, environment, emit_stage
        raise sign_error("ERR-SIGN-302")

    monkeypatch.setattr(module, "_sign_once", fail_with_code)
    connection = _CaptureConnection()
    module._signing_worker(connection, statement, SigningEnvironment.STAGING)
    assert connection.messages == [module._FailureMessage("ERR-SIGN-302")]

    monkeypatch.setattr(module, "_sign_once", lambda *arguments: _success())
    broken = _BrokenConnection()
    module._signing_worker(broken, statement, SigningEnvironment.STAGING)
    assert broken.closed
