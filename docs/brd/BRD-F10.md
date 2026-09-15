# BRD-F10 — CLI

| Field | Value |
|---|---|
| Document ID | `BRD-F10` |
| Feature | `F-10` |
| Milestone | M2 |
| Package | `attest-cli` |
| Depends on | `F-01`…`F-09`, including `REQ-F04-150` and `REQ-F08-170` |
| Status | Planned · contract accepted in `ADR-045`; starts only after F-04 and F-08 return to Done |

---

## 1. Purpose

The composition root and complete user-facing surface. It contains orchestration, configuration,
safe application-layer file I/O, and presentation only—never collection, signing, verification,
storage, policy, or export business logic. Shell and CI callers depend on its command names,
machine output, and exit codes as public APIs.

F-09 is an explicit dependency because `attest gate` and `attest run` compose its `Decision`. The
CLI owns policy-file I/O, complete ChangeSet context construction, and the distinction between an
absent policy and a configured-but-unreadable policy. F-04 owns GitHub context semantics; F-08 owns
Bundle inspection and verification semantics.

## 2. Scope trace

`SCOPE-09`.

## 3. Command and option surface

Exit `1` is possible for an unexpected, sanitised internal failure in every command. The table
lists it explicitly so the complete contract is snapshot-testable.

| Command | Purpose | Exit codes |
|---|---|---|
| `attest init` | Create config, starter policy, and a secure GitHub workflow | 0, 1, 2 |
| `attest collect` | Run collectors and write a Collection Artifact | 0, 1, 2, 6 |
| `attest build` | Build a Statement from a Collection Artifact | 0, 1, 2 |
| `attest sign` | Sign a Statement into exact Sigstore Bundle bytes | 0, 1, 2, 6 |
| `attest push` | Store exact Bundle bytes under a supplied ChangeSet Digest | 0, 1, 2, 6 |
| `attest verify` | Verify a Bundle against mandatory identity and issuer constraints | 0, 1, 2, 4, 5 |
| `attest gate` | Verify a Bundle, then evaluate policy | 0, 1, 2, 3, 4, 5 |
| `attest run` | collect → build → sign → push → verify → gate | 0, 1, 2, 3, 4, 5, 6 |
| `attest inspect` | Parse and render a Bundle as explicitly unverified identity | 0, 1, 2, 5 |
| `attest config show` | Print resolved configuration with value provenance | 0, 1, 2 |
| `attest doctor` | Diagnose the environment without signing | 0, 1, 2 |
| `attest version` | Print version and build metadata | 0, 1 |

`attest export` is reserved for F-12. Until F-12 is implemented it is not registered, does not
appear in help or completion, and has no placeholder success or not-implemented response.

Every leaf command accepts `--json`; all except `version` also accept `--config PATH`. Every human
rendering command accepts `--no-color`; colour is otherwise enabled only for a TTY when `NO_COLOR`
is absent. `--help` and `--version` follow framework conventions and perform no configuration,
filesystem discovery, credential lookup, or network operation.

### 3.1 Command-specific options

Command data options not listed below, and configuration options not listed in §4, do not exist in
v0.1. Required paths are explicit; `-` is not a stdin or stdout alias because stdout is reserved
for the JSON report.

