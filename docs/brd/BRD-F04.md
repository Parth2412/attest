# BRD-F04 — Review Record Collector (GitHub)

| Field | Value |
|---|---|
| Document ID | `BRD-F04` |
| Feature | `F-04` |
| Milestone | M2 |
| Package | `attest-collect` |
| Depends on | `F-01` |
| Status | In progress · Effective review-state correction governed by `ADR-042` |

---

## 1. Purpose

Collect forge-verified evidence of human review. This is the field auditors care about most:
whether a human — a specific, identifiable, non-author human — approved the change, and when.

## 2. Scope trace

`SCOPE-03`. Implements `SPEC-001 §6.4`, §6.5.

## 3. Dependencies

`F-01`.

## 4. Data contracts

```python
class ForgeAdapter(Protocol):
    def fetch_reviews(self, repo: str, pr_number: int) -> tuple[JsonObject, ...]: ...
    def fetch_review_requirement(self, repo: str, base_branch: str) -> ReviewRequirementData: ...
    def fetch_checks(self, repo: str, head_sha: str) -> ForgeCheckData: ...

def collect_review(data: ForgeReviewData, change_author_ids: set[str]) -> Review: ...

def collect_github(adapter: ForgeAdapter, context: GitHubReviewContext) -> GitHubCollection: ...
```

`GitHubReviewContext` is an immutable, validated context with a kind of `pull-request`,
`direct-push`, or `undetermined`; canonical `owner/repository`; head SHA; base branch; resolved
immutable commit author and committer IDs; optional positive PR number; and optional timezone-aware
last-push timestamp. Pull-request context requires a PR number, direct-push context forbids one,
and undetermined or inconsistent context is `ERR-COLLECT-124`.

