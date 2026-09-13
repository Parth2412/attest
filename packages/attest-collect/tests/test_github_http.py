"""Bounded GitHub HTTP boundary tests for BRD-F04."""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from attest_collect._github_http import GitHubHttpClient, GitHubToken, load_github_token
from attest_collect.errors import CollectError

FIXTURES = Path(__file__).parent / "fixtures" / "github"
TOKEN = "github_pat_test_secret_123"
TIMEOUT_MESSAGE = "timed out"


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _page_url(page: int) -> str:
    return f"https://api.github.com/repos/acme/widgets/pulls/7/reviews?per_page=100&page={page}"


def _links(*, next_page: int | None, last_page: int) -> str:
    values: list[str] = []
    if next_page is not None:
        values.append(f'<{_page_url(next_page)}>; rel="next"')
    values.append(f'<{_page_url(last_page)}>; rel="last"')
    return ", ".join(values)


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    request_timeout: float = 5.0,
    operation_deadline: float = 30.0,
    wall_clock: Callable[[], float] = time.time,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> GitHubHttpClient:
    return GitHubHttpClient(
        GitHubToken(TOKEN),
        transport=httpx.MockTransport(handler),
        request_timeout=request_timeout,
        operation_deadline=operation_deadline,
        wall_clock=wall_clock,
        monotonic=monotonic,
        sleep=sleep,
    )


@pytest.mark.ac("AC-F04-070")
def test_three_review_pages_are_collected_exhaustively() -> None:
    pages = {
        1: _fixture("reviews-page-1.json"),
        2: _fixture("reviews-page-2.json"),
        3: _fixture("reviews-page-3.json"),
    }
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        seen.append(page)
        return httpx.Response(
            200,
            headers={"Link": _links(next_page=page + 1 if page < 3 else None, last_page=3)},
            json=pages[page],
        )

    with _client(handler) as client:
        responses = client.fetch_reviews("acme/widgets", 7)

    assert [response["id"] for response in responses] == [1001, 1002, 1003]
    assert seen == [1, 2, 3]


@pytest.mark.ac("AC-F04-070")
def test_missing_next_link_before_established_last_page_is_incomplete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if page == 1:
            return httpx.Response(
                200,
                headers={"Link": _links(next_page=2, last_page=3)},
                json=_fixture("reviews-page-1.json"),
            )
        return httpx.Response(
            200,
            headers={"Link": _links(next_page=None, last_page=3)},
            json=_fixture("reviews-page-2.json"),
        )

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == "ERR-COLLECT-122"


@pytest.mark.parametrize(
    "bad_link",
    [
        '<https://evil.example/reviews?per_page=100&page=2>; rel="next", '
        f'<{_page_url(2)}>; rel="last"',
        "<https://api.github.com/repos/acme/other/pulls/7/reviews?per_page=100&page=2>; "
        'rel="next", '
        f'<{_page_url(2)}>; rel="last"',
        f'<{_page_url(1)}>; rel="next", <{_page_url(2)}>; rel="last"',
    ],
)
def test_pagination_rejects_cross_origin_path_change_and_cycle(bad_link: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Link": bad_link},
            json=_fixture("reviews-page-1.json"),
        )

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == "ERR-COLLECT-122"


def test_duplicate_record_id_across_pages_is_incomplete() -> None:
    first = _fixture("reviews-page-1.json")

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            headers={"Link": _links(next_page=2 if page == 1 else None, last_page=2)},
            json=first,
        )

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == "ERR-COLLECT-122"


@dataclass(slots=True)
class FakeClock:
    wall: float = 1000.0
    monotonic_value: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def wall_time(self) -> float:
        return self.wall

    def monotonic(self) -> float:
        return self.monotonic_value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.wall += seconds
        self.monotonic_value += seconds


@pytest.mark.ac("AC-F04-080")
def test_primary_rate_limit_honours_reset_then_stops_at_deadline() -> None:
    clock = FakeClock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            403,
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1002"},
            json={"message": "private response text"},
        )

    with (
        _client(
            handler,
            operation_deadline=3.0,
            wall_clock=clock.wall_time,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        ) as client,
        pytest.raises(CollectError) as captured,
    ):
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == "ERR-COLLECT-123"
    assert clock.sleeps == [2.0]
    assert calls == 2


