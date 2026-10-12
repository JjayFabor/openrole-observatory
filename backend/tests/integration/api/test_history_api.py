from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.dependencies import get_job_query_service, get_source_query_service
from app.config import get_settings
from app.database.models import REGISTERED_MODELS
from app.jobs.absence_confirmation import AbsenceConfirmationService
from app.jobs.first_absence import FirstAbsenceDetectionService
from app.jobs.models import Job, JobChangeEvent, JobLifecycleEvent, JobVersion
from app.jobs.present_reconciliation import PresentJobReconciliationService
from app.jobs.query_service import JobQueryService
from app.jobs.schemas import CanonicalJobInput
from app.jobs.service import (
    ApplyChangedObservationCommand,
    ChangedJobPersistenceService,
)
from app.main import create_app
from app.pipeline_runs.models import PipelineRun
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.greenhouse.schemas import GreenhouseJob
from app.sources.models import SourceConnection
from app.sources.query_service import SourceQueryService
from tests.integration.lifecycle.helpers import (
    create_lifecycle_job,
    create_presence_run,
)
from tests.test_changed_job_persistence import (
    FIRST_OBSERVED_AT,
    SECOND_OBSERVED_AT,
    THIRD_OBSERVED_AT,
    DatabaseContext,
    create_existing_job_setup,
    create_observation,
    create_source,
    fixture_job,
    load_versions,
)
from tests.test_changed_job_persistence import database_context as database_context

ABSENT_AT = datetime(2026, 10, 10, 12, tzinfo=UTC)
CONFIRMED_AT = ABSENT_AT + timedelta(days=1)
REAPPEARED_AT = CONFIRMED_AT + timedelta(days=1)


