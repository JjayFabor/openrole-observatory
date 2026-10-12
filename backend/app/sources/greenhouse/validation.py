import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pydantic import ValidationError

from app.sources.greenhouse.errors import GreenhouseResponseShapeError
from app.sources.greenhouse.schemas import GreenhouseJob, GreenhouseJobBoardResponse

GREENHOUSE_RECORD_INVALID = "GREENHOUSE_RECORD_INVALID"


@dataclass(frozen=True, slots=True)
class InvalidGreenhouseRecord:
    index: int
    external_job_id: str | None
    error_code: str
    error_message: str


@dataclass(frozen=True, slots=True)
class ValidatedGreenhouseRecord:
    index: int
    source_record: GreenhouseJob
    raw_record: dict[str, object]


@dataclass(frozen=True, slots=True)
class GreenhouseValidationResult:
    valid_records: tuple[GreenhouseJob, ...]
    invalid_records: tuple[InvalidGreenhouseRecord, ...]
    validated_records: tuple[ValidatedGreenhouseRecord, ...]


def parse_greenhouse_response(
    raw_json: str | bytes | bytearray,
) -> GreenhouseValidationResult:
    """Decode and validate one raw Greenhouse job-board response."""

    try:
        raw_data: object = json.loads(raw_json)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise GreenhouseResponseShapeError(
            "Greenhouse response is not valid JSON."
        ) from None

    return validate_greenhouse_response(raw_data)


def validate_greenhouse_response(raw_data: object) -> GreenhouseValidationResult:
    """Validate the response envelope first, then isolate invalid child records."""

    try:
        response = GreenhouseJobBoardResponse.model_validate(raw_data)
    except ValidationError as error:
        raise GreenhouseResponseShapeError(
            f"Greenhouse response has an invalid top-level shape: {_summarize(error)}"
        ) from None

    valid_records: list[GreenhouseJob] = []
    invalid_records: list[InvalidGreenhouseRecord] = []
    validated_records: list[ValidatedGreenhouseRecord] = []

    for index, raw_record in enumerate(response.jobs):
        try:
            source_record = GreenhouseJob.model_validate(raw_record)
        except ValidationError as error:
            invalid_records.append(
                InvalidGreenhouseRecord(
                    index=index,
                    external_job_id=_extract_external_job_id(raw_record),
                    error_code=GREENHOUSE_RECORD_INVALID,
                    error_message=_summarize(error),
                )
            )
        else:
            if not isinstance(raw_record, Mapping):
                raise AssertionError("validated Greenhouse record must be a mapping")
            raw_record_mapping = cast(Mapping[str, object], raw_record)
            valid_records.append(source_record)
            validated_records.append(
                ValidatedGreenhouseRecord(
                    index=index,
                    source_record=source_record,
                    raw_record=dict(raw_record_mapping),
                )
            )

    return GreenhouseValidationResult(
        valid_records=tuple(valid_records),
        invalid_records=tuple(invalid_records),
        validated_records=tuple(validated_records),
    )


def _extract_external_job_id(raw_record: object) -> str | None:
    if not isinstance(raw_record, Mapping):
        return None

    raw_id = raw_record.get("id")
    if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
        return None
    return str(raw_id)


def _summarize(error: ValidationError) -> str:
    errors = error.errors(include_url=False, include_input=False)
    if not errors:
        return "Source value failed validation."

    first_error = errors[0]
    location = ".".join(str(part) for part in first_error["loc"])
    message = str(first_error["msg"])
    prefix = f"{location}: " if location else ""

    if len(errors) == 1:
        return f"{prefix}{message}"
    return f"{len(errors)} validation errors; first: {prefix}{message}"
