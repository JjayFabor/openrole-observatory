from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, select

from app.api.dependencies import get_quarantine_query_service
from app.config import get_settings
from app.main import create_app
from app.quarantine.models import QuarantineRecord, QuarantineStatus
from app.quarantine.query_service import QuarantineQueryService
from app.sources.models import SourceConnection
from tests.database_counts import capture_table_counts
from tests.test_changed_job_persistence import DatabaseContext, create_source
from tests.test_changed_job_persistence import database_context as database_context
from tests.test_quarantine_records import (
    OBSERVED_AT,
    build_quarantine_record,
    create_run_and_snapshot,
)


@pytest_asyncio.fixture
async def client(database_context: DatabaseContext) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(get_settings())
    service = QuarantineQueryService(database_context.session_factory)
    app.dependency_overrides[get_quarantine_query_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        yield api


async def create_record(
    context: DatabaseContext,
    source: SourceConnection,
    *,
    status: QuarantineStatus = QuarantineStatus.OPEN,
    category: str = "record_validation_failed",
    external_id: str | None = "1001",
    days: int = 0,
) -> QuarantineRecord:
    async with context.session_factory.begin() as session:
        source = await session.merge(source)
        run, snapshot = await create_run_and_snapshot(session, source)
        record = build_quarantine_record(
            source, run, snapshot, external_job_id=external_id, error_category=category
        )
        record.created_at = OBSERVED_AT + timedelta(days=days)
        record.status = status.value
        record.resolved_at = (
            OBSERVED_AT if status == QuarantineStatus.RESOLVED else None
        )
        session.add(record)
        await session.flush()
        return record


@pytest.mark.asyncio
async def test_empty_default_list(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/quarantine")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 25, "offset": 0}


@pytest.mark.asyncio
async def test_safe_list_and_detail_with_nullable_identity_and_json(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    record = await create_record(database_context, source, external_id=None)
    details: dict[str, object] = {
        "nested": [None, False, 0, {"message": "<script>bad()</script>"}]
    }
    async with database_context.session_factory.begin() as session:
        stored = await session.get(QuarantineRecord, record.id)
        connection = await session.get(SourceConnection, source.id)
        assert stored is not None and connection is not None
        stored.raw_record_locator = None
        stored.error_code = None
        stored.error_details = details
        connection.configuration = {"secret": "must-not-appear"}
    listing = await client.get("/api/v1/quarantine")
    detail = await client.get(f"/api/v1/quarantine/{record.id}")
    assert listing.status_code == detail.status_code == 200
    item = listing.json()["items"][0]
    assert detail.json() == {**item, "error_details": details}
    assert item["source"] == {
        "provider": "greenhouse",
        "company_name": source.company.name,
    }
    assert item["id"] == str(record.id)
    assert item["pipeline_run_id"] == str(record.pipeline_run_id)
    assert item["source_connection_id"] == str(source.id)
    assert item["raw_snapshot_id"] == str(record.raw_snapshot_id)
    assert item["external_job_id"] is None
    assert item["raw_record_locator"] is None and item["error_code"] is None
    assert item["resolved_at"] is None and item["status"] == "open"
    assert set(item) == {
        "id",
        "pipeline_run_id",
        "source_connection_id",
        "raw_snapshot_id",
        "external_job_id",
        "raw_record_locator",
        "error_category",
        "error_code",
        "error_message",
        "status",
        "created_at",
        "resolved_at",
        "source",
    }
    for response in (listing, detail):
        for excluded in (
            "must-not-appear",
            "r2_object_key",
            "configuration",
            "bronze/test",
        ):
            assert excluded not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("status", list(QuarantineStatus))
async def test_status_source_run_category_filters(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
    status: QuarantineStatus,
) -> None:
    source_a = await create_source(database_context.session_factory)
    source_b = await create_source(database_context.session_factory)
    wanted = await create_record(database_context, source_a, status=status)
    other = (
        QuarantineStatus.RESOLVED
        if status == QuarantineStatus.OPEN
        else QuarantineStatus.OPEN
    )
    await create_record(
        database_context, source_a, status=other, category="duplicate_source_identifier"
    )
    await create_record(
        database_context,
        source_b,
        status=status,
        category="duplicate_source_identifier",
    )
    for params, expected in (
        ({"status": status.value}, 2),
        ({"source_connection_id": str(source_a.id)}, 2),
        ({"pipeline_run_id": str(wanted.pipeline_run_id)}, 1),
        ({"error_category": "duplicate_source_identifier"}, 2),
        (
            {
                "status": status.value,
                "source_connection_id": str(source_a.id),
                "pipeline_run_id": str(wanted.pipeline_run_id),
                "error_category": "  record_validation_failed  ",
            },
            1,
        ),
    ):
        body = (await client.get("/api/v1/quarantine", params=params)).json()
        assert body["total"] == expected
        if expected == 1:
            assert body["items"][0]["id"] == str(wanted.id)
    body = (await client.get(f"/api/v1/quarantine/{wanted.id}")).json()
    assert body["status"] == status.value
    assert (body["resolved_at"] is not None) == (status == QuarantineStatus.RESOLVED)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["source_connection_id", "pipeline_run_id"])
async def test_unknown_scope_is_empty(client: httpx.AsyncClient, name: str) -> None:
    body = (await client.get("/api/v1/quarantine", params={name: str(uuid4())})).json()
    assert body["items"] == [] and body["total"] == 0


@pytest.mark.asyncio
async def test_category_literal_and_blank(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    record = await create_record(database_context, source, category="custom_%' OR 1=1")
    await create_record(database_context, source)
    body = (
        await client.get(
            "/api/v1/quarantine", params={"error_category": "custom_%' OR 1=1"}
        )
    ).json()
    assert body["total"] == 1 and body["items"][0]["id"] == str(record.id)
    assert (
        await client.get("/api/v1/quarantine", params={"error_category": "   "})
    ).json()["total"] == 2


@pytest.mark.asyncio
async def test_pagination_filtered_total_stable_order(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    ids = [(await create_record(database_context, source)).id for _ in range(4)]
    newest = await create_record(database_context, source, days=1)
    await create_record(database_context, source, category="normalization_failed")
    expected = [str(newest.id), *sorted(map(str, ids), reverse=True)]
    observed: list[str] = []
    for offset in (0, 2, 4, 6):
        body = (
            await client.get(
                "/api/v1/quarantine",
                params={
                    "limit": 2,
                    "offset": offset,
                    "error_category": "record_validation_failed",
                },
            )
        ).json()
        assert (body["total"], body["limit"], body["offset"]) == (5, 2, offset)
        observed.extend(item["id"] for item in body["items"])
    assert observed == expected and len(set(observed)) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 2147483648},
        {"limit": "invalid"},
        {"status": "ignored"},
        {"pipeline_run_id": "invalid"},
        {"source_connection_id": "invalid"},
        {"error_category": "x" * 101},
    ],
)
async def test_invalid_parameters(
    client: httpx.AsyncClient, params: dict[str, str | int]
) -> None:
    assert (await client.get("/api/v1/quarantine", params=params)).status_code == 422


@pytest.mark.asyncio
async def test_unknown_and_invalid_detail(client: httpx.AsyncClient) -> None:
    response = await client.get(
        f"/api/v1/quarantine/{uuid4()}", headers={"X-Request-ID": "quarantine-request"}
    )
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "QUARANTINE_RECORD_NOT_FOUND",
        "message": "The quarantined record was not found.",
        "request_id": "quarantine-request",
    }
    assert (await client.get("/api/v1/quarantine/invalid")).status_code == 422