| Command | Options and constraints |
|---|---|
| `init` | `--repository PATH` (default `.`), optional `--github-repository OWNER/REPO`, optional `--default-branch NAME`, required `--checkout-ref OWNER/REPO[/PATH]@40_HEX` and `--action-ref OWNER/REPO[/PATH]@40_HEX`; discovery must resolve omitted GitHub values unambiguously or exit `2` |
| `collect` | `--repository PATH`, `--output PATH`, optional `--overwrite`, repeated `--claim JSON`, optional `--base 40_HEX`, `--head 40_HEX`, `--target-branch NAME`, `--github-repository OWNER/REPO`, `--pr POSITIVE_INT`, and `--github-event PATH`; event mode conflicts with all explicit context, explicit PR mode requires repository/PR/base/head/target, and local mode requires base/head/target while forbidding repository/PR |
| `build` | required `--input PATH`, `--output PATH`; optional `--overwrite` |
| `sign` | required `--input PATH`, `--output PATH`; optional `--overwrite`; signing settings resolve from §4 |
| `push` | required `--input PATH` and `--change-set-digest 64_HEX`; storage settings resolve from §4 |
| `verify` | required `--input PATH`; optional all-or-none `--repository PATH`, `--base 40_HEX`, `--head 40_HEX`; verification settings resolve from §4 |
| `gate` | required `--input PATH`, `--repository PATH`, `--base 40_HEX`, `--head 40_HEX`, and `--target-branch NAME`; optional `--policy PATH`; verification settings resolve from §4 |
| `run` | `collect` context inputs; required `--output PATH`; optional `--overwrite`, `--work-directory PATH`, and `--policy PATH`; signing, verification, and storage settings resolve from §4 |
| `inspect` | required `--input PATH` |
| `config show` | required `--resolved`; no unresolved or secret-value mode exists |
| `doctor` | optional `--probe-network`; without it no network probe runs |
| `version` | no command-specific options |

Each configuration option in §4 exists only on commands that consume that field and on
`config show`/`doctor` where it is reported; it is not installed indiscriminately on every command.

`--github-event` is an application-layer file input. When absent in GitHub Actions, its value may
come from `ATTEST_GITHUB_EVENT_PATH` or ambient `GITHUB_EVENT_PATH` only after F-05 identifies a
trusted GitHub Actions environment. The CLI reads bytes and delegates parsing and Compare
resolution, including current PR-field binding, to F-04. Explicit GitHub inputs construct F-04's
typed input without parsing forge responses. Outside those modes, base/head/target selects local
collection with `Review.state == unknown`; it never fabricates forge evidence. `run` and `gate` use
one selected base/head pair for F-02 collection and mandatory F-08 repository recomputation.

## 4. Configuration contract

`.attest/config.yaml` is a closed safe-YAML document. It is at most 1 MiB, UTF-8 without BOM,
single-document, alias/anchor/tag/merge/duplicate-key free, depth at most 32, and validated by a
strict Pydantic model before use. Null and unknown keys are invalid. Its schema is generated as
`spec/schemas/cli-config-v1.schema.json`; root `version` is strict integer `1`.

Repository config is read only from `<resolved-repository>/.attest/config.yaml`; the CLI does not
walk parent directories. `--config` replaces that source and a missing or unreadable explicit file
is an error. Precedence is command flag, named environment variable, repository/explicit config,
then built-in. The v1.1 organisation layer is inactive, reported `unsupported`, and never fetched.

