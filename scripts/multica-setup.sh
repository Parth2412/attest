#!/usr/bin/env bash
# multica-setup.sh — provision the attest board in Multica.
#
# Idempotent: re-running creates nothing that already exists (matched by name/title).
# Requires: multica CLI authenticated, daemon running, jq.
#
# Design rule — READ THIS BEFORE EDITING:
#   Tickets POINT AT the document set. They never copy REQ/AC text into the
#   description. Two copies of a requirement is two sources of truth, which is
#   exactly the drift MPD-001 §12 exists to prevent. A ticket carries: scope,
#   gates, owner, and where the normative text lives.
#
# Usage:
#   bash scripts/multica-setup.sh            # provision
#   bash scripts/multica-setup.sh --dry-run  # print what would be created

set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

REPO_URL="git@github.com:Parth2412/attest.git"
REPO_HTTPS="https://github.com/Parth2412/attest"

# ---------------------------------------------------------------- preflight --

require() { command -v "$1" >/dev/null || { echo "missing: $1" >&2; exit 1; }; }
require multica
require jq

if ! multica auth status >/dev/null 2>&1; then
  echo "Not authenticated. Run: multica setup self-host" >&2
  exit 1
fi

WORKSPACE_ID="$(multica workspace get --output json 2>/dev/null | jq -r '.id // empty')"
[[ -n "$WORKSPACE_ID" ]] || { echo "No default workspace. Run: multica workspace switch <id|slug>" >&2; exit 1; }
echo "==> workspace: $WORKSPACE_ID"

# `list` commands return either a bare array or an object with a named key,
# depending on the endpoint. This makes the accessor type-safe for both.
JQ_ARR='def arr(k): if type=="array" then . else (.[k] // []) end;'

# Prefer an online Claude runtime; fall back to any online runtime.
RUNTIME_PROVIDER="${ATTEST_RUNTIME_PROVIDER:-claude}"
RUNTIME_ID="$(multica runtime list --output json 2>/dev/null | jq -r \
  --arg p "$RUNTIME_PROVIDER" "$JQ_ARR"'
    (arr("runtimes") | map(select(.provider==$p and .status=="online")) | .[0].id)
    // (arr("runtimes") | map(select(.status=="online")) | .[0].id)
    // empty')"
if [[ -z "$RUNTIME_ID" ]]; then
  echo "No online runtime registered. Start the daemon first: multica daemon start" >&2
  exit 1
fi
echo "==> runtime:   $RUNTIME_ID ($RUNTIME_PROVIDER)"

# Model is intentionally NOT guessed. Unset means "whatever the runtime defaults to",
# which is the installed Claude Code's own default. Set ATTEST_AGENT_MODEL to pin one.
MODEL="${ATTEST_AGENT_MODEL:-}"

# ------------------------------------------------------------------ helpers --

run() { if (( DRY_RUN )); then echo "DRY: $*"; else "$@"; fi; }

# project_ensure <title> <icon> <description> -> prints project id
project_ensure() {
  local title="$1" icon="$2" desc="$3" id
  id="$(multica project list --output json 2>/dev/null \
        | jq -r --arg t "$title" "$JQ_ARR"'arr("projects")[]? | select(.title==$t) | .id' | head -1)"
  if [[ -n "$id" ]]; then echo "$id"; return; fi
  if (( DRY_RUN )); then echo "DRY-PROJECT-$title"; return; fi
  multica project create --title "$title" --icon "$icon" --description "$desc" \
    --lead "Lambda" --output json | jq -r '.id'
}

# issue_id_by_title <title> -> prints id or empty
issue_id_by_title() {
  multica issue list --limit 500 --output json 2>/dev/null \
    | jq -r --arg t "$1" "$JQ_ARR"'arr("issues")[]? | select(.title==$t) | .id' | head -1
}

# issue_ensure <title> <assignee> <priority> <project_id> <parent_id|""> [meta k=v ...]
# description is read from stdin
issue_ensure() {
  local title="$1" assignee="$2" priority="$3" project="$4" parent="$5"; shift 5
  local desc id
  desc="$(cat)"

  id="$(issue_id_by_title "$title")"
  if [[ -n "$id" ]]; then
    echo "    = exists: $title" >&2
    issue_label "$id" "$@"
    echo "$id"; return
  fi
  if (( DRY_RUN )); then
    echo "DRY: issue create --title \"$title\" --assignee $assignee --priority $priority" >&2
    echo "DRY-ISSUE"; return
  fi

  local args=(issue create --title "$title" --assignee "$assignee"
              --priority "$priority" --project "$project"
              --status backlog --description-stdin --output json)
  [[ -n "$parent" ]] && args+=(--parent "$parent")

  id="$(printf '%s' "$desc" | multica "${args[@]}" | jq -r '.id')"
  echo "    + created: $title ($id)" >&2
  issue_label "$id" "$@"
  echo "$id"
}

# issue_label <issue-id> <label-name>... — idempotent, safe to re-apply
issue_label() {
  local id="$1"; shift
  (( DRY_RUN )) && return 0
  local have lname lid
  have="$(multica issue label list "$id" --full-id --output json 2>/dev/null \
          | jq -r "$JQ_ARR"'arr("labels")[]?.name' 2>/dev/null || true)"
  for lname in "$@"; do
    grep -qxF "$lname" <<<"$have" && continue
    lid="$(label_ensure "$lname")"
    [[ -n "$lid" ]] && multica issue label add "$id" "$lid" >/dev/null 2>&1 || true
  done
}

# label_ensure <name> -> prints label id (creates on first use)
label_ensure() {
  local name="$1" id colour
  id="$(multica label list --output json 2>/dev/null \
        | jq -r --arg n "$name" "$JQ_ARR"'arr("labels")[]? | select(.name==$n) | .id' | head -1)"
  if [[ -n "$id" ]]; then echo "$id"; return; fi
  case "$name" in
    F-*)         colour="#3b82f6" ;;  # feature      blue
    CH-*)        colour="#ef4444" ;;  # challenge    red
    M1|M2|M3|W0) colour="#8b5cf6" ;;  # milestone    violet
    pkg:*)       colour="#14b8a6" ;;  # package      teal
    gate:*)      colour="#f59e0b" ;;  # blocking     amber
    *)           colour="#6b7280" ;;  # kind         grey
  esac
  multica label create --name "$name" --color "$colour" --output json 2>/dev/null | jq -r '.id'
}

# agent_ensure <name> <charter-path> <description>
agent_ensure() {
  local name="$1" charter="$2" desc="$3" id
  id="$(multica agent list --output json 2>/dev/null \
        | jq -r --arg n "$name" "$JQ_ARR"'arr("agents")[]? | select(.name==$n) | .id' | head -1)"
  if [[ -n "$id" ]]; then echo "    = agent exists: $name" >&2; echo "$id"; return; fi
  if (( DRY_RUN )); then echo "DRY: agent create --name $name" >&2; echo "DRY-AGENT"; return; fi

  local margs=()
  [[ -n "$MODEL" ]] && margs=(--model "$MODEL")
  id="$(multica agent create \
        --name "$name" \
        --runtime-id "$RUNTIME_ID" \
        "${margs[@]}" \
        --visibility workspace \
        --description "$desc" \
        --instructions "$(agent_instructions "$name" "$charter")" \
        --output json | jq -r '.id')"
  echo "    + agent created: $name ($id)" >&2
  echo "$id"
}

