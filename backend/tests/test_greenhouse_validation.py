from pathlib import Path

import pytest

from app.sources.greenhouse.errors import GreenhouseResponseShapeError
from app.sources.greenhouse.validation import (
    GREENHOUSE_RECORD_INVALID,
    parse_greenhouse_response,
    validate_greenhouse_response,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "greenhouse"


def fixture_text(name: str) -> str:
    return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


def minimal_job(**overrides: object) -> dict[str, object]:
    job: dict[str, object] = {
        "id": 9999,
        "title": "Test Engineer",
        "absolute_url": "https://boards.greenhouse.io/openrolefictional/jobs/9999",
    }
    job.update(overrides)
    return job


def test_v1_fixture_parses_all_provider_records() -> None:
    result = parse_greenhouse_response(fixture_text("jobs_v1.json"))

    assert [job.id for job in result.valid_records] == [1001, 1002, 1003, 1004]
    assert result.invalid_records == ()

    first_job = result.valid_records[0]
    assert first_job.title == "Backend Engineer"
    assert str(first_job.absolute_url) == (
        "https://boards.greenhouse.io/openrolefictional/jobs/1001"
    )
    assert first_job.location is not None
    assert first_job.location.name == "Berlin, Germany"
    assert first_job.updated_at is not None
    assert first_job.updated_at.tzinfo is not None
    assert first_job.content == (
        "<p>Build reliable backend services for fictional products.</p>"
    )
    assert first_job.departments is not None
    assert first_job.departments[0].name == "Engineering"


def test_v2_fixture_preserves_changed_source_values() -> None:
    result = parse_greenhouse_response(fixture_text("jobs_v2.json"))
    jobs = {job.id: job for job in result.valid_records}

    assert result.invalid_records == ()
    assert jobs[1001].location is not None
    assert jobs[1001].location.name == "Munich, Germany — Hybrid"
    assert jobs[1002].title == "Senior Data Engineer"
    assert jobs[1003].title == "Product Designer"


def test_invalid_child_record_is_isolated_from_valid_records() -> None:
    result = parse_greenhouse_response(fixture_text("jobs_invalid_record.json"))

    assert [job.id for job in result.valid_records] == [2001, 2003]
    assert len(result.invalid_records) == 1
    invalid = result.invalid_records[0]
    assert invalid.index == 1
    assert invalid.external_job_id is None
    assert invalid.error_code == GREENHOUSE_RECORD_INVALID
    assert "id" in invalid.error_message
    assert "intentionally malformed" not in invalid.error_message


def test_invalid_top_level_fixture_raises_stable_source_error() -> None:
    with pytest.raises(
        GreenhouseResponseShapeError,
        match="invalid top-level shape",
    ):
        parse_greenhouse_response(fixture_text("jobs_invalid_top_level.json"))


def test_optional_fields_remain_none() -> None:
    result = parse_greenhouse_response(fixture_text("jobs_optional_fields.json"))

    assert result.invalid_records == ()
    sparse = result.valid_records[0]
    assert sparse.internal_job_id is None
    assert sparse.updated_at is None
    assert sparse.requisition_id is None
    assert sparse.location is None
    assert sparse.language is None
    assert sparse.metadata is None
    assert sparse.content is None
    assert sparse.departments is None
    assert sparse.offices is None


def test_unknown_greenhouse_fields_are_ignored() -> None:
    result = parse_greenhouse_response(fixture_text("jobs_v1.json"))
    record = result.valid_records[3]

    assert record.id == 1004
    assert "future_greenhouse_field" not in record.model_dump()


@pytest.mark.parametrize("raw_id", [None, "9999", True, -1])
def test_missing_or_malformed_external_id_is_a_record_failure(raw_id: object) -> None:
    record = minimal_job()
    if raw_id is None:
        record.pop("id")
    else:
        record["id"] = raw_id

    result = validate_greenhouse_response({"jobs": [record]})

    assert result.valid_records == ()
    assert len(result.invalid_records) == 1


@pytest.mark.parametrize("title", [None, "", "   "])
def test_missing_or_blank_title_is_a_record_failure(title: object) -> None:
    record = minimal_job()
    if title is None:
        record.pop("title")
    else:
        record["title"] = title

    result = validate_greenhouse_response({"jobs": [record]})

    assert result.valid_records == ()
    assert len(result.invalid_records) == 1
    assert "title" in result.invalid_records[0].error_message


def test_timestamp_must_be_timezone_aware_when_present() -> None:
    result = validate_greenhouse_response(
        {
            "jobs": [
                minimal_job(id=4001, updated_at="2026-10-06T12:00:00Z"),
                minimal_job(id=4002, updated_at="not-a-timestamp"),
                minimal_job(id=4003, updated_at="2026-10-06T12:00:00"),
                minimal_job(id=4004),
            ]
        }
    )

    assert [job.id for job in result.valid_records] == [4001, 4004]
    assert [record.index for record in result.invalid_records] == [1, 2]
    assert all(
        "updated_at" in record.error_message for record in result.invalid_records
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"absolute_url": "not-a-url"},
        {"location": "Berlin"},
        {"location": {"name": "   "}},
    ],
)
def test_malformed_url_or_location_is_a_record_failure(
    overrides: dict[str, object],
) -> None:
    result = validate_greenhouse_response({"jobs": [minimal_job(**overrides)]})

    assert result.valid_records == ()
    assert len(result.invalid_records) == 1


def test_invalid_json_raises_top_level_source_error() -> None:
    with pytest.raises(GreenhouseResponseShapeError, match="not valid JSON"):
        parse_greenhouse_response(b'{"jobs":')
