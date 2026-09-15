"""Secret-safe, bounded GitHub REST transport governed by BRD-F04 and ADR-041."""

from __future__ import annotations

import math
import os
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final, cast
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

import httpx

from attest_collect.errors import collect_error
from attest_core import JsonValue

type JsonObject = dict[str, JsonValue]

_API_ORIGIN: Final[str] = "https://api.github.com"
_API_VERSION: Final[str] = "2026-03-10"
_PER_PAGE: Final[str] = "100"
_TOKEN_SOURCES: Final[tuple[str, ...]] = (
    "ATTEST_GITHUB_TOKEN",
    "GITHUB_TOKEN",
    "ATTEST_GITHUB_TOKEN_FILE",
)


class GitHubToken:
    """Hold a validated token without exposing it (REQ-F04-090)."""

    __slots__ = ("__value",)

    def __init__(self, value: object) -> None:
        if (
            not isinstance(value, str)
            or not value
            or any(character.isspace() for character in value)
        ):
            raise collect_error("ERR-COLLECT-121")
        self.__value = value

    def _authorization_header(self) -> str:
        return f"Bearer {self.__value}"

    def __repr__(self) -> str:
        return "GitHubToken(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


def _read_token_file(path_value: str) -> str:
    if not path_value:
        raise collect_error("ERR-COLLECT-121")
    try:
        value = Path(path_value).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        value = None
    if value is None:
        raise collect_error("ERR-COLLECT-121")
    if value.endswith("\n"):
        value = value[:-1]
        if value.endswith("\r"):
            value = value[:-1]
    return value


def load_github_token(environ: Mapping[str, str] | None = None) -> GitHubToken:
    """Load exactly one environment or file token source (REQ-F04-090)."""
    source = os.environ if environ is None else environ
    configured = [name for name in _TOKEN_SOURCES if name in source]
    if len(configured) != 1:
        raise collect_error("ERR-COLLECT-121")
    name = configured[0]
    value = source[name]
    if name == "ATTEST_GITHUB_TOKEN_FILE":
        value = _read_token_file(value)
    return GitHubToken(value)


def _positive_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise collect_error("ERR-COLLECT-125")
    rendered = float(value)
    if not math.isfinite(rendered) or rendered <= 0:
        raise collect_error("ERR-COLLECT-125")
    return rendered


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise collect_error("ERR-COLLECT-125")
        return {key: _json_value(item) for key, item in value.items()}
    raise collect_error("ERR-COLLECT-125")


