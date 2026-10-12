import argparse
import asyncio
import sys
from collections.abc import Sequence
from uuid import UUID

from app.composition import build_runtime_services
from app.config import get_settings
from app.database.engine import create_database_engine
from app.database.session import create_session_factory
from app.ingestion.errors import SourceSyncFailedError
from app.ingestion.orchestration import PIPELINE_INTERNAL_ERROR
from app.ingestion.sync import SourceSyncResult
from app.pipeline_runs.errors import (
    SourceConnectionInactiveError,
    SourceConnectionNotFoundError,
    SourceSyncAlreadyRunningError,
)


def format_success(result: SourceSyncResult) -> str:
    lines = [
        "OpenRole source sync completed",
        "",
        f"Source:      {result.source_connection_id}",
        f"Run:         {result.pipeline_run_id}",
        f"Status:      {result.status.value}",
        "",
        f"Fetched:     {result.records_fetched}",
        f"Valid:       {result.records_valid}",
        f"Quarantined: {result.records_quarantined}",
        "",
        f"New:         {result.jobs_new}",
        f"Changed:     {result.jobs_changed}",
        f"Unchanged:   {result.jobs_unchanged}",
    ]
    if result.lifecycle is not None:
        lines.extend(["", "Lifecycle:"])
        if result.lifecycle.performed:
            lines.extend(
                [
                    f"First absences:    {result.lifecycle.first_absences_detected}",
                    f"Confirmed absent:  {result.lifecycle.jobs_confirmed_not_observed}",
                    f"Reappeared:        {result.lifecycle.jobs_reappeared}",
                    f"Absences reset:    {result.lifecycle.tentative_absences_reset}",
                ]
            )
        else:
            lines.append("Skipped — source membership incomplete")
    return "\n".join(lines)


def format_failure(*, code: str, pipeline_run_id: UUID | None = None) -> str:
    lines = ["Source sync failed", ""]
    if pipeline_run_id is not None:
        lines.append(f"Run:  {pipeline_run_id}")
    lines.append(f"Code: {code}")
    return "\n".join(lines)


async def run(source_connection_id: UUID) -> int:
    settings = get_settings()
    database_engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(database_engine)

    try:
        async with build_runtime_services(
            settings=settings,
            database_engine=database_engine,
            session_factory=session_factory,
        ) as services:
            try:
                result = await services.source_sync.sync_source(source_connection_id)
            except SourceSyncFailedError as error:
                print(
                    format_failure(
                        code=error.code,
                        pipeline_run_id=error.pipeline_run_id,
                    ),
                    file=sys.stderr,
                )
                return 1
            except (
                SourceConnectionNotFoundError,
                SourceConnectionInactiveError,
                SourceSyncAlreadyRunningError,
            ) as error:
                print(format_failure(code=error.code), file=sys.stderr)
                return 1

            print(format_success(result))
            return 0
    except Exception:
        print(format_failure(code=PIPELINE_INTERNAL_ERROR), file=sys.stderr)
        return 1
    finally:
        await database_engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synchronize one OpenRole source.")
    parser.add_argument("source_connection_id", type=UUID)
    arguments = parser.parse_args(argv)
    return asyncio.run(run(arguments.source_connection_id))


if __name__ == "__main__":
    raise SystemExit(main())