`ForgeReviewData` carries the complete fetched review-response objects, the independently resolved
review-required value, and the optional last-push timestamp. `ReviewRequirementData` carries a
boolean or `unknown` result plus source-specific warnings. `ForgeCheckData` carries normalized
checks plus non-fatal warnings. `GitHubCollection` carries a `Review`, successful checks as a tuple
or unavailable checks as `None`, and stable warnings. Strict fetch and pagination failures never
return partial pages; `collect_github` is the default fail-open boundary described by
`REQ-F04-130` and `ADR-041`.

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F04-010` | Reviewer identity **MUST** be `<provider>:<immutable-numeric-id>:<login>`. The numeric ID **MUST** be present; logins alone are insufficient because they are renameable. |
| `REQ-F04-020` | Only the **latest** review state per immutable reviewer ID **MUST** count toward `humanApprovals`; latest is the greatest `(submittedAt, numeric review ID)` pair. Every retained human record **MUST** carry `effective`; exactly one record per immutable reviewer ID is `true`, and all superseded records are `false`. Aggregate state precedence **MUST** be `changes-requested`, `approved`, `commented`, then `none` across effective human verdicts. |
| `REQ-F04-030` | Dismissed reviews **MUST NOT** count toward `humanApprovals`. |
| `REQ-F04-040` | GitHub `User` accounts **MUST** be classified as human and `Bot` accounts as `automatedReviews`; automated accounts **MUST NOT** count toward `humanApprovals`. Classification uses the forge account type, not name heuristics. Pending drafts are omitted with `WARN-COLLECT-006`; unsupported submitted account types degrade review collection to unknown. |
| `REQ-F04-050` | `isChangeAuthor` **MUST** be computed by comparing reviewer immutable ID against the caller-resolved set of commit author and committer IDs in the ChangeSet; the collector **MUST NOT** infer a Git-to-GitHub identity mapping. |
| `REQ-F04-060` | `evidence.digest`, `findingsDigest`, and `detailsDigest` **MUST** be the SHA-256 of the existing RFC 8785 canonicalisation of the complete individual forge API response object that established the record. Raw response bodies **MUST NOT** be retained or logged. |
| `REQ-F04-070` | API responses **MUST** use `per_page=100` and be paginated exhaustively from same-operation, same-origin GitHub `Link` relations. Missing expected pages, malformed or cyclic links, duplicate record IDs, or count disagreement **MUST** raise `ERR-COLLECT-122` rather than return partial evidence. |
| `REQ-F04-080` | Rate limiting **MUST** use exponential backoff while honouring valid `Retry-After` and `X-RateLimit-Reset` delays, up to a positive configurable monotonic deadline, then `ERR-COLLECT-123`. Wall clock, monotonic clock, and sleep **MUST** be injectable. |
| `REQ-F04-090` | Authentication token **MUST** come from exactly one of `ATTEST_GITHUB_TOKEN`, `GITHUB_TOKEN`, or the file named by `ATTEST_GITHUB_TOKEN_FILE`; ambiguous or invalid sources are `ERR-COLLECT-121`. A token value **MUST NOT** be accepted as a CLI flag or appear in representations, logs, output streams, warnings, or diagnostics. |
| `REQ-F04-100` | `required` **MUST** evaluate both active branch rulesets and classic branch protection per `ADR-041`: either positive source yields `true`, `false` requires both sources to be determinately negative, otherwise it is `unknown`. For known direct push, `Review.state` **MUST** be `none`. |
| `REQ-F04-110` | `reviewLatencySeconds` **MUST** be computed from an explicitly supplied last commit push time to the earliest approval among humans whose latest verdict is approved. It **MUST** be omitted when either value is unavailable or approval precedes push; authored, committed, repository-push, and workflow-start times **MUST NOT** substitute. |
| `REQ-F04-120` | All network calls **MUST** have an explicit timeout; there **MUST NOT** be an unbounded request. |
| `REQ-F04-130` | Forge failures **MUST NOT** abort the public collection call by default. Review failures produce `Review.state == unknown`; branch-rule-only failures produce `required == unknown`; check failures omit checks. Every degradation carries a stable warning and partial pages are discarded. Policy decides whether the result is acceptable. |
| `REQ-F04-140` | Checks **MUST** be collected through every paginated check suite and every paginated run in each suite with `filter=all`. Every distinct terminal run, including reruns, is retained with exact name and decimal run ID. Predicate-native conclusions map directly; GitHub `action_required` and `stale` map to `failure`; nonterminal runs are omitted with `WARN-COLLECT-005`. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F04-010` | A recorded response produces `github:12345:bob`; renaming the login does not change the ID portion in a replayed fixture. |
| `AC-F04-020` | A reviewer who requested changes then approved counts once, as approved; the approval is `effective == true` and the superseded change request is `effective == false`, including an equal-timestamp case resolved by numeric review ID. |
| `AC-F04-030` | A dismissed approval yields `humanApprovals == 0`. |
| `AC-F04-040` | A `Bot`-type approving account appears in `automatedReviews` and yields `humanApprovals == 0`. |
| `AC-F04-050` | A self-approval yields `isChangeAuthor == True`. |
| `AC-F04-060` | `evidence.digest` matches an independently computed digest of the fixture response. |
| `AC-F04-070` | A 3-page fixture yields all reviewers; truncating page 2 raises `ERR-COLLECT-122`. |
| `AC-F04-080` | A 403 rate-limit fixture triggers backoff and eventual `ERR-COLLECT-123`. |
| `AC-F04-090` | The token value never appears in any log line, diagnostic output, or error message across the full test suite. |
| `AC-F04-100` | A direct-push context yields `state == "none"`; fixtures separately prove classic protection, active ruleset, determinately unprotected, and inaccessible-source `required` values. |
| `AC-F04-110` | Missing push time and approval-before-push each omit `reviewLatencySeconds`; a valid supplied push time produces exact integer UTC seconds. |
| `AC-F04-120` | Every `httpx` call site is constructed with an explicit timeout, asserted by a test. |
| `AC-F04-130` | A 500 from the review endpoint makes the public collection call return normally with `state == "unknown"` plus `ERR-COLLECT-125`; independent branch-rule and check failures preserve valid review evidence and emit their own warnings. |
| `AC-F04-140` | A multi-page suite/run fixture proves every terminal rerun is retained, nonterminal runs warn and are omitted, `action_required` and `stale` map to `failure`, and each check digest independently matches its complete fixture object. |

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-COLLECT-121` | Forge authentication failed | Check token scopes: `pull-requests: read`, `checks: read` |
| `ERR-COLLECT-122` | Incomplete pagination | Retry; report if persistent |
| `ERR-COLLECT-123` | Rate limit deadline exceeded | Increase deadline or reduce frequency |
| `ERR-COLLECT-124` | PR context could not be determined | Pass `--pr` explicitly |
| `ERR-COLLECT-125` | Forge request failed or returned an invalid response | Check GitHub availability and the recorded response contract, then retry |

Warnings emitted without invalidating other collected evidence:

| Code | Condition | Remediation |
|---|---|---|
| `WARN-COLLECT-005` | A check run has no terminal predicate conclusion | Retry after the check completes |
| `WARN-COLLECT-006` | A pending draft review has no submitted verdict | Submit the review before collecting final evidence |

## 8. Out of scope

- GitLab and Bitbucket adapters (`OOS-02`, v1.1)
- GitHub Enterprise Server and configurable production API origins (a later ADR)
- Judging review quality — attest records that review occurred, never whether it was good
- Enforcing review requirements (F-09 owns that)

## 9. Definition of Done

- [x] All `REQ-F04-*` implemented, all `AC-F04-*` green, including effective-state marking
- [x] Recorded HTTP fixtures for all paths; no live calls in the default test suite
- [x] Nightly live smoke test against a real repository
- [x] Token-leak test asserts absence across all output streams
- [x] Coverage ≥ 90%
- [x] Cross-cutting obligations satisfied
