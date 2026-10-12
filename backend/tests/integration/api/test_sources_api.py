from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, select

from app.api.dependencies import (
    get_pipeline_run_query_service,
    get_source_query_service,
)
from app.companies.models import Company
from app.config import get_settings
from app.main import create_app
from app.pipeline_runs.models import PipelineRun
from app.pipeline_runs.query_service import PipelineRunQueryService
from app.sources.models import SourceConnection
from app.sources.query_service import SourceQueryService
from tests.database_counts import capture_table_counts
from tests.test_changed_job_persistence import (
    FIRST_OBSERVED_AT,
    SECOND_OBSERVED_AT,
    DatabaseContext,
    create_source,
)
from tests.test_changed_job_persistence import database_context as database_context


@pytest_asyncio.fixture
async def client(database_context: DatabaseContext) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(get_settings())
    source_service = SourceQueryService(database_context.session_factory)
    run_service = PipelineRunQueryService(database_context.session_factory)
    app.dependency_overrides[get_source_query_service] = lambda: source_service
    app.dependency_overrides[get_pipeline_run_query_service] = lambda: run_service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        yield api


async def configure_source(
    context: DatabaseContext, *, name: str, active: bool = True
) -> SourceConnection:
    source = await create_source(context.session_factory)
    async with context.session_factory.begin() as session:
        company = await session.get(Company, source.company_id)
        stored = await session.get(SourceConnection, source.id)
        assert company is not None and stored is not None
        company.name = name
        stored.is_active = active
    return source


async def create_run(
    context: DatabaseContext,
    source: SourceConnection,
    *,
    status: str = "completed",
    days: int = 0,
) -> PipelineRun:
    async with context.session_factory.begin() as session:
        run = PipelineRun(
            source_connection_id=source.id,
            status=status,
            started_at=FIRST_OBSERVED_AT + timedelta(days=days),
            completed_at=FIRST_OBSERVED_AT + timedelta(days=days),
            records_fetched=3,
            records_valid=2,
            records_quarantined=1,
            jobs_new=1,
            jobs_changed=1,
        )
        session.add(run)
        await session.flush()
        return run


