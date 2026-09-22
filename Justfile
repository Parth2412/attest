default: check

# Full local gate — run before every commit
check: lint types imports test

lint:
    uv run ruff check .
    uv run ruff format --check .

fmt:
    uv run ruff check --fix .
    uv run ruff format .

types:
    uv run python scripts/run_mypy.py

imports:
    uv run lint-imports

test:
    uv run pytest

test-cov:
    uv run pytest --cov --cov-report=term-missing

vectors:
    uv run python scripts/run_test_group.py vectors F-01 F-02

adversarial:
    uv run python scripts/run_test_group.py adversarial F-08

verifier-coverage:
    uv run pytest packages/attest-sign/tests/test_verifier.py packages/attest-sign/tests/test_inspection.py --cov=attest_sign.verifier --cov-report=term-missing --cov-fail-under=95

github-coverage:
    uv run pytest packages/attest-collect/tests/test_github_review.py packages/attest-collect/tests/test_github_http.py packages/attest-collect/tests/test_github_checks.py packages/attest-collect/tests/test_github_context.py --cov=attest_collect.github --cov=attest_collect._github_http --cov-report=term-missing --cov-fail-under=90

policy-coverage:
    uv run pytest packages/attest-policy/tests --cov=attest_policy --cov-report=term-missing --cov-fail-under=95

store-coverage:
    uv run pytest packages/attest-store/tests --cov=attest_store --cov-report=term-missing --cov-fail-under=90

cli-coverage:
    uv run pytest packages/attest-cli/tests -m "not performance" --cov=attest_cli --cov-report=term-missing --cov-fail-under=90

cli-performance:
    uv run pytest packages/attest-cli/tests/test_cli_surface.py::test_ten_clean_installed_help_processes_each_finish_under_300ms -m performance

package-contract:
    uv build --package attest-core --out-dir build/release-dist --clear --no-create-gitignore
    uv build --package attest-collect --out-dir build/release-dist --no-create-gitignore
    uv build --package attest-sign --out-dir build/release-dist --no-create-gitignore
    uv build --package attest-store --out-dir build/release-dist --no-create-gitignore
    uv build --package attest-policy --out-dir build/release-dist --no-create-gitignore
    uv build --package attest-cli --out-dir build/release-dist --no-create-gitignore
    uv run --no-project python scripts/validate_release_artifacts.py build/release-dist --hash-output build/SHA256SUMS

action-contract:
    uv run --no-project python scripts/prepare_action_context.py build/action-context --manifest-output build/action-context-manifest.json --digest-output build/action-context.sha256
    docker build --tag attest-action-runtime:test --file build/action-context/action/Dockerfile build/action-context
    ATTEST_ACTION_IMAGE=attest-action-runtime:test uv run pytest action/tests/test_container.py -m container

mutation-core:
    cd packages/attest-core && uv run mutmut run
    cd packages/attest-core && uv run mutmut results
    cd packages/attest-core && ! uv run mutmut results | grep -q ': survived$'

mutation-verifier:
    cd packages/attest-sign && uv run mutmut run
    cd packages/attest-sign && uv run mutmut results
    cd packages/attest-sign && ! uv run mutmut results | grep -q ': survived$'

schema:
    uv run python scripts/write_schema.py

schema-check:
    uv run python scripts/write_schema.py --check

banned:
    uv run python scripts/check_banned_language.py

trace:
    uv run python scripts/check_traceability.py

security:
    uv run bandit -r packages action --exclude "*/tests/*,*/mutants/*" -c pyproject.toml
    uv run pip-audit

adr TITLE:
    uv run python scripts/new_adr.py "{{TITLE}}"

# The full release gate from QA-001 §12
release-gate: check vectors adversarial verifier-coverage github-coverage policy-coverage store-coverage cli-coverage cli-performance package-contract action-contract schema-check banned trace security
