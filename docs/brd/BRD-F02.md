# BRD-F02 — Git ChangeSet Collector

| Field | Value |
|---|---|
| Document ID | `BRD-F02` |
| Feature | `F-02` |
| Milestone | M1 |
| Package | `attest-collect` |
| Depends on | `F-01` |
| Status | Ready when F-01 Done · `CH-01` closed · `CH-08` gates DoD |

---

## 1. Purpose

Extract `ChangeSetEntry` objects from a real git repository so that `F-01` can digest them. This
is the only component that touches git, and it is where every reproducibility hazard lives:
rename detection, diff algorithm defaults, path encoding, submodules, and merge-base selection.

## 2. Scope trace

`SCOPE-01`. Implements `SPEC-001 §5.2`, §5.3 steps 1–3, §5.4, §6.2.

## 3. Dependencies

`F-01` (types, digest algorithm). `CH-01` real-repository conformance is closed. `CH-08`
(monorepo scale) remains a Definition-of-Done gate.

## 4. Data contracts

### 4.1 Interface

```python
class GitBackend(Protocol):
    def resolve_commit(self, rev: str) -> str: ...          # -> full 40-hex OID
    def merge_base(self, a: str, b: str) -> str: ...
    def diff_entries(self, base: str, head: str) -> list[ChangeSetEntry]: ...
    def repository_url(self) -> str | None: ...

def collect_changeset(
    repo_path: Path, base_rev: str, head_rev: str, backend: GitBackend
) -> ChangeSetCollection: ...
```

```python
@dataclass(frozen=True)
class ChangeSetCollection:
    record: ChangeSetRecord      # feeds F-01 digest
    info: ChangeSetInfo          # feeds F-05 predicate
    warnings: list[CollectionWarning]
```

### 4.2 Backends

Two implementations, per `ADR-007`:

| Backend | Library | Role |
|---|---|---|
| `Pygit2Backend` | `pygit2` | Default |
| `SubprocessBackend` | `git` CLI | Fallback when libgit2 unavailable |

Both **MUST** pass the identical conformance suite.

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F02-010` | Rename detection **MUST** be disabled. `pygit2`: do not call `find_similar()`. Subprocess: use `--no-renames`. |
| `REQ-F02-020` | Copy detection **MUST** be disabled. |
| `REQ-F02-030` | Diff **MUST** be computed tree-to-tree, not against the working directory or index. |
| `REQ-F02-040` | Untracked and ignored files **MUST NOT** appear in the ChangeSet. |
| `REQ-F02-050` | Modes **MUST** be recorded as 6-digit octal strings (`100644`, `100755`, `120000`, `160000`). |
| `REQ-F02-060` | Submodule (gitlink) entries **MUST** be included, with the submodule commit OID in the blob field. |
| `REQ-F02-070` | Symlink entries **MUST** be included, with the OID of the blob holding the link target. |
| `REQ-F02-080` | Paths **MUST** be extracted as raw bytes and converted to the canonical percent-encoded representation from `SPEC-001 §4.1`, preserving byte-identical round-trip without Unicode decoding or normalisation. |
| `REQ-F02-090` | When both `base_rev` and `head_rev` are supplied without an explicit merge base, `baseCommit` **MUST** be used as given; attest **MUST NOT** silently compute a merge base. |
| `REQ-F02-100` | When invoked in a pull-request context, the caller supplies the forge-reported merge base; it **MUST** be recorded in `ChangeSetInfo.merge_base` and used as `baseCommit`. |
| `REQ-F02-110` | Repository URL **MUST** be normalised: scheme forced to `https`, credentials stripped, `.git` suffix removed, trailing slash removed, host lowercased. |
| `REQ-F02-120` | A shallow clone lacking the base commit **MUST** raise `ERR-COLLECT-101` with remediation naming `fetch-depth: 0`. |
| `REQ-F02-130` | A dirty working tree **MUST NOT** affect the result, and **MUST** emit a warning if the head commit differs from `HEAD`. |
| `REQ-F02-140` | `ChangeSetInfo.stats` **MUST** contain only integer file counts. Line counts **MUST NOT** be produced. |
| `REQ-F02-150` | `paths` **MUST** be truncated at 1000 entries with `paths_truncated=True` set. |
| `REQ-F02-160` | Backend selection **MUST** be automatic with an override flag, and the selected backend **MUST** be reported in diagnostics. |
| `REQ-F02-170` | Both backends **MUST** produce byte-identical `ChangeSetRecord` for every conformance fixture. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F02-010` | A fixture repo where `a.py` is renamed to `b.py` yields exactly one `deleted` and one `added` entry. |
| `AC-F02-020` | A fixture with an identical copied file yields two independent `added` entries. |
| `AC-F02-030` | Modifying the working tree after commit does not change the digest. |
| `AC-F02-040` | An untracked file and a gitignored file are absent from entries. |
| `AC-F02-050` | `chmod +x` with unchanged content yields `modified` with differing modes and identical blob OIDs. |
| `AC-F02-060` | A submodule pointer bump yields one `modified` entry with mode `160000`. |
| `AC-F02-070` | Adding a symlink yields one `added` entry with mode `120000`. |
| `AC-F02-080` | Paths containing valid multibyte UTF-8, `%`, and invalid UTF-8 bytes are emitted canonically, round-trip byte-identically, and produce stable digests across runs. |
| `AC-F02-090` | Omitting an explicit base while providing two revs never triggers implicit merge-base computation. |
| `AC-F02-100` | Given a forge merge base, `info.merge_base` equals it and `record.base_commit` equals it. |
| `AC-F02-110` | `git@github.com:Org/Repo.git` normalises to `https://github.com/Org/Repo`. |
| `AC-F02-120` | A depth-1 clone raises `ERR-COLLECT-101` whose remediation text contains `fetch-depth`. |
| `AC-F02-130` | Dirty tree produces a warning; digest is unaffected. |
| `AC-F02-140` | `ChangeSetInfo.stats` has no line-count key. |
| `AC-F02-150` | A 1500-file ChangeSet yields 1000 paths and `paths_truncated=True`. |
| `AC-F02-160` | Forcing the subprocess backend is reflected in diagnostic output. |
| `AC-F02-170` | The full fixture matrix is run twice, once per backend, and all digests match. |

## 7. Test fixtures required

Construct programmatically in `tmp_path`, never committed as binary repos:

`empty-repo`, `single-add`, `modify-delete`, `rename`, `copy`, `mode-change`, `symlink`,
`submodule`, `unicode-paths`, `invalid-utf8-path`, `binary-file`, `large-1500-files`,
`merge-commit`, `shallow-clone`.

## 8. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-COLLECT-101` | Commit not present (shallow clone) | Set `fetch-depth: 0` in checkout |
| `ERR-COLLECT-102` | Not a git repository | Run inside a repository or pass `--repo` |
| `ERR-COLLECT-103` | Revision cannot be resolved | Check the ref exists and is fetched |
| `ERR-COLLECT-104` | No usable git backend | Install libgit2 or ensure `git` is on PATH |

## 9. Out of scope

- Reading claims (F-03), reviews (F-04)
- Computing the digest (F-01 owns the algorithm)
- Line-level statistics — permanently out of scope per `SPEC-001 §6.2`

## 10. Definition of Done

- [ ] All `REQ-F02-*` implemented, all `AC-F02-*` green
- [ ] Both backends pass the full fixture matrix identically
- [ ] All `spec/testvectors/csd1-*` pass end-to-end from a real repository
- [ ] Coverage ≥ 90%
- [ ] Cross-cutting obligations satisfied
