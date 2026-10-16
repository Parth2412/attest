#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="ghcr.io/parth2412/attest@sha256:6e1656ab5da1d5abc43c0ec36e6f3010f1f52c2528ff0e868eb2f62b5754906a"
ISSUER="https://token.actions.githubusercontent.com"
CONFIG="/evidence/verification-config.yaml"

for command_name in docker jq sha256sum; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'missing prerequisite: %s\n' "${command_name}" >&2
    exit 2
  fi
done

cd "${ROOT}"

printf 'Checking manifest-indexed file digests...\n'
jq -r '.files[] | "\(.sha256)  \(.path)"' manifest.json | sha256sum --check --strict

verify_bundle() {
  local file_name="$1"
  local identity="$2"
  local change_set_digest="$3"
  local authorship_mode="$4"
  local claim_count="$5"
  local review_state="$6"
  local approval_count="$7"
  local run_id="$8"
  local run_attempt="$9"
  local report

  printf '\nVerifying %s...\n' "${file_name}"
  report="$(
    docker run --rm --network none \
      --entrypoint /opt/venv/bin/attest \
      --volume "${ROOT}:/evidence:ro" \
      --workdir /evidence \
      "${IMAGE}" \
      verify \
      --input "/evidence/attestations/${file_name}" \
      --identity "${identity}" \
      --issuer "${ISSUER}" \
      --verify-environment production \
      --offline \
      --config "${CONFIG}" \
      --json \
      --no-color
  )"

  printf '%s\n' "${report}" | jq -e \
    --arg identity "${identity}" \
    --arg issuer "${ISSUER}" \
    --arg digest "${change_set_digest}" \
    --arg mode "${authorship_mode}" \
    --argjson claims "${claim_count}" \
    --arg review "${review_state}" \
    --argjson approvals "${approval_count}" \
    --arg run "${run_id}" \
    --argjson attempt "${run_attempt}" \
    '
      .outcome == "success" and
      .exitCode == 0 and
      .data.verification.status == "verified" and
      .data.verification.verifiedIdentity == $identity and
      .data.verification.verifiedIssuer == $issuer and
      .data.verification.transparencyLogVerified == true and
      (.data.verification.checks | all(
        if .name == "changeset-recomputation"
        then .result == "skipped"
        else .result == "passed"
        end
      )) and
      .data.verification.statement.subject[0].digest.sha256 == $digest and
      .data.verification.statement.predicate.changeSet.digest == $digest and
      .data.verification.statement.predicate.authorship.mode == $mode and
      (.data.verification.statement.predicate.authorship.claims | length) == $claims and
      .data.verification.statement.predicate.review.state == $review and
      .data.verification.statement.predicate.review.humanApprovals == $approvals and
      .data.verification.statement.predicate.collection.environment.runId == $run and
      .data.verification.statement.predicate.collection.environment.runAttempt == $attempt
    ' >/dev/null
}

verify_bundle \
  "e39d6cb916ca81bb5beaf07048e3f28c74b9142b5e34d9bc91d4aafc6d988533.sigstore.json" \
  "https://github.com/Parth2412/attest-action-proof/.github/workflows/attest.yml@refs/pull/4/merge" \
  "7356fbb663dcf6edcd7f40aae67dd4dce34d4004f85037c0057bb62a22df0ac2" \
  "human-authored" 0 "none" 0 "35996154567" 2

verify_bundle \
  "e60df59e1a27fbe7c42b4d7ad484acadbbd8a0ff96937faeb9a371d7d7bde843.sigstore.json" \
  "https://github.com/Parth2412/attest-action-proof/.github/workflows/attest.yml@refs/pull/4/merge" \
  "7356fbb663dcf6edcd7f40aae67dd4dce34d4004f85037c0057bb62a22df0ac2" \
  "human-authored" 0 "approved" 1 "35996154567" 3

verify_bundle \
  "1e43cd876d32233989e7561fb01a182b3d55ac847edc7c7433c07c4e72628654.sigstore.json" \
  "https://github.com/Parth2412/attest-action-proof/.github/workflows/attest.yml@refs/pull/8/merge" \
  "ed8d845eebb48b1fe38e916e8767b65ea0103b82d8d8a1a7d32aa1d311974081" \
  "human-authored" 0 "approved" 1 "38711403197" 3

verify_bundle \
  "ef80b71e6031013075e669a593cdf8f5939a18213d2e4d76024b46f2099ae70d.sigstore.json" \
  "https://github.com/Parth2412/attest-action-proof/.github/workflows/attest.yml@refs/pull/10/merge" \
  "9b369576434dfecc2d65418479c997533f8926d5c64a58d144c338b3ceaadced" \
  "ai-authored" 1 "none" 0 "38869963939" 1

verify_bundle \
  "7a6a5ec34871032dee948b244180a214223a9fcb6a99feb33fed5355c0b90f96.sigstore.json" \
  "https://github.com/Parth2412/attest-action-proof/.github/workflows/attest.yml@refs/pull/10/merge" \
  "9b369576434dfecc2d65418479c997533f8926d5c64a58d144c338b3ceaadced" \
  "ai-authored" 1 "approved" 1 "38869963939" 2

printf '\nVerified all 5 Bundles.\n'
