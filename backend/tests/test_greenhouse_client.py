from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.sources.greenhouse.client import GreenhouseClient
from app.sources.greenhouse.errors import (
    GreenhouseBoardNotFoundError,
    GreenhouseConfigurationError,
    GreenhouseRateLimitError,
    GreenhouseRequestError,
    GreenhouseTimeoutError,
)
from app.sources.greenhouse.validation import parse_greenhouse_response

RETRIEVED_AT = datetime(2026, 10, 6, 9, tzinfo=UTC)
RAW_RESPONSE = b'{\n  "jobs": [],\n  "meta": {"total": 0}\n}\n'
Handler = Callable[[httpx.Request], httpx.Response]


async def no_sleep(_: float) -> None:
    return None


@pytest.mark.asyncio
async def test_native_board_metadata_uses_existing_retry_policy_and_preserves_bytes() -> (
    None
):
    requests: list[httpx.Request] = []
    body = b'{ "name": "Native Employer" }\n'

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503 if len(requests) == 1 else 200, content=body)

    client, http_client = create_client(respond)
    async with http_client:
        result = await client.fetch_board(board_token="acme-board")
    assert len(requests) == 2
    assert (
        str(requests[-1].url) == "https://boards-api.greenhouse.io/v1/boards/acme-board"
    )
    assert result.body == body
    assert result.retrieved_at == RETRIEVED_AT


def create_client(
    handler: Handler,
    *,
    max_attempts: int = 3,
    sleep: Callable[[float], Awaitable[None]] = no_sleep,
    max_retry_delay_seconds: float = 10.0,
) -> tuple[GreenhouseClient, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GreenhouseClient(
        http_client,
        connect_timeout_seconds=2.5,
        read_timeout_seconds=15.0,
        max_attempts=max_attempts,
        retry_base_delay_seconds=1.0,
        max_retry_delay_seconds=max_retry_delay_seconds,
        sleep=sleep,
        clock=lambda: RETRIEVED_AT,
    )
    return client, http_client


@pytest.mark.asyncio
async def test_success_constructs_endpoint_and_preserves_exact_response_bytes() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            content=RAW_RESPONSE,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    client, http_client = create_client(handler)
    async with http_client:
        result = await client.fetch_jobs(board_token="acme-board")

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == (
        "https://boards-api.greenhouse.io/v1/boards/acme-board/jobs?content=true"
    )
    assert request.headers["Accept"] == "application/json"
    assert request.headers["User-Agent"] == "OpenRoleObservatory/0.1.0"
    assert request.extensions["timeout"] == {
        "connect": 2.5,
        "read": 15.0,
        "write": 15.0,
        "pool": 2.5,
    }
    assert result.body == RAW_RESPONSE
    assert result.status_code == 200
    assert result.content_type == "application/json; charset=utf-8"
    assert result.retrieved_at == RETRIEVED_AT
    assert result.retrieved_at.tzinfo is not None


@pytest.mark.asyncio
async def test_board_token_is_encoded_as_one_url_path_segment() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=RAW_RESPONSE)

    client, http_client = create_client(handler)
    async with http_client:
        await client.fetch_jobs(board_token="acme/engineering")

    assert requests[0].url.raw_path.startswith(b"/v1/boards/acme%2Fengineering/jobs")


@pytest.mark.asyncio
async def test_blank_or_padded_board_token_fails_without_http_request() -> None:
    request_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, content=RAW_RESPONSE)

    client, http_client = create_client(handler)
    async with http_client:
        for board_token in ("", "   ", " acme"):
            with pytest.raises(GreenhouseConfigurationError):
                await client.fetch_jobs(board_token=board_token)

    assert request_count == 0


@pytest.mark.asyncio
async def test_invalid_board_is_not_retried() -> None:
    request_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(404)

    client, http_client = create_client(handler)
    async with http_client:
        with pytest.raises(GreenhouseBoardNotFoundError) as captured:
            await client.fetch_jobs(board_token="missing-board")

    assert captured.value.status_code == 404
    assert request_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403])
async def test_other_client_errors_are_not_retried(status_code: int) -> None:
    request_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(status_code)

    client, http_client = create_client(handler)
    async with http_client:
        with pytest.raises(GreenhouseRequestError) as captured:
            await client.fetch_jobs(board_token="acme")

    assert captured.value.status_code == status_code
    assert request_count == 1


