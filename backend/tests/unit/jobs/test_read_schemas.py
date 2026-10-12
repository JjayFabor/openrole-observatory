from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import JsonValue

from app.jobs.models import Job, JobLifecycleEvent, JobVersion
from app.jobs.read_schemas import (
    JobChangeRead,
    JobDetailRead,
    JobLifecycleEventRead,
    JobRead,
    JobVersionRead,
)
from app.sources.schemas import SourceHealthRead

NOW = datetime(2026, 10, 10, 12, tzinfo=UTC)


def test_job_and_version_mapping_preserves_identity_decimal_and_nulls() -> None:
    job = Job(
        id=uuid4(),
        company_id=uuid4(),
        source_connection_id=uuid4(),
        external_job_id="1001",
        lifecycle_status="not_observed",
        consecutive_absent_runs=2,
        first_seen_at=NOW,
        last_seen_at=NOW,
        absence_first_detected_at=NOW,
        no_longer_observed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    version = JobVersion(
        id=uuid4(),
        job_id=job.id,
        version_number=2,
        source_observation_id=uuid4(),
        content_hash="a" * 64,
        title="Engineer",
        source_url="https://example.com/jobs/1001",
        salary_min=Decimal("65000.01"),
        salary_max=Decimal("90000.99"),
        canonical_metadata={"tags": ["python"]},
        is_current=True,
        effective_from=NOW,
        created_at=NOW,
    )

    detail = JobDetailRead(
        **JobRead.model_validate(job).model_dump(),
        current_version=JobVersionRead.model_validate(version),
    ).model_dump(mode="json")

    assert detail["id"] == str(job.id)
    assert detail["lifecycle_status"] == "not_observed"
    assert detail["reappeared_at"] is None
    assert detail["current_version"]["source_observation_id"] == str(
        version.source_observation_id
    )
    assert detail["current_version"]["salary_min"] == "65000.01"
    assert detail["current_version"]["salary_max"] == "90000.99"
    assert detail["current_version"]["description"] is None
    assert detail["current_version"]["canonical_metadata"] == {"tags": ["python"]}
    assert datetime.fromisoformat(detail["last_seen_at"]) == NOW


@pytest.mark.parametrize(
    "value", [None, "65000.01", 42, True, ["a", None], {"a": [1, False]}]
)
def test_change_projection_keeps_json_values(value: JsonValue) -> None:
    from_id, to_id = uuid4(), uuid4()
    response = JobChangeRead.model_validate(
        {
            "id": uuid4(),
            "field_name": "canonical_metadata",
            "change_type": "modified",
            "old_value": value,
            "new_value": {"new": value},
            "from_version_id": from_id,
            "to_version_id": to_id,
            "from_version_number": 1,
            "to_version_number": 2,
            "detected_at": NOW,
            "created_at": NOW,
        }
    ).model_dump(mode="json")

    assert response["old_value"] == value
    assert type(response["old_value"]) is type(value)
    assert response["new_value"] == {"new": value}
    assert response["from_version_id"] == str(from_id)
    assert response["to_version_number"] == 2


def test_lifecycle_metadata_maps_orm_attribute_to_api_name() -> None:
    event = JobLifecycleEvent(
        id=uuid4(),
        job_id=uuid4(),
        pipeline_run_id=uuid4(),
        event_type="absence_detected",
        previous_status=None,
        new_status="observed",
        occurred_at=NOW,
        created_at=NOW,
        event_metadata={"consecutive_absent_runs": 1},
    )

    response = JobLifecycleEventRead.model_validate(event).model_dump(mode="json")

    assert response["metadata"] == {"consecutive_absent_runs": 1}
    assert "event_metadata" not in response
    assert response["previous_status"] is None
    assert response["pipeline_run_id"] == str(event.pipeline_run_id)


def test_source_health_schema_exposes_only_approved_fields() -> None:
    source_id = uuid4()
    response = SourceHealthRead.model_validate(
        {
            "id": source_id,
            "company_id": uuid4(),
            "provider": "greenhouse",
            "is_active": True,
            "last_attempted_sync_at": None,
            "last_successful_sync_at": None,
            "latest_run": None,
            "configuration": {"secret": "should-not-leak"},
            "external_account_key": "private-key",
        }
    ).model_dump(mode="json")

    assert response["id"] == str(source_id)
    assert response["latest_run"] is None
    assert "configuration" not in response
    assert "external_account_key" not in response
