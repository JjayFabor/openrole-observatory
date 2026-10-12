from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, select

from app.api.dependencies import get_public_job_query_service
from app.companies.models import Company
from app.config import get_settings
from app.jobs.models import Job, JobLifecycleStatus, JobVersion
from app.jobs.public_query_service import PublicJobQueryService
from app.jobs.public_read_schemas import PublicEmploymentFilter, PublicWorkplaceFilter
from app.jobs.schemas import CanonicalJobInput
from app.jobs.service import NewJobPersistenceService, PersistNewJobCommand
from app.main import create_app
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.models import SourceConnection
from tests.integration.api.test_history_api import create_history, database_contents
from tests.integration.lifecycle.helpers import create_lifecycle_job
from tests.test_changed_job_persistence import (
    FIRST_OBSERVED_AT,
    DatabaseContext,
    create_observation,
    create_source,
    fixture_job,
)
from tests.test_changed_job_persistence import database_context as database_context

PUBLIC_JOBS = "/api/v1/public/jobs"


@pytest_asyncio.fixture
async def client(database_context: DatabaseContext) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(get_settings())
    service = PublicJobQueryService(database_context.session_factory)
    app.dependency_overrides[get_public_job_query_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        yield api


async def create_job(
    context: DatabaseContext,
    source: SourceConnection,
    external_id: int,
    *,
    title: str = "Backend Engineer",
    location: str | None = None,
    status: JobLifecycleStatus = JobLifecycleStatus.OBSERVED,
    days_seen: int = 0,
    canonical: CanonicalJobInput | None = None,
) -> UUID:
    record = fixture_job("jobs_v1.json").model_copy(update={"id": external_id})
    observation = await create_observation(
        context.session_factory, source.id, record, FIRST_OBSERVED_AT
    )
    mapped = (
        canonical.model_copy(update={"external_job_id": str(external_id)})
        if canonical is not None
        else map_greenhouse_job(record).model_copy(
            update={"title": title, "location_text": location}
        )
    )
    result = await NewJobPersistenceService(
        context.session_factory, mapper=lambda _: mapped
    ).create_new_job(PersistNewJobCommand(observation.id, record))
    async with context.session_factory.begin() as session:
        job = await session.get(Job, result.job_id)
        assert job is not None
        job.lifecycle_status = status.value
        job.last_seen_at = FIRST_OBSERVED_AT + timedelta(days=days_seen)
        if status == JobLifecycleStatus.NOT_OBSERVED:
            job.no_longer_observed_at = FIRST_OBSERVED_AT + timedelta(days=10)
    return result.job_id


@pytest.mark.asyncio
async def test_public_jobs_empty_list(client: httpx.AsyncClient) -> None:
    response = await client.get(PUBLIC_JOBS)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 25, "offset": 0}


