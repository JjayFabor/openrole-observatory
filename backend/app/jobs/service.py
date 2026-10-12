import logging
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.exc import IntegrityError, MultipleResultsFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs.change_detection import JobVersionComparable, diff_job_versions
from app.jobs.changes import FieldChange
from app.jobs.errors import (
    ChangedJobDatabaseError,
    ChangedJobRequiresVersioningError,
    CurrentJobVersionInvariantError,
    CurrentJobVersionMissingError,
    ExistingJobRequiresComparisonError,
    HistoricalJobContentAlreadyExistsError,
    JobDiffInvariantError,
    NewJobDatabaseError,
    NewJobRequiredError,
    SourceObservationAlreadyMaterializedError,
    SourceObservationNotFoundError,
    SourceObservationRecordMismatchError,
    SourceRecordHashingError,
    SourceRecordNormalizationError,
    StaleJobObservationError,
    UnchangedJobDatabaseError,
    UnchangedJobRequiresFreshnessUpdateError,
    UnsupportedJobObservationProviderError,
)
from app.jobs.hashing import compute_canonical_job_hash
from app.jobs.models import Job, JobChangeEvent, JobLifecycleStatus, JobVersion
from app.jobs.repository import JobObservationContext, JobRepository
from app.jobs.schemas import CanonicalJobInput
from app.sources.greenhouse.mapper import map_greenhouse_job
from app.sources.greenhouse.schemas import GreenhouseJob
from app.sources.models import SourceProvider

logger = logging.getLogger(__name__)

_STABLE_IDENTITY_CONSTRAINT = "uq_jobs_source_connection_id_external_job_id"
_OBSERVATION_VERSION_CONSTRAINT = "uq_job_versions_source_observation_id"
_CONTENT_HASH_CONSTRAINT = "uq_job_versions_job_id_content_hash"

CanonicalMapper = Callable[[GreenhouseJob], CanonicalJobInput]
CanonicalHasher = Callable[[CanonicalJobInput], str]


@dataclass(frozen=True, slots=True)
class PersistNewJobCommand:
    source_observation_id: UUID
    source_record: GreenhouseJob


@dataclass(frozen=True, slots=True)
class NewJobPersistenceResult:
    job_id: UUID
    job_version_id: UUID
    version_number: int
    content_hash: str


