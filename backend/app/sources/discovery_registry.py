"""Register a positively identified Greenhouse board in a short transaction."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.companies.models import Company
from app.sources.greenhouse.discovery import TOKEN_PATTERN, DirectoryError, NativeBoard
from app.sources.models import SourceConnection, SourceProvider
from app.storage.base import StoredObject


@dataclass(frozen=True, slots=True)
class RegisteredBoard:
    source_id: UUID
    created: bool


class _ConcurrentRegistration(Exception):
    pass


async def find_greenhouse_source(
    session_factory: async_sessionmaker[AsyncSession], token: str
) -> UUID | None:
    async with session_factory() as session:
        return await session.scalar(
            select(SourceConnection.id).where(
                SourceConnection.provider == SourceProvider.GREENHOUSE.value,
                SourceConnection.external_account_key == token,
            )
        )


async def register_discovered_board(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    token: str,
    board: NativeBoard,
    directory_url: str,
    directory_snapshot: StoredObject,
    board_snapshot: StoredObject,
    discovered_at: datetime,
) -> RegisteredBoard:
    if not TOKEN_PATTERN.fullmatch(token):
        raise DirectoryError("BOARD_TOKEN_INVALID")
    slug = "gh-board-" + hashlib.sha256(token.encode()).hexdigest()
    try:
        async with session_factory.begin() as session:
            existing = await session.scalar(
                select(SourceConnection.id).where(
                    SourceConnection.provider == SourceProvider.GREENHOUSE.value,
                    SourceConnection.external_account_key == token,
                )
            )
            if existing is not None:
                return RegisteredBoard(existing, False)
            company_id = await session.scalar(
                insert(Company)
                .values(
                    name=board.name,
                    slug=slug,
                    careers_url=f"https://job-boards.greenhouse.io/{token}",
                )
                .on_conflict_do_nothing(index_elements=[Company.slug])
                .returning(Company.id)
            )
            if company_id is None:
                company = (
                    await session.execute(
                        select(Company.id, Company.name).where(Company.slug == slug)
                    )
                ).one()
                if company.name != board.name:
                    raise DirectoryError("DISCOVERY_COMPANY_CONFLICT")
                company_id = company.id
            source_id = await session.scalar(
                insert(SourceConnection)
                .values(
                    company_id=company_id,
                    provider=SourceProvider.GREENHOUSE.value,
                    external_account_key=token,
                    configuration={
                        "discovery": {
                            "directory_url": directory_url,
                            "directory_object_key": directory_snapshot.key,
                            "directory_sha256": directory_snapshot.content_hash,
                            "board_object_key": board_snapshot.key,
                            "board_sha256": board_snapshot.content_hash,
                            "discovered_at": discovered_at.isoformat(),
                        }
                    },
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        SourceConnection.provider,
                        SourceConnection.external_account_key,
                    ]
                )
                .returning(SourceConnection.id)
            )
            if source_id is None:
                # Roll back a newly inserted company if manual registration won.
                raise _ConcurrentRegistration
            return RegisteredBoard(source_id, True)
    except _ConcurrentRegistration:
        existing = await find_greenhouse_source(session_factory, token)
        if existing is None:
            raise DirectoryError("DISCOVERY_REGISTRATION_CONFLICT") from None
        return RegisteredBoard(existing, False)
