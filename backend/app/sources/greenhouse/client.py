import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from app.sources.greenhouse.errors import (
    GreenhouseBoardNotFoundError,
    GreenhouseConfigurationError,
    GreenhouseRateLimitError,
    GreenhouseRequestError,
    GreenhouseTimeoutError,
)

GREENHOUSE_API_BASE_URL = "https://boards-api.greenhouse.io"
GREENHOUSE_USER_AGENT = "OpenRoleObservatory/0.1.0"
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

Clock = Callable[[], datetime]
Sleeper = Callable[[float], Awaitable[None]]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class GreenhouseFetchResult:
    body: bytes
    status_code: int
    content_type: str | None
    retrieved_at: datetime


class GreenhouseClient:
    """Retrieve raw public job-board responses without persistence or parsing."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 30.0,
        max_attempts: int = 3,
        retry_base_delay_seconds: float = 1.0,
        max_retry_delay_seconds: float = 10.0,
        sleep: Sleeper = asyncio.sleep,
        clock: Clock = _utc_now,
    ) -> None:
        if connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be greater than zero")
        if read_timeout_seconds <= 0:
            raise ValueError("read_timeout_seconds must be greater than zero")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if retry_base_delay_seconds < 0:
            raise ValueError("retry_base_delay_seconds must not be negative")
        if max_retry_delay_seconds < 0:
            raise ValueError("max_retry_delay_seconds must not be negative")

        self._http_client = http_client
        self._max_attempts = max_attempts
        self._retry_base_delay_seconds = retry_base_delay_seconds
        self._max_retry_delay_seconds = max_retry_delay_seconds
        self._sleep = sleep
        self._clock = clock
        self._timeout = httpx.Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=read_timeout_seconds,
            pool=connect_timeout_seconds,
        )

    async def fetch_jobs(self, *, board_token: str) -> GreenhouseFetchResult:
        """Fetch one board's exact response bytes using bounded retries."""
        return await self._fetch(board_token=board_token, jobs=True)

    async def fetch_board(self, *, board_token: str) -> GreenhouseFetchResult:
        """Fetch native board metadata for factual automatic source registration."""
        return await self._fetch(board_token=board_token, jobs=False)

    async def _fetch(self, *, board_token: str, jobs: bool) -> GreenhouseFetchResult:

        normalized_token = board_token.strip()
        if not normalized_token or normalized_token != board_token:
            raise GreenhouseConfigurationError(
                "Greenhouse board token must be non-blank and contain no "
                "surrounding whitespace."
            )

        encoded_token = quote(normalized_token, safe="")
        url = f"{GREENHOUSE_API_BASE_URL}/v1/boards/{encoded_token}"
        if jobs:
            url += "/jobs"

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._http_client.get(
                    url,
                    params={"content": "true"} if jobs else None,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": GREENHOUSE_USER_AGENT,
                    },
                    timeout=self._timeout,
                )
            except httpx.TimeoutException as error:
                if attempt == self._max_attempts:
                    raise GreenhouseTimeoutError(
                        "Greenhouse request timed out after "
                        f"{self._max_attempts} attempts."
                    ) from error
                await self._sleep(self._backoff_delay(attempt))
                continue
            except httpx.TransportError as error:
                if attempt == self._max_attempts:
                    raise GreenhouseRequestError(
                        "Greenhouse transport failed after "
                        f"{self._max_attempts} attempts."
                    ) from error
                await self._sleep(self._backoff_delay(attempt))
                continue

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt < self._max_attempts:
                    await self._sleep(self._retry_delay(response, attempt))
                    continue
                self._raise_exhausted_response(response)

            if response.status_code == 404:
                raise GreenhouseBoardNotFoundError(
                    "Greenhouse board was not found.",
                    status_code=response.status_code,
                )

            if not response.is_success:
                raise GreenhouseRequestError(
                    f"Greenhouse returned HTTP {response.status_code}.",
                    status_code=response.status_code,
                )

            retrieved_at = self._clock()
            if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
                raise ValueError("clock must return a timezone-aware datetime")

            return GreenhouseFetchResult(
                body=response.content,
                status_code=response.status_code,
                content_type=response.headers.get("Content-Type"),
                retrieved_at=retrieved_at.astimezone(UTC),
            )

        raise AssertionError("Greenhouse request loop exited unexpectedly")

    def _backoff_delay(self, failed_attempt: int) -> float:
        delay = self._retry_base_delay_seconds * (2.0 ** (failed_attempt - 1))
        return min(delay, self._max_retry_delay_seconds)

    def _retry_delay(self, response: httpx.Response, failed_attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                requested_delay = float(retry_after)
            except ValueError:
                pass
            else:
                if requested_delay >= 0:
                    return min(requested_delay, self._max_retry_delay_seconds)

        return self._backoff_delay(failed_attempt)

    @staticmethod
    def _raise_exhausted_response(response: httpx.Response) -> None:
        if response.status_code == 429:
            raise GreenhouseRateLimitError(
                "Greenhouse rate limit remained active after bounded retries.",
                status_code=response.status_code,
            )

        raise GreenhouseRequestError(
            f"Greenhouse returned HTTP {response.status_code} after bounded retries.",
            status_code=response.status_code,
        )
