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

printf 'Checking synthetic policy-exception lifecycle links...\n'
generated_at="$(jq -er '.generatedAt | strings' manifest.json)"

jq -e --arg generated_at "${generated_at}" '
  (.files | map(.path) | length) == (.files | map(.path) | unique | length) and
  .exceptions.evidenceFailures.unattestedChangesEvaluated == false and
  (.exceptions.evidenceFailures.verificationFailures | type == "array") and
  (.exceptions.policyExceptions | length == 3) and
  (.exceptions.policyExceptions | map(.exceptionId) | length) ==
    (.exceptions.policyExceptions | map(.exceptionId) | unique | length) and
  (.exceptions.policyExceptions | map(.integrityStatus) |
    all(. == "synthetic-unsigned-validation-only")) and
  (.exceptions.policyExceptions | map(.derivedAt) | all(. == $generated_at)) and
  (.exceptions.policyExceptions | map(.derivedState) | sort == ["closed", "open", "overdue"])
' manifest.json >/dev/null

while IFS=$'\t' read -r exception_id integrity_status derived_state authorization_path \
  authorization_sha review_deadline closure_path closure_sha; do
  actual_authorization_sha="$(sha256sum "${authorization_path}" | awk '{print $1}')"
  if [[ "${actual_authorization_sha}" != "${authorization_sha}" ]]; then
    printf 'authorization digest mismatch for %s\n' "${exception_id}" >&2
    exit 1
  fi

  jq -e \
    --arg exception_id "${exception_id}" \
    --arg integrity_status "${integrity_status}" \
    --arg review_deadline "${review_deadline}" \
    '
      .candidateFormat == "policy-exception-event/v0-validation" and
      .integrityStatus == $integrity_status and
      .scenario.synthetic == true and
      .exceptionId == $exception_id and
      .eventType == "authorized" and
      (.changeSetDigest | test("^[0-9a-f]{64}$")) and
      .policy.decision == "deny" and
      (.policy.decisionSha256 | test("^[0-9a-f]{64}$")) and
      (.policy.sourceSha256 | test("^[0-9a-f]{64}$")) and
      (.policy.failedPredicates | type == "array" and length > 0) and
      (.deployment.workflowRunId | strings | length > 0) and
      (.deployment.workflowRunAttempt | numbers | . >= 1) and
      (.requester.identity | strings | length > 0) and
      (.decisionOwner.identity | strings | length > 0) and
      (.separationOfDuties.decisionOwnerIsRequester | type == "boolean") and
      (.separationOfDuties.decisionOwnerIsChangeAuthor | type == "boolean") and
      (.reason.code | strings | length > 0) and
      (.reason.summary | strings | length > 0) and
      (.source.digest | test("^[0-9a-f]{64}$")) and
      .retrospectiveReviewDueAt == $review_deadline and
      ((.authorizedAt | fromdateiso8601) <= (.retrospectiveReviewDueAt | fromdateiso8601))
    ' "${authorization_path}" >/dev/null

  authorization_change_set="$(jq -er '.changeSetDigest' "${authorization_path}")"
  authorization_time="$(jq -er '.authorizedAt' "${authorization_path}")"

  if [[ -n "${closure_path}" ]]; then
    if [[ "${derived_state}" != "closed" || -z "${closure_sha}" ]]; then
      printf 'closed lifecycle metadata is incomplete for %s\n' "${exception_id}" >&2
      exit 1
    fi

    actual_closure_sha="$(sha256sum "${closure_path}" | awk '{print $1}')"
    if [[ "${actual_closure_sha}" != "${closure_sha}" ]]; then
      printf 'closure digest mismatch for %s\n' "${exception_id}" >&2
      exit 1
    fi

    jq -e \
      --arg exception_id "${exception_id}" \
      --arg integrity_status "${integrity_status}" \
      --arg authorization_sha "${authorization_sha}" \
      --arg change_set "${authorization_change_set}" \
      --arg authorization_time "${authorization_time}" \
      '
        .candidateFormat == "policy-exception-event/v0-validation" and
        .integrityStatus == $integrity_status and
        .scenario.synthetic == true and
        .exceptionId == $exception_id and
        .eventType == "retrospective-review-completed" and
        .authorizationEventSha256 == $authorization_sha and
        .changeSetDigest == $change_set and
        (.reviewer.identity | strings | length > 0) and
        .review.missingReviewPerformed == true and
        ((.review.completedAt | fromdateiso8601) >= ($authorization_time | fromdateiso8601)) and
        (.review.disposition | strings | length > 0) and
        .review.reviewEvidence.changeSetDigest == $change_set and
        (.review.reviewEvidence.sha256 | test("^[0-9a-f]{64}$")) and
        (.review.remediationReferences | type == "array") and
        (.source.digest | test("^[0-9a-f]{64}$"))
      ' "${closure_path}" >/dev/null

    review_evidence_path="$(jq -er '.review.reviewEvidence.path' "${closure_path}")"
    case "${review_evidence_path}" in
      ../attestations/*.sigstore.json) ;;
      *)
        printf 'invalid review-evidence path for %s\n' "${exception_id}" >&2
        exit 1
        ;;
    esac
    expected_review_evidence_sha="$(jq -er '.review.reviewEvidence.sha256' "${closure_path}")"
    actual_review_evidence_sha="$(
      sha256sum "$(dirname -- "${closure_path}")/${review_evidence_path}" | awk '{print $1}'
    )"
    if [[ "${actual_review_evidence_sha}" != "${expected_review_evidence_sha}" ]]; then
      printf 'review-evidence digest mismatch for %s\n' "${exception_id}" >&2
      exit 1
    fi
  else
    if [[ -n "${closure_sha}" ]]; then
      printf 'closure digest exists without a closure path for %s\n' "${exception_id}" >&2
      exit 1
    fi
    expected_state="$(
      jq -nr \
        --arg generated_at "${generated_at}" \
        --arg review_deadline "${review_deadline}" \
        'if ($generated_at | fromdateiso8601) > ($review_deadline | fromdateiso8601)
         then "overdue" else "open" end'
    )"
    if [[ "${derived_state}" != "${expected_state}" ]]; then
      printf 'derived lifecycle state mismatch for %s\n' "${exception_id}" >&2
      exit 1
    fi
  fi
done < <(
  jq -r '
    .exceptions.policyExceptions[] |
    [
      .exceptionId,
      .integrityStatus,
      .derivedState,
      .authorizationPath,
      .authorizationSha256,
      .reviewDeadline,
      (.closurePath // ""),
      (.closureSha256 // "")
    ] | @tsv
  ' manifest.json
)

printf '%s\n' 'Policy-exception files are structurally linked synthetic mocks, not signed evidence.'

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
