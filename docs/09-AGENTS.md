# AGENTS.md — Rules for AI Coding Agents on this Repository

| Field | Value |
|---|---|
| Document ID | `AGENTS.md` |
| Version | `1.0.4` |
| Status | **NORMATIVE** for agent behaviour |
| Last updated | 2026-09-11 |

> Place this file at the repository root. It is read natively by most coding agents. Its purpose
> is narrow: **stop the agent inventing things.** This project's value is exactness — a
> hallucinated field name, an imagined library call, or a "helpfully simplified" digest
> algorithm silently destroys the product's entire premise.

---

## 1. What this project is

attest produces cryptographically signed, tamper-evident provenance attestations for code
changes. It records **claims** about AI authorship and **forge-verified** review records, binds
them to a deterministic ChangeSet digest, and signs the result with a CI workload identity.

It does **not** detect AI-generated code. It does **not** guarantee compliance. Read
`docs/00-MASTER-PROJECT-DOCUMENT.md §2.2` before writing anything user-facing.

---

## 2. Document authority

Before implementing anything, know which document governs:

| Question | Read |
|---|---|
| What does this field mean? What are the exact rules? | `docs/02-SPEC-001-*.md` — **normative** |
| What is this thing called? | `docs/01-GLOSSARY-AND-CONVENTIONS.md` — **normative** |
| Where does this code live? What may it import? | `docs/03-SYSTEM-ARCHITECTURE.md` — **normative** |
| Which library, which version? | `docs/04-TECH-STACK-PYTHON.md` — **normative** |
| What exactly must this feature do? | `docs/brd/BRD-Fxx.md` — **normative** |
| Why was it done this way? | `docs/05-ADR-LOG.md` |
| How do I create the repository scaffold? | `docs/13-BOOTSTRAP-AND-BOILERPLATE.md` — **normative** |
| What is still genuinely unknown? | `docs/14-OPEN-CHALLENGES-AND-VALIDATION.md` — **normative** |

**If these documents conflict, stop and ask. Do not choose.** A silent reconciliation is a defect
that will be discovered much later at much higher cost.

---

## 3. The five prohibitions

These are absolute.

### 3.1 Do not invent specification behaviour

If `SPEC-001` does not define it, it is not defined. Do not fill gaps with reasonable-seeming
defaults. Report the gap; a human closes it with an ADR.

### 3.2 Do not modify normative documents without an ADR

`SPEC-001`, `GLOSS-001`, `ARCH-001`, `TECH-001`, and the BRDs are baselined. Changing them
requires a new ADR recording what changed and why. Never edit them silently mid-implementation to
match code you have written.

### 3.3 Do not regenerate failing test vectors

If a test vector in `spec/testvectors/` fails, **the implementation is wrong until a human says
otherwise**. Regenerating the expected value to make a test pass destroys the specification and
is the single most damaging action available in this repository. See `QA-001 §4`.

### 3.4 Do not weaken verification

Never add a flag, environment variable, config key, or code path that allows verification to
report success without an identity constraint. See `ADR-004` and `REQ-F08-040`. If a test is
inconvenient because identity checking is mandatory, the test is wrong, not the requirement.

### 3.5 Do not reopen a closed decision

Six questions are closed by `ADR-012` through `ADR-017`: language, predicate URI, storage backend,
inclusion proof, control mappings, licence. Do not propose alternatives, do not add a "simpler
option", do not raise TypeScript. `ADR-011` contains the only condition under which any of this
reopens, and it is not yours to trigger.

If you believe a closed decision is wrong, say so once, in writing, as a `CONFLICT:` report. Do
not act on it.

### 3.6 Do not start a feature whose challenge is open

`CHALLENGE-001 §2` lists which challenges block which features. If `CH-01` is `OPEN`, `BRD-F01`
and `BRD-F02` may not be started. Check `CHALLENGE-001 §12` before beginning any work.

### 3.7 Do not write claims the product cannot support

The banned phrases in `GLOSS-001 §2.2` are checked in CI. Do not reproduce them here or write
them anywhere outside that section's marked allowlist — including code, docstrings, errors,
README, or commit messages.

---

## 4. Library usage rule (most important practical rule)

**You do not know the API surface of the pinned libraries. Verify before you write.**

Before calling into `sigstore`, `pygit2`, `rfc8785`,
or any other dependency:

1. Confirm the installed version: `uv pip show <package>`
2. Read the actual installed source or use `python -c "import x; help(x.y)"`
3. Write a throwaway script that exercises the call and run it
4. Only then write the implementation

Do **not** write code from a remembered API. These libraries change, and cryptographic libraries
that *appear* to work while being used incorrectly are the worst possible outcome for this
project — the failure is invisible until an auditor cannot verify.

If you cannot verify a call, say so and stop. Guessing is never acceptable here.

---

## 5. Workflow per session

