import hashlib
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.errors import (
    PipelineRunNotRunningError,
    RawSnapshotAlreadyProcessedError,
    RawSnapshotIntegrityError,
    RawSnapshotNotFoundError,
    RawSnapshotPipelineMismatchError,
    UnsupportedSourceProviderError,
)
from app.pipeline_runs.models import PipelineRunStatus
from app.source_observations.models import SourceObservation
from app.source_observations.repository import (
    SourceObservationRepository,
    SourceProcessingContext,
)
from app.source_observations.source_records import (
    build_raw_record_locator,
    compute_source_content_hash,
)
from app.sources.greenhouse.schemas import GreenhouseJob
from app.sources.greenhouse.validation import (
    GreenhouseValidationResult,
    parse_greenhouse_response,
)
from app.sources.models import SourceProvider
from app.storage.base import ObjectStorage

logger = logging.getLogger(__name__)

RECORD_VALIDATION_FAILED = "record_validation_failed"
DUPLICATE_SOURCE_IDENTIFIER = "duplicate_source_identifier"


@dataclass(frozen=True, slots=True)
class ProcessedSourceRecord:
    observation_id: UUID
    raw_record_locator: str
    source_record: GreenhouseJob


@dataclass(frozen=True, slots=True)
class InvalidProcessedSourceRecord:
    source_record_index: int
    raw_record_locator: str
    external_job_id: str | None
    error_category: str
    error_code: str | None
    error_message: str
    error_details: dict[str, object]


@dataclass(frozen=True, slots=True)
class SourceRecordProcessingResult:
    records_fetched: int
    valid_records: tuple[ProcessedSourceRecord, ...]
    invalid_records: tuple[InvalidProcessedSourceRecord, ...]

    @property
    def records_valid(self) -> int:
        return len(self.valid_records)

    @property
    def records_invalid(self) -> int:
        return len(self.invalid_records)


@dataclass(frozen=True, slots=True)
class _PreparedSourceRecord:
    source_record_index: int
    raw_record_locator: str
    external_job_id: str
    source_content_hash: str
    source_record: GreenhouseJob


