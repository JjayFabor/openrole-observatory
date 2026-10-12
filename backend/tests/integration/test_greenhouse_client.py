import os

import httpx
import pytest

from app.sources.greenhouse.client import GreenhouseClient
from app.sources.greenhouse.validation import parse_greenhouse_response

RUN_GREENHOUSE_INTEGRATION_TESTS = (
    os.getenv("RUN_GREENHOUSE_INTEGRATION_TESTS", "").lower() == "true"
)
GREENHOUSE_TEST_BOARD_TOKEN = os.getenv("GREENHOUSE_TEST_BOARD_TOKEN")

pytestmark = pytest.mark.skipif(
    not RUN_GREENHOUSE_INTEGRATION_TESTS or not GREENHOUSE_TEST_BOARD_TOKEN,
    reason=(
        "Set RUN_GREENHOUSE_INTEGRATION_TESTS=true and "
        "GREENHOUSE_TEST_BOARD_TOKEN to test the public Greenhouse API"
    ),
)


@pytest.mark.asyncio
async def test_greenhouse_client_against_public_job_board() -> None:
    assert GREENHOUSE_TEST_BOARD_TOKEN is not None

    async with httpx.AsyncClient() as http_client:
        client = GreenhouseClient(http_client, max_attempts=1)
        result = await client.fetch_jobs(board_token=GREENHOUSE_TEST_BOARD_TOKEN)

    validation = parse_greenhouse_response(result.body)

    assert result.status_code == 200
    assert result.body
    assert result.retrieved_at.tzinfo is not None
    assert isinstance(validation.valid_records, tuple)
    assert isinstance(validation.invalid_records, tuple)