1. **Read** `AGENTS.md`, `GLOSS-001`, `SPEC-001`, and the single `BRD-Fxx` in scope. Do not read
   the whole document set — irrelevant context produces invented connections.
2. **Plan.** Produce a plan listing every `REQ-Fxx-NNN` you will implement and the file each
   touches. Wait for approval.
3. **Verify dependencies** per §4.
4. **Write tests first**, each marked with its `AC-` id:
   ```python
   @pytest.mark.ac("AC-F02-010")
   def test_rename_is_delete_plus_add() -> None: ...
   ```
5. **Implement** the minimum satisfying the requirements. No speculative features.
6. **Run `just check`** after every meaningful change.
7. **Self-review** against §9.
8. **Report**: which `REQ-` ids are done, which are not, what you could not verify, and every
   assumption you made.

---

## 6. Scope discipline

- One BRD per session.
- Anything not traceable to a `REQ-` id in the BRD in scope is out of scope.
- Found a bug in another feature? Report it. Do not fix it in this session.
- Think a design is wrong? Say so in writing and propose an ADR. Do not implement your preferred
  alternative.

---

## 7. Code rules

| Rule |
|---|
| `mypy --strict` must pass. No new `type: ignore` without an error code and a justification comment |
| `attest_core` imports nothing with I/O and no sibling package (`ARCH-001 §2.1`) |
| All wire models are Pydantic with `extra="forbid"`, `frozen=True` |
| No naive datetimes anywhere. Timezone-aware UTC only |
| No floats in any signed field |
| Every attest-defined error crossing a public operation boundary carries a code from `GLOSS-001 §6`, a message, and a remediation hint; direct Pydantic diagnostics follow `ADR-030` |
| No secret may be a CLI flag; environment or file only |
| No network call may lack an explicit timeout |
| No new dependency without an ADR |
| Never `print()`; use the structured logger or the CLI output layer |

---

## 8. Uncertainty protocol

When you are unsure, use this exact vocabulary in your report so a human can act:

| Say | Meaning |
|---|---|
| `BLOCKED: <what>` | Cannot proceed without a decision |
| `UNVERIFIED: <what>` | Wrote code against an API I could not confirm — needs human check |
| `ASSUMED: <what>` | Made an assumption; here it is, explicitly |
| `SPEC-GAP: <what>` | The specification does not cover this case |
| `CONFLICT: <a> vs <b>` | Two documents disagree |

**Never** resolve a `SPEC-GAP` or `CONFLICT` yourself. Never leave an `UNVERIFIED` unreported.

An honest "I could not verify this" is far more valuable here than confident wrong code. In a
security product, confident wrong code is the primary risk.

---

## 9. Self-review checklist

Before reporting done:

- [ ] Every `REQ-` in scope implemented, or explicitly listed as not done
- [ ] Every `AC-` has a test referencing its id, and it passes
- [ ] `just check` green (ruff, mypy, import-linter, pytest)
- [ ] No test vector expected value changed
- [ ] No verification bypass introduced
- [ ] No banned language added
- [ ] No new dependency without an ADR
- [ ] No normative document edited without an ADR
- [ ] Every library call verified against the installed version, or flagged `UNVERIFIED`
- [ ] All assumptions reported

---

## 10. Things that look helpful but are forbidden

Listed because they are exactly what a capable agent tends to do:

| Tempting action | Why it is forbidden |
|---|---|
| "Simplifying" the digest algorithm | It is a wire format. Any change breaks every existing attestation. |
| Using `json.dumps(sort_keys=True)` instead of RFC 8785 | Not equivalent. Silent interoperability failure. `TECH-001 §10` |
| Adding a `--skip-identity-check` flag for testing | Destroys the security property. `ADR-004` |
| Adding a retry that swallows a Rekor failure | Produces attestations with no transparency log entry. `REQ-F06-060` |
| Enabling rename detection "because it is more accurate" | Non-deterministic. `ADR-001` |
| Adding line counts to the predicate | Non-reproducible. `SPEC-001 §6.2` |
| Defaulting authorship mode to `human-authored` | Falsifies the record when data is missing. `REQ-F01-170` |
| Storing prompt text "for debugging" | Leaks secrets and personal data. `SEC-001 C-06` |
| Hand-editing the generated JSON Schema | Guarantees spec/implementation drift. `ADR-010` |
| Treating generated JSON Schema as semantic validation | Cross-field invariants require runtime validators. `ADR-021` |
| Importing `securesystemslib` for DSSE handling | Sigstore owns DSSE and bundle operations end-to-end. `ADR-020` |
| Merging verification and policy logic | They answer different questions and must fail differently. `BRD-F09 §8` |
| Adding blockchain anchoring | Rekor already provides this. `ADR-009` |
| Fixing an unrelated bug you noticed | Scope violation. Report it. |
