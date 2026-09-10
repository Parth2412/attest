# BRD-F04 — Review Record Collector (GitHub)

| Field | Value |
|---|---|
| Document ID | `BRD-F04` |
| Feature | `F-04` |
| Milestone | M2 |
| Package | `attest-collect` |
| Depends on | `F-01` |
| Status | Ready when F-01 Done · no open question |

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
    def fetch_reviews(self, repo: str, pr_number: int) -> ForgeReviewData: ...
    def fetch_checks(self, repo: str, head_sha: str) -> list[Check]: ...

def collect_review(data: ForgeReviewData, change_author_ids: set[str]) -> Review: ...
```

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F04-010` | Reviewer identity **MUST** be `<provider>:<immutable-numeric-id>:<login>`. The numeric ID **MUST** be present; logins alone are insufficient because they are renameable. |
| `REQ-F04-020` | Only the **latest** review state per reviewer **MUST** count toward `humanApprovals`; superseded reviews are recorded in `reviewers` but not counted. |
| `REQ-F04-030` | Dismissed reviews **MUST NOT** count toward `humanApprovals`. |
| `REQ-F04-040` | Bot and app accounts **MUST** be classified as `automatedReviews` and **MUST NOT** count toward `humanApprovals`. Classification uses the forge's account type, not name heuristics. |
| `REQ-F04-050` | `isChangeAuthor` **MUST** be computed by comparing reviewer immutable ID against the set of commit author and committer IDs in the ChangeSet. |
| `REQ-F04-060` | `evidence.digest` **MUST** be the SHA-256 of the canonicalised forge API response that established the record. |
| `REQ-F04-070` | API responses **MUST** be paginated exhaustively; partial collection **MUST** raise `ERR-COLLECT-122` rather than under-reporting approvals. |
| `REQ-F04-080` | Rate limiting **MUST** be handled with exponential backoff honouring the reset header, up to a configurable deadline, then `ERR-COLLECT-123`. |
| `REQ-F04-090` | Authentication token **MUST** be read from environment or a file, **MUST NOT** be accepted as a CLI flag, and **MUST NOT** appear in logs or diagnostics. |
| `REQ-F04-100` | When no PR context exists (direct push), `Review.state` **MUST** be `none` and `required` **MUST** reflect branch protection if determinable, else `unknown`. |
| `REQ-F04-110` | `reviewLatencySeconds` **MUST** be computed from the last commit push time to the first qualifying approval; if either is unavailable the field **MUST** be omitted, not zeroed. |
| `REQ-F04-120` | All network calls **MUST** have an explicit timeout; there **MUST NOT** be an unbounded request. |
| `REQ-F04-130` | Forge failures **MUST NOT** abort the run by default; `Review.state` becomes `unknown` with a warning. Policy decides whether that is acceptable. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F04-010` | A recorded response produces `github:12345:bob`; renaming the login does not change the ID portion in a replayed fixture. |
| `AC-F04-020` | A reviewer who requested changes then approved counts once, as approved. |
| `AC-F04-030` | A dismissed approval yields `humanApprovals == 0`. |
| `AC-F04-040` | A `Bot`-type approving account appears in `automatedReviews` and yields `humanApprovals == 0`. |
| `AC-F04-050` | A self-approval yields `isChangeAuthor == True`. |
| `AC-F04-060` | `evidence.digest` matches an independently computed digest of the fixture response. |
| `AC-F04-070` | A 3-page fixture yields all reviewers; truncating page 2 raises `ERR-COLLECT-122`. |
| `AC-F04-080` | A 403 rate-limit fixture triggers backoff and eventual `ERR-COLLECT-123`. |
| `AC-F04-090` | The token value never appears in any log line, diagnostic output, or error message across the full test suite. |
| `AC-F04-100` | A direct-push context yields `state == "none"`. |
| `AC-F04-110` | Missing push time omits `reviewLatencySeconds` entirely. |
| `AC-F04-120` | Every `httpx` call site is constructed with an explicit timeout, asserted by a test. |
| `AC-F04-130` | A 500 from the forge yields `state == "unknown"` plus a warning, exit code 0. |

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-COLLECT-121` | Forge authentication failed | Check token scopes: `pull-requests: read`, `checks: read` |
| `ERR-COLLECT-122` | Incomplete pagination | Retry; report if persistent |
| `ERR-COLLECT-123` | Rate limit deadline exceeded | Increase deadline or reduce frequency |
| `ERR-COLLECT-124` | PR context could not be determined | Pass `--pr` explicitly |

## 8. Out of scope

- GitLab and Bitbucket adapters (`OOS-02`, v1.1)
- Judging review quality — attest records that review occurred, never whether it was good
- Enforcing review requirements (F-09 owns that)

## 9. Definition of Done

- [ ] All `REQ-F04-*` implemented, all `AC-F04-*` green
- [ ] Recorded HTTP fixtures for all paths; no live calls in the default test suite
- [ ] Nightly live smoke test against a real repository
- [ ] Token-leak test asserts absence across all output streams
- [ ] Coverage ≥ 90%
- [ ] Cross-cutting obligations satisfied
