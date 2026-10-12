from pydantic import JsonValue

from app.jobs.schemas import CanonicalJobInput
from app.sources.greenhouse.schemas import GreenhouseJob


def map_greenhouse_job(job: GreenhouseJob) -> CanonicalJobInput:
    """Map one validated Greenhouse record into provider-independent job content."""

    return CanonicalJobInput(
        external_job_id=str(job.id),
        title=job.title.strip(),
        description=job.content,
        location_text=job.location.name.strip() if job.location is not None else None,
        city=None,
        region=None,
        country_code=None,
        workplace_type=None,
        employment_type=None,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_period=None,
        source_url=job.absolute_url,
        source_published_at=None,
        source_updated_at=job.updated_at,
        canonical_metadata=_canonical_metadata(job),
    )


def _canonical_metadata(job: GreenhouseJob) -> dict[str, JsonValue]:
    metadata: dict[str, JsonValue] = {}

    if job.departments is not None:
        metadata["departments"] = [
            department.model_dump(mode="json") for department in job.departments
        ]

    if job.offices is not None:
        metadata["offices"] = [office.model_dump(mode="json") for office in job.offices]

    return metadata
