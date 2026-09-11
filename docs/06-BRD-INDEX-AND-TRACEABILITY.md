# attest — BRD Index, Build Order, and Traceability

| Field | Value |
|---|---|
| Document ID | `BRD-INDEX` |
| Version | `1.2.0` |
| Status | Baselined |
| Last updated | 2026-09-11 |

---

## 1. How to use the BRDs

Each `BRD-Fxx` is a self-contained work package. Each contains:

1. **Purpose** — one paragraph, why this feature exists
2. **Scope trace** — which `SCOPE-xx` items it satisfies
3. **Dependencies** — which features must exist first
4. **Data contracts** — exact inputs and outputs
5. **Requirements** — `REQ-Fxx-NNN`, each testable
6. **Acceptance criteria** — `AC-Fxx-NNN`, matched one-to-one to requirements
7. **Error codes** — what this feature can raise
8. **Out of scope** — explicit exclusions to prevent creep
9. **Definition of Done** — the checklist

**Rule for implementation (including AI agents):** do not begin a feature until (a) every feature
in its dependency list is Done, and (b) every challenge blocking it in `CHALLENGE-001 §2` is
closed in `CHALLENGE-001 §12`. Later features consume earlier contracts. Building out of order
means inventing the contracts, which is precisely how drift starts.

---

## 2. Build order (NORMATIVE)

```
M1 ─────────────────────────────────────────────────────────────
  F-01  Core domain and predicate schema          (no deps)
  F-02  Git ChangeSet collector                   (F-01)
  F-03  Authorship claim collector                (F-01)
  F-05  Attestation builder                       (F-01, F-02, F-03)
  F-06  Sigstore signing                          (F-01, F-05)
  F-08  Verification                              (F-01, F-06)
  F-10  CLI                                       (F-01…F-08)

M2 ─────────────────────────────────────────────────────────────
  F-04  Review record collector (GitHub)          (F-01)
  F-07  Storage and retrieval                     (F-01, F-06)
  F-09  Policy engine and CI gate                 (F-01, F-04, F-08)
  F-11  GitHub Action packaging                   (F-06, F-07, F-09, F-10)

M3 ─────────────────────────────────────────────────────────────
  F-12  Evidence export and control mapping       (F-07, F-08)
```

### 2.1 Dependency graph

```
                     F-01 (core)
        ┌──────┬───────┼───────┬────────┬────────┐
        │      │       │       │        │        │
      F-02   F-03    F-04    F-06     F-07     F-09
        │      │       │       │        │        │
        └──┬───┘       │       │        │        │
           ▼           │       ▼        │        │
         F-05 ─────────┼───▶ F-06 ──▶ F-08 ──────┘
                       │                │
                       └────────────────┴──▶ F-10 ──▶ F-11
                                             │
                                             └──▶ F-12
```

---

## 3. Feature summary

| ID | Feature | Milestone | Depends on | Primary package |
|---|---|---|---|---|
| `F-01` | Core domain model and predicate schema | M1 | — · gated by `CH-01`, `CH-02` | `attest-core` |
| `F-02` | Git ChangeSet collector (`CSD-1`) | M1 | F-01 · gated by `CH-01`, `CH-08` | `attest-collect` |
| `F-03` | Authorship claim collector | M1 | F-01 | `attest-collect` |
| `F-04` | Review record collector (GitHub) | M2 | F-01 | `attest-collect` |
| `F-05` | Attestation builder | M1 | F-01, F-02, F-03 | `attest-core` |
| `F-06` | Sigstore signing | M1 | F-01, F-05 · gated by `CH-02` | `attest-sign` |
| `F-07` | Storage and retrieval | M2 | F-01, F-06 | `attest-store` |
| `F-08` | Verification | M1 | F-01, F-06 · gated by `CH-02` | `attest-sign` |
| `F-09` | Policy engine and CI gate | M2 | F-01, F-04, F-08 | `attest-policy` |
| `F-10` | CLI | M1 | F-01…F-08 | `attest-cli` |
| `F-11` | GitHub Action packaging | M2 | F-06, F-07, F-09, F-10 | `action/` |
| `F-12` | Evidence export and control mapping | M3 | F-07, F-08 · DoD gated by `CH-04` | `attest-export` |

---

## 4. Scope traceability matrix

Every scope item maps to at least one feature. Every feature maps to at least one scope item. No
orphans in either direction.

| Scope | Description | Features |
|---|---|---|
| `SCOPE-01` | Deterministic ChangeSet digest | F-01, F-02 |
| `SCOPE-02` | Authorship claim collection | F-03 |
| `SCOPE-03` | Review record collection | F-04 |
| `SCOPE-04` | in-toto Statement construction | F-01, F-05 |
| `SCOPE-05` | Keyless signing, DSSE, bundle | F-06 |
| `SCOPE-06` | Git-ref and OCI storage | F-07 |
| `SCOPE-07` | Full verification | F-08 |
| `SCOPE-08` | Policy engine and gate | F-09 |
| `SCOPE-09` | CLI with deterministic exit codes | F-10 |
| `SCOPE-10` | GitHub Action packaging | F-11 |
| `SCOPE-11` | Evidence export | F-12 |

