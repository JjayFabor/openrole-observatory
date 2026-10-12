from pathlib import Path

from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.greenhouse.schemas import GreenhouseJob
from app.sources.greenhouse.validation import parse_greenhouse_response

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "greenhouse"


def fixture_text(name: str) -> str:
    return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


def fixture_jobs(name: str) -> tuple[GreenhouseJob, ...]:
    result = parse_greenhouse_response(fixture_text(name))
    assert result.invalid_records == ()
    return result.valid_records


def test_v1_fixture_maps_to_canonical_jobs() -> None:
    canonical_jobs = [map_greenhouse_job(job) for job in fixture_jobs("jobs_v1.json")]

    assert len(canonical_jobs) == 4
    first_job = canonical_jobs[0]
    assert first_job.external_job_id == "1001"
    assert first_job.title == "Backend Engineer"
    assert first_job.description == (
        "<p>Build reliable backend services for fictional products.</p>"
    )
    assert first_job.location_text == "Berlin, Germany"
    assert str(first_job.source_url) == (
        "https://boards.greenhouse.io/openrolefictional/jobs/1001"
    )
    assert first_job.source_updated_at is not None
    assert first_job.source_updated_at.isoformat() == "2026-10-01T10:00:00+00:00"


def test_unsupported_canonical_fields_remain_null() -> None:
    canonical = map_greenhouse_job(fixture_jobs("jobs_v1.json")[0])

    assert canonical.city is None
    assert canonical.region is None
    assert canonical.country_code is None
    assert canonical.workplace_type is None
    assert canonical.employment_type is None
    assert canonical.salary_min is None
    assert canonical.salary_max is None
    assert canonical.salary_currency is None
    assert canonical.salary_period is None
    assert canonical.source_published_at is None


def test_sparse_source_values_remain_null_without_guesses() -> None:
    canonical = map_greenhouse_job(fixture_jobs("jobs_optional_fields.json")[0])

    assert canonical.external_job_id == "3001"
    assert canonical.description is None
    assert canonical.location_text is None
    assert canonical.source_updated_at is None
    assert canonical.canonical_metadata == {}


def test_mapper_trims_title_and_location_without_rewriting_content() -> None:
    source = GreenhouseJob.model_validate(
        {
            "id": 9001,
            "title": "  Backend Engineer  ",
            "location": {"name": "  Berlin, Germany  "},
            "absolute_url": "https://boards.greenhouse.io/example/jobs/9001",
            "content": "  <p>Preserve this source HTML.</p>  ",
        }
    )

    canonical = map_greenhouse_job(source)

    assert canonical.title == "Backend Engineer"
    assert canonical.location_text == "Berlin, Germany"
    assert canonical.description == "  <p>Preserve this source HTML.</p>  "


def test_canonical_metadata_contains_only_selected_nested_source_data() -> None:
    source = fixture_jobs("jobs_v1.json")[0]
    canonical = map_greenhouse_job(source)

    assert set(canonical.canonical_metadata) == {"departments", "offices"}
    departments = canonical.canonical_metadata["departments"]
    offices = canonical.canonical_metadata["offices"]
    assert isinstance(departments, list)
    assert isinstance(offices, list)
    department = departments[0]
    office = offices[0]
    assert isinstance(department, dict)
    assert isinstance(office, dict)
    assert department["name"] == "Engineering"
    assert office["name"] == "Berlin"
    assert "metadata" not in canonical.canonical_metadata
    assert "internal_job_id" not in canonical.canonical_metadata
    assert "requisition_id" not in canonical.canonical_metadata


def test_present_empty_nested_lists_remain_present_in_metadata() -> None:
    canonical = map_greenhouse_job(fixture_jobs("jobs_v1.json")[1])

    assert canonical.canonical_metadata["offices"] == []


def test_mapping_is_deterministic_and_does_not_mutate_source() -> None:
    source = fixture_jobs("jobs_v1.json")[0]
    source_before = source.model_dump(mode="json")

    canonical_a = map_greenhouse_job(source)
    canonical_b = map_greenhouse_job(source)

    assert canonical_a == canonical_b
    assert canonical_a.model_dump(mode="json") == canonical_b.model_dump(mode="json")
    assert source.model_dump(mode="json") == source_before


def test_v2_source_changes_are_reflected_without_diffing() -> None:
    v1_jobs = {job.id: map_greenhouse_job(job) for job in fixture_jobs("jobs_v1.json")}
    v2_jobs = {job.id: map_greenhouse_job(job) for job in fixture_jobs("jobs_v2.json")}

    assert v1_jobs[1001].location_text == "Berlin, Germany"
    assert v2_jobs[1001].location_text == "Munich, Germany — Hybrid"
    assert v1_jobs[1002].title == "Data Engineer"
    assert v2_jobs[1002].title == "Senior Data Engineer"
    assert v1_jobs[1003] == v2_jobs[1003]