| YAML key | Environment | Command option | Default |
|---|---|---|---|
| `repository.path` | `ATTEST_REPOSITORY` | `--repository` | `.` |
| `repository.backend` | `ATTEST_GIT_BACKEND` | `--git-backend` | `auto` |
| `github.eventPath` | `ATTEST_GITHUB_EVENT_PATH` | `--github-event` | trusted ambient `GITHUB_EVENT_PATH`, otherwise absent |
| `signing.environment` | `ATTEST_SIGNING_ENVIRONMENT` | `--signing-environment` | `production` |
| `signing.timeoutSeconds` | `ATTEST_SIGNING_TIMEOUT_SECONDS` | `--signing-timeout-seconds` | `120` |
| `verification.identity` | `ATTEST_IDENTITY` | `--identity` | absent |
| `verification.issuer` | `ATTEST_ISSUER` | `--issuer` | absent |
| `verification.environment` | `ATTEST_VERIFY_ENVIRONMENT` | `--verify-environment` | `production` |
| `verification.offline` | `ATTEST_VERIFY_OFFLINE` | `--offline` / `--online` | `true` |
| `verification.trustConfigFile` | `ATTEST_TRUST_CONFIG_FILE` | `--trust-config-file` | absent |
| `policy.path` | `ATTEST_POLICY_PATH` | `--policy` | `.attest/policy.yaml` |
| `storage.backend` | `ATTEST_STORE_BACKEND` | `--store-backend` | `git-ref` |
| `storage.directory` | `ATTEST_STORE_DIRECTORY` | `--store-directory` | `.attest/bundles` |
| `storage.fallbackDirectory` | `ATTEST_FALLBACK_DIRECTORY` | `--fallback-directory` | `.attest/fallback` |
| `storage.git.remote` | `ATTEST_GIT_REMOTE` | `--git-remote` | `origin` |
| `storage.git.timeoutSeconds` | `ATTEST_GIT_TIMEOUT_SECONDS` | `--git-timeout-seconds` | `120` |
| `storage.oci.repository` | `ATTEST_OCI_REPOSITORY` | `--oci-repository` | absent |
| `storage.oci.subject.mediaType` | `ATTEST_OCI_SUBJECT_MEDIA_TYPE` | `--oci-subject-media-type` | absent |
| `storage.oci.subject.digest` | `ATTEST_OCI_SUBJECT_DIGEST` | `--oci-subject-digest` | absent |
| `storage.oci.subject.size` | `ATTEST_OCI_SUBJECT_SIZE` | `--oci-subject-size` | absent |
| `storage.oci.stagingDirectory` | `ATTEST_OCI_STAGING_DIRECTORY` | `--oci-staging-directory` | absent |
| `storage.oci.authConfigFile` | `ATTEST_OCI_AUTH_CONFIG_FILE` | none; secret-bearing file source | absent |
| `storage.oci.insecure` | `ATTEST_OCI_INSECURE` | `--oci-insecure` | `false` |
| `storage.oci.tlsVerify` | `ATTEST_OCI_TLS_VERIFY` | `--oci-tls-verify` | `true` |
| `storage.oci.timeoutSeconds` | `ATTEST_OCI_TIMEOUT_SECONDS` | `--oci-timeout-seconds` | `120` |

Enums and scalar types are strict. Boolean environment values are exactly `true` or `false` after
ASCII case-folding; integers are canonical unsigned decimal; whitespace, signs, empties, and other
spellings are invalid. A supplied trust-config file conflicts with service environment and
offline/online overrides. OCI selection requires every subject and staging field. Filesystem
selection requires `directory`; Git-ref requires repository and remote. Every primary store has a
configured filesystem fallback.

GitHub and OCI tokens/passwords are governed by their adapters and never become resolved string
values. `config show --resolved` reports each non-secret value plus source (`flag`,
`environment:<NAME>`, `config:<PATH>`, `ambient:<NAME>`, or `builtin`). Secret-bearing inputs report
only `configured: true|false` and source. Credential file contents are never output.

## 5. Intermediate artifact contracts

Artifacts and reports are different channels. Commands write artifacts only to explicit paths and
emit progress/reports separately. JSON artifacts are canonical RFC 8785 JSON followed by one LF.

| Stage | Input | Output |
|---|---|---|
| `collect` | repository plus exact ChangeSet context | `CollectionArtifact`, validated by `cli-collection-v0.1.schema.json` |
| `build` | `CollectionArtifact` | canonical in-toto `Statement`, validated by the predicate-version schema |
| `sign` | canonical `Statement` | exact upstream Sigstore Bundle JSON bytes |
| `push` | exact Bundle bytes plus ChangeSet Digest | F-07 `StoreRef`; no Bundle parsing/verification |
| `verify` | exact Bundle bytes plus mandatory constraints | F-08 `VerificationResult` |
| `gate` | verified result plus same repository/context and policy | F-09 `Decision` |