### 4.1 Reverse trace

| Feature | Satisfies |
|---|---|
| F-01 | SCOPE-01, SCOPE-04 |
| F-02 | SCOPE-01 |
| F-03 | SCOPE-02 |
| F-04 | SCOPE-03 |
| F-05 | SCOPE-04 |
| F-06 | SCOPE-05 |
| F-07 | SCOPE-06 |
| F-08 | SCOPE-07 |
| F-09 | SCOPE-08 |
| F-10 | SCOPE-09 |
| F-11 | SCOPE-10 |
| F-12 | SCOPE-11 |

---

## 5. Specification traceability

Which BRD implements which normative section of `SPEC-001`. Every normative section must have
explicit ownership. Shared sections distinguish the F-01 wire structure from the downstream
features that populate it, so no responsibility is orphaned or ambiguous.

| `SPEC-001` section | Subject | Implemented by |
|---|---|---|
| §3 | Statement structure | F-01, F-05 |
| §4 | Canonicalisation | F-01 |
| §5 | `CSD-1` digest algorithm | F-01 (algorithm), F-02 (entry extraction) |
| §6.1 | Predicate structure | F-01 (structure), F-05 (population) |
| §6.2 | `changeSet` field | F-01 (structure), F-02 and F-05 (population) |
| §6.3 | `authorship` field | F-01 (structure), F-03 and F-05 (population) |
| §6.4 | `review` field | F-01 (structure), F-04 and F-05 (population) |
| §6.5 | `checks` field | F-01 (structure), F-04 and F-05 (population) |
| §6.6 | `collection` field | F-01 (structure), F-05 (population) |
| §7 | Signing | F-06 |
| §8 | Verification pipeline | F-08 |
| §8.1 | Mandatory identity check | F-08 |
| §9 | Storage and discovery | F-07 |
| §11 | JSON Schema generation | F-01 |
| §12 | Test vectors | F-01, F-02 |

---

## 6. Cross-cutting obligations

These apply to **every** feature and are part of every Definition of Done. They are listed once
here rather than repeated in each BRD.

| ID | Obligation |
|---|---|
| `X-01` | `mypy --strict` passes; no new `type: ignore` without a coded justification |
| `X-02` | `ruff check` and `ruff format --check` pass |
| `X-03` | import-linter contract passes (no boundary violations) |
| `X-04` | Unit test coverage ≥ 90% for the feature's package; ≥ 95% for `attest-core` |
| `X-05` | Every error path raises a coded error from `GLOSS-001 §6` with a remediation hint |
| `X-06` | No banned language from `GLOSS-001 §2.2` in code, docs, or messages |
| `X-07` | No naive datetimes; all timestamps timezone-aware UTC |
| `X-08` | No network calls in `attest-core`; no I/O in pure modules |
| `X-09` | Public API documented with docstrings that reference the governing `REQ-` id |
| `X-10` | CHANGELOG entry added |

---

## 7. Requirement traceability matrix (to be maintained)

### 7.1 Feature completion status

This is the repository's machine-readable feature lifecycle registry. Valid values are `Planned`,
`In progress`, and `Done`. Only `Done` activates completeness gates for that feature. Update the
status in the same commit that starts or completes the feature; readiness and challenge gates
remain governed by the individual BRD and `CHALLENGE-001`.

| Feature | Status |
|---|---|
| `F-01` | Planned |
| `F-02` | Planned |
| `F-03` | Planned |
| `F-04` | Planned |
| `F-05` | Planned |
| `F-06` | Planned |
| `F-07` | Planned |
| `F-08` | Planned |
| `F-09` | Planned |
| `F-10` | Planned |
| `F-11` | Planned |
| `F-12` | Planned |

### 7.2 Requirement-to-test mapping

Maintained as features are completed. Each row: requirement → acceptance criterion → test. CI
fails if a `REQ-` id exists with no test referencing it (`QA-001 §8`).

| Requirement | Acceptance | Test module | Status |
|---|---|---|---|
| `REQ-F01-010` | `AC-F01-010` | `tests/core/test_models.py` | ☐ |
| `REQ-F01-020` | `AC-F01-020` | `tests/core/test_canonical.py` | ☐ |
| … | … | … | ☐ |

> Populate this table as work proceeds. It is the artifact that proves "no gaps" — an empty cell
> is a gap, visibly.

---

## 8. Anti-gap checklist

Run this before declaring any milestone complete.

- [ ] Every `SCOPE-xx` traced to a feature, and vice versa (§4)
- [ ] Every normative `SPEC-001` section traced to a feature (§5)
- [ ] Every `REQ-` has a matching `AC-` with the same number
- [ ] Every `AC-` has at least one test referencing its ID
- [ ] Every error code raised in code appears in a BRD error table
- [ ] Every challenge `CH-xx` blocking a built feature is closed in `CHALLENGE-001 §12`
- [ ] All `OQ-xx` remain closed; no new one added without an ADR
- [ ] Every cross-cutting obligation `X-01`…`X-10` satisfied for each completed feature
- [ ] Committed JSON Schema matches regenerated schema
- [ ] All `spec/testvectors/` pass on both git backends