def _json_object(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise collect_error("ERR-COLLECT-125")
    return value


def _positive_integer(value: JsonValue) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise collect_error("ERR-COLLECT-125")
    return value


def _repository_path(repository: object) -> str:
    if not isinstance(repository, str) or repository != repository.strip():
        raise collect_error("ERR-COLLECT-124")
    parts = repository.split("/")
    if len(parts) != 2:
        raise collect_error("ERR-COLLECT-124")
    owner, name = parts
    allowed = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._")
    if (
        not owner
        or not name
        or owner in {".", ".."}
        or name in {".", ".."}
        or any(character not in allowed for character in owner)
        or any(character not in allowed for character in name)
    ):
        raise collect_error("ERR-COLLECT-124")
    return f"{quote(owner, safe='')}/{quote(name, safe='')}"


def _positive_context_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise collect_error("ERR-COLLECT-124")
    return value


def _head_sha(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise collect_error("ERR-COLLECT-124")
    return value


def _branch(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "*" in value
        or any(not character.isprintable() for character in value)
    ):
        raise collect_error("ERR-COLLECT-124")
    return quote(value, safe="")


def _query_items(value: str) -> dict[str, str]:
    pairs = parse_qsl(value, keep_blank_values=True)
    if len({key for key, _ in pairs}) != len(pairs):
        raise collect_error("ERR-COLLECT-122")
    return dict(pairs)


def _page_number(query: dict[str, str]) -> int:
    value = query.get("page")
    if value is None or not value.isascii() or not value.isdecimal():
        raise collect_error("ERR-COLLECT-122")
    page = int(value)
    if page < 1 or str(page) != value:
        raise collect_error("ERR-COLLECT-122")
    return page


def _record_identity(record: JsonObject, keys: Sequence[str]) -> tuple[str | int, ...]:
    identity: list[str | int] = []
    for key in keys:
        value = record.get(key)
        if isinstance(value, bool) or not isinstance(value, (str, int)) or value == "":
            raise collect_error("ERR-COLLECT-125")
        identity.append(value)
    return tuple(identity)


class GitHubHttpClient:
    """Perform bounded fixed-origin GitHub GETs (REQ-F04-070/080/120/140)."""

    def __init__(
        self,
        token: GitHubToken,
        *,
        transport: httpx.BaseTransport | None = None,
        request_timeout: float = 10.0,
        operation_deadline: float = 60.0,
        wall_clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._request_timeout = _positive_seconds(request_timeout)
        self._operation_deadline = _positive_seconds(operation_deadline)
        self._wall_clock = wall_clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._client = httpx.Client(
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": token._authorization_header(),
                "User-Agent": "attest-collect/0.1",
                "X-GitHub-Api-Version": _API_VERSION,
            },
            transport=transport,
            timeout=httpx.Timeout(self._request_timeout),
            follow_redirects=False,
            trust_env=False,
        )

    def __enter__(self) -> GitHubHttpClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the owned HTTP connection pool."""
        self._client.close()

    def _new_deadline(self) -> float:
        return self._monotonic() + self._operation_deadline

    def _rate_delay(self, response: httpx.Response, attempt: int) -> float | None:
        retry_after = response.headers.get("Retry-After")
        remaining = response.headers.get("X-RateLimit-Remaining")
        is_rate_limit = response.status_code == 429 or retry_after is not None or remaining == "0"
        if response.status_code != 403 and response.status_code != 429:
            return None
        if not is_rate_limit:
            return None

        exponential = 2.0 ** min(attempt, 6)
        if retry_after is not None:
            if not retry_after.isascii() or not retry_after.isdecimal():
                raise collect_error("ERR-COLLECT-123")
            return max(exponential, float(int(retry_after)))
        if remaining == "0":
            reset = response.headers.get("X-RateLimit-Reset")
            if reset is None or not reset.isascii() or not reset.isdecimal():
                raise collect_error("ERR-COLLECT-123")
            return max(exponential, float(int(reset)) - self._wall_clock(), 0.0)
        return max(exponential, 60.0)

    def _request_json(
        self,
        url: str,
        *,
        deadline_at: float,
        allow_not_found: bool = False,
    ) -> tuple[httpx.Response, JsonValue | None]:
        attempt = 0
        while True:
            remaining = deadline_at - self._monotonic()
            if remaining <= 0:
                raise collect_error("ERR-COLLECT-123")
            effective_timeout = min(self._request_timeout, remaining)
            response: httpx.Response | None = None
            try:
                response = self._client.get(
                    url,
                    timeout=httpx.Timeout(effective_timeout),
                )
            except httpx.RequestError:
                response = None
            if response is None:
                raise collect_error("ERR-COLLECT-125")

            delay = self._rate_delay(response, attempt)
            if delay is not None:
                remaining = deadline_at - self._monotonic()
                if delay >= remaining:
                    raise collect_error("ERR-COLLECT-123")
                self._sleep(delay)
                attempt += 1
                continue
            if response.status_code in {401, 403}:
                raise collect_error("ERR-COLLECT-121")
            if allow_not_found and response.status_code == 404:
                return response, None
            if response.status_code != 200:
                raise collect_error("ERR-COLLECT-125")
            sentinel = object()
            parsed: object = sentinel
            try:
                parsed = response.json()
            except (UnicodeError, ValueError):
                parsed = sentinel
            if parsed is sentinel:
                raise collect_error("ERR-COLLECT-125")
            return response, _json_value(parsed)

    def _validated_relation_url(
        self,
        value: object,
        *,
        initial_url: str,
        expected_page: int | None,
    ) -> tuple[str, int]:
        if not isinstance(value, str):
            raise collect_error("ERR-COLLECT-122")
        initial = urlsplit(initial_url)
        candidate = urlsplit(value)
        if (
            candidate.scheme != "https"
            or candidate.netloc != initial.netloc
            or candidate.path != initial.path
            or candidate.fragment
            or candidate.username is not None
            or candidate.password is not None
        ):
            raise collect_error("ERR-COLLECT-122")
        initial_query = _query_items(initial.query)
        candidate_query = _query_items(candidate.query)
        initial_fixed = {key: item for key, item in initial_query.items() if key != "page"}
        candidate_fixed = {key: item for key, item in candidate_query.items() if key != "page"}
        page = _page_number(candidate_query)
        if candidate_fixed != initial_fixed or (
            expected_page is not None and page != expected_page
        ):
            raise collect_error("ERR-COLLECT-122")
        return value, page

    def _relations(self, response: httpx.Response) -> dict[str, dict[str, str]]:
        relations: dict[str | None, dict[str, str]] | None = None
        try:
            relations = response.links
        except (KeyError, ValueError):
            relations = None
        if relations is None:
            raise collect_error("ERR-COLLECT-122")
        if "Link" in response.headers and not relations:
            raise collect_error("ERR-COLLECT-122")
        if any(key is None for key in relations):
            raise collect_error("ERR-COLLECT-122")
        return cast(dict[str, dict[str, str]], relations)

    def _paginate(
        self,
        url: str,
        *,
        container_key: str | None,
        identity_keys: Sequence[str],
        deadline_at: float,
    ) -> tuple[JsonObject, ...]:
        initial_url = url
        current_url = url
        current_page = 1
        expected_last: int | None = None
        expected_count: int | None = None
        seen_urls: set[str] = set()
        seen_records: set[tuple[str | int, ...]] = set()
        records: list[JsonObject] = []

        while True:
            if current_url in seen_urls:
                raise collect_error("ERR-COLLECT-122")
            seen_urls.add(current_url)
            response, parsed = self._request_json(current_url, deadline_at=deadline_at)
            if parsed is None:
                raise collect_error("ERR-COLLECT-125")

            page_values: list[JsonValue]
            if container_key is None:
                if not isinstance(parsed, list):
                    raise collect_error("ERR-COLLECT-125")
                page_values = parsed
            else:
                wrapper = _json_object(parsed)
                count = wrapper.get("total_count")
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise collect_error("ERR-COLLECT-125")
                if expected_count is None:
                    expected_count = count
                elif count != expected_count:
                    raise collect_error("ERR-COLLECT-122")
                raw_page_values = wrapper.get(container_key)
                if not isinstance(raw_page_values, list):
                    raise collect_error("ERR-COLLECT-125")
                page_values = raw_page_values

            for value in page_values:
                record = _json_object(value)
                identity = _record_identity(record, identity_keys)
                if identity in seen_records:
                    raise collect_error("ERR-COLLECT-122")
                seen_records.add(identity)
                records.append(record)

            relations = self._relations(response)
            last_relation = relations.get("last")
            if last_relation is not None:
                _, last_page = self._validated_relation_url(
                    last_relation.get("url"),
                    initial_url=initial_url,
                    expected_page=None,
                )
                if last_page < current_page or (
                    expected_last is not None and last_page != expected_last
                ):
                    raise collect_error("ERR-COLLECT-122")
                expected_last = last_page

            next_relation = relations.get("next")
            if next_relation is None:
                if expected_last is not None and current_page < expected_last:
                    raise collect_error("ERR-COLLECT-122")
                break
            if expected_last is not None and current_page >= expected_last:
                raise collect_error("ERR-COLLECT-122")
            current_url, current_page = self._validated_relation_url(
                next_relation.get("url"),
                initial_url=initial_url,
                expected_page=current_page + 1,
            )

        if expected_count is not None and len(records) != expected_count:
            raise collect_error("ERR-COLLECT-122")
        return tuple(records)

    def _paginate_objects(
        self,
        url: str,
        *,
        deadline_at: float,
    ) -> tuple[JsonObject, ...]:
        initial_url = url
        current_url = url
        current_page = 1
        expected_last: int | None = None
        seen_urls: set[str] = set()
        pages: list[JsonObject] = []

        while True:
            if current_url in seen_urls:
                raise collect_error("ERR-COLLECT-122")
            seen_urls.add(current_url)
            response, parsed = self._request_json(current_url, deadline_at=deadline_at)
            if parsed is None:
                raise collect_error("ERR-COLLECT-125")
            pages.append(_json_object(parsed))

            relations = self._relations(response)
            last_relation = relations.get("last")
            if last_relation is not None:
                _, last_page = self._validated_relation_url(
                    last_relation.get("url"),
                    initial_url=initial_url,
                    expected_page=None,
                )
                if last_page < current_page or (
                    expected_last is not None and last_page != expected_last
                ):
                    raise collect_error("ERR-COLLECT-122")
                expected_last = last_page

            next_relation = relations.get("next")
            if next_relation is None:
                if expected_last is not None and current_page < expected_last:
                    raise collect_error("ERR-COLLECT-122")
                break
            if expected_last is not None and current_page >= expected_last:
                raise collect_error("ERR-COLLECT-122")
            current_url, current_page = self._validated_relation_url(
                next_relation.get("url"),
                initial_url=initial_url,
                expected_page=current_page + 1,
            )

        return tuple(pages)

    def fetch_pull_request(self, repository: str, pr_number: int) -> JsonObject:
        """Fetch one exact pull-request response for context binding (REQ-F04-150)."""
        repo = _repository_path(repository)
        number = _positive_context_integer(pr_number)
        url = f"{_API_ORIGIN}/repos/{repo}/pulls/{number}"
        _, parsed = self._request_json(url, deadline_at=self._new_deadline())
        if parsed is None:
            raise collect_error("ERR-COLLECT-125")
        return _json_object(parsed)

    def fetch_comparison_pages(
        self,
        repository: str,
        base_revision: str,
        head_revision: str,
    ) -> tuple[JsonObject, ...]:
        """Fetch every ordered Compare response page for one exact pair (REQ-F04-150)."""
        repo = _repository_path(repository)
        base = _head_sha(base_revision)
        head = _head_sha(head_revision)
        query = urlencode((("per_page", _PER_PAGE), ("page", "1")))
        url = f"{_API_ORIGIN}/repos/{repo}/compare/{base}...{head}?{query}"
        return self._paginate_objects(url, deadline_at=self._new_deadline())

    def fetch_reviews(self, repository: str, pr_number: int) -> tuple[JsonObject, ...]:
        """Fetch every pull-request review response object (REQ-F04-070)."""
        repo = _repository_path(repository)
        number = _positive_context_integer(pr_number)
        query = urlencode((("per_page", _PER_PAGE), ("page", "1")))
        url = f"{_API_ORIGIN}/repos/{repo}/pulls/{number}/reviews?{query}"
        return self._paginate(
            url,
            container_key=None,
            identity_keys=("id",),
            deadline_at=self._new_deadline(),
        )

    def fetch_branch_rules(self, repository: str, base_branch: str) -> tuple[JsonObject, ...]:
        """Fetch every active ruleset rule for a branch (REQ-F04-100)."""
        repo = _repository_path(repository)
        branch = _branch(base_branch)
        query = urlencode((("per_page", _PER_PAGE), ("page", "1")))
        url = f"{_API_ORIGIN}/repos/{repo}/rules/branches/{branch}?{query}"
        return self._paginate(
            url,
            container_key=None,
            identity_keys=("ruleset_id", "type"),
            deadline_at=self._new_deadline(),
        )

    def fetch_classic_protection(
        self,
        repository: str,
        base_branch: str,
    ) -> JsonObject | None:
        """Fetch classic branch protection, treating a validated 404 as absent."""
        repo = _repository_path(repository)
        branch = _branch(base_branch)
        url = f"{_API_ORIGIN}/repos/{repo}/branches/{branch}/protection"
        _, parsed = self._request_json(
            url,
            deadline_at=self._new_deadline(),
            allow_not_found=True,
        )
        if parsed is None:
            return None
        return _json_object(parsed)

    def fetch_check_runs(self, repository: str, head_sha: str) -> tuple[JsonObject, ...]:
        """Enumerate all check suites and runs for a head commit (REQ-F04-140)."""
        repo = _repository_path(repository)
        head = _head_sha(head_sha)
        deadline = self._new_deadline()
        suite_query = urlencode((("per_page", _PER_PAGE), ("page", "1")))
        suite_url = f"{_API_ORIGIN}/repos/{repo}/commits/{head}/check-suites?{suite_query}"
        suites = self._paginate(
            suite_url,
            container_key="check_suites",
            identity_keys=("id",),
            deadline_at=deadline,
        )
        records: list[JsonObject] = []
        seen_run_ids: set[int] = set()
        for suite in suites:
            suite_id = _positive_integer(suite.get("id"))
            run_query = urlencode((("filter", "all"), ("per_page", _PER_PAGE), ("page", "1")))
            run_url = f"{_API_ORIGIN}/repos/{repo}/check-suites/{suite_id}/check-runs?{run_query}"
            runs = self._paginate(
                run_url,
                container_key="check_runs",
                identity_keys=("id",),
                deadline_at=deadline,
            )
            for run in runs:
                run_id = _positive_integer(run.get("id"))
                if run_id in seen_run_ids:
                    raise collect_error("ERR-COLLECT-122")
                seen_run_ids.add(run_id)
                records.append(run)
        return tuple(records)