class NewJobPersistenceService:
    """Create a logical job and its first canonical version atomically."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        mapper: CanonicalMapper = map_greenhouse_job,
        hasher: CanonicalHasher = compute_canonical_job_hash,
    ) -> None:
        self._session_factory = session_factory
        self._mapper = mapper
        self._hasher = hasher

    async def create_new_job(
        self,
        command: PersistNewJobCommand,
    ) -> NewJobPersistenceResult:
        identity: tuple[UUID, str] | None = None

        try:
            async with self._session_factory.begin() as session:
                repository = JobRepository(session)
                context = await repository.get_observation_context(
                    command.source_observation_id,
                    for_update=True,
                )
                if context is None:
                    raise SourceObservationNotFoundError(command.source_observation_id)

                _validate_source_context(
                    context,
                    command.source_observation_id,
                    command.source_record,
                )
                identity = (
                    context.observation.source_connection_id,
                    context.observation.external_job_id,
                )

                if (
                    await repository.get_version_by_source_observation(
                        context.observation.id
                    )
                    is not None
                ):
                    raise SourceObservationAlreadyMaterializedError(
                        context.observation.id
                    )

                if await repository.get_by_source_identity(*identity) is not None:
                    raise ExistingJobRequiresComparisonError(*identity)

                canonical_job = _map_source_record(
                    self._mapper,
                    command.source_observation_id,
                    command.source_record,
                )
                content_hash = _hash_canonical_job(
                    self._hasher,
                    command.source_observation_id,
                    canonical_job,
                )
                job = self._build_job(context)
                await repository.add_job(job)

                version = _build_job_version(
                    job_id=job.id,
                    source_observation_id=context.observation.id,
                    version_number=1,
                    canonical_job=canonical_job,
                    content_hash=content_hash,
                    effective_from=context.observation.observed_at,
                )
                await repository.add_version(version)

                result = NewJobPersistenceResult(
                    job_id=job.id,
                    job_version_id=version.id,
                    version_number=version.version_number,
                    content_hash=version.content_hash,
                )
        except IntegrityError as error:
            constraint_name = _find_constraint_name(error)
            if constraint_name == _STABLE_IDENTITY_CONSTRAINT and identity is not None:
                raise ExistingJobRequiresComparisonError(*identity) from error
            if constraint_name == _OBSERVATION_VERSION_CONSTRAINT:
                raise SourceObservationAlreadyMaterializedError(
                    command.source_observation_id
                ) from error
            raise NewJobDatabaseError(command.source_observation_id) from error

        logger.info(
            "new_job_persisted",
            extra={
                "source_observation_id": str(command.source_observation_id),
                "job_id": str(result.job_id),
                "job_version_id": str(result.job_version_id),
                "version_number": result.version_number,
            },
        )
        return result

    @staticmethod
    def _build_job(context: JobObservationContext) -> Job:
        observation = context.observation
        return Job(
            company_id=context.company.id,
            source_connection_id=observation.source_connection_id,
            external_job_id=observation.external_job_id,
            first_seen_at=observation.observed_at,
            last_seen_at=observation.observed_at,
            lifecycle_status=JobLifecycleStatus.OBSERVED.value,
            no_longer_observed_at=None,
            reappeared_at=None,
        )


@dataclass(frozen=True, slots=True)
class ApplyUnchangedObservationCommand:
    source_observation_id: UUID
    source_record: GreenhouseJob


@dataclass(frozen=True, slots=True)
class UnchangedJobResult:
    job_id: UUID
    current_version_id: UUID
    content_hash: str
    observed_at: datetime
    outcome: Literal["unchanged"] = "unchanged"


class UnchangedJobPersistenceService:
    """Apply a repeat observation whose canonical job content is unchanged."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        mapper: CanonicalMapper = map_greenhouse_job,
        hasher: CanonicalHasher = compute_canonical_job_hash,
    ) -> None:
        self._session_factory = session_factory
        self._mapper = mapper
        self._hasher = hasher

    async def apply_unchanged_observation(
        self,
        command: ApplyUnchangedObservationCommand,
    ) -> UnchangedJobResult:
        try:
            async with self._session_factory.begin() as session:
                repository = JobRepository(session)
                context = await repository.get_observation_context(
                    command.source_observation_id,
                    for_update=True,
                )
                if context is None:
                    raise SourceObservationNotFoundError(command.source_observation_id)

                _validate_source_context(
                    context,
                    command.source_observation_id,
                    command.source_record,
                )
                if (
                    await repository.get_version_by_source_observation(
                        context.observation.id
                    )
                    is not None
                ):
                    raise SourceObservationAlreadyMaterializedError(
                        context.observation.id
                    )

                identity = (
                    context.observation.source_connection_id,
                    context.observation.external_job_id,
                )
                job = await repository.get_by_source_identity(
                    *identity,
                    for_update=True,
                )
                if job is None:
                    raise NewJobRequiredError(*identity)

                current_version = await _get_current_version(repository, job.id)
                canonical_job = _map_source_record(
                    self._mapper,
                    command.source_observation_id,
                    command.source_record,
                )
                content_hash = _hash_canonical_job(
                    self._hasher,
                    command.source_observation_id,
                    canonical_job,
                )
                if content_hash != current_version.content_hash:
                    raise ChangedJobRequiresVersioningError(job.id)

                await repository.advance_last_seen_at(
                    job,
                    context.observation.observed_at,
                )
                result = UnchangedJobResult(
                    job_id=job.id,
                    current_version_id=current_version.id,
                    content_hash=current_version.content_hash,
                    observed_at=context.observation.observed_at,
                )
        except SQLAlchemyError as error:
            raise UnchangedJobDatabaseError(command.source_observation_id) from error

        logger.info(
            "unchanged_job_observation_applied",
            extra={
                "source_observation_id": str(command.source_observation_id),
                "job_id": str(result.job_id),
                "current_version_id": str(result.current_version_id),
                "outcome": result.outcome,
            },
        )
        return result


@dataclass(frozen=True, slots=True)
class ApplyChangedObservationCommand:
    source_observation_id: UUID
    source_record: GreenhouseJob


@dataclass(frozen=True, slots=True)
class ChangedJobResult:
    job_id: UUID
    previous_version_id: UUID
    new_version_id: UUID
    previous_version_number: int
    new_version_number: int
    previous_content_hash: str
    new_content_hash: str
    observed_at: datetime
    outcome: Literal["changed"] = "changed"