agent_instructions() {
  local name="$1" charter="$2"
  cat <<EOF
You are ${name} on the attest project.

FIRST, in this order, every session:
  1. git clone ${REPO_URL} (or reuse the checkout) and cd into it
  2. Read AGENTS.md at the repository root — NORMATIVE for your behaviour
  3. Read ${charter} — your charter: scope, non-negotiables, workflow
  4. Read CLAUDE.md §5 (session protocol) and §10 (validation checklist)
  5. Read the single BRD named in your assigned issue. Nothing else.

HARD RULES (AGENTS.md §3 — absolute):
  - Never regenerate a failing test vector's expected value. A failing vector
    means the implementation is wrong until a human says otherwise.
  - Never add a flag, env var, config key, or code path that lets verification
    succeed without an identity constraint.
  - Never write a library call from memory. Confirm the installed version, read
    the installed source, run a throwaway script, then implement.
  - Never edit a normative document without an ADR in the same commit.
  - Never reopen ADR-012 through ADR-017.
  - Never start a feature whose blocking CH-xx is OPEN in CHALLENGE-001 §12.
  - Never use banned language from GLOSS-001 §2.2 — including in commit messages.
  - Never fix an unrelated bug you notice. Report it as a new issue instead.

WHEN UNSURE, use this exact vocabulary in an issue comment and STOP:
  BLOCKED: <what>   UNVERIFIED: <what>   ASSUMED: <what>
  SPEC-GAP: <what>  CONFLICT: <a> vs <b>
Never resolve a SPEC-GAP or CONFLICT yourself — comment and reassign to Lambda.

DELIVERY:
  - Branch feat/F-NN-<slug>; PR targets dev, never main.
  - Commit body MUST list the REQ- ids implemented.
  - Every commit carries: X-Attest-Claim: agent=claude-code; model=anthropic/<model>; session=<id>
  - Run 'just check' after every meaningful change.
  - Move the issue to in_review and comment with: REQ ids done, REQ ids not done,
    every UNVERIFIED, every ASSUMED.
EOF
}

# ------------------------------------------------------------------- agents --

echo "==> agents"
agent_ensure "Lambda"  "agents/lambda/AGENT.md"  "Coordinator & Tech Lead — gate enforcement, ADR intake, merges into dev" >/dev/null
agent_ensure "Atlas"   "agents/atlas/AGENT.md"   "Core & Specification Engineer — attest-core, spec/, test vectors" >/dev/null
agent_ensure "Sage"    "agents/sage/AGENT.md"    "Collectors & Storage Engineer — attest-collect, attest-store" >/dev/null
agent_ensure "Cipher"  "agents/cipher/AGENT.md"  "Signing, Verification & Security Reviewer — attest-sign, SEC-001" >/dev/null
agent_ensure "Pixel"   "agents/pixel/AGENT.md"   "Policy & CLI Engineer — attest-policy, attest-cli" >/dev/null
agent_ensure "Forge"   "agents/forge/AGENT.md"   "DevOps & Packaging Engineer — CI, container, Action, release" >/dev/null
agent_ensure "Quill"   "agents/quill/AGENT.md"   "Documentation, Spec Publication & Compliance — docs/, attest-export" >/dev/null
agent_ensure "Nexus"   "agents/nexus/AGENT.md"   "Code Quality & Correctness Reviewer — reviews every PR" >/dev/null
agent_ensure "Arbiter" "agents/arbiter/AGENT.md" "Release Authority — dev to main, QA-001 §12 gate" >/dev/null

# ----------------------------------------------------------------- projects --

echo "==> projects"
P_W0="$(project_ensure "Week 0 — Validation" "🔬" \
  "Five days, throwaway code only, none committed. Closes CH-01 and CH-02 before BOOT-001 may run. CHALLENGE-001 §13.")"
P_M1="$(project_ensure "M1 — Signed core" "🔐" \
  "Days 0-30. Exit: a signed attestation is produced in real CI and verifies on a clean machine with no local state. SPEC-001 published. ROADMAP-001 §2.")"
P_M2="$(project_ensure "M2 — Enforcement" "🚦" \
  "Days 31-60. Exit: a policy violation blocks a real merge via a required status check. Three external repositories running it. ROADMAP-001 §3.")"
P_M3="$(project_ensure "M3 — Evidence" "📋" \
  "Days 61-90. Exit: a practising auditor confirms in writing an exported bundle is usable as change-management evidence. One paid pilot agreed. ROADMAP-001 §4.")"
echo "    W0=$P_W0  M1=$P_M1  M2=$P_M2  M3=$P_M3"

# ======================================================================= W0 ==

echo "==> Week 0 issues"

CH01="$(issue_ensure "CH-01 — Prove CSD-1 survives real repositories" Atlas urgent "$P_W0" "" "CH-01" "W0" "blocks:F-01" "blocks:F-02" "validation" <<'EOF'
Normative: CHALLENGE-001 §3. Gate: §3 "Gate — all must hold".

WHY THIS IS FIRST
CSD-1 is a wire format. Once published and signed against, a flaw in it invalidates
every attestation ever produced. Two days now, or a rewrite later.

THROWAWAY ONLY. None of this code is committed to the repository. Do not create
packages/, do not run BOOT-001, do not write production code.

WORK (CHALLENGE-001 §3 "The experiment")
1. Implement CSD-1 per SPEC-001 §5.3 in ~150 lines using pygit2.
2. Run against at least five real repositories: one large monorepo, one with
   submodules, one with non-ASCII paths, one with heavy binary content, one of ours.
3. For each, compute the digest for the last 200 merge commits.
4. Re-run everything on a second machine and a different OS.
5. Independently implement step 3 with `git diff-tree --no-renames --raw` and compare.

EXIT — all four must hold, verbatim from CHALLENGE-001 §3:
[ ] Digests identical across machines and OSes for every commit
[ ] pygit2 and git-CLI implementations agree on 100% of cases
[ ] Every squash-merged PR produces a stable digest across the squash
[ ] No repository produces an unhandled case not covered by SPEC-001 §5.4

OUTCOMES
- All hold        -> record CLOSED in CHALLENGE-001 §12; F-01 unblocks
- New edge case   -> add to SPEC-001 §5.4 BEFORE publication, via ADR. Cheap now,
                     impossible later.
- Implementations disagree -> STOP. Disagreement means CSD-1 is under-specified,
                     which is fatal for a standard. Escalate to Lambda.

DONE = the outcome row for CH-01 in CHALLENGE-001 §12 is filled in and committed.
EOF
)"

CH02="$(issue_ensure "CH-02 — Verify the eight library assumptions by executing code" Cipher urgent "$P_W0" "" "CH-02" "W0" "blocks:F-06" "blocks:F-08" "validation" <<'EOF'
Normative: CHALLENGE-001 §4.

THROWAWAY ONLY. One script per assumption. Each must ACTUALLY RUN — reading
documentation is not verification.

ASSUMPTIONS (CHALLENGE-001 §4)
  A  sigstore-python detects the GitHub Actions ambient OIDC credential without
     manual token handling                                        REQ-F06-030
  B  The emitted bundle embeds a Rekor inclusion proof verifiable OFFLINE
                                                       REQ-F08-070, ADR-015
  C  Verification can be constrained to an expected certificate identity AND
     issuer                                                        REQ-F08-040
  D  A Sigstore staging environment is usable for tests             QA-001 §10
  E  securesystemslib DSSE envelopes interoperate with the Sigstore bundle format
                                                                   REQ-F06-020
  F  pygit2 exposes tree-diff with rename detection genuinely off   REQ-F02-010
  G  rfc8785 output matches a second independent JCS implementation REQ-F01-030
  H  Pydantic v2 JSON Schema generation covers every construct the models need
                                                                   REQ-F01-120

ASSUMPTION C IS THE ONE THAT STOPS THE PROJECT.
Verify it NEGATIVELY: sign with identity X, verify constrained to identity Y,
confirm verification FAILS. A passing verification proves nothing here.

EXIT
[ ] All eight verified by executing code
[ ] C demonstrated by a FAILING verification, not a passing one
[ ] Exact working versions recorded (they get pinned into uv.lock at bootstrap)

OUTCOMES
- All hold  -> record CLOSED in CHALLENGE-001 §12; F-06/F-08 unblock
- C fails   -> STOP EVERYTHING. Without identity-constrained verification the
               product has no security property (ADR-004). Escalate to Lambda
               and the human owner. This is a re-evaluate-the-approach event.