class SourceRecordProcessingService:
    """Validate one stored Greenhouse snapshot and persist its observations."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        object_storage: ObjectStorage,
    ) -> None:
        self._session_factory = session_factory
        self._object_storage = object_storage

    async def process_raw_snapshot(
        self,
        *,
        pipeline_run_id: UUID,
        raw_snapshot_id: UUID,
    ) -> SourceRecordProcessingResult:
        context = await self._load_context(raw_snapshot_id)
        self._validate_context(context, pipeline_run_id)

        log_fields = {
            "pipeline_run_id": str(pipeline_run_id),
            "raw_snapshot_id": str(raw_snapshot_id),
            "source_connection_id": str(context.source_connection.id),
            "provider": context.source_connection.provider,
        }
        logger.info("source_snapshot_processing_started", extra=log_fields)
        raw_bytes = await self._object_storage.get_bytes(
            key=context.raw_snapshot.r2_object_key
        )
        logger.info(
            "source_snapshot_loaded",
            extra={**log_fields, "content_length_bytes": len(raw_bytes)},
        )
        self._verify_integrity(context, raw_bytes)
        logger.info("source_snapshot_integrity_verified", extra=log_fields)

        validation_result = parse_greenhouse_response(raw_bytes)
        prepared_records, invalid_records = self._prepare_records(validation_result)
        record_count = len(validation_result.validated_records) + len(
            validation_result.invalid_records
        )
        observations = await self._persist_observations(
            pipeline_run_id=pipeline_run_id,
            raw_snapshot_id=raw_snapshot_id,
            prepared_records=prepared_records,
            record_count=record_count,
        )
        valid_records = tuple(
            ProcessedSourceRecord(
                observation_id=observation.id,
                raw_record_locator=prepared.raw_record_locator,
                source_record=prepared.source_record,
            )
            for prepared, observation in zip(
                prepared_records,
                observations,
                strict=True,
            )
        )
        result = SourceRecordProcessingResult(
            records_fetched=record_count,
            valid_records=valid_records,
            invalid_records=invalid_records,
        )
        logger.info(
            "source_snapshot_processing_completed",
            extra={
                **log_fields,
                "records_fetched": result.records_fetched,
                "records_valid": result.records_valid,
                "records_invalid": result.records_invalid,
            },
        )
        return result

    async def _load_context(self, raw_snapshot_id: UUID) -> SourceProcessingContext:
        async with self._session_factory() as session:
            context = await SourceObservationRepository(session).get_processing_context(
                raw_snapshot_id
            )
        if context is None:
            raise RawSnapshotNotFoundError(raw_snapshot_id)
        return context

    async def _persist_observations(
        self,
        *,
        pipeline_run_id: UUID,
        raw_snapshot_id: UUID,
        prepared_records: tuple[_PreparedSourceRecord, ...],
        record_count: int,
    ) -> list[SourceObservation]:
        async with self._session_factory.begin() as session:
            repository = SourceObservationRepository(session)
            context = await repository.get_processing_context(
                raw_snapshot_id,
                for_update=True,
            )
            if context is None:
                raise RawSnapshotNotFoundError(raw_snapshot_id)
            self._validate_context(context, pipeline_run_id)

            observations = [
                SourceObservation(
                    pipeline_run_id=context.pipeline_run.id,
                    source_connection_id=context.source_connection.id,
                    raw_snapshot_id=context.raw_snapshot.id,
                    external_job_id=record.external_job_id,
                    raw_record_locator=record.raw_record_locator,
                    source_content_hash=record.source_content_hash,
                    observed_at=context.raw_snapshot.retrieved_at,
                    source_metadata={"source_record_index": record.source_record_index},
                )
                for record in prepared_records
            ]
            await repository.persist_processing_result(
                raw_snapshot=context.raw_snapshot,
                record_count=record_count,
                observations=observations,
            )

        logger.info(
            "source_observations_persisted",
            extra={
                "pipeline_run_id": str(pipeline_run_id),
                "raw_snapshot_id": str(raw_snapshot_id),
                "observation_count": len(observations),
            },
        )
        return observations

    @staticmethod
    def _verify_integrity(
        context: SourceProcessingContext,
        raw_bytes: bytes,
    ) -> None:
        actual_hash = hashlib.sha256(raw_bytes).hexdigest()
        if actual_hash != context.raw_snapshot.content_hash:
            raise RawSnapshotIntegrityError(
                context.raw_snapshot.id,
                "SHA-256 hash does not match stored metadata",
            )
        expected_size = context.raw_snapshot.content_length_bytes
        if expected_size is not None and len(raw_bytes) != expected_size:
            raise RawSnapshotIntegrityError(
                context.raw_snapshot.id,
                "byte length does not match stored metadata",
            )

    @staticmethod
    def _prepare_records(
        validation_result: GreenhouseValidationResult,
    ) -> tuple[
        tuple[_PreparedSourceRecord, ...],
        tuple[InvalidProcessedSourceRecord, ...],
    ]:
        prepared_records: list[_PreparedSourceRecord] = []
        invalid_records = [
            InvalidProcessedSourceRecord(
                source_record_index=record.index,
                raw_record_locator=build_raw_record_locator(record.index),
                external_job_id=record.external_job_id,
                error_category=RECORD_VALIDATION_FAILED,
                error_code=record.error_code,
                error_message=record.error_message,
                error_details={"source_record_index": record.index},
            )
            for record in validation_result.invalid_records
        ]
        first_locator_by_external_id: dict[str, str] = {}

        for record in validation_result.validated_records:
            external_job_id = str(record.source_record.id)
            locator = build_raw_record_locator(record.index)
            first_locator = first_locator_by_external_id.get(external_job_id)
            if first_locator is not None:
                invalid_records.append(
                    InvalidProcessedSourceRecord(
                        source_record_index=record.index,
                        raw_record_locator=locator,
                        external_job_id=external_job_id,
                        error_category=DUPLICATE_SOURCE_IDENTIFIER,
                        error_code="DUPLICATE_SOURCE_IDENTIFIER",
                        error_message=(
                            f"External job ID {external_job_id} already appeared at "
                            f"{first_locator}."
                        ),
                        error_details={
                            "source_record_index": record.index,
                            "first_occurrence_locator": first_locator,
                        },
                    )
                )
                continue

            first_locator_by_external_id[external_job_id] = locator
            prepared_records.append(
                _PreparedSourceRecord(
                    source_record_index=record.index,
                    raw_record_locator=locator,
                    external_job_id=external_job_id,
                    source_content_hash=compute_source_content_hash(record.raw_record),
                    source_record=record.source_record,
                )
            )

        invalid_records.sort(key=lambda record: record.source_record_index)
        return tuple(prepared_records), tuple(invalid_records)

    @staticmethod
    def _validate_context(
        context: SourceProcessingContext,
        supplied_pipeline_run_id: UUID,
    ) -> None:
        if context.pipeline_run.id != supplied_pipeline_run_id:
            raise RawSnapshotPipelineMismatchError(
                context.raw_snapshot.id,
                context.pipeline_run.id,
                supplied_pipeline_run_id,
            )
        if context.raw_snapshot.record_count is not None or context.has_observations:
            raise RawSnapshotAlreadyProcessedError(context.raw_snapshot.id)
        if context.pipeline_run.status != PipelineRunStatus.RUNNING.value:
            raise PipelineRunNotRunningError(
                context.pipeline_run.id,
                context.pipeline_run.status,
            )
        if context.source_connection.provider != SourceProvider.GREENHOUSE.value:
            raise UnsupportedSourceProviderError(context.source_connection.provider)