`CollectionArtifact` is a closed Pydantic wire model with `schemaVersion == "0.1.0"`,
`changeSetRecord`, `changeSet`, `authorship`, `review`, optional `checks`, `collection`, and
`context`. `context` has full base/head OIDs, optional merge-base OID, and non-empty target branch.
It contains the complete record paths required by policy and exact typed F-05 inputs; it contains no
token, repository filesystem path, raw forge response, prompt text, or arbitrary extension map.

`run --work-directory` writes `collection.json`, `statement.json`, and `bundle.sigstore.json` with
the same serializers/readers as standalone stages. Without it, private temporary stage files are
removed after closure. With injected deterministic adapters, standalone composition and `run` call
operations in the same order with equal typed inputs and exact artifact bytes. A failed stage
prevents every later stage.

## 6. Machine-output and human-output contract

With `--json`, each invocation writes exactly one UTF-8 JSON object followed by LF to stdout,
including usage/configuration and command-controlled failures. Nothing else reaches stdout. Human
progress/diagnostics go to stderr. The root exception boundary converts Click/Typer usage errors,
coded domain failures, and unexpected exceptions without leaking tracebacks, secret values, raw
HTTP/subprocess output, or chained exception text.

Generated `spec/schemas/cli-output-v0.1.schema.json` is a closed discriminated union. Every report
has exactly `schemaVersion` (`"0.1.0"`), `command`, `outcome`, `exitCode`, `data`, `warnings`, and
optional `error`. `outcome` is `success`, `warning`, `denied`, `failed`, or
`unverified-identity`; exit code must agree. `warnings` is an ordered list of closed
`{code,message,remediation}` diagnostics. `error`, when present, has the same shape and is required
only for `failed`; a policy `denied` report carries the complete `Decision` and its stable predicate
reason codes without fabricating a domain error. `command` is exactly one of `attest`, `init`,
`collect`, `build`, `sign`, `push`, `verify`, `gate`, `run`, `inspect`, `config-show`, `doctor`, or
`version`; it is `attest` only when dispatch never reached a leaf. `data` is the closed command
model for a dispatched result and JSON `null` for pre-dispatch or pre-operation failure.

Outcome and exit agreement is exact: `success`, `warning`, and `unverified-identity` require exit
`0`; `denied` is available only to `gate`/`run`, requires a complete F-09 `Decision` with outcome
`deny`, and uses that Decision's exit `3`, `4`, or `5`; `failed` uses exit `1`, `2`, `4`, `5`, or
`6` according to §8. A F-09 `allow` Decision maps to `success`, and `warn` maps to `warning`.
Standalone F-08 verification failure is `failed` with its complete `VerificationResult`; the same
result inside gate/run is the F-09 verification-failed `denied` Decision. Command data models are
closed and typed:

| Command data | Required content |
|---|---|
| `init` | created paths and exact generated workflow identity |
| `collect` | output path, ChangeSet Digest, base/head/merge-base/target, collector backend |
| `build` | output path and ChangeSet Digest |
| `sign` | output path, environment, certificate identity/issuer, Rekor index |
| `push` | complete `StoreRef` and optional fallback path |
| `verify` | complete `VerificationResult` except raw Bundle bytes |
| `gate` | verification summary and complete `Decision` |
| `run` | ordered stage summaries, final `StoreRef`, verification summary, and `Decision` |
| `inspect` | complete `InspectionResult`; success outcome is `unverified-identity` |
| `config show` | ordered field/value/source entries with secret values absent |
| `doctor` | ordered diagnostic checks and selected backend/environment names |
| `version` | CLI version, Python version, and optional immutable build revision |

Config entries follow §4 table order; run stage summaries follow §5 pipeline order; doctor checks
follow their order in `REQ-F10-120`. All other diagnostics are ordered by producing stage, then
code, then message. No renderer may depend on map iteration, filesystem enumeration, or response
arrival order.

