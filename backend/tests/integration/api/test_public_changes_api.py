from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import event, select

from app.jobs.models import Job, JobChangeEvent
from app.jobs.schemas import CanonicalJobInput
from app.jobs.service import (
    ApplyChangedObservationCommand,
    ChangedJobPersistenceService,
)
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.models import SourceConnection
from tests.integration.api.test_history_api import HistorySetup, database_contents
from tests.integration.api.test_public_jobs_api import client as client
from tests.integration.api.test_public_jobs_api import create_job
from tests.test_changed_job_persistence import (
    SECOND_OBSERVED_AT,
    THIRD_OBSERVED_AT,
    DatabaseContext,
    create_observation,
    create_source,
    fixture_job,
    load_versions,
)
from tests.test_changed_job_persistence import database_context as database_context


async def append_public_change(
    context: DatabaseContext,
    source: SourceConnection,
    canonical: CanonicalJobInput,
    observed_at: datetime,
) -> None:
    record = fixture_job("jobs_v1.json")
    observation = await create_observation(
        context.session_factory, source.id, record, observed_at
    )
    await ChangedJobPersistenceService(
        context.session_factory, mapper=lambda _: canonical
    ).apply_changed_observation(ApplyChangedObservationCommand(observation.id, record))


async def create_public_history(
    context: DatabaseContext,
    *,
    version_count: int = 3,
) -> tuple[HistorySetup, CanonicalJobInput]:
    source = await create_source(context.session_factory)
    canonical = map_greenhouse_job(fixture_job("jobs_v1.json")).model_copy(
        update={
            "title": "Backend Engineer",
            "location_text": "Remote",
            "workplace_type": "remote",
            "employment_type": "contract",
            "description": "<p>private historical description before</p>",
            "canonical_metadata": {"provider_debug": "private-metadata-before"},
        }
    )
    job_id = await create_job(context, source, 1001, canonical=canonical)
    if version_count >= 2:
        canonical = canonical.model_copy(
            update={
                "title": "Senior Backend Engineer",
                "location_text": "Berlin, Germany",
                "city": "Berlin",
                "region": "Berlin",
                "country_code": "DE",
                "workplace_type": "hybrid",
                "employment_type": "full_time",
                "description": "<script>private historical description after</script>",
                "salary_min": Decimal("90000.01"),
                "salary_max": Decimal("110000.99"),
                "salary_currency": "USD",
                "salary_period": "year",
                "canonical_metadata": {"provider_debug": "private-metadata-after"},
                "source_url": "https://example.test/updated-source",
            }
        )
        await append_public_change(context, source, canonical, SECOND_OBSERVED_AT)
    if version_count >= 3:
        canonical = canonical.model_copy(
            update={
                "title": "Staff Backend Engineer",
                "salary_min": Decimal("90000.02"),
                "employment_type": None,
                "location_text": None,
                "description": None,
            }
        )
        await append_public_change(context, source, canonical, THIRD_OBSERVED_AT)
    return HistorySetup(
        source, job_id, await load_versions(context.session_factory, job_id)
    ), canonical


def url(job_id: UUID) -> str:
    return f"/api/v1/public/jobs/{job_id}/changes"


