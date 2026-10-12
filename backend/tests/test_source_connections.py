from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.companies.models import Company
from app.sources.models import SourceConnection, SourceProvider


@pytest.mark.asyncio
async def test_source_connection_persists_relationship_jsonb_and_defaults(
    db_session: AsyncSession,
) -> None:
    company = Company(name="Acme", slug="acme")
    source = SourceConnection(
        company=company,
        provider=SourceProvider.GREENHOUSE.value,
        external_account_key="acme",
        configuration={"include_content": True},
    )
    db_session.add(source)
    await db_session.flush()

    company_id = company.id
    source_id = source.id
    db_session.expunge_all()

    loaded_source = (
        await db_session.execute(
            select(SourceConnection)
            .options(joinedload(SourceConnection.company))
            .where(SourceConnection.id == source_id)
        )
    ).scalar_one()
    loaded_company = (
        await db_session.execute(
            select(Company)
            .options(selectinload(Company.source_connections))
            .where(Company.id == company_id)
        )
    ).scalar_one()

    assert loaded_source.company.id == company_id
    assert [item.id for item in loaded_company.source_connections] == [source_id]
    assert loaded_source.configuration == {"include_content": True}
    assert loaded_source.is_active is True
    assert loaded_source.last_successful_sync_at is None
    assert loaded_source.last_attempted_sync_at is None


@pytest.mark.asyncio
async def test_source_company_foreign_key_is_enforced(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                SourceConnection(
                    company_id=uuid4(),
                    provider=SourceProvider.GREENHOUSE.value,
                    external_account_key="missing-company",
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_provider_and_external_account_key_are_unique_together(
    db_session: AsyncSession,
) -> None:
    company = Company(name="Acme", slug="acme")
    db_session.add(company)
    await db_session.flush()
    db_session.add(
        SourceConnection(
            company_id=company.id,
            provider=SourceProvider.GREENHOUSE.value,
            external_account_key="acme",
        )
    )
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                SourceConnection(
                    company_id=company.id,
                    provider=SourceProvider.GREENHOUSE.value,
                    external_account_key="acme",
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_same_provider_allows_different_external_account_keys(
    db_session: AsyncSession,
) -> None:
    company = Company(name="Acme", slug="acme")
    db_session.add(company)
    await db_session.flush()
    db_session.add_all(
        [
            SourceConnection(
                company_id=company.id,
                provider=SourceProvider.GREENHOUSE.value,
                external_account_key="acme",
            ),
            SourceConnection(
                company_id=company.id,
                provider=SourceProvider.GREENHOUSE.value,
                external_account_key="other-company",
            ),
        ]
    )

    await db_session.flush()


@pytest.mark.asyncio
async def test_company_delete_is_restricted_while_source_exists(
    db_session: AsyncSession,
) -> None:
    company = Company(name="Acme", slug="acme")
    source = SourceConnection(
        company=company,
        provider=SourceProvider.GREENHOUSE.value,
        external_account_key="acme",
    )
    db_session.add(source)
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(delete(Company).where(Company.id == company.id))