@pytest_asyncio.fixture
async def api_client(
    database_context: DatabaseContext,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(get_settings())
    jobs = JobQueryService(database_context.session_factory)
    sources = SourceQueryService(database_context.session_factory)
    app.dependency_overrides[get_job_query_service] = lambda: jobs
    app.dependency_overrides[get_source_query_service] = lambda: sources
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@dataclass(frozen=True)
class HistorySetup:
    source: SourceConnection
    job_id: UUID
    versions: list[JobVersion]


async def create_history(
    context: DatabaseContext, *, version_count: int = 3
) -> HistorySetup:
    record = fixture_job("jobs_v1.json")
    setup = await create_existing_job_setup(context.session_factory, record)
    canonical = map_greenhouse_job(record).model_copy(
        update={
            "title": "Engineer II",
            "description": "<p>Updated description</p>",
            "city": "Manila",
            "region": "Metro Manila",
            "country_code": "PH",
            "workplace_type": "hybrid",
            "employment_type": "full_time",
            "salary_min": Decimal("65000.01"),
            "salary_max": Decimal("90000.99"),
            "salary_currency": "USD",
            "salary_period": "year",
            "canonical_metadata": {"tags": ["python", 2, True, None]},
        }
    )

    def mapper(_: GreenhouseJob) -> CanonicalJobInput:
        return canonical

    for number, observed_at in [(2, SECOND_OBSERVED_AT), (3, THIRD_OBSERVED_AT)]:
        if number > version_count:
            break
        if number == 3:
            canonical = canonical.model_copy(
                update={
                    "title": "Engineer III",
                    "salary_min": Decimal("65000.02"),
                    "employment_type": None,
                    "canonical_metadata": {},
                }
            )
        observation = await create_observation(
            context.session_factory, setup.source_connection.id, record, observed_at
        )
        await ChangedJobPersistenceService(
            context.session_factory, mapper=mapper
        ).apply_changed_observation(
            ApplyChangedObservationCommand(observation.id, record)
        )
    return HistorySetup(
        setup.source_connection,
        setup.job_id,
        await load_versions(context.session_factory, setup.job_id),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["observed", "not_observed"])
async def test_detail_returns_current_version_and_lifecycle(
    database_context: DatabaseContext, api_client: httpx.AsyncClient, status: str
) -> None:
    setup = await create_history(database_context, version_count=2)
    async with database_context.session_factory.begin() as session:
        job = await session.get(Job, setup.job_id)
        assert job is not None
        job.lifecycle_status = status
        if status == "not_observed":
            job.consecutive_absent_runs = 2
            job.absence_first_detected_at = ABSENT_AT
            job.no_longer_observed_at = CONFIRMED_AT

    response = await api_client.get(f"/api/v1/jobs/{setup.job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["company_id"] == str(setup.source.company_id)
    assert body["source_connection_id"] == str(setup.source.id)
    assert body["external_job_id"] == "1001"
    assert body["lifecycle_status"] == status
    assert body["consecutive_absent_runs"] == (2 if status == "not_observed" else 0)
    version = body["current_version"]
    assert version["id"] == str(setup.versions[1].id)
    assert version["version_number"] == 2
    assert version["title"] == "Engineer II"
    assert version["description"] == "<p>Updated description</p>"
    assert [version[key] for key in ("city", "region", "country_code")] == [
        "Manila",
        "Metro Manila",
        "PH",
    ]
    assert version["salary_min"] == "65000.01"
    assert version["salary_max"] == "90000.99"
    assert version["salary_currency"] == "USD"
    assert version["source_observation_id"] == str(
        setup.versions[1].source_observation_id
    )
    assert version["content_hash"] == setup.versions[1].content_hash
    assert version["is_current"] is True
    assert version["effective_to"] is None
    assert datetime.fromisoformat(version["effective_from"]) == SECOND_OBSERVED_AT
    assert datetime.fromisoformat(body["last_seen_at"]).tzinfo is not None


@pytest.mark.asyncio
async def test_existing_job_without_current_version_is_stable_invariant_error(
    database_context: DatabaseContext, api_client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    job = await create_lifecycle_job(database_context, source, "missing-version")

    response = await api_client.get(
        f"/api/v1/jobs/{job.id}", headers={"X-Request-ID": "history-request"}
    )

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "CURRENT_JOB_VERSION_MISSING",
        "message": "The job's current canonical version is inconsistent.",
        "request_id": "history-request",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "jobs/{id}",
        "jobs/{id}/versions",
        "jobs/{id}/changes",
        "jobs/{id}/lifecycle",
        "sources/{id}",
    ],
)
async def test_unknown_resource_returns_stable_404(
    api_client: httpx.AsyncClient, path: str
) -> None:
    response = await api_client.get(
        f"/api/v1/{path.format(id=uuid4())}", headers={"X-Request-ID": "missing"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == (
        "SOURCE_CONNECTION_NOT_FOUND" if path.startswith("sources") else "JOB_NOT_FOUND"
    )
    assert response.json()["error"]["request_id"] == "missing"


@pytest.mark.asyncio
async def test_versions_are_chronological_and_paginated(
    database_context: DatabaseContext, api_client: httpx.AsyncClient
) -> None:
    setup = await create_history(database_context)
    path = f"/api/v1/jobs/{setup.job_id}/versions"

    response = await api_client.get(path)
    assert response.status_code == 200
    body = response.json()
    assert (body["limit"], body["offset"]) == (50, 0)
    assert [item["version_number"] for item in body["items"]] == [1, 2, 3]
    assert [item["is_current"] for item in body["items"]] == [False, False, True]
    assert [
        datetime.fromisoformat(item["effective_from"]) for item in body["items"]
    ] == [FIRST_OBSERVED_AT, SECOND_OBSERVED_AT, THIRD_OBSERVED_AT]
    assert [
        datetime.fromisoformat(item["effective_to"]) if item["effective_to"] else None
        for item in body["items"]
    ] == [SECOND_OBSERVED_AT, THIRD_OBSERVED_AT, None]
    page = (await api_client.get(path, params={"limit": 1, "offset": 1})).json()
    assert page["items"] == [body["items"][1]]
    assert (page["limit"], page["offset"]) == (1, 1)
    assert (await api_client.get(path, params={"offset": 3})).json()["items"] == []


@pytest.mark.asyncio
async def test_changes_return_persisted_json_values_and_joined_version_numbers(
    database_context: DatabaseContext, api_client: httpx.AsyncClient
) -> None:
    setup = await create_history(database_context)
    response = await api_client.get(f"/api/v1/jobs/{setup.job_id}/changes")
    assert response.status_code == 200
    items = response.json()["items"]
    assert [
        (item["to_version_number"], item["field_name"]) for item in items
    ] == sorted((item["to_version_number"], item["field_name"]) for item in items)
    async with database_context.session_factory() as session:
        stored = list(
            await session.scalars(
                select(JobChangeEvent).where(JobChangeEvent.job_id == setup.job_id)
            )
        )
    assert {item["id"] for item in items} == {str(event.id) for event in stored}
    for event in stored:
        item = next(item for item in items if item["id"] == str(event.id))
        assert item["old_value"] == event.old_value
        assert item["new_value"] == event.new_value
        assert item["change_type"] == event.change_type
        assert item["from_version_id"] == str(event.from_version_id)
        assert item["to_version_id"] == str(event.to_version_id)
        assert item["from_version_number"] == item["to_version_number"] - 1
        assert datetime.fromisoformat(item["detected_at"]) == event.detected_at
    second = {
        item["field_name"]: item for item in items if item["to_version_number"] == 2
    }
    assert second["salary_min"]["new_value"] == "65000.01"
    assert second["salary_min"]["old_value"] is None
    assert second["salary_min"]["change_type"] == "added"
    assert second["canonical_metadata"]["new_value"] == {
        "tags": ["python", 2, True, None]
    }
    assert second["description"]["new_value"] == "<p>Updated description</p>"
    third = {
        item["field_name"]: item for item in items if item["to_version_number"] == 3
    }
    assert third["employment_type"]["change_type"] == "removed"
    assert third["employment_type"]["new_value"] is None
    assert third["salary_min"]["change_type"] == "modified"
    page = (
        await api_client.get(
            f"/api/v1/jobs/{setup.job_id}/changes", params={"limit": 2, "offset": 1}
        )
    ).json()
    assert page["items"] == items[1:3]


@pytest.mark.asyncio
async def test_existing_job_empty_histories_are_not_404(
    database_context: DatabaseContext, api_client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    job = await create_lifecycle_job(database_context, source, "empty-history")
    for suffix, collection in [
        ("versions", "items"),
        ("changes", "items"),
        ("lifecycle", "events"),
    ]:
        response = await api_client.get(f"/api/v1/jobs/{job.id}/{suffix}")
        assert response.status_code == 200
        assert response.json()[collection] == []
    single = await create_history(database_context, version_count=1)
    assert (await api_client.get(f"/api/v1/jobs/{single.job_id}/changes")).json()[
        "items"
    ] == []


@pytest.mark.asyncio
async def test_lifecycle_exposes_tentative_absence_confirmation_and_reappearance(
    database_context: DatabaseContext, api_client: httpx.AsyncClient
) -> None:
    setup = await create_history(database_context, version_count=1)
    path = f"/api/v1/jobs/{setup.job_id}/lifecycle"
    first = await create_presence_run(
        database_context, source=setup.source, retrieved_at=ABSENT_AT
    )
    await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(first.run.id)
    tentative = (await api_client.get(path)).json()
    assert tentative["current_status"] == "observed"
    assert tentative["consecutive_absent_runs"] == 1
    assert datetime.fromisoformat(tentative["absence_first_detected_at"]) == ABSENT_AT
    assert tentative["events"][0]["event_type"] == "absence_detected"
    confirmed = await create_presence_run(
        database_context, source=setup.source, retrieved_at=CONFIRMED_AT
    )
    await AbsenceConfirmationService(database_context.session_factory).confirm_absences(
        confirmed.run.id
    )
    absent = (await api_client.get(path)).json()
    assert absent["current_status"] == "not_observed"
    assert absent["consecutive_absent_runs"] == 2
    assert datetime.fromisoformat(absent["no_longer_observed_at"]) == CONFIRMED_AT
    reappeared = await create_presence_run(
        database_context,
        source=setup.source,
        observations=[("1001", "jobs[0]")],
        retrieved_at=REAPPEARED_AT,
    )
    await PresentJobReconciliationService(
        database_context.session_factory
    ).reconcile_present_jobs(reappeared.run.id)
    response = await api_client.get(path)
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == str(setup.job_id)
    assert body["current_status"] == "observed"
    assert body["consecutive_absent_runs"] == 0
    assert body["absence_first_detected_at"] is None
    assert datetime.fromisoformat(body["no_longer_observed_at"]) == CONFIRMED_AT
    assert datetime.fromisoformat(body["reappeared_at"]) == REAPPEARED_AT
    events = body["events"]
    assert [event["event_type"] for event in events] == [
        "absence_detected",
        "not_observed_confirmed",
        "reappeared",
    ]
    assert [event["pipeline_run_id"] for event in events] == [
        str(first.run.id),
        str(confirmed.run.id),
        str(reappeared.run.id),
    ]
    assert [datetime.fromisoformat(event["occurred_at"]) for event in events] == [
        ABSENT_AT,
        CONFIRMED_AT,
        REAPPEARED_AT,
    ]
    assert [(event["previous_status"], event["new_status"]) for event in events] == [
        ("observed", "observed"),
        ("observed", "not_observed"),
        ("not_observed", "observed"),
    ]
    assert events[1]["metadata"] == {
        "consecutive_absent_runs": 2,
        "confirmation_threshold": 2,
    }
    assert (await api_client.get(path, params={"limit": 1, "offset": 1})).json()[
        "events"
    ] == [events[1]]
    detail = (await api_client.get(f"/api/v1/jobs/{setup.job_id}")).json()
    assert detail["no_longer_observed_at"] == body["no_longer_observed_at"]
    assert detail["reappeared_at"] == body["reappeared_at"]
    assert detail["current_version"]["version_number"] == 1


@pytest.mark.asyncio
async def test_lifecycle_orders_equal_occurrence_times_by_creation_then_id(
    database_context: DatabaseContext, api_client: httpx.AsyncClient
) -> None:
    setup = await create_history(database_context, version_count=1)
    async with database_context.session_factory.begin() as session:
        for event_id, creation_offset in [(3, 0), (1, 1), (2, 0)]:
            run = PipelineRun(
                source_connection_id=setup.source.id,
                status="completed",
                started_at=ABSENT_AT,
            )
            session.add(
                JobLifecycleEvent(
                    id=UUID(int=event_id),
                    job_id=setup.job_id,
                    pipeline_run=run,
                    event_type="absence_detected",
                    occurred_at=ABSENT_AT,
                    previous_status=None,
                    new_status=None,
                    created_at=ABSENT_AT + timedelta(seconds=creation_offset),
                    event_metadata={"count": event_id},
                )
            )
    body = (await api_client.get(f"/api/v1/jobs/{setup.job_id}/lifecycle")).json()
    assert [event["id"] for event in body["events"]] == [
        str(UUID(int=i)) for i in [2, 3, 1]
    ]
    assert body["events"][0]["previous_status"] is None
    assert body["events"][0]["metadata"] == {"count": 2}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "latest_status", ["completed", "completed_with_errors", "failed", "running"]
)
async def test_source_health_keeps_success_freshness_separate_from_latest_run(
    database_context: DatabaseContext, api_client: httpx.AsyncClient, latest_status: str
) -> None:
    source = await create_source(database_context.session_factory)
    async with database_context.session_factory.begin() as session:
        stored_source = await session.get(SourceConnection, source.id)
        assert stored_source is not None
        stored_source.configuration = {
            "some_secret": "should-not-leak",
            "internal_lock_key": "private",
        }
        stored_source.is_active = False
        stored_source.last_attempted_sync_at = SECOND_OBSERVED_AT
        stored_source.last_successful_sync_at = (
            SECOND_OBSERVED_AT
            if latest_status.startswith("completed")
            else FIRST_OBSERVED_AT
        )
        older = PipelineRun(
            source_connection_id=source.id,
            status="completed",
            started_at=FIRST_OBSERVED_AT,
            completed_at=FIRST_OBSERVED_AT,
        )
        latest = PipelineRun(
            source_connection_id=source.id,
            status=latest_status,
            started_at=SECOND_OBSERVED_AT,
            completed_at=SECOND_OBSERVED_AT if latest_status != "running" else None,
            records_fetched=3,
            records_valid=2,
            records_quarantined=1,
            jobs_new=1,
            jobs_changed=1,
            jobs_unchanged=0,
            error_code="SOURCE_REQUEST_FAILED" if latest_status == "failed" else None,
            error_summary="The source request failed."
            if latest_status == "failed"
            else None,
        )
        session.add_all([older, latest])
        await session.flush()
    response = await api_client.get(f"/api/v1/sources/{source.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "greenhouse"
    assert body["company_id"] == str(source.company_id)
    assert body["is_active"] is False
    assert datetime.fromisoformat(body["last_attempted_sync_at"]) == SECOND_OBSERVED_AT
    expected_success = (
        SECOND_OBSERVED_AT
        if latest_status.startswith("completed")
        else FIRST_OBSERVED_AT
    )
    assert datetime.fromisoformat(body["last_successful_sync_at"]) == expected_success
    assert body["latest_run"]["id"] == str(latest.id)
    assert body["latest_run"]["status"] == latest_status
    for field in [
        "records_fetched",
        "records_valid",
        "records_quarantined",
        "jobs_new",
        "jobs_changed",
        "jobs_unchanged",
    ]:
        assert body["latest_run"][field] == getattr(latest, field)
    assert body["latest_run"]["error_code"] == latest.error_code
    assert body["latest_run"]["error_summary"] == latest.error_summary
    assert "configuration" not in body
    assert "external_account_key" not in body
    assert "should-not-leak" not in response.text
    assert "internal_lock_key" not in response.text


@pytest.mark.asyncio
async def test_never_synchronized_source_has_no_run_or_freshness(
    database_context: DatabaseContext, api_client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    response = await api_client.get(f"/api/v1/sources/{source.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["latest_run"] is None
    assert body["last_attempted_sync_at"] is None
    assert body["last_successful_sync_at"] is None


@pytest.mark.asyncio
async def test_source_latest_run_uses_id_fallback_for_equal_start_times(
    database_context: DatabaseContext, api_client: httpx.AsyncClient
) -> None:
    source = await create_source(database_context.session_factory)
    run_ids = sorted([uuid4(), uuid4()])
    async with database_context.session_factory.begin() as session:
        session.add_all(
            [
                PipelineRun(
                    id=run_id,
                    source_connection_id=source.id,
                    status="running",
                    started_at=ABSENT_AT,
                )
                for run_id in reversed(run_ids)
            ]
        )
    body = (await api_client.get(f"/api/v1/sources/{source.id}")).json()
    assert body["latest_run"]["id"] == str(run_ids[-1])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "query"),
    [
        ("versions", "limit=0"),
        ("changes", "limit=101"),
        ("lifecycle", "offset=-1"),
        ("versions", "limit=many"),
        ("changes", "offset=next"),
    ],
)
async def test_history_pagination_validation(
    api_client: httpx.AsyncClient, suffix: str, query: str
) -> None:
    response = await api_client.get(f"/api/v1/jobs/{uuid4()}/{suffix}?{query}")
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "jobs/{id}",
        "jobs/{id}/versions",
        "jobs/{id}/changes",
        "jobs/{id}/lifecycle",
        "sources/{id}",
    ],
)
async def test_inspection_path_requires_uuid(
    api_client: httpx.AsyncClient, path: str
) -> None:
    assert (
        await api_client.get(f"/api/v1/{path.format(id='invalid')}")
    ).status_code == 422


async def database_contents(
    context: DatabaseContext,
) -> dict[str, list[dict[str, object]]]:
    contents: dict[str, list[dict[str, object]]] = {}
    for model in REGISTERED_MODELS:
        table = model.__table__
        rows = await context.connection.execute(select(table).order_by(table.c.id))
        contents[model.__tablename__] = [dict(row) for row in rows.mappings()]
    return contents


@pytest.mark.asyncio
async def test_inspection_gets_do_not_mutate_any_persisted_rows(
    database_context: DatabaseContext, api_client: httpx.AsyncClient
) -> None:
    setup = await create_history(database_context)
    run = await create_presence_run(
        database_context, source=setup.source, retrieved_at=ABSENT_AT
    )
    await FirstAbsenceDetectionService(
        database_context.session_factory
    ).detect_first_absences(run.run.id)
    before = await database_contents(database_context)
    for path in [
        f"jobs/{setup.job_id}",
        f"jobs/{setup.job_id}/versions",
        f"jobs/{setup.job_id}/changes",
        f"jobs/{setup.job_id}/lifecycle",
        f"sources/{setup.source.id}",
    ]:
        assert (await api_client.get(f"/api/v1/{path}")).status_code == 200
    assert await database_contents(database_context) == before