Human output contains the same facts but is not a stable parseable format. Colour is presentation
only. `inspect` prominently prints `UNVERIFIED IDENTITY` and uses JSON outcome
`unverified-identity`; it never uses `verified` or `trusted` without that prefix.

## 7. Safe I/O, egress, and generated workflow

CLI-controlled config, policy, event, artifact, trust, and credential-config inputs are bounded
regular files opened without following symbolic links. Config, policy, and event files are at most
1 MiB; Statements are at most 16 MiB; Collection Artifacts, Bundles, and supplied trust
configurations are at most 64 MiB. A file that
changes identity or size while read is rejected. JSON rejects BOM, non-UTF-8, duplicate keys,
non-finite numbers, trailing input, and a wrong top-level type.

Outputs reject symlinks, directories, devices, and existing paths unless `--overwrite` is supported
and supplied. They create a mode-`0600` temporary regular file in the resolved parent, flush it,
and atomically publish without a partial target. Overwrite replaces only a revalidated regular file
and never follows links. `init` never overwrites any target and leaves no subset if preflight fails.

There is no telemetry. Permitted egress is limited to F-04 GitHub operations, F-06 signing, F-07
explicit storage/push, explicitly online F-08 trust refresh, and `doctor --probe-network`. Doctor
derives signing endpoints from the same selected public Sigstore configuration, sends no
credentials, follows no redirect, verifies TLS, uses a five-second per-endpoint timeout, and makes
no OIDC request, signature, Rekor write, storage write, or policy decision. Without the flag doctor
is offline; unavailable required local capability exits `2`, while failed optional probes warn and
exit `0`.

`init` creates `.attest/config.yaml`, `.attest/policy.yaml`, and
`.github/workflows/attest.yml`. The workflow triggers only on `pull_request`, never
`pull_request_target`; declares only `contents: write`, `pull-requests: read`, `checks: read`, and
`id-token: write`; and invokes only the exact caller-supplied full-SHA checkout and attest Actions.
Its identity is exactly
`https://github.com/<owner>/<repo>/.github/workflows/attest.yml@refs/heads/<default-branch>`, matching
`GITHUB_WORKFLOW_REF`. F-10 snapshots and locally integration-tests these bytes. F-11 owns the
published Action, immutable image digest, live least-privilege validation, and proof that the
workflow runs unmodified in a fresh repository.

### 7.1 Exact `init` templates

`init` substitutes only `<identity>`, `<default-branch>`, `<checkout-ref>`, and `<action-ref>` below.
It emits LF line endings, one terminal LF, two-space YAML indentation, and no comments beyond those
shown. `<identity>` is the exact URI above; refs are validated full-SHA
`owner/repository[/path]@sha` values. Config and policy strings are double-quoted where shown.

`.attest/config.yaml`:

```yaml
version: 1
repository:
  path: "."
  backend: auto
signing:
  environment: production
  timeoutSeconds: 120
verification:
  identity: "<identity>"
  issuer: "https://token.actions.githubusercontent.com"
  environment: production
  offline: true
policy:
  path: ".attest/policy.yaml"
storage:
  backend: git-ref
  directory: ".attest/bundles"
  fallbackDirectory: ".attest/fallback"
  git:
    remote: origin
    timeoutSeconds: 120
```

`.attest/policy.yaml`:

```yaml
version: 1
policies:
  - id: ATTEST-DEFAULT-001
    description: "Require trusted signed provenance and independent human review"
    match:
      branches: ["<default-branch>"]
      paths: ["**"]
    require:
      attestation: true
      environment:
        trusted: true
      signer:
        issuer: "https://token.actions.githubusercontent.com"
        identity: "<identity>"
      transparencyLog: true
      review:
        minHumanApprovals: 1
        approverMustNotBeAuthor: true
    onViolation: block
```

`.github/workflows/attest.yml`:

```yaml
name: attest

on:
  pull_request:

permissions:
  contents: write
  id-token: write
  pull-requests: read
  checks: read

jobs:
  attest:
    runs-on: ubuntu-latest
    steps:
      - uses: <checkout-ref>
        with:
          fetch-depth: 0
      - uses: <action-ref>
        with:
          mode: run
          policy: .attest/policy.yaml
          push-attestation: "true"
          fail-on-violation: "true"
```

## 8. Error and exit mapping

| Code | Condition | Exit |
|---|---|---:|
| `ERR-CONFIG-001` | Invalid/missing/conflicting invocation or resolved value | 2 |
| `ERR-CONFIG-002` | Unsafe, unreadable, malformed, or unsupported configuration | 2 |
| `ERR-CONFIG-003` | Unsafe, unreadable, malformed, oversized, or wrong-version input artifact | 2 |
| `ERR-CONFIG-004` | Unsafe/existing/unwritable output target or failed atomic publication | 2 |
| `ERR-CONFIG-005` | Mandatory verification identity or issuer is unresolved | 2 |
| `ERR-CONFIG-006` | Required local diagnostic capability is unavailable or invalid | 2 |
| `ERR-INTERNAL-001` | Unexpected failure at the CLI exception boundary | 1 |

Domain errors map by semantics, never by exception text:

| Source | Exit mapping |
|---|---|
| F-02/F-03/F-04/F-05 | caller/config/input error → 2; exhausted forge transport/rate-limit → 6; otherwise → 1 |
| F-06 | configuration/invalid input → 2; Fulcio/Rekor/deadline → 6; invalid output/internal invariant → 1 |
| F-07 | invalid input/config → 2; auth/transport/deadline → 6; required absence → 5; integrity/fallback failure → 1 |
| F-08 | missing Bundle → 5; missing/invalid constraints → 2; every failed `VerificationResult` → 4 |
| F-09 | invalid/unreadable explicit policy/context → 2; `Decision.exit_code` → exactly 0, 3, 4, or 5 |
| F-08 inspection | missing Bundle → 5; parse/schema/model failure → 2; success → 0 with `unverified-identity` |
| Uncaught exception | 1 with `ERR-INTERNAL-001`; traceback only under test/developer logging |

Every failure error emits one code, plain message, and remediation. A policy decision emits its
closed predicate reason codes and complete decision data; it is not relabelled as an exception.
Primary-store failure with a successful fallback retains the primary exit and reports the
credential-free fallback path. Exit `0` is never used for partial signing, failed verification,
denied policy, missing required evidence, or a placeholder.

## 9. Requirements

