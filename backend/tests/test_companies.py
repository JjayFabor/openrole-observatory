import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company


@pytest.mark.asyncio
async def test_company_can_be_persisted_with_defaults(
    db_session: AsyncSession,
) -> None:
    company = Company(
        name="Acme Technologies",
        slug="acme-technologies",
        domain="acme.example",
        careers_url="https://careers.acme.example",
    )
    db_session.add(company)

    await db_session.flush()
    await db_session.refresh(company)

    assert company.id is not None
    assert company.is_active is True
    assert company.created_at.tzinfo is not None
    assert company.updated_at.tzinfo is not None


@pytest.mark.asyncio
async def test_company_slug_uniqueness_is_enforced(
    db_session: AsyncSession,
) -> None:
    db_session.add(Company(name="First Acme", slug="acme"))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(Company(name="Second Acme", slug="acme"))
            await db_session.flush()


@pytest.mark.asyncio
async def test_multiple_companies_may_share_a_name(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            Company(name="Acme", slug="acme-one"),
            Company(name="Acme", slug="acme-two"),
        ]
    )

    await db_session.flush()