@pytest.mark.asyncio
async def test_rate_limit_retries_and_can_recover() -> None:
    status_codes = iter([429, 200])
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(next(status_codes), content=RAW_RESPONSE)

    client, http_client = create_client(handler, sleep=record_sleep)
    async with http_client:
        result = await client.fetch_jobs(board_token="acme")

    assert result.status_code == 200
    assert delays == [1.0]


@pytest.mark.asyncio
async def test_retry_after_seconds_is_respected_but_bounded() -> None:
    status_codes = iter([503, 200])
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    def handler(_: httpx.Request) -> httpx.Response:
        status_code = next(status_codes)
        return httpx.Response(
            status_code,
            content=RAW_RESPONSE,
            headers={"Retry-After": "120"} if status_code == 503 else None,
        )

    client, http_client = create_client(
        handler,
        sleep=record_sleep,
        max_retry_delay_seconds=4.0,
    )
    async with http_client:
        await client.fetch_jobs(board_token="acme")

    assert delays == [4.0]


@pytest.mark.asyncio
async def test_exhausted_rate_limit_raises_stable_error() -> None:
    request_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(429)

    client, http_client = create_client(handler)
    async with http_client:
        with pytest.raises(GreenhouseRateLimitError) as captured:
            await client.fetch_jobs(board_token="acme")

    assert captured.value.status_code == 429
    assert request_count == 3


@pytest.mark.asyncio
async def test_server_errors_retry_with_exponential_backoff_and_can_recover() -> None:
    status_codes = iter([503, 503, 200])
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(next(status_codes), content=RAW_RESPONSE)

    client, http_client = create_client(handler, sleep=record_sleep)
    async with http_client:
        result = await client.fetch_jobs(board_token="acme")

    assert result.status_code == 200
    assert delays == [1.0, 2.0]


@pytest.mark.asyncio
async def test_exhausted_server_error_raises_stable_request_error() -> None:
    request_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(503)

    client, http_client = create_client(handler)
    async with http_client:
        with pytest.raises(GreenhouseRequestError) as captured:
            await client.fetch_jobs(board_token="acme")

    assert captured.value.status_code == 503
    assert request_count == 3


@pytest.mark.asyncio
async def test_read_timeout_retries_and_can_recover() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            raise httpx.ReadTimeout("read timed out", request=request)
        return httpx.Response(200, content=RAW_RESPONSE)

    client, http_client = create_client(handler)
    async with http_client:
        result = await client.fetch_jobs(board_token="acme")

    assert result.body == RAW_RESPONSE
    assert request_count == 2


@pytest.mark.asyncio
async def test_connection_error_retries_and_can_recover() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, content=RAW_RESPONSE)

    client, http_client = create_client(handler)
    async with http_client:
        result = await client.fetch_jobs(board_token="acme")

    assert result.body == RAW_RESPONSE
    assert request_count == 2


@pytest.mark.asyncio
async def test_exhausted_transport_error_preserves_cause() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise httpx.ConnectError("connection refused", request=request)

    client, http_client = create_client(handler)
    async with http_client:
        with pytest.raises(GreenhouseRequestError) as captured:
            await client.fetch_jobs(board_token="acme")

    assert isinstance(captured.value.__cause__, httpx.ConnectError)
    assert request_count == 3


@pytest.mark.asyncio
async def test_exhausted_timeout_preserves_transport_cause() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        raise httpx.ReadTimeout("read timed out", request=request)

    client, http_client = create_client(handler)
    async with http_client:
        with pytest.raises(GreenhouseTimeoutError) as captured:
            await client.fetch_jobs(board_token="acme")

    assert isinstance(captured.value.__cause__, httpx.ReadTimeout)
    assert request_count == 3


@pytest.mark.asyncio
async def test_empty_successful_board_remains_compatible_with_validation_layer() -> (
    None
):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=RAW_RESPONSE)

    client, http_client = create_client(handler)
    async with http_client:
        result = await client.fetch_jobs(board_token="empty-board")

    validation = parse_greenhouse_response(result.body)

    assert validation.valid_records == ()
    assert validation.invalid_records == ()


@pytest.mark.asyncio
async def test_missing_content_type_is_preserved_as_none() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=RAW_RESPONSE)

    client, http_client = create_client(handler)
    async with http_client:
        result = await client.fetch_jobs(board_token="acme")

    assert result.content_type is None
