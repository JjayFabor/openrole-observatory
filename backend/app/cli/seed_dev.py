import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.companies.models import Company
from app.config import get_settings
from app.database.engine import create_database_engine
from app.database.session import create_session_factory
from app.sources.models import SourceConnection, SourceProvider

DEFAULT_COMPANY_NAME = "OpenRole Development Company"
DEFAULT_COMPANY_SLUG = "openrole-development"


@dataclass(frozen=True, slots=True)
class SeedDevResult:
    company_id: UUID
    source_connection_id: UUID
    source_created: bool


async def seed_development_source(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    board_token: str,
    company_name: str = DEFAULT_COMPANY_NAME,
    company_slug: str = DEFAULT_COMPANY_SLUG,
) -> SeedDevResult:
    normalized_token = _non_blank(board_token, "board_token")
    normalized_name = _non_blank(company_name, "company_name")
    normalized_slug = _non_blank(company_slug, "company_slug").lower()

    async with session_factory.begin() as session:
        existing_source = await session.scalar(
            select(SourceConnection).where(
                SourceConnection.provider == SourceProvider.GREENHOUSE.value,
                SourceConnection.external_account_key == normalized_token,
            )
        )
        if existing_source is not None:
            return SeedDevResult(
                company_id=existing_source.company_id,
                source_connection_id=existing_source.id,
                source_created=False,
            )

        company = await session.scalar(
            select(Company).where(func.lower(Company.slug) == normalized_slug)
        )
        if company is None:
            company = Company(name=normalized_name, slug=normalized_slug)
            session.add(company)
            await session.flush()

        source = SourceConnection(
            company_id=company.id,
            provider=SourceProvider.GREENHOUSE.value,
            external_account_key=normalized_token,
        )
        session.add(source)
        await session.flush()

        return SeedDevResult(
            company_id=company.id,
            source_connection_id=source.id,
            source_created=True,
        )


def format_result(result: SeedDevResult) -> str:
    action = "created" if result.source_created else "already exists"
    return "\n".join(
        [
            f"Development source {action}",
            "",
            f"Company: {result.company_id}",
            f"Source:  {result.source_connection_id}",
        ]
    )


async def run(
    *,
    board_token: str,
    company_name: str,
    company_slug: str,
) -> int:
    settings = get_settings()
    database_engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(database_engine)

    try:
        result = await seed_development_source(
            session_factory,
            board_token=board_token,
            company_name=company_name,
            company_slug=company_slug,
        )
        print(format_result(result))
        return 0
    finally:
        await database_engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create an idempotent development Greenhouse source.",
    )
    parser.add_argument("board_token", help="Public Greenhouse board token")
    parser.add_argument("--company-name", default=DEFAULT_COMPANY_NAME)
    parser.add_argument("--company-slug", default=DEFAULT_COMPANY_SLUG)
    arguments = parser.parse_args(argv)
    return asyncio.run(
        run(
            board_token=arguments.board_token,
            company_name=arguments.company_name,
            company_slug=arguments.company_slug,
        )
    )


def _non_blank(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())
