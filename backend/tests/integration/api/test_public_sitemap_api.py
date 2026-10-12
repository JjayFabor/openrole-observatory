from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from sqlalchemy import delete, event

from app.jobs.models import Job, JobLifecycleStatus, JobVersion
from app.sources.models import SourceConnection
from tests.integration.api.test_history_api import database_contents
from tests.integration.api.test_public_jobs_api import client as client
from tests.integration.api.test_public_jobs_api import create_job
from tests.test_changed_job_persistence import DatabaseContext, create_source
from tests.test_changed_job_persistence import database_context as database_context

PATH = "/api/v1/public/jobs/sitemap"


@pytest.mark.asyncio
async def test_public_sitemap_is_a_static_id_only_route_with_bounded_default(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(PATH)
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_after": None, "limit": 1000}


@pytest.mark.asyncio
async def test_public_sitemap_walks_eligible_ids_independently_of_observation_order(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
) -> None:
    source = await create_source(database_context.session_factory)
    ids = [
        await create_job(database_context, source, 1000 + i, days_seen=i)
        for i in range(7)
    ]
    await create_job(
        database_context, source, 2000, status=JobLifecycleStatus.NOT_OBSERVED
    )
    inactive = await create_source(database_context.session_factory)
    await create_job(database_context, inactive, 2001)
    async with database_context.session_factory.begin() as session:
        stored = await session.get(SourceConnection, inactive.id)
        assert stored is not None
        stored.is_active = False
    collected: list[str] = []
    after: str | None = None
    before = await database_contents(database_context)
    while True:
        params: dict[str, str] = {"limit": "2"}
        if after:
            params["after"] = after
        response = await client.get(PATH, params=params)
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"items", "next_after", "limit"}
        assert all(set(item) == {"id"} for item in body["items"])
        assert len(body["items"]) <= 2 and body["limit"] == 2
        collected.extend(item["id"] for item in body["items"])
        after = body["next_after"]
        if after is None:
            break
        assert after == body["items"][-1]["id"]
    assert collected == sorted(map(str, ids))
    assert await database_contents(database_context) == before


@pytest.mark.asyncio
async def test_public_sitemap_membership_follows_absence_reappearance_and_source_activity(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
) -> None:
    source = await create_source(database_context.session_factory)
    job_id = await create_job(database_context, source, 1001)
    assert (await client.get(PATH)).json()["items"] == [{"id": str(job_id)}]
    async with database_context.session_factory.begin() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        job.lifecycle_status = "not_observed"
        job.no_longer_observed_at = job.last_seen_at + timedelta(days=2)
    assert (await client.get(PATH)).json()["items"] == []
    async with database_context.session_factory.begin() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        job.lifecycle_status = "observed"
        job.reappeared_at = job.last_seen_at + timedelta(days=3)
    assert (await client.get(PATH)).json()["items"] == [{"id": str(job_id)}]
    async with database_context.session_factory.begin() as session:
        stored = await session.get(SourceConnection, source.id)
        assert stored is not None
        stored.is_active = False
    assert (await client.get(PATH)).json()["items"] == []


@pytest.mark.asyncio
async def test_public_sitemap_invalid_current_version_fails_without_diagnostic_ids(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
) -> None:
    source = await create_source(database_context.session_factory)
    job_id = await create_job(database_context, source, 1001)
    async with database_context.session_factory.begin() as session:
        await session.execute(delete(JobVersion).where(JobVersion.job_id == job_id))
    response = await client.get(PATH)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PUBLIC_JOBS_UNAVAILABLE"
    assert str(job_id) not in response.text


@pytest.mark.asyncio
async def test_public_sitemap_uses_one_scalar_query_without_content_history_or_count_walk(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
) -> None:
    source = await create_source(database_context.session_factory)
    for index in range(5):
        await create_job(database_context, source, 1000 + index)
    statements: list[str] = []

    def capture(
        _conn: object,
        _cursor: object,
        statement: str,
        _params: object,
        _ctx: object,
        _many: object,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(database_context.engine.sync_engine, "before_cursor_execute", capture)
    try:
        response = await client.get(PATH, params={"limit": 2})
    finally:
        event.remove(
            database_context.engine.sync_engine, "before_cursor_execute", capture
        )
    assert response.status_code == 200 and len(statements) == 1
    for field in (
        "description",
        "title",
        "salary",
        "canonical_metadata",
        "job_change_events",
        "job_lifecycle_events",
        "configuration",
    ):
        assert field not in statements[0]
    after_last = await client.get(PATH, params={"after": str(UUID(int=(1 << 128) - 1))})
    assert after_last.json()["items"] == [] and after_last.json()["next_after"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 1001}, {"limit": "bad"}, {"after": "bad"}]
)
async def test_public_sitemap_rejects_invalid_pagination(
    client: httpx.AsyncClient, params: dict[str, int | str]
) -> None:
    assert (await client.get(PATH, params=params)).status_code == 422