- B fails   -> offline verification impossible with the current library;
               ADR-015 needs revisiting via a new ADR before F-08
- Any other -> record the ACTUAL behaviour; amend the affected BRD via ADR
               before implementing

All test signing targets Sigstore STAGING. Never the production transparency log.

DONE = the outcome row for CH-02 in CHALLENGE-001 §12 is filled in and committed.
EOF
)"

issue_ensure "CH-03 — Can agent harnesses reliably emit claims?" Sage high "$P_W0" "" "CH-03" "W0" "blocks:M2-exit" "validation" <<'EOF'
Normative: CHALLENGE-001 §5. This is RISK-07, the highest-scored technical risk.

WHY IT MATTERS
If harnesses do not emit claims, most attestations record mode: unknown. Every
other part of the system can be perfect and the product is still worthless — a
cryptographically impeccable record of nothing.

WORK
For each of Claude Code, Cursor, and one CLI agent (Codex or Gemini CLI):
1. Write the smallest hook that writes a sidecar claim on file modification,
   per the format in ARCH-001 §7.
2. Use it for a full working week on real work.
3. Measure: what fraction of AI-touched changes produced a claim; whether
   session IDs are obtainable; whether path scope is accurate; how often the
   hook silently fails.

EXIT
[ ] At least two harnesses reliably emit claims
[ ] Claim rate above 90% of AI-touched changes for those harnesses
[ ] Path scope accurate enough that ai-assisted vs ai-authored is meaningful
[ ] Session ID obtainable for at least one harness

OUTCOMES
- Gate met         -> hooks become examples/hooks/ and a headline onboarding asset
- Only one harness -> proceed, but scope the product to that harness in GTM and
                      say so plainly
- None reliable    -> RECONSIDER THE PRODUCT. Fall back to review-record
                      attestation only. Record as an ADR and rewrite MPD-001 §2.

Starts in Week 0, runs in parallel with M1, gates the M2 exit.
Ongoing metric: mode == "unknown" share. Above 50% after onboarding triggers K4.
EOF

issue_ensure "CH-04 — Does the evidence shape satisfy a real auditor?" Quill high "$P_W0" "" "CH-04" "W0" "blocks:F-12-DoD" "validation" <<'EOF'
Normative: CHALLENGE-001 §6. One week elapsed, ~4 hours of work.

WHY IT MATTERS
The entire compliance thesis rests on assumption A1: auditors will accept
cryptographic attestations as change-management evidence. Nobody has tested this.

WORK
Hand-build a MOCK evidence bundle — manifest.json, summary.md, one control
narrative, five real attestations, verify.sh. No code required beyond CH-01/CH-02
output. Show it to TWO practising auditors (SOC 2, ideally one with ISO 42001
exposure) and ask exactly three questions:
  1. Would you accept this as change-management evidence for AI-generated code?
  2. What is missing that you would need?
  3. Which control identifiers would you actually cite?

Question 3 supplies the input ADR-016 deliberately defers. Do not guess mappings.

EXIT
[ ] Two auditors reviewed the mock
[ ] At least one would accept it, with or without stated additions
[ ] Control identifiers obtained for at least one framework

OUTCOMES
- Accepted            -> mark the mapping status: reviewed per ADR-016; F-12 can
                         reach DoD
- Accepted with adds  -> add missing fields to SPEC-001 via ADR BEFORE M1
                         publication if they touch the format
- Both reject         -> kill criterion K2 territory. The compliance thesis is
                         wrong; re-evaluate against RISK-001 §5 before building F-12.

Starts in Week 0, gates the F-12 Definition of Done.
EOF

BOOT="$(issue_ensure "BOOT-001 — Bootstrap the repository scaffold (zero logic)" Forge urgent "$P_W0" "" "W0" "gate:CH-01" "gate:CH-02" "bootstrap" <<'EOF'
Normative: BOOT-001 (docs/13-BOOTSTRAP-AND-BOILERPLATE.md). Every file listed,
every config given verbatim.

BLOCKED until CH-01 and CH-02 are recorded CLOSED in CHALLENGE-001 §12.
Check that first. If either is OPEN, comment "BLOCKED: gated by CH-0x" and stop.

THE SCAFFOLD CONTAINS NO BUSINESS LOGIC.
If any logic is written during bootstrap, the bootstrap is wrong (BOOT-001 §16).
Stub modules are a docstring naming their governing BRD and nothing else — no
pass, no TODO, no placeholder functions.

WORK
1. Create every path in BOOT-001 §2. Reproduce §3 (root pyproject.toml),
   §5 (.importlinter), §6 (Justfile), §7 (.pre-commit-config.yaml),
   §8 (.gitignore), §12 (ci.yml), §13 (constants.py, exit_codes.py) VERBATIM.
   They are marked NORMATIVE — reproduce, do not improve.
2. Copy ../project-info/ into docs/ (including brd/). Then delete CLAUDE.md §0.1,
   because the path mapping it documents no longer applies.
3. Replace <org> in packages/attest-core/src/attest_core/constants.py (ADR-013).
4. Write the three scripts to their behaviour contracts: §9 check_banned_language.py,
   §10 check_traceability.py, §11 new_adr.py.
5. Do not create e2e-sign.yml, action-candidate.yml, or release.yml. Their owning
   BRDs (F-06, F-11) create those paths only when the workflows are valid
   (ADR-028, ADR-046).
6. uv sync --all-packages && uv run pre-commit install

FORBIDDEN during bootstrap (BOOT-001 §17)
  implementing any function · hand-writing the JSON Schema · creating test vectors ·
  pinning dependency versions from memory · adding a dependency not in §4.1 ·
  creating e2e-sign.yml, action-candidate.yml, or release.yml · choosing a different layout ·
  "improving" any configuration in BOOT-001

EXIT — the fourteen boxes of BOOT-001 §16, all of them. Notably:
[ ] just check passes with zero findings on an empty codebase
[ ] just imports passes — all four contracts load and pass
[ ] just trace passes and prints a table with zero Done features
[ ] just schema FAILS CLEANLY with a "not yet implemented" error, NOT a traceback
[ ] No stub module contains executable code
[ ] <org> replaced in constants.py
[ ] AGENTS.md at the root (already present — verify it is byte-identical to docs/09-AGENTS.md)
[ ] LICENSE is Apache-2.0 and LICENSE.spec is CC-BY-4.0 (ADR-017)
[ ] CI green on the bootstrap commit
[ ] Zero business logic anywhere

Commit: chore: bootstrap repository scaffold per BOOT-001
EOF
)"

# ======================================================================= M1 ==

echo "==> M1 issues"

F01="$(issue_ensure "F-01 — Core domain model and predicate schema" Atlas urgent "$P_M1" "" "F-01" "pkg:attest-core" "M1" "gate:CH-01" "gate:CH-02" <<'EOF'
Normative: docs/brd/BRD-F01.md. Scope: SCOPE-01, SCOPE-04.
Implements SPEC-001 §3, §4, §5 (algorithm), §11, §12.

GATES: CH-01 and CH-02 closed in CHALLENGE-001 §12. Dependencies: none — this is
the root of the dependency graph.

WHY IT IS FIRST AND WHY IT IS OVER-TESTED
Every other feature either produces or consumes these types. Get this wrong and
every downstream feature inherits the error.

SCOPE — the requirements are REQ-F01-010 .. REQ-F01-180 in the BRD. Read them
there; they are not duplicated here on purpose. Highlights that get broken most:
  - attest-core imports NO sibling package and NO I/O library (REQ-F01-140)
  - canonicalize() is RFC 8785 via the rfc8785 library. json.dumps(sort_keys=True)
    is NOT equivalent (REQ-F01-030)
  - CSD-1 sorts by RAW UTF-8 BYTES. No locale collation, no Unicode normalisation
    (REQ-F01-050, REQ-F01-060)
  - AuthorshipMode NEVER defaults to human-authored. Absence is unknown (REQ-F01-170)
  - The JSON Schema is GENERATED. Never hand-authored, never hand-edited (ADR-010)
  - digest.py takes ChangeSetEntry[] and never touches git — that is what makes it
    testable against fixed vectors with no repository