@pytest.mark.asyncio
async def test_read_only(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    record = await create_record(database_context, source)
    connection = database_context.connection
    before_counts = await capture_table_counts(connection)
    before = (
        (await connection.execute(select(QuarantineRecord.__table__))).mappings().all()
    )
    await client.get("/api/v1/quarantine")
    await client.get(f"/api/v1/quarantine/{record.id}")
    await client.get(f"/api/v1/quarantine/{uuid4()}")
    assert await capture_table_counts(connection) == before_counts
    assert (
        await connection.execute(select(QuarantineRecord.__table__))
    ).mappings().all() == before
    for method in ("post", "patch", "delete"):
        assert (
            await client.request(method, f"/api/v1/quarantine/{record.id}")
        ).status_code == 405


@pytest.mark.asyncio
async def test_bounded_constant_selects(
    database_context: DatabaseContext, client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    records = [await create_record(database_context, source) for _ in range(26)]
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
        response = await client.get("/api/v1/quarantine")
        assert len(response.json()["items"]) == 25 and response.json()["total"] == 26
        assert len(statements) == 2
        assert all("error_details" not in statement for statement in statements)
        statements.clear()
        response = await client.get(f"/api/v1/quarantine/{records[0].id}")
        assert response.status_code == 200 and len(statements) == 1
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)