| ID | Requirement |
|---|---|
| `REQ-F10-010` | Exit codes **MUST** match §3 and `GLOSS-001 §7` exactly and **MUST NOT** change without a major CLI version bump. |
| `REQ-F10-020` | Every registered leaf command **MUST** support `--json` and validate every success, warning, denial, usage error, and failure against the generated versioned schema in §6. |
| `REQ-F10-030` | With `--json`, stdout **MUST** contain exactly one report object plus LF and all human output **MUST** go to stderr. |
| `REQ-F10-040` | CLI handlers **MUST** only resolve inputs, perform safe application I/O, orchestrate public package operations, and map typed results/errors; business logic and peer private imports are forbidden. |
| `REQ-F10-050` | Configuration **MUST** implement the exact strict vocabulary, validation, conflicts, precedence, and provenance rules in §4; inactive organisation policy **MUST NOT** be fetched. |
| `REQ-F10-060` | Secrets **MUST NOT** be accepted as flags, printed, logged, represented, or exposed by resolved configuration; only governed environment/file sources are permitted. |
| `REQ-F10-070` | Every error **MUST** contain one stable domain code, sanitised message, and remediation and **MUST** use the exact typed mapping in §8; policy Decisions retain their typed predicate reason codes and are not exceptions. |
| `REQ-F10-080` | `attest --help` **MUST** return under 300 ms from the installed wheel; heavy package imports **MUST** be deferred to command execution. |
| `REQ-F10-090` | Colour **MUST** be disabled when not a TTY, when `NO_COLOR` exists, under `--json`, or under `--no-color`; no ANSI sequence may enter JSON. |
| `REQ-F10-100` | Verify/gate/run **MUST** require both identity and issuer from flag or config and exit `2` with `ERR-CONFIG-005` before verification if either is absent. No bypass exists. |
| `REQ-F10-110` | Standalone stages and `run` **MUST** use the exact artifacts and equivalent typed inputs/order in §5; each stage is independently consumable and failure stops later stages. |
| `REQ-F10-120` | Doctor **MUST** report selected git backend, ambient identity availability, CI detection, resolved policy path, and signing-endpoint reachability under §7's no-signing/no-credential probe rules. |
| `REQ-F10-130` | No command **MUST** send telemetry; all permitted egress **MUST** be explicit, bounded, documented, and deny-by-default tested. |
| `REQ-F10-140` | Gate/run **MUST** use one caller-selected base/head ChangeSet for collection, mandatory F-08 recomputation, and F-09 complete path/target context, and stop before policy on failed verification. |
| `REQ-F10-150` | Commands/options **MUST** be exactly §3; `attest export` **MUST** remain unregistered until F-12 implements it. |
| `REQ-F10-160` | CLI reads/writes **MUST** satisfy every bound, type, symlink, race, containment, create-only, overwrite, permission, and atomic-publication rule in §7. |
| `REQ-F10-170` | `inspect` **MUST** delegate to F-08 inspection, prominently return `unverified-identity`, and **MUST NOT** verify, gate, expose trusted identity, or supply policy evidence. |
| `REQ-F10-180` | GitHub PR collect/run **MUST** delegate event/PR/Compare semantics to F-04 and use its PR-bound repository/base/head/target, exact merge base, and complete author/committer IDs; local mode **MUST NOT** fabricate forge evidence. |
| `REQ-F10-190` | `init` **MUST** atomically create §7.1's three exact files, use `pull_request` plus caller-supplied full-SHA checkout and attest Actions, and generate the exact workflow identity; live publication/proof remains F-11. |
| `REQ-F10-200` | Config, Collection Artifact, and CLI output schemas **MUST** be generated from strict runtime models, committed, and independently drift-checked. |
| `REQ-F10-210` | `push` **MUST** pass exact Bundle bytes and supplied validated ChangeSet Digest to F-07 without parsing/verifying the Bundle and preserve fallback reporting. |
| `REQ-F10-220` | Human/JSON output **MUST** contain equivalent facts, stable ordering, and no traceback, raw chained exception, credential, raw forge body, raw subprocess output, prompt, or source content. |
| `REQ-F10-230` | Config/environment discovery and help **MUST** perform no ambient credential exchange; only sign/run signing may request OIDC. |
| `REQ-F10-240` | The installed distribution **MUST** expose exactly one `attest` script invoking the tested root app and `python -m attest_cli` **MUST** be equivalent. |
| `REQ-F10-250` | Every command **MUST** be non-interactive without TTY and under CI; no security input or overwrite confirmation may be prompted. |