@pytest.mark.asyncio
async def test_empty_default_source_list(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/sources")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 25, "offset": 0}


@pytest.mark.asyncio
async def test_safe_company_fields_and_configuration_exclusion(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await configure_source(database_context, name="Acme")
    async with database_context.session_factory.begin() as session:
        company = await session.get(Company, source.company_id)
        stored = await session.get(SourceConnection, source.id)
        assert company is not None and stored is not None
        company.domain = "acme.example"
        company.careers_url = "https://acme.example/careers"
        stored.configuration = {"credentials": "DO_NOT_EXPOSE_SECRET"}
        stored.external_account_key = "DO_NOT_EXPOSE_ACCOUNT_KEY"
    listing = await client.get("/api/v1/sources")
    detail = await client.get(f"/api/v1/sources/{source.id}")
    assert listing.status_code == detail.status_code == 200
    body = detail.json()
    assert listing.json()["items"] == [body]
    assert body["company"] == {
        "id": str(source.company_id),
        "name": "Acme",
        "domain": "acme.example",
        "careers_url": "https://acme.example/careers",
    }
    assert set(body) == {
        "id",
        "company_id",
        "company",
        "provider",
        "is_active",
        "last_attempted_sync_at",
        "last_successful_sync_at",
        "latest_run",
    }
    assert body["latest_run"] is None
    assert body["last_attempted_sync_at"] is None
    assert body["last_successful_sync_at"] is None
    for response in (listing, detail):
        for excluded in (
            "configuration",
            "credentials",
            "DO_NOT_EXPOSE_SECRET",
            "external_account_key",
            "DO_NOT_EXPOSE_ACCOUNT_KEY",
        ):
            assert excluded not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("active", [True, False])
async def test_active_and_provider_filters_before_pagination(
    database_context: DatabaseContext, client: httpx.AsyncClient, active: bool
) -> None:
    wanted = await configure_source(database_context, name="Z wanted", active=active)
    await configure_source(database_context, name="A other", active=not active)
    response = await client.get(
        "/api/v1/sources",
        params={
            "is_active": str(active).lower(),
            "provider": "greenhouse",
            "limit": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1 and body["items"][0]["id"] == str(wanted.id)
    assert body["items"][0]["is_active"] is active
    assert (
        await client.get("/api/v1/sources", params={"provider": "greenhouse"})
    ).json()["total"] == 2


@pytest.mark.asyncio
async def test_latest_failed_run_preserves_active_state_and_older_success(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await configure_source(database_context, name="Acme")
    await create_run(database_context, source, days=0)
    latest = await create_run(database_context, source, status="failed", days=3)
    async with database_context.session_factory.begin() as session:
        stored = await session.get(SourceConnection, source.id)
        assert stored is not None
        stored.last_attempted_sync_at = SECOND_OBSERVED_AT
        stored.last_successful_sync_at = FIRST_OBSERVED_AT
    listing = (await client.get("/api/v1/sources")).json()
    detail = (await client.get(f"/api/v1/sources/{source.id}")).json()
    assert listing["items"] == [detail]
    assert detail["is_active"] is True
    assert detail["latest_run"]["id"] == str(latest.id)
    assert detail["latest_run"]["status"] == "failed"
    assert detail["last_attempted_sync_at"] != detail["last_successful_sync_at"]
    assert detail["latest_run"]["records_fetched"] == 3
    assert detail["latest_run"]["records_quarantined"] == 1
    assert detail["latest_run"]["jobs_changed"] == 1


@pytest.mark.asyncio
async def test_latest_run_ties_are_deterministic_and_isolated_per_source(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source_a = await configure_source(database_context, name="Acme")
    source_b = await configure_source(database_context, name="Beacon")
    run_a1 = await create_run(database_context, source_a)
    run_a2 = await create_run(database_context, source_a)
    run_b = await create_run(database_context, source_b, days=5)
    expected = max(run_a1.id, run_a2.id)
    body = (await client.get("/api/v1/sources")).json()
    assert [item["latest_run"]["id"] for item in body["items"]] == [
        str(expected),
        str(run_b.id),
    ]
    assert (await client.get(f"/api/v1/sources/{source_a.id}")).json()["latest_run"][
        "id"
    ] == str(expected)


@pytest.mark.asyncio
async def test_company_order_id_ties_and_filtered_pagination_total(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    await configure_source(database_context, name="A excluded", active=False)
    ids = [
        (await configure_source(database_context, name="Beacon")).id for _ in range(3)
    ]
    acme = await configure_source(database_context, name="Acme")
    expected = [str(acme.id), *sorted(map(str, ids))]
    observed: list[str] = []
    for offset in (0, 2, 4):
        body = (
            await client.get(
                "/api/v1/sources",
                params={
                    "is_active": "true",
                    "limit": 2,
                    "offset": offset,
                },
            )
        ).json()
        assert (body["total"], body["limit"], body["offset"]) == (4, 2, offset)
        observed.extend(item["id"] for item in body["items"])
    assert observed == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 2147483648},
        {"is_active": "invalid"},
        {"provider": "lever"},
        {"limit": "invalid"},
    ],
)
async def test_invalid_source_list_query(
    client: httpx.AsyncClient, params: dict[str, str | int]
) -> None:
    assert (await client.get("/api/v1/sources", params=params)).status_code == 422


@pytest.mark.asyncio
async def test_unknown_source_detail_and_invalid_uuid(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        f"/api/v1/sources/{uuid4()}", headers={"X-Request-ID": "source-request"}
    )
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "SOURCE_CONNECTION_NOT_FOUND",
        "message": "The source connection was not found.",
        "request_id": "source-request",
    }
    assert (await client.get("/api/v1/sources/invalid")).status_code == 422


@pytest.mark.asyncio
async def test_source_reads_do_not_mutate_sources_or_runs(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await configure_source(database_context, name="Acme")
    await create_run(database_context, source)
    connection = database_context.connection
    counts = await capture_table_counts(connection)
    source_values = (
        (await connection.execute(select(SourceConnection.__table__))).mappings().all()
    )
    run_values = (
        (await connection.execute(select(PipelineRun.__table__))).mappings().all()
    )
    await client.get("/api/v1/sources")
    await client.get(f"/api/v1/sources/{source.id}")
    await client.get(
        "/api/v1/pipeline-runs", params={"source_connection_id": str(source.id)}
    )
    assert await capture_table_counts(connection) == counts
    assert (
        await connection.execute(select(SourceConnection.__table__))
    ).mappings().all() == source_values
    assert (
        await connection.execute(select(PipelineRun.__table__))
    ).mappings().all() == run_values


@pytest.mark.asyncio
async def test_bounded_source_page_uses_two_selects_and_detail_one(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    sources = [
        await configure_source(database_context, name=f"Source {n:02}")
        for n in range(26)
    ]
    for source in sources:
        await create_run(database_context, source)
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
        response = await client.get("/api/v1/sources")
        assert response.status_code == 200
        assert response.json()["total"] == 26 and len(response.json()["items"]) == 25
        assert len(statements) == 2
        assert all(
            "configuration" not in statement and "external_account_key" not in statement
            for statement in statements
        )
        statements.clear()
        response = await client.get(f"/api/v1/sources/{sources[0].id}")
        assert response.status_code == 200 and len(statements) == 1
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)


@pytest.mark.asyncio
async def test_source_run_filter_precedes_pagination_and_retains_global_default(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source_a = await configure_source(database_context, name="Acme")
    source_b = await configure_source(database_context, name="Beacon")
    run_a1 = await create_run(database_context, source_a, days=1)
    run_a2 = await create_run(database_context, source_a, days=2)
    run_a3 = await create_run(database_context, source_a, days=2)
    run_b = await create_run(database_context, source_b, days=5)
    expected = [*sorted([str(run_a2.id), str(run_a3.id)], reverse=True), str(run_a1.id)]
    observed: list[str] = []
    for offset in (0, 1, 2, 3):
        body = (
            await client.get(
                "/api/v1/pipeline-runs",
                params={
                    "source_connection_id": str(source_a.id),
                    "limit": 1,
                    "offset": offset,
                },
            )
        ).json()
        assert (body["limit"], body["offset"]) == (1, offset)
        assert all(
            item["source_connection_id"] == str(source_a.id) for item in body["items"]
        )
        observed.extend(item["id"] for item in body["items"])
    assert observed == expected
    global_body = (await client.get("/api/v1/pipeline-runs")).json()
    assert global_body["limit"] == 50 and global_body["items"][0]["id"] == str(run_b.id)
    assert len(global_body["items"]) == 4
    assert (
        await client.get(
            "/api/v1/pipeline-runs",
            params={
                "source_connection_id": str(uuid4()),
            },
        )
    ).json()["items"] == []
    assert (
        await client.get(
            "/api/v1/pipeline-runs",
            params={
                "source_connection_id": "invalid",
            },
        )
    ).status_code == 422


@pytest.mark.asyncio
async def test_run_status_and_source_filters_before_pagination(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await configure_source(database_context, name="Acme")
    other = await configure_source(database_context, name="Beacon")
    await create_run(database_context, source, status="completed", days=5)
    await create_run(database_context, other, status="failed", days=6)
    first = await create_run(database_context, source, status="failed", days=2)
    second = await create_run(database_context, source, status="failed", days=2)
    expected = sorted([str(first.id), str(second.id)], reverse=True)
    observed: list[str] = []
    counts = await capture_table_counts(database_context.connection)
    for offset in (0, 1, 2):
        body = (
            await client.get(
                "/api/v1/pipeline-runs",
                params={
                    "source_connection_id": str(source.id),
                    "status": "failed",
                    "limit": 1,
                    "offset": offset,
                },
            )
        ).json()
        assert all(item["status"] == "failed" for item in body["items"])
        observed.extend(item["id"] for item in body["items"])
    assert observed == expected
    assert await capture_table_counts(database_context.connection) == counts
    for status in ("pending", "running", "completed_with_errors"):
        assert (
            await client.get("/api/v1/pipeline-runs", params={"status": status})
        ).json()["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"status": "unknown"}, {"offset": 2147483648}])
async def test_invalid_run_filters(
    client: httpx.AsyncClient, params: dict[str, str | int]
) -> None:
    assert (await client.get("/api/v1/pipeline-runs", params=params)).status_code == 422
