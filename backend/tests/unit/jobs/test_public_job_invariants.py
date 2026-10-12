from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs.errors import CurrentJobVersionInvariantError
from app.jobs.public_query_service import PublicJobQueryService


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["list", "detail", "sitemap"])
async def test_public_jobs_reject_duplicate_current_versions(operation: str) -> None:
    # Real PostgreSQL prevents this state with uq_job_versions_current. Inject
    # an impossible read result to verify the defensive application boundary.
    job_id = uuid4()
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    session.execute.return_value = result
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=context)
    service = PublicJobQueryService(cast(async_sessionmaker[AsyncSession], factory))

    if operation == "list":
        result.one_or_none.return_value = MagicMock(id=job_id, current_count=2)
    elif operation == "detail":
        result.mappings.return_value.one_or_none.side_effect = MultipleResultsFound
    else:
        result.all.return_value = [MagicMock(id=job_id, current_count=2)]

    with pytest.raises(CurrentJobVersionInvariantError):
        if operation == "list":
            await service.list(limit=25, offset=0)
        elif operation == "detail":
            await service.get(job_id)
        else:
            await service.sitemap(limit=1000)