@pytest.mark.asyncio
async def test_public_changes_curated_complete_transition_projection(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
) -> None:
    setup, _ = await create_public_history(database_context)
    response = await client.get(url(setup.job_id))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"job_id", "items", "limit"}
    assert body["job_id"] == str(setup.job_id) and body["limit"] == 10
    assert [group["observed_at"] for group in body["items"]] == [
        "2026-10-09T12:00:00Z",
        "2026-10-08T12:00:00Z",
    ]
    latest = {change["field"]: change for change in body["items"][0]["changes"]}
    older = {change["field"]: change for change in body["items"][1]["changes"]}
    assert latest["employment_type"] == {
        "field": "employment_type",
        "change_type": "removed",
        "old_value": "full_time",
        "new_value": None,
    }
    assert latest["location_text"]["new_value"] is None
    assert latest["description"] == {"field": "description", "change_type": "removed"}
    assert older["workplace_type"] == {
        "field": "workplace_type",
        "change_type": "modified",
        "old_value": "remote",
        "new_value": "hybrid",
    }
    assert older["description"] == {"field": "description", "change_type": "modified"}
    assert older["city"]["change_type"] == "added"
    assert older["salary"] == {
        "field": "salary",
        "change_type": "added",
        "old_value": None,
        "new_value": {
            "min": "90000.01",
            "max": "110000.99",
            "currency": "USD",
            "period": "year",
        },
    }
    # Only the minimum changed in this transition; unchanged salary context is retained.
    assert latest["salary"]["change_type"] == "modified"
    assert latest["salary"]["old_value"] == older["salary"]["new_value"]
    assert latest["salary"]["new_value"] == {
        "min": "90000.02",
        "max": "110000.99",
        "currency": "USD",
        "period": "year",
    }
    assert list(older) == [
        "title",
        "location_text",
        "city",
        "region",
        "country_code",
        "workplace_type",
        "employment_type",
        "salary",
        "description",
    ]
    for group in body["items"]:
        assert set(group) == {"observed_at", "changes"}
        assert sum(change["field"] == "salary" for change in group["changes"]) == 1
    for private in (
        "private historical",
        "private-metadata",
        "source_url",
        "canonical_metadata",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_period",
        "from_version",
        "to_version",
        "version_number",
        "created_at",
        "content_hash",
        "source_observation_id",
        "pipeline_run_id",
        "raw_snapshot_id",
        str(setup.source.id),
        *(str(v.id) for v in setup.versions),
    ):
        assert private not in response.text


@pytest.mark.asyncio
async def test_public_changes_limit_keeps_groups_whole_and_ignores_newer_excluded_churn(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
) -> None:
    setup, canonical = await create_public_history(database_context, version_count=2)
    await append_public_change(
        database_context,
        setup.source,
        canonical.model_copy(
            update={
                "canonical_metadata": {"debug": "private excluded-only transition"},
                "source_url": "https://example.test/moved-source",
            }
        ),
        THIRD_OBSERVED_AT,
    )
    response = await client.get(url(setup.job_id), params={"limit": 1})
    assert response.status_code == 200
    assert response.json()["limit"] == 1
    groups = response.json()["items"]
    assert len(groups) == 1 and len(groups[0]["changes"]) == 9
    assert groups[0]["observed_at"] == "2026-10-08T12:00:00Z"
    assert "private excluded" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,active", [("observed", True), ("not_observed", True), ("observed", False)]
)
async def test_public_changes_history_is_addressable_for_known_jobs(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
    status: str,
    active: bool,
) -> None:
    setup, _ = await create_public_history(database_context, version_count=2)
    async with database_context.session_factory.begin() as session:
        job = await session.get(Job, setup.job_id)
        source = await session.get(SourceConnection, setup.source.id)
        assert job is not None and source is not None
        job.lifecycle_status = status
        source.is_active = active
    response = await client.get(url(setup.job_id))
    assert response.status_code == 200 and len(response.json()["items"]) == 1