CHILD ISSUES carry the actual work. This issue closes when all of them close and
BRD-F01 §10 Definition of Done is fully ticked.

DoD (BRD-F01 §10)
[ ] All REQ-F01-* implemented, all AC-F01-* green
[ ] All four properties in BRD-F01 §7 implemented in Hypothesis
[ ] All SPEC-001 §12 vectors present and passing
[ ] Coverage >= 95% on attest-core
[ ] Cross-cutting X-01..X-10 satisfied
[ ] Generated schema committed and drift check green
[ ] mutmut run on digest.py and canonical.py; surviving mutants killed or
    justified IN WRITING
EOF
)"

issue_ensure "F-01a — Wire models, enums, and error taxonomy" Atlas high "$P_M1" "$F01" "F-01" "pkg:attest-core" "M1" <<'EOF'
Parent: F-01. Normative: BRD-F01 §4.1, §4.2. Requirements REQ-F01-010, -020,
-070, -080, -090, -100, -110, -150, -170, -180.

Types: Statement, Subject, Predicate, ChangeSetInfo, Authorship, AuthorshipClaim,
AgentRef, ModelRef, ClaimSource, ClaimScope, Review, Reviewer, AutomatedReview,
Check, Collection, CollectorRef, EnvironmentRef, ChangeSetRecord, ChangeSetEntry.

Enums are CLOSED. An unknown value from an external source raises ERR-BUILD-204 —
never silently coerced.

Model config on every wire type: extra="forbid", frozen=True, populate_by_name=True.
Python snake_case, serialisation aliases camelCase, dumped by alias.

Tests carry @pytest.mark.ac("AC-F01-0NN") for AC-F01-010, -020, -070, -080, -090,
-100, -110, -150, -170, -180.
EOF

issue_ensure "F-01b — RFC 8785 canonicalisation" Atlas high "$P_M1" "$F01" "F-01" "pkg:attest-core" "M1" <<'EOF'
Parent: F-01. Normative: SPEC-001 §4, REQ-F01-030, REQ-F01-040.

Use the rfc8785 library. Do NOT hand-roll. json.dumps(sort_keys=True) differs on
number formatting, key ordering (code point vs UTF-16 code unit), and escaping —
a silent interoperability bug that only surfaces once a second implementation
exists, i.e. exactly when the standards play starts working (TECH-001 §10).

Raise ERR-BUILD-201 on a float, NaN, infinity, or a non-UTF-8-representable string.

Authors the spec/testvectors/jcs-canonical/ vectors. They are NORMATIVE — a
vector's expected value is never regenerated to make a test pass.

Property test: canonicalize(v) == canonicalize(json.loads(canonicalize(v))).

Tests: AC-F01-030, AC-F01-040.
EOF

issue_ensure "F-01c — CSD-1 digest" Atlas urgent "$P_M1" "$F01" "F-01" "pkg:attest-core" "M1" "gate:CH-01" <<'EOF'
Parent: F-01. Normative: SPEC-001 §5, REQ-F01-050, REQ-F01-060.

THE WIRE FORMAT. Whatever ships here is permanent from publication.

Sort entries by RAW UTF-8 BYTES of path, ascending. No locale collation. No
Unicode normalisation. Build the record per SPEC-001 §5.3 step 5, canonicalise,
SHA-256, lowercase hex.

compute_changeset_digest() takes an already-built ChangeSetRecord. It NEVER reads
a repository — entry extraction is F-02's job.

Property tests (BRD-F01 §7):
  - digest invariant under entry permutation
  - digest changes under ANY single-field mutation

AC-F01-060 is the important one: csd1-path-ordering must pass under
LC_ALL=tr_TR.UTF-8 AND LC_ALL=C. That test exists because locale-sensitive
sorting is the most plausible way CSD-1 silently diverges between two
independent implementations.

Run mutmut on digest.py. Every surviving mutant killed or justified in writing.

Tests: AC-F01-050, AC-F01-060.
EOF

issue_ensure "F-01d — JSON Schema generation and drift check" Atlas high "$P_M1" "$F01" "F-01" "pkg:attest-core" "M1" <<'EOF'
Parent: F-01. Normative: SPEC-001 §11, ADR-010, REQ-F01-120, REQ-F01-130.

generate_json_schema() produces the schema FROM THE MODELS. `just schema` writes
it to spec/schemas/ai-authorship-v0.1.schema.json. CI fails if the committed file
differs from the regenerated one.

Hand-editing the generated schema guarantees spec/implementation drift. Since the
specification is the strategic asset, that is the single most damaging quality
failure available to this project.

Wire the schema-drift CI job (BOOT-001 §12) to `just schema-check`.

Tests: AC-F01-120, AC-F01-130.
EOF

issue_ensure "F-01e — Author the normative test vectors" Atlas urgent "$P_M1" "$F01" "F-01" "pkg:attest-core" "M1" "spec" <<'EOF'
Parent: F-01. Normative: SPEC-001 §12, QA-001 §4, REQ-F01-160.

spec/testvectors/ IS the definition of correctness. These are published under
CC-BY-4.0 alongside SPEC-001 and are what a second implementer conforms to.

Directories to author:
  jcs-canonical · csd1-empty · csd1-single-add · csd1-modify-delete · csd1-rename ·
  csd1-mode-change · csd1-unicode-paths · csd1-submodule · csd1-symlink ·
  csd1-path-ordering · statement-valid · statement-invalid-*

RULES (QA-001 §4)
  - Vectors are plain files, interpretable WITHOUT attest's own code
  - A vector's expected value is NEVER regenerated from the implementation when a
    test fails. If implementation and vector disagree, one is wrong and A HUMAN
    DECIDES WHICH — never the failing party
  - Adding or changing a vector that changes normative behaviour requires an ADR
  - Every vector runs against BOTH git backends (ADR-007)

Vector directories should be CODEOWNERS-protected (SEC-001 C-12).

Tests: AC-F01-160.
EOF

F02="$(issue_ensure "F-02 — Git ChangeSet collector" Sage urgent "$P_M1" "" "F-02" "pkg:attest-collect" "M1" "gate:CH-01" "gate:CH-08" <<'EOF'
Normative: docs/brd/BRD-F02.md. Scope: SCOPE-01. Depends on: F-01.
Gated by CH-01; its Definition of Done is gated by CH-08.

Produces the ChangeSetEntry list that F-01's digest.py consumes. That boundary is
the most important interface in the codebase — it was agreed in F-01 and is not
renegotiated here.

NON-NEGOTIABLE: rename AND copy detection are OFF (REQ-F02-010, ADR-001). Renames
appear as delete + add. Rename detection is a heuristic and therefore
non-deterministic across git versions; enabling it "because it is more accurate"
breaks digest reproducibility forever.

The git collector is the ONE collector whose failure is fatal — there is nothing
to attest without it (ARCH-001 §3.2).

Child issues carry the work. Closes when BRD-F02's DoD is fully ticked and
CH-08 is closed.
EOF
)"

issue_ensure "F-02a — GitBackend protocol and pygit2 implementation" Sage high "$P_M1" "$F02" "F-02" "pkg:attest-collect" "M1" <<'EOF'
Parent: F-02. Normative: BRD-F02, ADR-007.

Define a narrow GitBackend protocol, then the pygit2 implementation.

VERIFY BEFORE WRITING (AGENTS.md §4, CH-02 assumption F): pygit2 must expose
tree-diff with rename detection genuinely off. Confirm by executing code, not by
reading documentation. pygit2 makes this awkward to guarantee via porcelain flags,
which is exactly why the project uses it rather than parsing git diff-tree output.