class ChangedJobPersistenceService:
    """Atomically persist a version transition and its derived field changes."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        mapper: CanonicalMapper = map_greenhouse_job,
        hasher: CanonicalHasher = compute_canonical_job_hash,
    ) -> None:
        self._session_factory = session_factory
        self._mapper = mapper
        self._hasher = hasher

    async def apply_changed_observation(
        self,
        command: ApplyChangedObservationCommand,
    ) -> ChangedJobResult:
        job_id: UUID | None = None

        try:
            async with self._session_factory.begin() as session:
                repository = JobRepository(session)
                context = await repository.get_observation_context(
                    command.source_observation_id,
                    for_update=True,
                )
                if context is None:
                    raise SourceObservationNotFoundError(command.source_observation_id)

                _validate_source_context(
                    context,
                    command.source_observation_id,
                    command.source_record,
                )
                if (
                    await repository.get_version_by_source_observation(
                        context.observation.id
                    )
                    is not None
                ):
                    raise SourceObservationAlreadyMaterializedError(
                        context.observation.id
                    )

                identity = (
                    context.observation.source_connection_id,
                    context.observation.external_job_id,
                )
                job = await repository.get_by_source_identity(
                    *identity,
                    for_update=True,
                )
                if job is None:
                    raise NewJobRequiredError(*identity)
                job_id = job.id

                current_version = await _get_current_version(
                    repository,
                    job.id,
                    for_update=True,
                )
                canonical_job = _map_source_record(
                    self._mapper,
                    command.source_observation_id,
                    command.source_record,
                )
                new_content_hash = _hash_canonical_job(
                    self._hasher,
                    command.source_observation_id,
                    canonical_job,
                )
                if new_content_hash == current_version.content_hash:
                    raise UnchangedJobRequiresFreshnessUpdateError(job.id)

                observed_at = context.observation.observed_at
                latest_known_at = max(
                    job.last_seen_at,
                    current_version.effective_from,
                )
                if observed_at <= latest_known_at:
                    raise StaleJobObservationError(
                        context.observation.id,
                        observed_at,
                        latest_known_at,
                    )

                historical_version = await repository.get_version_by_content_hash(
                    job.id,
                    new_content_hash,
                )
                if historical_version is not None:
                    raise HistoricalJobContentAlreadyExistsError(
                        job.id,
                        historical_version.id,
                    )

                new_version = _build_job_version(
                    job_id=job.id,
                    source_observation_id=context.observation.id,
                    version_number=current_version.version_number + 1,
                    canonical_job=canonical_job,
                    content_hash=new_content_hash,
                    effective_from=observed_at,
                )

                current_version.is_current = False
                current_version.effective_to = observed_at
                await repository.flush()
                await repository.add_version(new_version)

                changes = diff_job_versions(
                    _build_comparable_version(current_version),
                    _build_comparable_version(new_version),
                )
                if not changes:
                    raise JobDiffInvariantError(job.id)

                await repository.add_change_events(
                    _build_job_change_events(
                        job_id=job.id,
                        from_version_id=current_version.id,
                        to_version_id=new_version.id,
                        detected_at=observed_at,
                        changes=changes,
                    )
                )
                await repository.advance_last_seen_at(job, observed_at)

                result = ChangedJobResult(
                    job_id=job.id,
                    previous_version_id=current_version.id,
                    new_version_id=new_version.id,
                    previous_version_number=current_version.version_number,
                    new_version_number=new_version.version_number,
                    previous_content_hash=current_version.content_hash,
                    new_content_hash=new_version.content_hash,
                    observed_at=observed_at,
                )
        except IntegrityError as error:
            constraint_name = _find_constraint_name(error)
            if constraint_name == _OBSERVATION_VERSION_CONSTRAINT:
                raise SourceObservationAlreadyMaterializedError(
                    command.source_observation_id
                ) from error
            if constraint_name == _CONTENT_HASH_CONSTRAINT and job_id is not None:
                raise HistoricalJobContentAlreadyExistsError(job_id) from error
            raise ChangedJobDatabaseError(command.source_observation_id) from error
        except SQLAlchemyError as error:
            raise ChangedJobDatabaseError(command.source_observation_id) from error

        logger.info(
            "changed_job_observation_applied",
            extra={
                "source_observation_id": str(command.source_observation_id),
                "job_id": str(result.job_id),
                "previous_version_id": str(result.previous_version_id),
                "new_version_id": str(result.new_version_id),
                "new_version_number": result.new_version_number,
                "change_count": len(changes),
                "outcome": result.outcome,
            },
        )
        return result


async def _get_current_version(
    repository: JobRepository,
    job_id: UUID,
    *,
    for_update: bool = False,
) -> JobVersion:
    try:
        if for_update:
            current_version = await repository.get_current_version(
                job_id,
                for_update=True,
            )
        else:
            current_version = await repository.get_current_version(job_id)
    except MultipleResultsFound as error:
        raise CurrentJobVersionInvariantError(job_id) from error
    if current_version is None:
        raise CurrentJobVersionMissingError(job_id)
    return current_version


def _build_comparable_version(version: JobVersion) -> JobVersionComparable:
    return JobVersionComparable(
        title=version.title,
        description=version.description,
        location_text=version.location_text,
        city=version.city,
        region=version.region,
        country_code=version.country_code,
        workplace_type=version.workplace_type,
        employment_type=version.employment_type,
        salary_min=version.salary_min,
        salary_max=version.salary_max,
        salary_currency=version.salary_currency,
        salary_period=version.salary_period,
        source_url=version.source_url,
        canonical_metadata=deepcopy(
            cast(dict[str, JsonValue], version.canonical_metadata)
        ),
    )


def _build_job_change_events(
    *,
    job_id: UUID,
    from_version_id: UUID,
    to_version_id: UUID,
    detected_at: datetime,
    changes: Sequence[FieldChange],
) -> list[JobChangeEvent]:
    return [
        JobChangeEvent(
            job_id=job_id,
            from_version_id=from_version_id,
            to_version_id=to_version_id,
            field_name=change.field_name,
            change_type=change.change_type.value,
            old_value=change.old_value,
            new_value=change.new_value,
            detected_at=detected_at,
        )
        for change in changes
    ]


def _build_job_version(
    *,
    job_id: UUID,
    source_observation_id: UUID,
    version_number: int,
    canonical_job: CanonicalJobInput,
    content_hash: str,
    effective_from: datetime,
) -> JobVersion:
    return JobVersion(
        job_id=job_id,
        source_observation_id=source_observation_id,
        version_number=version_number,
        content_hash=content_hash,
        title=canonical_job.title,
        description=canonical_job.description,
        location_text=canonical_job.location_text,
        city=canonical_job.city,
        region=canonical_job.region,
        country_code=canonical_job.country_code,
        workplace_type=canonical_job.workplace_type,
        employment_type=canonical_job.employment_type,
        salary_min=canonical_job.salary_min,
        salary_max=canonical_job.salary_max,
        salary_currency=canonical_job.salary_currency,
        salary_period=canonical_job.salary_period,
        source_url=str(canonical_job.source_url),
        source_published_at=canonical_job.source_published_at,
        source_updated_at=canonical_job.source_updated_at,
        effective_from=effective_from,
        effective_to=None,
        is_current=True,
        canonical_metadata=dict(canonical_job.canonical_metadata),
    )


def _validate_source_context(
    context: JobObservationContext,
    source_observation_id: UUID,
    source_record: GreenhouseJob,
) -> None:
    observation = context.observation
    supplied_external_job_id = str(source_record.id)
    if supplied_external_job_id != observation.external_job_id:
        raise SourceObservationRecordMismatchError(
            source_observation_id,
            observation.external_job_id,
            supplied_external_job_id,
        )
    if context.source_connection.provider != SourceProvider.GREENHOUSE.value:
        raise UnsupportedJobObservationProviderError(
            source_observation_id,
            context.source_connection.provider,
        )


def _map_source_record(
    mapper: CanonicalMapper,
    source_observation_id: UUID,
    source_record: GreenhouseJob,
) -> CanonicalJobInput:
    try:
        return mapper(source_record)
    except Exception as error:
        raise SourceRecordNormalizationError(source_observation_id) from error


def _hash_canonical_job(
    hasher: CanonicalHasher,
    source_observation_id: UUID,
    canonical_job: CanonicalJobInput,
) -> str:
    try:
        return hasher(canonical_job)
    except Exception as error:
        raise SourceRecordHashingError(source_observation_id) from error


def _find_constraint_name(error: IntegrityError) -> str | None:
    candidates: list[object] = [error, error.orig]
    cause = getattr(error.orig, "__cause__", None)
    context = getattr(error.orig, "__context__", None)
    candidates.extend((cause, context))

    for candidate in candidates:
        constraint_name = getattr(candidate, "constraint_name", None)
        if isinstance(constraint_name, str):
            return constraint_name
    return None