@pytest.mark.asyncio
async def test_public_jobs_default_eligibility_and_freshness_order(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    ids = [
        await create_job(database_context, source, 1001 + day, days_seen=day)
        for day in range(3)
    ]
    await create_job(
        database_context, source, 1004, status=JobLifecycleStatus.NOT_OBSERVED
    )
    response = await client.get(PUBLIC_JOBS)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == list(map(str, reversed(ids)))
    assert all(item["first_seen_at"] and item["last_seen_at"] for item in body["items"])


@pytest.mark.asyncio
async def test_public_jobs_pagination_total_and_tie_order(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    ids = [await create_job(database_context, source, n) for n in range(1001, 1005)]
    newest = await create_job(database_context, source, 1005, days_seen=1)
    expected = [str(newest), *sorted(map(str, ids))]
    actual: list[str] = []
    for offset in (0, 2, 4, 6):
        response = await client.get(PUBLIC_JOBS, params={"limit": 2, "offset": offset})
        assert response.status_code == 200
        body = response.json()
        assert (body["total"], body["limit"], body["offset"]) == (5, 2, offset)
        actual.extend(item["id"] for item in body["items"])
    assert actual == expected
    assert len(set(actual)) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["BACKEND", "  backend  ", "employer", "manILA"])
async def test_public_jobs_search_title_company_location(
    database_context: DatabaseContext, client: httpx.AsyncClient, query: str
) -> None:
    source = await create_source(database_context.session_factory)
    other_source = await create_source(database_context.session_factory)
    async with database_context.session_factory.begin() as session:
        source.company.name = "Distinct Employer"
        session.add(source.company)
    expected = await create_job(database_context, source, 1001, location="Manila")
    await create_job(
        database_context,
        source,
        1002,
        location="Manila",
        status=JobLifecycleStatus.NOT_OBSERVED,
    )
    await create_job(
        database_context, other_source, 1003, title="Designer", location="Berlin"
    )
    response = await client.get(PUBLIC_JOBS, params={"q": query})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [item["id"] for item in response.json()["items"]] == [str(expected)]


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["100%", "under_score", "slash/", "x' OR 1=1 --"])
async def test_public_jobs_search_and_location_are_literal_parameterized_text(
    database_context: DatabaseContext, client: httpx.AsyncClient, text: str
) -> None:
    source = await create_source(database_context.session_factory)
    expected = await create_job(
        database_context, source, 1001, title=text, location=text
    )
    await create_job(database_context, source, 1002, title="Other", location="Other")
    for param in ("q", "location"):
        response = await client.get(PUBLIC_JOBS, params={param: text})
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert [item["id"] for item in response.json()["items"]] == [str(expected)]


