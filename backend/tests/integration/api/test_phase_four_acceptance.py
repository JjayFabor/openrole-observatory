"""Verify production ingestion outcomes through all public job read contracts."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.dependencies import get_public_job_query_service
from app.config import get_settings
from app.ingestion.errors import SourceSyncFailedError
from app.jobs.models import Job
from app.jobs.public_query_service import PublicJobQueryService
from app.main import create_app
from app.sources.models import SourceConnection
from tests.integration.ingestion.phase_two_scenarios import (
    PhaseTwoScenario,
    acceptance_board,
)
from tests.integration.ingestion.test_source_sync import DatabaseContext, create_source
from tests.integration.ingestion.test_source_sync import (
    database_context as database_context,
)

PUBLIC_JOBS = "/api/v1/public/jobs"
PRIVATE_FIELDS = (
    "pipeline_run_id",
    "raw_snapshot_id",
    "source_observation_id",
    "source_connection_id",
    "content_hash",
    "canonical_metadata",
    "configuration",
    "external_job_id",
    "from_version_id",
    "to_version_id",
    "phase-four-private",
)


@pytest_asyncio.fixture
async def scenario(
    database_context: DatabaseContext, tmp_path: Path
) -> AsyncIterator[PhaseTwoScenario]:
    scenario = PhaseTwoScenario(database_context, tmp_path)
    try:
        yield scenario
    finally:
        await scenario.close()


@pytest_asyncio.fixture
async def public_client(
    database_context: DatabaseContext,
) -> AsyncIterator[httpx.AsyncClient]:
    application = create_app(get_settings())
    service = PublicJobQueryService(database_context.session_factory)
    application.dependency_overrides[get_public_job_query_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        yield client


def assert_public(response: httpx.Response) -> None:
    assert response.status_code == 200
    for field in PRIVATE_FIELDS:
        assert field not in response.text


def changed_board() -> bytes:
    body = json.loads(acceptance_board(workplace="hybrid", multiple_changes=True))
    body["jobs"][0]["title"] = "Senior Backend Engineer < > & \" '"
    body["jobs"][0]["content"] = "<p>Current description.</p>"
    body["jobs"][0]["departments"] = [
        {"id": 1, "name": "phase-four-private-provider-metadata"}
    ]
    return json.dumps(body).encode()


@pytest.mark.asyncio
async def test_ingestion_to_public_changes_absence_and_reappearance(
    database_context: DatabaseContext,
    scenario: PhaseTwoScenario,
    public_client: httpx.AsyncClient,
) -> None:
    source = await create_source(database_context)
    async with database_context.session_factory.begin() as session:
        stored = await session.get(SourceConnection, source.id)
        assert stored is not None
        stored.configuration = {"secret": "phase-four-private-source-configuration"}

    initial = await scenario.sync(source.id, acceptance_board())
    unchanged = await scenario.sync(source.id, acceptance_board())
    assert initial.jobs_new == unchanged.jobs_unchanged == 2
    async with database_context.session_factory() as session:
        jobs = list(
            await session.scalars(
                select(Job).where(Job.source_connection_id == source.id)
            )
        )
    by_external_id = {job.external_job_id: job.id for job in jobs}
    changed_id, returning_id = by_external_id["1001"], by_external_id["1002"]
    detail_path = f"{PUBLIC_JOBS}/{changed_id}"
    returning_path = f"{PUBLIC_JOBS}/{returning_id}"
    initial_history = await public_client.get(f"{detail_path}/changes")
    assert_public(initial_history)
    assert initial_history.json()["items"] == []

    changed_body = changed_board()
    changed = await scenario.sync(source.id, changed_body)
    assert changed.jobs_changed == changed.jobs_unchanged == 1
    discovery = await public_client.get(
        PUBLIC_JOBS,
        params={
            "q": "  SENIOR BACKEND  ",
            "location": "manila",
            "workplace_type": "hybrid",
            "employment_type": "full_time",
        },
    )
    assert_public(discovery)
    assert discovery.json()["total"] == 1
    assert discovery.json()["items"][0]["id"] == str(changed_id)
    assert "description" not in discovery.json()["items"][0]

    detail = await public_client.get(detail_path)
    assert_public(detail)
    assert detail.json()["title"] == "Senior Backend Engineer < > & \" '"
    assert detail.json()["lifecycle_status"] == "observed"
    assert detail.json()["first_seen_at"] != detail.json()["last_seen_at"]
    history = await public_client.get(f"{detail_path}/changes")
    assert_public(history)
    groups = history.json()["items"]
    assert len(groups) == 1
    assert groups[0]["observed_at"] == detail.json()["last_seen_at"]
    changes = {change["field"]: change for change in groups[0]["changes"]}
    assert set(changes) == {
        "title",
        "location_text",
        "workplace_type",
        "employment_type",
        "salary",
        "description",
    }
    assert changes["salary"]["new_value"]["min"] == "65000.01"
    assert changes["salary"]["new_value"]["max"] == "90000.99"
    assert changes["description"] == {
        "field": "description",
        "change_type": "modified",
    }
    assert "<p>" not in history.text

    missing = json.loads(changed_body)
    missing["jobs"] = [record for record in missing["jobs"] if record["id"] == 1001]
    missing_body = json.dumps(missing).encode()
    await scenario.sync(source.id, missing_body)
    tentative = await public_client.get(returning_path)
    assert_public(tentative)
    assert tentative.json()["lifecycle_status"] == "observed"
    assert tentative.json()["absence_first_detected_at"] is not None

    await scenario.sync(source.id, missing_body)
    historical = await public_client.get(returning_path)
    assert_public(historical)
    assert historical.json()["lifecycle_status"] == "not_observed"
    assert historical.json()["no_longer_observed_at"] is not None
    for path in (PUBLIC_JOBS, f"{PUBLIC_JOBS}/sitemap"):
        response = await public_client.get(path)
        assert_public(response)
        assert [item["id"] for item in response.json()["items"]] == [str(changed_id)]
    historical_changes = await public_client.get(f"{returning_path}/changes")
    assert_public(historical_changes)
    assert historical_changes.json()["items"] == []

    returned = await scenario.sync(source.id, changed_body)
    assert returned.jobs_unchanged == 2
    reappeared = await public_client.get(returning_path)
    assert_public(reappeared)
    assert reappeared.json()["id"] == historical.json()["id"]
    assert reappeared.json()["lifecycle_status"] == "observed"
    assert reappeared.json()["reappeared_at"] == reappeared.json()["last_seen_at"]
    assert (
        reappeared.json()["no_longer_observed_at"]
        == historical.json()["no_longer_observed_at"]
    )
    sitemap = await public_client.get(f"{PUBLIC_JOBS}/sitemap", params={"limit": 1})
    assert_public(sitemap)
    next_page = await public_client.get(
        f"{PUBLIC_JOBS}/sitemap",
        params={"limit": 1, "after": sitemap.json()["next_after"]},
    )
    assert_public(next_page)
    assert next_page.json()["next_after"] is None
    assert {
        item["id"]
        for response in (sitemap, next_page)
        for item in response.json()["items"]
    } == {str(changed_id), str(returning_id)}
    assert (await public_client.get(f"{detail_path}/changes")).json() == history.json()


@pytest.mark.asyncio
async def test_moderate_public_discovery_survives_source_failure(
    database_context: DatabaseContext,
    scenario: PhaseTwoScenario,
    public_client: httpx.AsyncClient,
) -> None:
    source = await create_source(database_context)
    body = acceptance_board(tuple(range(1001, 1121)))
    result = await scenario.sync(source.id, body)
    assert result.jobs_new == 120
    collected: list[str] = []
    for offset in range(0, 120, 25):
        response = await public_client.get(PUBLIC_JOBS, params={"offset": offset})
        assert_public(response)
        assert response.json()["total"] == 120
        assert len(response.json()["items"]) == min(25, 120 - offset)
        assert all("description" not in item for item in response.json()["items"])
        collected.extend(item["id"] for item in response.json()["items"])
    assert collected == sorted(collected) and len(set(collected)) == 120
    before = await public_client.get(PUBLIC_JOBS)
    sitemap_before = await public_client.get(f"{PUBLIC_JOBS}/sitemap")
    with pytest.raises(SourceSyncFailedError):
        await scenario.sync(source.id, body, failure="503")
    after = await public_client.get(PUBLIC_JOBS)
    sitemap_after = await public_client.get(f"{PUBLIC_JOBS}/sitemap")
    assert_public(after)
    assert_public(sitemap_after)
    assert after.json() == before.json()
    assert sitemap_after.json() == sitemap_before.json()

    async with database_context.session_factory.begin() as session:
        stored = await session.get(SourceConnection, source.id)
        assert stored is not None
        stored.is_active = False
    excluded = await public_client.get(PUBLIC_JOBS)
    assert_public(excluded)
    assert excluded.json()["items"] == [] and excluded.json()["total"] == 0
    assert (await public_client.get(f"{PUBLIC_JOBS}/sitemap")).json()["items"] == []
    retained_detail = await public_client.get(f"{PUBLIC_JOBS}/{collected[0]}")
    assert_public(retained_detail)
    assert retained_detail.json()["lifecycle_status"] == "observed"
