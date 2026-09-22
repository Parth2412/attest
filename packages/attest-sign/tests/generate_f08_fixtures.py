"""Generate provenance-pinned F-08 bundles in the dedicated OIDC workflow."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from datetime import UTC, datetime
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Any, Final, cast

from cryptography.x509 import SubjectAlternativeName, UniformResourceIdentifier
from sigstore.dsse import Statement as SigstoreStatement
from sigstore.models import Bundle as SigstoreBundle
from sigstore.models import ClientTrustConfig
from sigstore.oidc import IdentityToken, detect_credential
from sigstore.sign import SigningContext
from sigstore.verify.policy import Identity

from attest_core import JsonValue, canonicalize

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
STAGING_STORE: Final[str] = "https%3A%2F%2Ftuf-repo-cdn.sigstage.dev"
UNKNOWN_PREDICATE: Final[str] = "https://parth2412.github.io/attest/ai-authorship/v9.9"


class FixtureGenerationError(RuntimeError):
    """Signal missing CI identity or inconsistent generated evidence."""


def _variants() -> dict[str, dict[str, Any]]:
    source: dict[str, Any] = json.loads(
        (REPOSITORY_ROOT / "spec" / "testvectors" / "statement-valid" / "input.json").read_text()
    )
    trusted = copy.deepcopy(source)
    untrusted = copy.deepcopy(source)
    untrusted["predicate"]["collection"]["environment"] = {
        "kind": "local",
        "trusted": False,
    }
    unknown = copy.deepcopy(source)
    unknown["predicateType"] = UNKNOWN_PREDICATE
    structural = copy.deepcopy(source)
    structural["predicate"]["unexpected"] = True
    semantic = copy.deepcopy(source)
    semantic["subject"][0]["digest"]["sha256"] = "f" * 64
    return {
        "historical-v0.1-trusted.sigstore.json": trusted,
        "historical-v0.1-untrusted.sigstore.json": untrusted,
        "unknown-predicate.sigstore.json": unknown,
        "structural-extra-field.sigstore.json": structural,
        "semantic-digest-mismatch.sigstore.json": semantic,
    }


def _trust_config_json() -> str:
    store = files("sigstore").joinpath("_store", STAGING_STORE)
    trusted_root = json.loads(store.joinpath("trusted_root.json").read_text(encoding="utf-8"))
    signing_config = json.loads(
        store.joinpath("signing_config.v0.2.json").read_text(encoding="utf-8")
    )
    rendered = json.dumps(
        {
            "mediaType": "application/vnd.dev.sigstore.clienttrustconfig.v0.1+json",
            "trustedRoot": trusted_root,
            "signingConfig": signing_config,
        },
        indent=2,
        sort_keys=True,
    )
    ClientTrustConfig.from_json(rendered)
    return rendered + "\n"


def _single_uri_identity(bundle: SigstoreBundle) -> str:
    extension = bundle.signing_certificate.extensions.get_extension_for_class(
        SubjectAlternativeName
    )
    identities = extension.value.get_values_for_type(UniformResourceIdentifier)
    if len(identities) != 1:
        raise FixtureGenerationError
    return identities[0]


def generate(output: Path) -> None:
    """Sign all exact fixture variants and emit a content-hashed manifest."""
    credential = detect_credential()
    if credential is None:
        raise FixtureGenerationError
    token = IdentityToken(credential)
    trust_config = ClientTrustConfig.staging()
    context = SigningContext.from_trust_config(trust_config)
    output.mkdir(parents=True, exist_ok=False)
    identity: str | None = None
    metadata: dict[str, dict[str, str]] = {}

    with context.signer(token) as signer:
        for name, wire in _variants().items():
            statement = SigstoreStatement(canonicalize(cast(JsonValue, wire)))
            bundle = signer.sign_dsse(statement)
            exact_identity = _single_uri_identity(bundle)
            Identity(identity=exact_identity, issuer=token.federated_issuer).verify(
                bundle.signing_certificate
            )
            if identity is not None and identity != exact_identity:
                raise FixtureGenerationError
            identity = exact_identity
            raw = (bundle.to_json() + "\n").encode()
            SigstoreBundle.from_json(raw)
            (output / name).write_bytes(raw)
            metadata[name] = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "predicate": wire["predicateType"],
            }

    if identity is None:
        raise FixtureGenerationError
    trust_raw = _trust_config_json().encode()
    trust_name = "client-trust-config.json"
    (output / trust_name).write_bytes(trust_raw)
    metadata[trust_name] = {
        "sha256": hashlib.sha256(trust_raw).hexdigest(),
        "predicate": "not-applicable",
    }
    run_id = os.environ["GITHUB_RUN_ID"]
    manifest = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "identity": identity,
        "issuer": token.federated_issuer,
        "sigstoreVersion": version("sigstore"),
        "sourceCommit": os.environ["GITHUB_SHA"],
        "sourceRun": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run_id}",
        "workflowRef": os.environ["GITHUB_WORKFLOW_REF"],
        "files": metadata,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Parse the destination path and generate F-08 fixtures."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    generate(arguments.output)


if __name__ == "__main__":
    main()
