from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import JsonValue

from app.jobs.changes import FieldChange, FieldChangeType
from app.jobs.hashing import normalize_canonical_job_values
from app.jobs.schemas import CanonicalJobInput

TRACKED_JOB_FIELDS = (
    "title",
    "description",
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
    "source_url",
    "canonical_metadata",
)


@dataclass(frozen=True, slots=True)
class JobVersionComparable:
    """Material state copied before comparison; no ORM identity or lazy attributes."""

    title: str
    source_url: str
    description: str | None = None
    location_text: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    workplace_type: str | None = None
    employment_type: str | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    canonical_metadata: dict[str, JsonValue] = field(default_factory=dict)

    @classmethod
    def from_canonical_job(cls, job: CanonicalJobInput) -> "JobVersionComparable":
        return cls(
            title=job.title,
            description=job.description,
            location_text=job.location_text,
            city=job.city,
            region=job.region,
            country_code=job.country_code,
            workplace_type=job.workplace_type,
            employment_type=job.employment_type,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            salary_period=job.salary_period,
            source_url=str(job.source_url),
            canonical_metadata=deepcopy(job.canonical_metadata),
        )


def diff_job_versions(
    previous: JobVersionComparable,
    current: JobVersionComparable,
) -> list[FieldChange]:
    """Return ordered material differences without mutating or persisting state."""

    if not isinstance(previous, JobVersionComparable) or not isinstance(
        current, JobVersionComparable
    ):
        raise TypeError("diff_job_versions requires JobVersionComparable snapshots.")

    old_values = normalize_canonical_job_values(
        {name: getattr(previous, name) for name in TRACKED_JOB_FIELDS}
    )
    new_values = normalize_canonical_job_values(
        {name: getattr(current, name) for name in TRACKED_JOB_FIELDS}
    )
    changes: list[FieldChange] = []
    for field_name in TRACKED_JOB_FIELDS:
        old_value = old_values[field_name]
        new_value = new_values[field_name]
        if _json_values_equal(old_value, new_value):
            continue

        if old_value is None:
            change_type = FieldChangeType.ADDED
        elif new_value is None:
            change_type = FieldChangeType.REMOVED
        else:
            change_type = FieldChangeType.MODIFIED

        changes.append(FieldChange(field_name, change_type, old_value, new_value))
    return changes


def _json_values_equal(previous: JsonValue, current: JsonValue) -> bool:
    # Python equates True with 1 and 1 with 1.0; the material JSON hash does not.
    if type(previous) is not type(current):
        return False
    if isinstance(previous, dict) and isinstance(current, dict):
        return previous.keys() == current.keys() and all(
            _json_values_equal(value, current[key]) for key, value in previous.items()
        )
    if isinstance(previous, list) and isinstance(current, list):
        return len(previous) == len(current) and all(
            _json_values_equal(old, new)
            for old, new in zip(previous, current, strict=True)
        )
    if isinstance(previous, float) and isinstance(current, float):
        # JSON distinguishes negative floating-point zero from positive zero.
        return previous.hex() == current.hex()
    return previous == current