Git fixtures are built programmatically in tmp_path. No committed binary
repositories (QA-001 §10).

Exotic input is tested deliberately: non-ASCII paths, byte 0xFF, symlinks,
submodules, mode changes, empty ChangeSets (SPEC-001 §5.4).
EOF

issue_ensure "F-02b — subprocess git backend, both backends pass the vector suite" Sage high "$P_M1" "$F02" "F-02" "pkg:attest-collect" "M1" <<'EOF'
Parent: F-02. Normative: ADR-007.

The subprocess fallback exists because pygit2 needs compiled libgit2, which is the
primary install-failure mode. Retrofitting the abstraction later is expensive;
building it now costs little.

BOTH backends MUST pass the same spec/testvectors/ conformance suite. The shared
vector suite is what guarantees the two cannot diverge silently.

Wire the vectors CI job to run the full suite on both backends.
EOF

issue_ensure "CH-08 — Does CSD-1 hold at monorepo scale?" Sage medium "$P_M1" "$F02" "CH-08" "M1" "blocks:F-02-DoD" "validation" <<'EOF'
Normative: CHALLENGE-001 §10. One day, week 2. Gates the F-02 Definition of Done.

ARCH-001 §11 targets CSD-1 under 500 ms for 1,000 changed files. That number is an
assertion, not a measurement.

EXPERIMENT
Run against a monorepo PR touching 1,000+ files. Measure BOTH backends. Measure a
10,000-file case.

EXIT
[ ] 1,000-file case under 500 ms
[ ] 10,000-file case completes without exhausting memory

IF NOT MET: optimise before F-02 DoD, or amend the target in ARCH-001 VIA ADR.
Do not silently ship a slower tool than the document claims.

DONE = the outcome row for CH-08 in CHALLENGE-001 §12 is filled in.
EOF

F03="$(issue_ensure "F-03 — Authorship claim collector" Sage high "$P_M1" "" "F-03" "pkg:attest-collect" "M1" <<'EOF'
Normative: docs/brd/BRD-F03.md. Scope: SCOPE-02. Depends on: F-01.

