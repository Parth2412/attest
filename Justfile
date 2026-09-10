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

schema:
    @echo "not yet implemented — schema generation belongs to BRD-F01" >&2
    @exit 2

schema-check: schema
    git diff --exit-code spec/schemas/

banned:
    uv run python scripts/check_banned_language.py

trace:
    uv run python scripts/check_traceability.py

security:
    uv run bandit -r packages --exclude "*/tests/*" -c pyproject.toml
    uv run pip-audit

adr TITLE:
    uv run python scripts/new_adr.py "{{TITLE}}"

# The full release gate from QA-001 §12
release-gate: check vectors adversarial schema-check banned trace security
