from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event

from app.api.dependencies import get_job_query_service
from app.config import get_settings
from app.jobs.models import Job, JobLifecycleStatus
from app.jobs.query_service import JobQueryService
from app.jobs.service import NewJobPersistenceService, PersistNewJobCommand
from app.main import create_app
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.models import SourceConnection
from tests.integration.api.test_history_api import create_history
from tests.integration.lifecycle.helpers import create_lifecycle_job
from tests.test_changed_job_persistence import (
    FIRST_OBSERVED_AT,
    DatabaseContext,
    create_observation,
    create_source,
    fixture_job,
)
from tests.test_changed_job_persistence import database_context as database_context


@pytest_asyncio.fixture
async def client(database_context: DatabaseContext) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(get_settings())
    service = JobQueryService(database_context.session_factory)
    app.dependency_overrides[get_job_query_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        yield api


async def create_job(
    context: DatabaseContext,
    source: SourceConnection,
    external_id: int,
    *,
    title: str = "Engineer",
    location: str | None = None,
    status: JobLifecycleStatus = JobLifecycleStatus.OBSERVED,
    days_seen: int = 0,
) -> UUID:
    record = fixture_job("jobs_v1.json").model_copy(update={"id": external_id})
    observation = await create_observation(
        context.session_factory, source.id, record, FIRST_OBSERVED_AT
    )
    canonical = map_greenhouse_job(record).model_copy(
        update={
            "title": title,
            "location_text": location,
            "workplace_type": None,
            "employment_type": None,
        }
    )
    result = await NewJobPersistenceService(
        context.session_factory, mapper=lambda _: canonical
    ).create_new_job(PersistNewJobCommand(observation.id, record))
    async with context.session_factory.begin() as session:
        job = await session.get(Job, result.job_id)
        assert job is not None
        job.lifecycle_status = status.value
        job.last_seen_at = FIRST_OBSERVED_AT + timedelta(days=days_seen)
    return result.job_id


@pytest.mark.asyncio
async def test_default_list_is_empty_with_real_total(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/jobs")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 25, "offset": 0}


@pytest.mark.asyncio
async def test_current_summary_and_safe_display_fields(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    setup = await create_history(database_context, version_count=2)
    async with database_context.session_factory.begin() as session:
        source = await session.get(SourceConnection, setup.source.id)
        job = await session.get(Job, setup.job_id)
        assert source is not None and job is not None
        source.configuration = {"secret": "must-not-appear"}
        job.consecutive_absent_runs = 1
        job.absence_first_detected_at = FIRST_OBSERVED_AT + timedelta(days=4)
        job.reappeared_at = FIRST_OBSERVED_AT + timedelta(days=2)
    response = await client.get("/api/v1/jobs")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == str(setup.job_id)
    assert item["company"] == {
        "id": str(setup.source.company_id),
        "name": setup.source.company.name,
    }
    assert item["source"] == {"id": str(setup.source.id), "provider": "greenhouse"}
    assert item["current_version"] == {
        "id": str(setup.versions[1].id),
        "version_number": 2,
        "title": "Engineer II",
        "location_text": setup.versions[1].location_text,
        "workplace_type": "hybrid",
        "employment_type": "full_time",
    }
    assert item["lifecycle_status"] == "observed"
    assert item["consecutive_absent_runs"] == 1
    assert item["absence_first_detected_at"] and item["reappeared_at"]
    assert "must-not-appear" not in response.text
    assert "description" not in item["current_version"]
    assert "configuration" not in item["source"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", list(JobLifecycleStatus))
async def test_lifecycle_and_source_filters(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
    status: JobLifecycleStatus,
) -> None:
    source_a = await create_source(database_context.session_factory)
    source_b = await create_source(database_context.session_factory)
    expected = await create_job(database_context, source_a, 1001, status=status)
    other_status = (
        JobLifecycleStatus.NOT_OBSERVED
        if status == JobLifecycleStatus.OBSERVED
        else JobLifecycleStatus.OBSERVED
    )
    await create_job(database_context, source_a, 1002, status=other_status)
    await create_job(database_context, source_b, 1003, status=status)
    body = (
        await client.get(
            "/api/v1/jobs",
            params={
                "source_connection_id": str(source_a.id),
                "lifecycle_status": status.value,
            },
        )
    ).json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(expected)]
    assert (
        await client.get("/api/v1/jobs", params={"source_connection_id": str(uuid4())})
    ).json()["total"] == 0


@pytest.mark.asyncio
async def test_pagination_total_deterministic_order_and_no_duplicates(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    ids = [await create_job(database_context, source, n) for n in range(1001, 1005)]
    newest = await create_job(database_context, source, 1005, days_seen=1)
    expected = [str(newest), *sorted(map(str, ids))]
    pages: list[str] = []
    for offset in (0, 2, 4, 6):
        response = await client.get(
            "/api/v1/jobs", params={"limit": 2, "offset": offset}
        )
        assert response.status_code == 200
        body = response.json()
        assert (body["total"], body["limit"], body["offset"]) == (5, 2, offset)
        pages.extend(item["id"] for item in body["items"])
    assert pages == expected
    assert len(set(pages)) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["ENGINEER", "manILA", "1001", "  engineer  "])
async def test_search_title_location_external_id(
    database_context: DatabaseContext, client: httpx.AsyncClient, query: str
) -> None:
    source = await create_source(database_context.session_factory)
    expected = await create_job(database_context, source, 1001, location="Manila")
    await create_job(
        database_context, source, 1002, title="Designer", location="Berlin"
    )
    body = (await client.get("/api/v1/jobs", params={"q": query})).json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [str(expected)]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["%", "_", "/", "' OR 1=1 --"])
async def test_search_literal_wildcards_and_bound_parameters(
    database_context: DatabaseContext, client: httpx.AsyncClient, query: str
) -> None:
    source = await create_source(database_context.session_factory)
    expected = await create_job(
        database_context, source, 1001, title=f"Literal {query}"
    )
    await create_job(database_context, source, 1002)
    response = await client.get("/api/v1/jobs", params={"q": query})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == str(expected)


@pytest.mark.asyncio
async def test_search_current_version_and_combined_filters(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    setup = await create_history(database_context, version_count=2)
    params: dict[str, str | int] = {
        "source_connection_id": str(setup.source.id),
        "lifecycle_status": "observed",
        "q": "Engineer II",
        "limit": 1,
    }
    assert (await client.get("/api/v1/jobs", params=params)).json()["total"] == 1
    params["q"] = setup.versions[0].title
    assert (await client.get("/api/v1/jobs", params=params)).json()["total"] == 0
    params["q"] = "   "
    assert (await client.get("/api/v1/jobs", params=params)).json()["total"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 2147483648},
        {"limit": "no"},
        {"lifecycle_status": "closed"},
        {"source_connection_id": "invalid"},
        {"q": "x" * 201},
    ],
)
async def test_invalid_query_422(
    client: httpx.AsyncClient, params: dict[str, str | int]
) -> None:
    assert (await client.get("/api/v1/jobs", params=params)).status_code == 422


@pytest.mark.asyncio
async def test_missing_version_invariant_even_outside_page_and_search(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    await create_job(database_context, source, 1001)
    await create_lifecycle_job(database_context, source, "missing-version")
    response = await client.get(
        "/api/v1/jobs",
        params={"offset": 100, "q": "engineer"},
        headers={"X-Request-ID": "jobs-list-request"},
    )
    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "CURRENT_JOB_VERSION_MISSING",
        "message": "The jobs' current canonical versions are inconsistent.",
        "request_id": "jobs-list-request",
    }
    good_source = await create_source(database_context.session_factory)
    await create_job(database_context, good_source, 1002)
    response = await client.get(
        "/api/v1/jobs", params={"source_connection_id": str(good_source.id)}
    )
    assert response.status_code == 200 and response.json()["total"] == 1


@pytest.mark.asyncio
async def test_constant_selects_for_full_page(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    for number in range(1001, 1026):
        await create_job(database_context, source, number)
    statements: list[str] = []

    def record_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = database_context.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        response = await client.get("/api/v1/jobs")
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 25
    assert len(statements) == 3  # Invariant check, filtered count, joined page.
    assert all("description" not in statement for statement in statements)