@pytest.mark.asyncio
async def test_public_jobs_search_does_not_use_internal_external_id_or_description(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    canonical = map_greenhouse_job(fixture_job("jobs_v1.json")).model_copy(
        update={"description": "private-search-token", "location_text": None}
    )
    await create_job(database_context, source, 1234567, canonical=canonical)
    for query in ("1234567", "private-search-token", "no-match"):
        body = (await client.get(PUBLIC_JOBS, params={"q": query})).json()
        assert body["total"] == 0
        assert body["items"] == []
    for query in ("", "   "):
        assert (await client.get(PUBLIC_JOBS, params={"q": query})).json()["total"] == 1


@pytest.mark.asyncio
async def test_public_jobs_filters_intersect_and_totals_use_same_filters(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    base = map_greenhouse_job(fixture_job("jobs_v1.json")).model_copy(
        update={
            "title": "Backend Engineer",
            "location_text": "Manila, Philippines",
            "workplace_type": "remote",
            "employment_type": "full_time",
        }
    )
    expected = await create_job(database_context, source, 1001, canonical=base)
    for n, update in enumerate(
        [
            {"workplace_type": "hybrid"},
            {"employment_type": "part_time"},
            {"location_text": "Berlin"},
            {"title": "Designer"},
        ],
        start=1002,
    ):
        await create_job(
            database_context, source, n, canonical=base.model_copy(update=update)
        )
    for params, count in [
        ({"workplace_type": "remote"}, 4),
        ({"employment_type": "full_time"}, 4),
        ({"location": "  PHILIPPINES "}, 4),
        (
            {
                "q": "backend",
                "location": "Manila",
                "workplace_type": "remote",
                "employment_type": "full_time",
            },
            1,
        ),
        ({"location": "no-such-place"}, 0),
        ({"location": "   "}, 5),
    ]:
        response = await client.get(PUBLIC_JOBS, params={**params, "limit": 1})
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == count
        if count == 1:
            assert body["items"][0]["id"] == str(expected)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [("workplace_type", value.value) for value in PublicWorkplaceFilter]
    + [("employment_type", value.value) for value in PublicEmploymentFilter],
)
async def test_public_jobs_each_supported_exact_filter(
    database_context: DatabaseContext, client: httpx.AsyncClient, field: str, value: str
) -> None:
    source = await create_source(database_context.session_factory)
    canonical = map_greenhouse_job(fixture_job("jobs_v1.json")).model_copy(
        update={field: value}
    )
    expected = await create_job(database_context, source, 1001, canonical=canonical)
    await create_job(database_context, source, 1002)
    response = await client.get(PUBLIC_JOBS, params={field: value})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [item["id"] for item in response.json()["items"]] == [str(expected)]


@pytest.mark.asyncio
async def test_public_jobs_large_salary_remains_exact(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    canonical = map_greenhouse_job(fixture_job("jobs_v1.json")).model_copy(
        update={"salary_max": Decimal("123456789012.34")}
    )
    job_id = await create_job(database_context, source, 1001, canonical=canonical)
    listing = (await client.get(PUBLIC_JOBS)).json()["items"][0]
    detail = (await client.get(f"{PUBLIC_JOBS}/{job_id}")).json()
    assert listing["salary_max"] == detail["salary_max"] == "123456789012.34"
    assert listing["salary_min"] is detail["salary_min"] is None
    assert detail["salary_currency"] is detail["salary_period"] is None


@pytest.mark.asyncio
async def test_public_jobs_current_version_salary_and_field_safety(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    setup = await create_history(database_context, version_count=2)
    async with database_context.session_factory.begin() as session:
        source = await session.get(SourceConnection, setup.source.id)
        assert source is not None
        source.configuration = {"credential": "source-secret-marker"}
        company = await session.get(Company, source.company_id)
        assert company is not None
        company.domain = "example.com"
        company.careers_url = "https://example.com/careers"
        current = await session.get(JobVersion, setup.versions[-1].id)
        assert current is not None
        current.canonical_metadata = {"internal": "metadata-secret-marker"}
    listing = await client.get(PUBLIC_JOBS)
    detail = await client.get(f"{PUBLIC_JOBS}/{setup.job_id}")
    assert listing.status_code == detail.status_code == 200
    item = listing.json()["items"][0]
    body = detail.json()
    assert item["title"] == body["title"] == "Engineer II"
    assert item["salary_min"] == body["salary_min"] == "65000.01"
    assert item["salary_max"] == body["salary_max"] == "90000.99"
    assert body["salary_currency"] == "USD"
    assert body["salary_period"] == "year"
    assert body["description"] == "<p>Updated description</p>"
    assert body["source_url"] == setup.versions[-1].source_url
    assert body["company"] == {
        "name": setup.source.company.name,
        "domain": "example.com",
        "careers_url": "https://example.com/careers",
    }
    assert item["company"] == {
        "name": setup.source.company.name,
        "domain": "example.com",
    }
    assert item["source"] == body["source"] == {"provider": "greenhouse"}
    assert [body[k] for k in ("city", "region", "country_code")] == [
        "Manila",
        "Metro Manila",
        "PH",
    ]
    expected_list_keys = {
        "id",
        "title",
        "company",
        "location_text",
        "city",
        "region",
        "country_code",
        "workplace_type",
        "employment_type",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_period",
        "first_seen_at",
        "last_seen_at",
        "source",
    }
    assert set(item) == expected_list_keys
    assert set(body) == expected_list_keys | {
        "description",
        "source_url",
        "lifecycle_status",
        "absence_first_detected_at",
        "no_longer_observed_at",
        "reappeared_at",
    }
    for response in (listing, detail):
        for forbidden in (
            "external_job_id",
            "source_connection_id",
            "company_id",
            "version_id",
            "current_version",
            "source_observation_id",
            "pipeline_run_id",
            "raw_snapshot_id",
            "content_hash",
            "canonical_metadata",
            "configuration",
            "external_account_key",
            "consecutive_absent_runs",
            "source-secret-marker",
            "metadata-secret-marker",
            str(setup.source.id),
            str(setup.source.company_id),
            str(setup.versions[-1].id),
        ):
            assert forbidden not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("status", list(JobLifecycleStatus))
async def test_public_jobs_detail_preserves_lifecycle_facts(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
    status: JobLifecycleStatus,
) -> None:
    source = await create_source(database_context.session_factory)
    job_id = await create_job(database_context, source, 1001, status=status)
    async with database_context.session_factory.begin() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        job.absence_first_detected_at = FIRST_OBSERVED_AT + timedelta(days=1)
    response = await client.get(f"{PUBLIC_JOBS}/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["lifecycle_status"] == status.value
    assert body["last_seen_at"].endswith("Z") or body["last_seen_at"].endswith("+00:00")
    assert body["absence_first_detected_at"] is not None
    if status == JobLifecycleStatus.NOT_OBSERVED:
        assert body["no_longer_observed_at"] is not None
        assert (await client.get(PUBLIC_JOBS)).json()["total"] == 0
    else:
        assert body["no_longer_observed_at"] is None
        assert (await client.get(PUBLIC_JOBS)).json()["total"] == 1


@pytest.mark.asyncio
async def test_public_jobs_reappeared_observed_job_is_discoverable(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    job_id = await create_job(database_context, source, 1001, days_seen=5)
    async with database_context.session_factory.begin() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        job.reappeared_at = FIRST_OBSERVED_AT + timedelta(days=5)
        job.no_longer_observed_at = FIRST_OBSERVED_AT + timedelta(days=3)
    body = (await client.get(f"{PUBLIC_JOBS}/{job_id}")).json()
    assert body["lifecycle_status"] == "observed"
    assert body["reappeared_at"] is not None
    assert body["no_longer_observed_at"] is not None
    assert (await client.get(PUBLIC_JOBS)).json()["items"][0]["id"] == str(job_id)


@pytest.mark.asyncio
async def test_public_jobs_inactive_source_excluded_but_detail_retained(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    job_id = await create_job(database_context, source, 1001)
    async with database_context.session_factory.begin() as session:
        stored = await session.get(SourceConnection, source.id)
        assert stored is not None
        stored.is_active = False
    assert (await client.get(PUBLIC_JOBS)).json()["total"] == 0
    response = await client.get(f"{PUBLIC_JOBS}/{job_id}")
    assert response.status_code == 200
    assert response.json()["lifecycle_status"] == "observed"


@pytest.mark.asyncio
async def test_public_jobs_optional_fields_stay_null_and_description_is_not_transformed(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    canonical = map_greenhouse_job(fixture_job("jobs_v1.json")).model_copy(
        update={
            "description": '<p onclick="bad()">Source</p><script>bad()</script>',
            "location_text": None,
        }
    )
    job_id = await create_job(database_context, source, 1001, canonical=canonical)
    listing = (await client.get(PUBLIC_JOBS)).json()["items"][0]
    detail = (await client.get(f"{PUBLIC_JOBS}/{job_id}")).json()
    for key in (
        "location_text",
        "city",
        "region",
        "country_code",
        "workplace_type",
        "employment_type",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_period",
    ):
        assert listing[key] is detail[key] is None
    assert detail["description"] == canonical.description
    assert detail["company"]["domain"] is detail["company"]["careers_url"] is None


@pytest.mark.asyncio
async def test_public_jobs_unknown_detail_and_invalid_uuid(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        f"{PUBLIC_JOBS}/{uuid4()}", headers={"X-Request-ID": "public-missing"}
    )
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "JOB_NOT_FOUND",
        "message": "The job was not found.",
        "request_id": "public-missing",
    }
    assert (await client.get(f"{PUBLIC_JOBS}/invalid")).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"limit": "0"},
        {"limit": "101"},
        {"offset": "-1"},
        {"offset": "2147483648"},
        {"limit": "many"},
        {"offset": "next"},
        {"q": "x" * 201},
        {"location": "x" * 201},
        {"workplace_type": "spaceship"},
        {"employment_type": "invented"},
    ],
)
async def test_public_jobs_query_validation(
    client: httpx.AsyncClient, params: dict[str, str]
) -> None:
    response = await client.get(PUBLIC_JOBS, params=params)
    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.asyncio
async def test_public_jobs_missing_current_version_fails_safely_before_content_search(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = await create_source(database_context.session_factory)
    job = await create_lifecycle_job(database_context, source, "missing-current")
    for path in (PUBLIC_JOBS, f"{PUBLIC_JOBS}/{job.id}", f"{PUBLIC_JOBS}?q=no-match"):
        response = await client.get(path, headers={"X-Request-ID": "public-invariant"})
        assert response.status_code == 500
        assert response.json()["error"] == {
            "code": "PUBLIC_JOBS_UNAVAILABLE",
            "message": "Job listings are temporarily unavailable.",
            "request_id": "public-invariant",
        }
        assert str(job.id) not in response.text
        assert "CURRENT_JOB_VERSION" not in response.text
    assert "public_job_read_invariant_failed" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_url",
    [
        "javascript:bad()",
        "data:text/html,bad",
        "//example.com/job",
        "https://user:password@example.com/job",
    ],
)
async def test_public_jobs_unsafe_source_url_not_published(
    database_context: DatabaseContext, client: httpx.AsyncClient, source_url: str
) -> None:
    source = await create_source(database_context.session_factory)
    job_id = await create_job(database_context, source, 1001)
    async with database_context.session_factory.begin() as session:
        version = await session.scalar(
            select(JobVersion).where(JobVersion.job_id == job_id)
        )
        assert version is not None
        version.source_url = source_url
    response = await client.get(f"{PUBLIC_JOBS}/{job_id}")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PUBLIC_JOBS_UNAVAILABLE"
    assert source_url not in response.text


@pytest.mark.asyncio
async def test_public_jobs_unsafe_optional_careers_url_is_omitted(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    job_id = await create_job(database_context, source, 1001)
    async with database_context.session_factory.begin() as session:
        source.company.careers_url = "javascript:bad()"
        session.add(source.company)
    response = await client.get(f"{PUBLIC_JOBS}/{job_id}")
    assert response.status_code == 200
    assert response.json()["company"]["careers_url"] is None


@pytest.mark.asyncio
async def test_public_jobs_gets_are_read_only_and_queries_do_not_grow_per_item(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    job_id = await create_job(database_context, source, 1001)
    statements: list[str] = []

    def record_query(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(
        database_context.engine.sync_engine, "before_cursor_execute", record_query
    )
    try:
        assert (await client.get(PUBLIC_JOBS)).status_code == 200
        first_count = len(statements)
        for external_id in (1002, 1003, 1004):
            await create_job(database_context, source, external_id)
        before = await database_contents(database_context)
        statements.clear()
        assert (await client.get(PUBLIC_JOBS)).status_code == 200
        assert len(statements) == first_count
        assert all("description" not in statement for statement in statements)
        assert all(
            "canonical_metadata" not in statement and "configuration" not in statement
            for statement in statements
        )
        statements.clear()
        assert (await client.get(f"{PUBLIC_JOBS}/{job_id}")).status_code == 200
        assert len(statements) == 1
        assert (
            "canonical_metadata" not in statements[0]
            and "configuration" not in statements[0]
        )
        assert await database_contents(database_context) == before
    finally:
        event.remove(
            database_context.engine.sync_engine, "before_cursor_execute", record_query
        )


def test_public_jobs_openapi_only_read_routes_and_public_query_contract() -> None:
    schema = create_app(get_settings()).openapi()
    assert set(schema["paths"][PUBLIC_JOBS]) == {"get"}
    assert set(schema["paths"][f"{PUBLIC_JOBS}/{{job_id}}"]) == {"get"}
    parameters = schema["paths"][PUBLIC_JOBS]["get"]["parameters"]
    assert {p["name"] for p in parameters} == {
        "q",
        "location",
        "workplace_type",
        "employment_type",
        "limit",
        "offset",
    }
    assert schema["components"]["schemas"]["PublicWorkplaceFilter"]["enum"] == [
        "remote",
        "hybrid",
        "onsite",
    ]