## 10. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F10-010` | A snapshot asserts every command/exit combination in §3 and frozen glossary meanings. |
| `AC-F10-020` | Parameterized success/warning/denial/usage/failure reports for every command validate against the committed CLI schema. |
| `AC-F10-030` | JSON-mode stdout is one parseable object plus LF with every human byte confined to stderr. |
| `AC-F10-040` | Static analysis finds no CLI domain algorithm, peer private import, Bundle/GitHub semantic parser, policy evaluator, signer, verifier, or store implementation. |
| `AC-F10-050` | Table tests cover every source, strict scalar, conflict, invalid document, inactive organisation layer, and winning provenance. |
| `AC-F10-060` | Command-tree and output/log tests prove no secret-pattern flag exists and injected credentials never appear. |
| `AC-F10-070` | Every mapped error fixture has exact code/message/remediation and exit; exception text cannot change mapping, while denied-policy fixtures contain Decision reason codes and no fabricated error. |
| `AC-F10-080` | Ten clean installed-wheel `attest --help` processes each complete under 300 ms on the CI baseline. |
| `AC-F10-090` | Pipe, `NO_COLOR`, JSON, and `--no-color` contain no ANSI; TTY colour never changes content fields. |
| `AC-F10-100` | Every missing identity/issuer combination exits `2` before constructing/calling F-08; valid constraints pass unchanged. |
| `AC-F10-110` | Deterministic injected adapters make staged and run execution byte-equal with equal ordered public calls; stage failure prevents later calls. |
| `AC-F10-120` | Offline and explicit-probe doctor fixtures report all fields, make only allowed bounded requests, and never request OIDC/sign. |
| `AC-F10-130` | Deny-by-default socket/HTTP tests prove only command/option-specific egress occurs and no telemetry endpoint exists. |
| `AC-F10-140` | Equal effective diff-base/head values (the forge merge base for PRs) reach F-02/F-08, complete paths/target reach F-09, and ChangeSet mismatch exits `4` before evaluation. |
| `AC-F10-150` | Command-tree snapshot contains exactly the active surface and `export` is absent from invocation, help, and completion. |
| `AC-F10-160` | File tests cover oversized/racing inputs, duplicate JSON/YAML keys, BOM, symlinks, devices, existing targets, overwrite races, permissions, atomic cleanup, and init all-or-none preflight. |
| `AC-F10-170` | Structurally valid signature-tampered input inspects only as `unverified-identity`; F-08 verify/F-09 evaluate are never called. |
| `AC-F10-180` | Recorded event/PR/Compare context passes unchanged to collection; any PR binding mismatch or incomplete context is fatal and local run emits unknown review without forge calls. |
| `AC-F10-190` | Golden files prove exact config/policy/workflow bytes, identity, event, permissions, and both full-SHA Actions; existing target leaves all unchanged. |
| `AC-F10-200` | Independent generation of all three schemas is diff-clean and wrong-version/unknown-field fixtures fail. |
| `AC-F10-210` | Opaque non-JSON Bundle bytes reach fake stores byte-for-byte with supplied digest; primary failure reports fallback path/exit. |
| `AC-F10-220` | Cross-renderer fixtures prove fact equivalence/order and scan all streams for prohibited content. |
| `AC-F10-230` | All non-signing command tests fail on attempted OIDC/credential exchange; only sign/run signing may request one. |
| `AC-F10-240` | Installed-wheel tests prove `attest` and `python -m attest_cli` equal and no additional console script exists. |
| `AC-F10-250` | Closed-stdin and CI tests cover every command/overwrite conflict without prompt or hang. |

## 11. Out of scope

- Evidence export and `attest export` (F-12)
- Publishing Action/container/PyPI artifacts and live fresh-repository proof (F-11)
- TUI, interactive setup, organisation distribution, GitLab/Bitbucket, non-framework completion,
  hidden auto-update, or telemetry

## 12. Definition of Done

- [ ] F-04 and F-08 prerequisites are Done before F-10 starts
- [ ] All `REQ-F10-*` implemented and every `AC-F10-*` green
- [ ] Every command has installed-wheel and `CliRunner` success/failure/JSON tests
- [ ] All three generated schemas are committed and independently drift-checked
- [ ] Command/option/exit, no-secret, no-egress, safe-I/O, and import-boundary snapshots are green
- [ ] Coverage ≥ 90% for `attest-cli`
- [ ] Cross-cutting obligations satisfied
- [ ] F-11 handoff records that publication and live fresh-repository proof remain open