@pytest.mark.asyncio
async def test_public_changes_known_initial_and_excluded_only_jobs_are_empty_not_missing(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
) -> None:
    setup, canonical = await create_public_history(database_context, version_count=1)
    expected = {"job_id": str(setup.job_id), "items": [], "limit": 10}
    assert (await client.get(url(setup.job_id))).json() == expected
    await append_public_change(
        database_context,
        setup.source,
        canonical.model_copy(
            update={
                "canonical_metadata": {"private": "excluded"},
                "source_url": "https://example.test/url-churn",
            }
        ),
        SECOND_OBSERVED_AT,
    )
    assert (await client.get(url(setup.job_id))).json() == expected
    response = await client.get(url(uuid4()))
    assert (
        response.status_code == 404
        and response.json()["error"]["code"] == "JOB_NOT_FOUND"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", ["0", "51", "-1", "bad"])
async def test_public_changes_reject_invalid_limits(
    client: httpx.AsyncClient, limit: str
) -> None:
    assert (await client.get(url(uuid4()), params={"limit": limit})).status_code == 422


@pytest.mark.asyncio
async def test_public_changes_same_time_transitions_remain_separate(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
) -> None:
    setup, _ = await create_public_history(database_context)
    async with database_context.session_factory.begin() as session:
        rows = await session.scalars(
            select(JobChangeEvent).where(JobChangeEvent.job_id == setup.job_id)
        )
        for change in rows:
            change.detected_at = SECOND_OBSERVED_AT
    first = await client.get(url(setup.job_id))
    second = await client.get(url(setup.job_id))
    assert first.json() == second.json()
    assert len(first.json()["items"]) == 2
    assert all(
        g["observed_at"] == "2026-10-08T12:00:00Z" for g in first.json()["items"]
    )


@pytest.mark.asyncio
async def test_public_changes_are_read_only_with_constant_queries(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
) -> None:
    setup, _ = await create_public_history(database_context)
    before = await database_contents(database_context)
    statements: list[str] = []

    def capture(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(database_context.engine.sync_engine, "before_cursor_execute", capture)
    try:
        assert (await client.get(url(setup.job_id))).status_code == 200
    finally:
        event.remove(
            database_context.engine.sync_engine, "before_cursor_execute", capture
        )
    reads = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(reads) == 2
    assert await database_contents(database_context) == before
    # The salary joins are scalar context, with no historical body/version loads.
    assert (
        "description" not in reads[1]
    )  # field name is a bind parameter, not a body column
    assert "canonical_metadata" not in reads[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["structured_text", "foreign_salary_version"])
async def test_public_changes_invalid_stored_data_fails_without_private_details(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
    corruption: str,
) -> None:
    setup, _ = await create_public_history(database_context)
    async with database_context.session_factory.begin() as session:
        if corruption == "structured_text":
            change = await session.scalar(
                select(JobChangeEvent).where(
                    JobChangeEvent.job_id == setup.job_id,
                    JobChangeEvent.field_name == "title",
                )
            )
            assert change is not None
            change.new_value = {"private": "unsafe debug marker"}
    if corruption == "foreign_salary_version":
        foreign, _ = await create_public_history(database_context, version_count=1)
        async with database_context.session_factory.begin() as session:
            change = await session.scalar(
                select(JobChangeEvent).where(
                    JobChangeEvent.job_id == setup.job_id,
                    JobChangeEvent.field_name == "salary_min",
                )
            )
            assert change is not None
            change.from_version_id = foreign.versions[0].id
    response = await client.get(url(setup.job_id))
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PUBLIC_JOBS_UNAVAILABLE"
    assert (
        "unsafe debug" not in response.text
        and str(setup.versions[0].id) not in response.text
    )


@pytest.mark.asyncio
async def test_public_changes_salary_removal_and_unit_only_addition(
    database_context: DatabaseContext,
    client: httpx.AsyncClient,
) -> None:
    setup, canonical = await create_public_history(database_context, version_count=2)
    empty = canonical.model_copy(
        update={
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_period": None,
        }
    )
    await append_public_change(database_context, setup.source, empty, THIRD_OBSERVED_AT)
    await append_public_change(
        database_context,
        setup.source,
        empty.model_copy(update={"salary_currency": "USD"}),
        THIRD_OBSERVED_AT + timedelta(days=1),
    )
    groups = (await client.get(url(setup.job_id))).json()["items"]
    assert groups[0]["changes"] == [
        {
            "field": "salary",
            "change_type": "added",
            "old_value": None,
            "new_value": {"min": None, "max": None, "currency": "USD", "period": None},
        }
    ]
    assert groups[1]["changes"][0]["change_type"] == "removed"
    assert groups[1]["changes"][0]["new_value"] is None
