---
name: brd-session
description: Use when implementing any feature in the attest repository - enforces the one-BRD-per-session loop from AGENTS.md §5, the challenge and dependency gates, the plan-before-code rule, and the AC-marked test-first discipline. Trigger whenever a session is about to touch packages/ or spec/.
---

# BRD session

The default workflow in this repository. One BRD per session. Long sessions drift
(`DEV-001 §6.1`), and drift in a project whose product is a wire format is expensive in a way
that is invisible until audit time.

## 1. Establish the scope — before reading any code

State which single `F-xx` this session implements. If you cannot name exactly one, stop and ask.

Read exactly four things:

1. `AGENTS.md` (repository root) — normative agent rules
2. `GLOSS-001` — the vocabulary
3. `SPEC-001` — the format, and only the sections the BRD cites
4. The single `BRD-Fxx` in scope

**Do not read the rest of the document set.** Irrelevant context produces invented connections.
This is a rule, not a preference (`AGENTS.md §5`, `DEV-001 §6.1`).

## 2. Check the gates — both, before anything else

```bash
# a. Are the blocking challenges closed?
#    CHALLENGE-001 §12 outcome log. If a blocking CH-xx is OPEN, this session cannot start.
grep -A 15 '^## 12. Outcome log' docs/14-OPEN-CHALLENGES-AND-VALIDATION.md

# b. Are the dependency features Done?
#    BRD-INDEX §2 build order, §7 traceability matrix.
grep -A 20 '^## 7. Requirement traceability matrix' docs/06-BRD-INDEX-AND-TRACEABILITY.md
```

Gate table:

| Feature | Blocked while OPEN |
|---|---|
| `F-01`, `F-02` | `CH-01`, `CH-02` (and `CH-08` for `F-02`'s DoD) |
| `F-06`, `F-08` | `CH-02` |
| `F-11` DoD | `CH-09` |
| `F-12` DoD | `CH-04` |

If a gate fails, report `BLOCKED: <feature> gated by <CH-xx>, still OPEN in CHALLENGE-001 §12`
and stop. Do not start "the parts that aren't blocked" — later features consume earlier
contracts, and building out of order means inventing them.

## 3. Plan, then wait

Produce a plan listing:

- every `REQ-Fxx-NNN` in scope, verbatim from the BRD
- the file each one touches
- which package each file belongs to, checked against `ARCH-001 §2`
- any `REQ-` you intend **not** to implement this session, and why

**Wait for approval before writing code.** A plan that names requirements is checkable; code that
name-drops them in comments is not.

## 4. Verify every library call

Use the `verify-library-api` skill. Do not skip this because the call looks obvious. A
cryptographic library used incorrectly *appears* to work — the failure is invisible until an
auditor cannot verify.

## 5. Tests first, each carrying its acceptance criterion

```python
@pytest.mark.ac("AC-F02-010")
def test_rename_is_delete_plus_add() -> None: ...
```

Every `AC-Fxx-NNN` in the BRD gets at least one referencing test. `just trace` enforces the
mapping; disabling the check is never the fix.

Also implement the BRD's §7 property-based tests where it has them — for `F-01` those are
canonicalisation idempotence, digest invariance under entry permutation, digest sensitivity to any
single-field mutation, and lossless alias round-trip.

## 6. Implement the minimum

No speculative features. Anything not traceable to a `REQ-` id in the BRD in scope is out of scope
(`AGENTS.md §6`). Found a bug in another feature? Report it. Do not fix it in this session.

Run `just check` after every meaningful change. Type errors and import-linter violations are the
early warning system for hallucinated structure.

## 7. Self-review, then report

Work the checklist in `AGENTS.md §9` and `CLAUDE.md §10`. Then report, using the exact vocabulary
from `AGENTS.md §8`:

- `REQ-` ids implemented
- `REQ-` ids **not** implemented, and why
- every `UNVERIFIED:` — code written against an API you could not confirm
- every `ASSUMED:` — stated explicitly, not buried
- any `SPEC-GAP:` or `CONFLICT:` — **never resolved by you**

An honest "I could not verify this" is worth far more here than confident wrong code.

## Red flags — stop if you catch yourself thinking any of these

| Thought | Reality |
|---|---|
| "The vector's expected value must be stale" | The implementation is wrong until a human says otherwise. `AGENTS.md §3.3` |
| "A `--skip-identity-check` flag would make testing easier" | It destroys the only security property the product has. `ADR-004` |
| "`json.dumps(sort_keys=True)` is the same as RFC 8785" | It is not. Silent interoperability failure. `TECH-001 §10` |
| "Rename detection would be more accurate" | Non-deterministic. `ADR-001` |
| "Defaulting to `human-authored` is friendlier" | It falsifies the record when data is missing. `REQ-F01-170` |
| "I'll fix this unrelated bug while I'm here" | Scope violation. Report it |
| "The spec doesn't say, so I'll pick something sensible" | `SPEC-GAP:`. A human closes it with an ADR |