@pytest.mark.ac("AC-F04-080")
def test_secondary_rate_limit_without_delay_requires_sixty_seconds() -> None:
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "secondary limit"})

    with (
        _client(
            handler,
            operation_deadline=59.0,
            wall_clock=clock.wall_time,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        ) as client,
        pytest.raises(CollectError) as captured,
    ):
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == "ERR-COLLECT-123"
    assert clock.sleeps == []


@pytest.mark.ac("AC-F04-090")
def test_token_sources_are_exclusive_and_file_source_is_supported(tmp_path: Path) -> None:
    token_file = tmp_path / "github-token"
    token_file.write_text(f"{TOKEN}\n", encoding="utf-8")

    direct = load_github_token({"ATTEST_GITHUB_TOKEN": TOKEN})
    standard = load_github_token({"GITHUB_TOKEN": TOKEN})
    from_file = load_github_token({"ATTEST_GITHUB_TOKEN_FILE": str(token_file)})

    assert repr(direct) == "GitHubToken(<redacted>)"
    assert str(standard) == "<redacted>"
    assert repr(from_file) == "GitHubToken(<redacted>)"

    with pytest.raises(CollectError) as ambiguous:
        load_github_token({"ATTEST_GITHUB_TOKEN": TOKEN, "GITHUB_TOKEN": TOKEN})
    assert ambiguous.value.code == "ERR-COLLECT-121"


@pytest.mark.ac("AC-F04-090")
def test_token_never_crosses_error_log_or_output_boundaries(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(500, text=f"upstream accidentally echoed {TOKEN}")

    token = GitHubToken(TOKEN)
    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_reviews("acme/widgets", 7)

    captured_streams = capsys.readouterr()
    rendered = "\n".join(
        (
            repr(token),
            str(token),
            str(captured.value),
            captured.value.message,
            captured.value.remediation,
            captured_streams.out,
            captured_streams.err,
            caplog.text,
        )
    )
    assert TOKEN not in rendered
    assert captured.value.code == "ERR-COLLECT-125"


@pytest.mark.ac("AC-F04-120")
def test_every_httpx_request_receives_explicit_timeout() -> None:
    observed: list[dict[str, float]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request.extensions["timeout"])
        return httpx.Response(200, json=[])

    with _client(handler, request_timeout=7.5) as client:
        client.fetch_reviews("acme/widgets", 7)

    assert observed == [{"connect": 7.5, "read": 7.5, "write": 7.5, "pool": 7.5}]
    request_source = inspect.getsource(GitHubHttpClient._request_json)
    assert "self._client.get" in request_source
    assert "timeout=" in request_source


def test_requests_pin_api_version_media_type_and_user_agent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-GitHub-Api-Version"] == "2026-03-10"
        assert request.headers["Accept"] == "application/vnd.github+json"
        assert request.headers["User-Agent"] == "attest-collect/0.1"
        return httpx.Response(200, json=[])

    with _client(handler) as client:
        client.fetch_reviews("acme/widgets", 7)


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, "ERR-COLLECT-121"), (403, "ERR-COLLECT-121"), (500, "ERR-COLLECT-125")],
)
def test_non_rate_http_failures_are_stably_classified(status: int, expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "not public"})

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == expected


def test_classic_protection_404_is_a_determinate_absence() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    with _client(handler) as client:
        assert client.fetch_classic_protection("acme/widgets", "main") is None


@pytest.mark.parametrize("value", ["", "has whitespace", "line\nbreak"])
def test_invalid_token_value_is_authentication_failure(value: str) -> None:
    with pytest.raises(CollectError) as captured:
        GitHubToken(value)

    assert captured.value.code == "ERR-COLLECT-121"


@pytest.mark.parametrize("contents", ["", f"{TOKEN}\n\n", "not utf8"])
def test_invalid_token_files_are_authentication_failures(
    tmp_path: Path,
    contents: str,
) -> None:
    token_file = tmp_path / "github-token"
    if contents == "not utf8":
        token_file.write_bytes(b"\xff")
    else:
        token_file.write_text(contents, encoding="utf-8")

    with pytest.raises(CollectError) as captured:
        load_github_token({"ATTEST_GITHUB_TOKEN_FILE": str(token_file)})

    assert captured.value.code == "ERR-COLLECT-121"


