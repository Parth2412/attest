---
name: adr-workflow
description: Use whenever a decision needs recording in the attest repository - changing a normative document, adding a dependency, amending a BRD, closing an open question, changing a test vector, or responding to a challenge outcome. ADRs are the only legal mechanism for changing a baselined document. Also use when tempted to reopen ADR-012 through ADR-017, which are closed.
---

# ADR workflow

`ADR-LOG` is normative for recorded decisions. The rule that makes the whole document set hold
together:

> **Any change to a normative document requires a new ADR recording what changed and why. Silent
> edits to normative documents are forbidden.** (`MPD-001 §12`, `AGENTS.md §3.2`)

This rule exists specifically so that a coding agent cannot quietly redefine the format
mid-implementation. ADRs are **append-only** — superseded, never edited.

## When an ADR is required

| Situation | ADR required |
|---|---|
| Changing `SPEC-001`, `GLOSS-001`, `ARCH-001`, `TECH-001`, or any `BRD-Fxx` | **Yes** |
| Adding, removing, or replacing a dependency | **Yes** (`AGENTS.md §7`) |
| Adding or changing a test vector that changes normative behaviour | **Yes** (`QA-001 §4`) |
| A challenge outcome that changes a decision | **Yes** (`CHALLENGE-001 §1`) |
| Amending a performance target you cannot meet | **Yes** (`CH-08`, `ARCH-001 §11`) |
| Extending the policy vocabulary | **Yes** (`ADR-008`) |
| Adding an `OQ-` to `MPD-001 §14` | **Yes** |
| Closing a challenge with the expected outcome, changing nothing | No — record in `CHALLENGE-001 §12` |
| Implementing a `REQ-` as written | No |
| Fixing a bug without changing specified behaviour | No |

## Writing one

```bash
just adr "Short imperative title"
```

That appends a skeleton to `docs/05-ADR-LOG.md` with the next sequential number and today's UTC
date (`BOOT-001 §11`). It never edits an existing ADR. Then fill the template:

```markdown
## ADR-0NN — <short imperative title>

**Status:** Proposed | Accepted | Superseded by ADR-0MM · **Date:** YYYY-MM-DD · **Affects:** <docs/features>

**Context.** What forced a decision.

**Decision.** What was decided, stated as a rule.

**Rationale.** Why, including the constraint that dominated.

**Rejected alternatives.** What else was considered and why it lost.

**Consequences.** What this costs, and what now becomes harder or impossible.
```

Quality bar, from the existing ADRs:

- **Decision is a rule**, not a description. "`CSD-1` digests a canonicalised, path-sorted list of
  `(path, changeType, oldMode, newMode, oldBlob, newBlob)` entries with rename and copy detection
  disabled" — testable. "We'll use git object IDs" — not.
- **Rejected alternatives are named with the reason they lost.** This is what stops the decision
  being relitigated in six months by a contributor or an agent proposing "a simpler approach".
- **Consequences state the cost honestly**, including what becomes impossible. `ADR-001` says
  outright that line-level statistics can never be part of the signed record.

## Same commit, both files

An ADR and the normative-document edit it authorises land **together**. An ADR with no
corresponding edit is a proposal; an edit with no ADR is a defect.

Also update in the same PR:
- `PROJECT_SPECS.md` if project state changed
- `COMPATIBILITY.md` if a version, runtime floor, or wire contract changed
- `CHANGELOG.md` always (`X-10`)

## The closed decisions — do not reopen

Six questions are closed. Do not propose alternatives, do not add "a simpler option", do not
raise TypeScript.

| ADR | Decision |
|---|---|
| `ADR-012` | Implementation language is **Python 3.12+**, final for v1.x |
| `ADR-013` | Predicate type URI is org-controlled; v0.x explicitly unstable; freezes at v1.0 |
| `ADR-014` | Storage is `refs/attestations/<digest>`; git notes are not used for storage |
| `ADR-015` | Inclusion proof embedded at signing, verified offline; no online substitute |
| `ADR-016` | Control mappings build now as `draft-unreviewed`; publishing gated on practitioner review |
| `ADR-017` | Apache-2.0 for code, CC-BY-4.0 for the specification |

`ADR-011` holds the **only** condition that reopens the language question — at the M2 exit gate,
installation or runtime friction ranked top complaint by a majority of design partners, and then
the **verifier only**. It is not yours to trigger. Nobody may begin such a port speculatively.

If you believe a closed decision is wrong: say so **once**, in writing, as a `CONFLICT:` report.
Do not act on it. (`AGENTS.md §3.5`)

## Decisions that are not open questions

Some things are permanently settled and are not ADR material at all — raising them is the
mistake:

- Whether authorship claims are true — unknowable by design (`ADR-003`)
- Whether reviewers understood the code — unknowable
- Statistical AI-code detection — permanently out of scope (`OOS-05`)
- Blockchain anchoring — Rekor already is the Merkle transparency log (`ADR-009`)
- A database in v1.0 — turns a decentralised tool into a service prematurely
- An embedded scripting language for policy — arbitrary code execution in a job holding signing
  permissions (`ADR-008`)