Three claim sources: commit trailers, sidecar files (.attest/claims.d/*.json),
and git notes (Git AI interoperability). ADR-006.

EVERYTHING COLLECTED HERE IS UNTRUSTED. Anyone can write
.attest/claims.d/fake.json claiming any agent authored anything. That is ACCEPTED,
not mitigated (SEC-001 T-01, ADR-003). Claims are recorded faithfully and never
used to make a security decision.

Any design discussion drifting toward "how do we make sure the AI claim is true"
has left the architecture. The answer is: we do not, and the format says so.

NEVER CARRY PROMPT TEXT. Only promptDigest. A prompt field in a sidecar is IGNORED
WITH A WARNING (REQ-F03-040). A negative test asserts no input can cause prompt
text to reach the output (AC-F03-040). Prompts routinely contain API keys,
customer data, and personal data — and the transparency log is public by default,
so anything reaching a predicate is effectively published (SEC-001 C-06).

A failing claim collector records a degradation reason and continues. It does not
abort the run. A missing signal produces unknown, never a confident default.
EOF
)"

issue_ensure "F-03a — Sidecar, trailer, and git-note claim sources" Sage high "$P_M1" "$F03" "F-03" "pkg:attest-collect" "M1" <<'EOF'
Parent: F-03. Normative: BRD-F03, ARCH-001 §7.

Sidecar format is fixed in ARCH-001 §7 — schemaVersion, claimId, agent, model,
sessionId, promptDigest, scope, claimedAt.

The file-drop protocol is the moat: it works with any tool that can write a file —
no API, no auth, no network, no vendor partnership, including with tools that do
not exist yet (ADR-006). Do not "improve" it into something requiring cooperation.

Merge logic across sources lives in authorship.py.
EOF

F05="$(issue_ensure "F-05 — Attestation builder" Atlas high "$P_M1" "" "F-05" "pkg:attest-core" "M1" <<'EOF'
Normative: docs/brd/BRD-F05.md. Scope: SCOPE-04. Depends on: F-01, F-02, F-03.

Builds the in-toto Statement. subject[0].name == "changeset", digest == the
ChangeSet Digest — NOT the commit SHA (ADR-002). Squash-merge rewrites commit
SHAs; if the SHA were the subject, every attestation created at PR time would
become unverifiable the moment the PR merged, which is precisely when the evidence
becomes valuable.

The predicate type URI is ONE CONSTANT — attest_core.constants.PREDICATE_TYPE_V0_1.
Never a literal at a call site (REQ-F05-040, ADR-013).

Schema validation happens BEFORE signing — fail fast (ARCH-001 §4 step 7).

Golden-file test for the built Statement.
EOF
)"

F06="$(issue_ensure "F-06 — Sigstore signing" Cipher urgent "$P_M1" "" "F-06" "pkg:attest-sign" "M1" "gate:CH-02" <<'EOF'
Normative: docs/brd/BRD-F06.md. Scope: SCOPE-05. Depends on: F-01, F-05.
Gated by CH-02.

DSSE envelope + Fulcio keyless certificate + Rekor entry -> Sigstore bundle.

NON-NEGOTIABLES
  - The inclusion proof and signed entry timestamp MUST be embedded in the bundle
    AT SIGNING TIME (ADR-015). Signing FAILS if the log entry cannot be obtained
    (REQ-F06-060). A bundle without a proof is not the product.
  - A retry that swallows a Rekor failure is FORBIDDEN — it produces attestations
    with no transparency log entry.
  - The signer RE-VERIFIES ITS OWN OUTPUT before reporting success (ADR-005,
    ARCH-001 §4 step 10). ~1-2s per run, accepted deliberately. The failure mode
    this eliminates is discovering at audit time that a year of attestations are
    invalid.
  - ALL TEST SIGNING TARGETS SIGSTORE STAGING. Writing test attestations to the
    production transparency log pollutes a public append-only log that cannot be
    cleaned. Add the guard test that fails the suite if a production endpoint is
    configured in test settings (QA-001 §10).

Verify every sigstore-python and securesystemslib call against the INSTALLED
version before writing it (AGENTS.md §4). CH-02 assumptions A, B, D, E are the
inputs here.

Also delivers .github/workflows/e2e-sign.yml; the file is absent until this feature implements it.
EOF
)"

F08="$(issue_ensure "F-08 — Verification" Cipher urgent "$P_M1" "" "F-08" "pkg:attest-sign" "M1" "gate:CH-02" <<'EOF'
Normative: docs/brd/BRD-F08.md. Scope: SCOPE-07. Depends on: F-01, F-06.
Gated by CH-02 — assumption C specifically.

THE MOST IMPORTANT CONTROL IN THE SYSTEM (SEC-001 T-03, control C-03):
Identity verification is MANDATORY AND CANNOT BE BYPASSED (ADR-004, REQ-F08-040).

Anyone can obtain a Fulcio certificate. A valid signature proves only that
SOMEONE signed, which is worth nothing. This check is the difference between a
security product and security theatre.

  - The identity constraint is a REQUIRED ARGUMENT, not an option with a default.
    The API is shaped so it cannot be forgotten.
  - Unbounded patterns are REJECTED (REQ-F08-050).
  - Unconstrained verification reports unverified-identity — never success.
  - No flag, environment variable, config key, or code path may allow
    verification to report success without it. AC-F08-040 is a static-analysis
    test that hunts for bypasses.

STRUCTURE
The pipeline is an EXPLICIT ORDERED LIST, each step returning a typed result, so
the order is auditable in review and testable step by step (ARCH-001 §3.3, §5):
  parse bundle · load trust root · cert chain + validity window ·
  IDENTITY + ISSUER MATCH · transparency log inclusion · DSSE signature over PAE ·
  statement parse + known predicate · schema validation ·
  subject<->predicate digest match · (optional) recompute CSD-1

attest_sign.verifier MUST NOT import attest_sign.sigstore_signer — enforced by the
verifier-isolation import-linter contract (ARCH-001 §1 P3). A verifier that reuses
the signer's assumptions cannot detect the signer's bugs.

Inclusion proof verified OFFLINE from bundle contents alone (ADR-015). Querying
the log at verification time is NOT an accepted substitute, and no configuration
may make verification depend on log availability.

Unknown predicate types are rejected outright (REQ-F08-090, T-11).

Coverage floor on the verifier module: 95%.
EOF
)"

issue_ensure "F-08a — Adversarial verification suite" Cipher urgent "$P_M1" "$F08" "F-08" "pkg:attest-sign" "M1" "security" <<'EOF'
Parent: F-08. Normative: BRD-F08 §7, QA-001 §9, SEC-001 §6.

Runs on EVERY commit. Forgery, tampering, replay.

THE MOST VALUABLE TEST IN THE CODEBASE (QA-001 §9):
Generate arbitrary valid bundles, mutate ONE BYTE anywhere, assert verification
NEVER succeeds.

Also required (SEC-001 §6):
[ ] Replay test — an attestation for ChangeSet A must not verify against
    ChangeSet B (T-02, AC-F08-110)
[ ] Identity-mismatch test — signed as X, constrained to Y, MUST fail (T-03)
[ ] Secret-leak test — no token appears in any output stream across the full suite
[ ] Downgrade test — unknown predicate types rejected (T-11)
[ ] No-egress test — attest-core and attest-policy make no network calls

mutmut on the verifier module runs weekly. An UNTRIAGED SURVIVING MUTANT IN THE
VERIFIER BLOCKS A RELEASE (QA-001 §11).
EOF

F10="$(issue_ensure "F-10 — CLI" Pixel high "$P_M1" "" "F-10" "pkg:attest-cli" "M1" <<'EOF'
Normative: docs/brd/BRD-F10.md. Scope: SCOPE-09. Depends on: F-01..F-08.

The composition root and the entire user-facing surface. Its contract with CI is
the EXIT CODE TABLE, which is effectively frozen from first release.

Command surface (BRD-F10 §3) — do not invent commands outside it:
  init · collect · build · sign · push · verify · gate · run · inspect · export ·
  config show · doctor · version

NON-NEGOTIABLES
  - Exit codes match GLOSS-001 §7 EXACTLY. Snapshot-tested; changing one fails
    the test (REQ-F10-010, AC-F10-010)
  - --json on every command; human output goes to STDERR when --json is active so
    stdout stays pure JSON (REQ-F10-020, -030)
  - attest verify REQUIRES an identity constraint; exits 2 if none is resolvable
    (REQ-F10-100)
  - Secrets are NEVER CLI flags — environment or file only (REQ-F10-060)
  - NO BUSINESS LOGIC in attest-cli. Handlers orchestrate and map results to exit
    codes (REQ-F10-040, AC-F10-040)
  - attest --help under 300 ms — heavy imports deferred into subcommands
  - NO TELEMETRY in v1.0 (REQ-F10-130)
  - Never print(). Output layer or structured logger only

attest init scaffolds .attest/config.yaml, a starter policy, and a workflow file
WITH THE CORRECT IDENTITY CONSTRAINT ALREADY FILLED IN. That is the mitigation for
ADR-004's ergonomic cost. Its DoD requires the generated workflow to run
successfully UNMODIFIED on a fresh repository.

Every command needs a CliRunner test for success and each failure path.
EOF
)"

issue_ensure "SPEC-001 — Publish the specification and open the RFC" Quill urgent "$P_M1" "" "M1" "spec" <<'EOF'
Normative: ROADMAP-001 §2 week 4, ADR-017, CH-07.

PUBLISH AT M1, NOT LATER. Standard ownership is the moat and it decays with time
(ROADMAP-001 §5). A specification with one implementation is not a standard.

WORK
[ ] Publish SPEC-001 publicly, with spec/testvectors/, under CC-BY-4.0 (ADR-017).
    CC-BY-4.0 signals that reimplementation is INVITED — that is the entire
    adoption strategy.
[ ] Open an RFC issue inviting review
[ ] Engage the in-toto, OpenSSF, and SLSA communities
[ ] Keep spec/SPEC-001.md byte-synchronised with docs/02-*. Divergence is a defect.
[ ] State prominently that v0.x predicate type URIs are UNSTABLE and may change
    (ADR-013)

MEASURED (CH-07): by day 120 either one external implementation exists, or one
standards-body conversation is underway. Missing both is kill criterion K5.
EOF

issue_ensure "README limitations and SECURITY.md" Cipher high "$P_M1" "" "M1" "docs" <<'EOF'
Normative: SEC-001 §5, §7.

EVERY residual risk must appear in the README limitations section — not buried.
Discovering your own limitations and publishing them is worth more than the risk
they represent.

README must state:
[ ] Unclaimed AI use is invisible to attest (R1)
[ ] A gate that is not a REQUIRED status check is decorative (R2)
[ ] The transparency log is PUBLIC by default; anything in an attestation is
    effectively published. A private Rekor instance is the documented mitigation (R3)
[ ] A review record proves approval, not comprehension (R4)
[ ] A compromised CI system can produce genuine attestations for malicious code (R5)
[ ] v0.x predicate type URIs are unstable (ADR-013)

SECURITY.md must specify (SEC-001 §7):
[ ] A contact address
[ ] A 90-day coordinated disclosure window
[ ] An explicit commitment that VERIFICATION-BYPASS REPORTS ARE CRITICAL SEVERITY
    REGARDLESS OF EXPLOITATION DIFFICULTY

For this product a verification bypass is the worst possible class of bug — it
silently converts every attestation into a false assurance.

Banned language (GLOSS-001 §2.2) applies to all of it. `just banned` must be green.
EOF

issue_ensure "Release v0.1.0 — attested by attest" Arbiter high "$P_M1" "" "M1" "release" <<'EOF'
Normative: QA-001 §12, TECH-001 §7 (dogfooding is NORMATIVE).

Ship to PyPI and GHCR, attested by itself.

THE RELEASE GATE — all eleven, no exceptions:
[ ]  1. All CI jobs green on the release commit
[ ]  2. All test vectors pass on BOTH git backends
[ ]  3. Adversarial suite green
[ ]  4. Schema drift check green
[ ]  5. Banned-language check green
[ ]  6. Traceability check green
[ ]  7. No untriaged surviving mutant in the verifier
[ ]  8. pip-audit reports no unmitigated high-severity advisory
[ ]  9. THE RELEASE IS ATTESTED BY ATTEST, AND THAT ATTESTATION VERIFIES PUBLICLY
[ ] 10. CHANGELOG updated
[ ] 11. Backwards compatibility: attestations from every prior version still verify

Gates 9 and 11 are the ones that distinguish this project. If attest cannot attest
its own release, the release does not ship — the tool is not ready for anyone else.
If any prior version's attestations stop verifying, the release does not ship —
audit evidence that stops verifying is worthless.

A release is PERMANENT. Signed artifacts go into a public append-only transparency
log. There is no unpublish.
EOF

issue_ensure "M1 exit gate — verify against reality" Lambda urgent "$P_M1" "" "M1" "gate" <<'EOF'
Normative: ROADMAP-001 §2 "M1 exit gate", BRD-INDEX §8 anti-gap checklist.

Verify against REALITY, not against checkbox status. These criteria are
deliberately external — something works in a real repository, or a real person
confirms something — because internal "feature complete" judgements are unreliable.

M1 EXIT
[ ] CH-01 and CH-02 recorded CLOSED in CHALLENGE-001 §12
[ ] A REAL GitHub Actions run produced a signed attestation logged to the
    transparency log
[ ] attest verify validated it ON A CLEAN CONTAINER WITH NO LOCAL STATE
[ ] Adversarial suite green
[ ] SPEC-001 and the test vectors are PUBLIC
[ ] The project attests its own release

ANTI-GAP CHECKLIST (BRD-INDEX §8) — run all of it:
[ ] Every SCOPE-xx traced to a feature, and vice versa
[ ] Every normative SPEC-001 section traced to a feature
[ ] Every REQ- has a matching AC- with the same number
[ ] Every AC- has at least one test referencing its ID
[ ] Every error code raised in code appears in a BRD error table
[ ] Every challenge blocking a built feature is closed
[ ] All OQ-xx remain closed; no new one added without an ADR
[ ] Every cross-cutting X-01..X-10 satisfied for each completed feature
[ ] Committed JSON Schema matches regenerated schema
[ ] All spec/testvectors/ pass on both git backends
EOF

# ======================================================================= M2 ==

echo "==> M2 issues"

issue_ensure "F-04 — Review record collector (GitHub)" Sage high "$P_M2" "" "F-04" "pkg:attest-collect" "M2" <<'EOF'
Normative: docs/brd/BRD-F04.md. Scope: SCOPE-03. Depends on: F-01.

PR reviews and check runs from the GitHub REST/GraphQL API.

Forge review records are SEMI-TRUSTED — trusted to the extent the GitHub API is
trusted (ARCH-001 §6). Record the API response digest so the basis is traceable.

REVIEWER IDENTITY IS NUMERIC, NEVER A LOGIN (REQ-F04-010, SEC-001 T-08). Logins
are renameable; immutable numeric IDs are not.

A failing forge collector records a degradation reason and CONTINUES. Only the git
collector's failure is fatal.

TESTS
[ ] Recorded HTTP fixtures by default; live calls only in a nightly job (QA-001 §10)
[ ] Token-leak test: no credential appears in any output stream across the suite

GitLab and Bitbucket are OOS-02, deferred to v1.1. Do not build them.
EOF

F07="$(issue_ensure "F-07 — Storage and retrieval" Sage high "$P_M2" "" "F-07" "pkg:attest-store" "M2" <<'EOF'
Normative: docs/brd/BRD-F07.md. Scope: SCOPE-06. Depends on: F-01, F-06.

Three backends behind one AttestationStore protocol: GitRefStore, FilesystemStore,
OciStore. They share ONE conformance suite.

STORAGE IS A REF NAMESPACE, NOT GIT NOTES (ADR-014):
refs/attestations/<changeset-digest>, one ref per attestation. Multiple
attestations per digest are legitimate and supported by suffixing /<log-index>.

Git notes concentrate every entry under one ref, which CONFLICTS when parallel CI
jobs write concurrently — a routine condition in a busy repository and the exact
failure REQ-F07-100 forbids. Independent refs are conflict-free by construction.

attest still READS git notes as a claim source (F-03). That is unaffected.

Refs must be pushed explicitly (REQ-F07-040) and require contents: write.
Fetching attestations requires an explicit refspec — document it in the quickstart.

Retrieval is keyed on the DIGEST, so the storage layer maps digest -> attestations.
EOF
)"

F09="$(issue_ensure "F-09 — Policy engine and CI gate" Pixel high "$P_M2" "" "F-09" "pkg:attest-policy" "M2" <<'EOF'
Normative: docs/brd/BRD-F09.md. Scope: SCOPE-08. Depends on: F-01, F-04, F-08.

Pure evaluation. Input: Predicate + VerificationResult + Policy. Output: Decision.
NO I/O WHATSOEVER, so policies are exhaustively testable with fixtures. Coverage
floor 95%.

THE VOCABULARY IS CLOSED (ADR-008). A fixed declarative YAML vocabulary, no
embedded scripting — not Rego, not CEL, not Lua, not Python. The gate runs in a
job holding id-token: write; arbitrary code execution there is a supply-chain
vulnerability, not a feature. Some exotic policies will be inexpressible — that is
the intended trade. Requests for scripting are answered by extending the
vocabulary WITH A NEW ADR, never by adding an escape hatch.

YAML IS LOADED SAFELY. Tags and anchors intended to trigger construction are
REJECTED (AC-F09-090, SEC-001 C-05).

POLICY IS NOT VERIFICATION (BRD-F09 §8). They answer different questions and must
fail differently:
  Is this attestation genuine?  -> verifier -> exit 4
  Is there an attestation at all? -> storage -> exit 5
  Is this change allowed?       -> policy   -> exit 3
Merging them is a rejected design. Collapsing the exit codes is worse.

ABSENCE IS A VIOLATION. The easiest attack on attest is producing no attestation
at all (SEC-001 T-04). Missing attestation is a blocking condition, exit 5
(REQ-F09-030).

Reviewer identity is numeric (REQ-F09-110).
Property test: evaluation is deterministic. Decision-table tests across every
predicate in the vocabulary.

VOCABULARY NOTE: policy output is a Decision (allow/warn/deny). "Verdict" is
RESERVED for a reviewer's conclusion inside a Review Record (GLOSS-001 §2.1).
EOF
)"

F11="$(issue_ensure "F-11 — GitHub Action packaging" Forge high "$P_M2" "" "F-11" "pkg:action" "M2" "gate:CH-09" <<'EOF'
Normative: docs/brd/BRD-F11.md. Scope: SCOPE-10. Depends on: F-06, F-07, F-09, F-10.
DoD gated by CH-09.

The container Action, job summary, and quickstart. Most users never see Python.

NON-NEGOTIABLES
  - THE ACTION PINS ITS IMAGE BY DIGEST, NOT BY TAG (REQ-F11-010, SEC-001 C-09).
    A tag is mutable; a digest is not. This is a supply-chain control.
  - Workflow permissions are minimal and explicit: id-token: write,
    contents: read (write only where refs are pushed), pull-requests: read,
    checks: read.
  - pull_request_target IS REJECTED (REQ-F11-070, SEC-001 T-10). Only validated
    branch pull_request and branch push events are supported. No mode executes
    repository content; an unprivileged fork fails before repository reads.
  - The gate MUST be re-run on the final merge candidate, and the required status
    check configured to require branches to be up to date (SEC-001 T-13). Document
    it in the quickstart.
  - checkout uses fetch-depth: 0 wherever a ChangeSet is computed — a shallow
    clone silently changes what the digest covers.

Also delivers action-candidate.yml and release.yml under ADR-046's two-phase contract:
candidate on protected dev, reviewed manifest-digest pin, then exact-manifest promotion and
Trusted Publishing from a manual dispatch on protected main. Under ADR-048, publish and publicly
verify the first three packages before exposing the protected registration checkpoint for the
remaining three; promote the release image only after both OIDC waves succeed. Publish the six
implemented 0.1.0 distributions only; Action version is independently v1.0.0/v1.

DoD: the quickstart works UNMODIFIED on a genuinely fresh repository.
EOF
)"

issue_ensure "CH-09 — Is container cold start acceptable?" Forge medium "$P_M2" "$F11" "CH-09" "M2" "blocks:F-11-DoD" "validation" <<'EOF'
Normative: CHALLENGE-001 §11. One day, week 8. Gates the F-11 Definition of Done.

REQ-F11-100 requires the full Action under 15 s p95. This is the one place the
Python decision (ADR-012) carries measurable risk.

EXPERIMENT: 20 independent ubuntu-latest jobs with the frozen staging fixture.
Measure the Action step including image pull and excluding checkout. Retain every
run ID/duration, runner image, Action SHA, image digest, p50, and nearest-rank p95
(sorted observation 19).

EXIT
[ ] p95 under 15 s

IF NOT MET: slim the image, defer heavy imports, cache layers. If it remains
unacceptable AND design partners rank it their top complaint, ADR-011's single
trigger fires — VERIFIER ONLY, recorded then as a new ADR. No other route reopens
the language question, and nobody may begin such a port speculatively.

DONE = the outcome row for CH-09 in CHALLENGE-001 §12 is filled in.
EOF

issue_ensure "CH-05 — Will design partners enable a BLOCKING gate?" Lambda high "$P_M2" "" "CH-05" "M2" "blocks:M2-exit" "validation" <<'EOF'
Normative: CHALLENGE-001 §7. Measured, not spiked. Assumption A2.

A gate nobody sets to blocking is a report, and reports do not get budget.

MEASUREMENT: of three design partners, how many configure `attest / gate` as a
REQUIRED status check within two weeks of onboarding, UNPROMPTED.

GATE: at least two of three.

IF NOT MET: find out whether the obstacle is trust in the tool, false positives,
or political. False positives are fixable; political resistance means the buyer is
wrong and assumption A5 needs revisiting.

Also in scope for this issue: onboard three external design partners
(ROADMAP-001 §3 week 8) and DOCUMENT ONBOARDING FRICTION FROM REAL PARTNER
FEEDBACK. That friction data is the input to ADR-011.
EOF

issue_ensure "M2 exit gate — verify against reality" Lambda urgent "$P_M2" "" "M2" "gate" <<'EOF'
Normative: ROADMAP-001 §3 "M2 exit gate", BRD-INDEX §8.

[ ] CH-03 closed: at least two harnesses emit claims reliably
[ ] CH-05 measured: at least two of three partners enabled a BLOCKING gate
[ ] CH-08 and CH-09 closed
[ ] A POLICY VIOLATION BLOCKED A MERGE via a required status check in a REAL
    repository
[ ] Three external repositories running the Action in CI
[ ] Quickstart works UNMODIFIED on a fresh repository
[ ] Onboarding friction documented from real partner feedback

Re-run the full BRD-INDEX §8 anti-gap checklist before declaring M2 complete.

NOTE: the M2 exit gate is also the ONLY point at which ADR-011's language-revisit
trigger can fire — and only if installation or runtime friction is the top-ranked
complaint from a MAJORITY of design partners, and only for the verifier.
EOF

# ======================================================================= M3 ==

echo "==> M3 issues"

F12="$(issue_ensure "F-12 — Evidence export and control mapping" Quill high "$P_M3" "" "F-12" "pkg:attest-export" "M3" "gate:CH-04" <<'EOF'
Normative: docs/brd/BRD-F12.md. Scope: SCOPE-11. Depends on: F-07, F-08.
DoD gated by CH-04.

The evidence bundle a compliance lead hands to an auditor: manifest.json,
summary.md, per-control narratives, verify.sh, an exceptions section.

BUILDING IS UNBLOCKED; PUBLISHING IS GATED (ADR-016).
Mapping files carry mandatory metadata:
    status: draft-unreviewed
    reviewedBy: null
    reviewedAt: null

Any export generated from a draft-unreviewed mapping MUST carry a prominent banner
in BOTH summary.md and manifest.json stating the mapping has not been reviewed by
a qualified practitioner. THE BANNER MUST NOT BE SUPPRESSIBLE BY A FLAG.

A mapping MUST NOT be marked status: reviewed without a named reviewer and a date.
F-12 cannot pass its DoD, and no export may be presented to a customer as audit
evidence, until at least one framework mapping is reviewed.

DO NOT GUESS CONTROL MAPPINGS. They come from CH-04. Guessed mappings are worse
than none.

OTHER NON-NEGOTIABLES
  - Exports contain NO SOURCE CODE (REQ-F12-090, SEC-001 T-07). Paths, digests,
    counts, identities, timestamps. Never content.
  - verify.sh MUST reproduce verification in a clean container, OFFLINE, from the
    bundle alone. That is the whole point: an auditor verifies without trusting
    the vendor.
  - Exports are DETERMINISTIC — the same inputs produce the same bundle bytes.

LANGUAGE: "compliance-enabling", never "compliant". Compliance is determined by
the auditor and the organisation (GLOSS-001 §2.2).
EOF
)"

issue_ensure "CH-04 close-out — auditor validation of a real bundle" Quill high "$P_M3" "$F12" "CH-04" "M3" "blocks:F-12-DoD" "validation" <<'EOF'
Normative: CHALLENGE-001 §6, ROADMAP-001 §4 weeks 9 and 11.

Closes the CH-04 loop opened in Week 0, now against a REAL exported bundle.

WORK
[ ] Generate a real bundle from a design partner's repository (with permission)
[ ] Auditor review; incorporate feedback
[ ] Harden the limitations language
[ ] Obtain control identifiers for at least one framework, with a NAMED REVIEWER
    and a DATE, then mark that mapping status: reviewed (ADR-016)

EXIT
[ ] A practising auditor confirms IN WRITING that the bundle is usable as
    change-management evidence
[ ] verify.sh reproduces verification in a clean container

If both auditors reject: kill criterion K2 territory. Re-evaluate against
RISK-001 §5 before investing further in F-12.
EOF

issue_ensure "CH-06 — Will anyone pay, and who signs?" Lambda high "$P_M3" "" "CH-06" "M3" "blocks:M3-exit" "validation" <<'EOF'
Normative: CHALLENGE-001 §8. Measured. Assumptions A1 and A5, and RISK-01 — the
highest-impact business risk. No hard willingness-to-pay benchmark exists for this
category.

MEASUREMENT: by day 90, one paid pilot agreed. RECORD THE SIGNER'S ROLE.

GATE: one pilot, AND the signer is compliance/security rather than engineering —
which is what confirms assumption A5.

IF NOT MET: kill criterion K1 applies at 6 months and 20+ qualified conversations.
If the signer is ENGINEERING rather than compliance, the POSITIONING is wrong and
GTM changes; the product does not.

This issue requires human decisions. Escalate rather than deciding.
EOF

issue_ensure "CH-07 — Will anyone else implement the spec?" Quill medium "$P_M3" "" "CH-07" "M3" "validation" <<'EOF'
Normative: CHALLENGE-001 §9. Ongoing from M1 publication.

The moat is specification ownership, and a specification with one implementation
is not a standard.

MEASUREMENT: by day 120, either one external implementation exists, or one
standards-body conversation is underway (in-toto, OpenSSF, SLSA community).

GATE: one of the two.

IF NOT MET: kill criterion K5. The standards thesis is not working; compete on
product depth — verification strength, policy, evidence export — and stop
investing in specification evangelism.
EOF

issue_ensure "M3 exit gate — verify against reality" Lambda urgent "$P_M3" "" "M3" "gate" <<'EOF'
Normative: ROADMAP-001 §4 "M3 exit gate", BRD-INDEX §8.

[ ] CH-04 closed: an auditor accepted the evidence shape
[ ] CH-06 measured: one paid pilot, signer's role recorded
[ ] A practising auditor confirms IN WRITING the bundle is usable as
    change-management evidence
[ ] verify.sh reproduces verification in a clean container
[ ] One paid pilot agreed
[ ] Adoption and conversion data collected against the RISK-001 thresholds

Re-run the full BRD-INDEX §8 anti-gap checklist.

WEEKLY REVIEW QUESTIONS (ROADMAP-001 §7) — answer honestly every Friday:
  1. What did a real external user do with attest this week?
  2. Which OQ- did I close, and which did I avoid?
  3. Did I add anything untraceable to a SCOPE- item?
  4. Did any kill criterion in RISK-001 move closer?
  5. Did I change a normative document without an ADR?
EOF

# ------------------------------------------------------------------- report --

echo
echo "==> done"
if (( DRY_RUN )); then
  echo "    (dry run — nothing was created)"
else
  echo "    issues:   $(multica issue list --limit 500 --output json | jq "$JQ_ARR"'arr("issues") | length')"
  echo "    projects: $(multica project list --output json | jq "$JQ_ARR"'arr("projects") | length')"
  echo "    agents:   $(multica agent list --output json | jq "$JQ_ARR"'arr("agents") | length')"
  echo
  echo "    Board:    http://localhost:3000"
  echo "    Next:     start with 'CH-01' and 'CH-02'. Nothing else may begin until"
  echo "              both are recorded CLOSED in CHALLENGE-001 §12."
fi