def test_token_file_accepts_one_crlf_terminator(tmp_path: Path) -> None:
    token_file = tmp_path / "github-token"
    token_file.write_bytes(f"{TOKEN}\r\n".encode())

    assert str(load_github_token({"ATTEST_GITHUB_TOKEN_FILE": str(token_file)})) == "<redacted>"


def test_missing_token_file_is_authentication_failure(tmp_path: Path) -> None:
    with pytest.raises(CollectError) as captured:
        load_github_token({"ATTEST_GITHUB_TOKEN_FILE": str(tmp_path / "missing")})

    assert captured.value.code == "ERR-COLLECT-121"


@pytest.mark.parametrize("value", [True, 0.0, float("nan")])
def test_invalid_timeout_configuration_is_response_failure(value: object) -> None:
    with pytest.raises(CollectError) as captured:
        GitHubHttpClient(GitHubToken(TOKEN), request_timeout=cast(Any, value))

    assert captured.value.code == "ERR-COLLECT-125"


@pytest.mark.parametrize(
    ("operation", "arguments"),
    [
        ("fetch_reviews", ("bad-repository", 7)),
        ("fetch_reviews", ("acme/widgets", True)),
        ("fetch_branch_rules", ("acme/widgets", "feature/*")),
        ("fetch_check_runs", ("acme/widgets", "ABC")),
    ],
)
def test_invalid_request_context_never_reaches_transport(
    operation: str,
    arguments: tuple[object, ...],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request.url)

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        getattr(client, operation)(*arguments)

    assert captured.value.code == "ERR-COLLECT-124"


@pytest.mark.parametrize(
    "body",
    [
        {"id": 1},
        ["not-an-object"],
        [{"id": True}],
        [{"id": 1, "score": 1.5}],
    ],
)
def test_invalid_review_payload_shapes_are_response_failures(body: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == "ERR-COLLECT-125"


def test_malformed_json_is_a_response_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{")

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == "ERR-COLLECT-125"


def test_transport_failure_is_a_response_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(TIMEOUT_MESSAGE, request=request)

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == "ERR-COLLECT-125"
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


@pytest.mark.parametrize(
    "headers",
    [
        {"Retry-After": "soon"},
        {"X-RateLimit-Remaining": "0"},
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "later"},
    ],
)
def test_malformed_rate_limit_metadata_is_rate_failure(headers: dict[str, str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers=headers)

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == "ERR-COLLECT-123"


def test_expired_operation_deadline_stops_before_transport() -> None:
    values = iter((0.0, 2.0))

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request.url)

    with (
        _client(handler, operation_deadline=1.0, monotonic=lambda: next(values)) as client,
        pytest.raises(CollectError) as captured,
    ):
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == "ERR-COLLECT-123"


@pytest.mark.parametrize(
    "link",
    [
        '<https://api.github.com/repos/acme/widgets/pulls/7/reviews?per_page=100>; rel="next"',
        "<https://api.github.com/repos/acme/widgets/pulls/7/reviews"
        '?per_page=100&page=02>; rel="next"',
        "<https://api.github.com/repos/acme/widgets/pulls/7/reviews"
        '?per_page=100&page=2&page=2>; rel="next"',
        "<https://api.github.com/repos/acme/widgets/pulls/7/reviews"
        '?per_page=50&page=2>; rel="next"',
    ],
)
def test_pagination_rejects_malformed_or_changed_query(link: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Link": link}, json=[])

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_reviews("acme/widgets", 7)

    assert captured.value.code == "ERR-COLLECT-122"


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"total_count": True, "check_suites": []},
        {"total_count": 0},
    ],
)
def test_invalid_check_suite_wrappers_are_response_failures(body: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with _client(handler) as client, pytest.raises(CollectError) as captured:
        client.fetch_check_runs("acme/widgets", "2" * 40)

    assert captured.value.code == "ERR-COLLECT-125"
