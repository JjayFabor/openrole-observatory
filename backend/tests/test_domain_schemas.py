from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.companies.models import Company
from app.companies.schemas import CompanyCreate, CompanyRead
from app.sources.models import SourceConnection, SourceProvider
from app.sources.schemas import SourceConnectionCreate, SourceConnectionRead


def test_create_schemas_reject_protected_system_fields() -> None:
    with pytest.raises(ValidationError):
        CompanyCreate.model_validate(
            {
                "id": str(uuid4()),
                "name": "Acme",
                "slug": "acme",
            }
        )

    with pytest.raises(ValidationError):
        SourceConnectionCreate.model_validate(
            {
                "company_id": str(uuid4()),
                "provider": "greenhouse",
                "external_account_key": "acme",
                "last_successful_sync_at": datetime.now(UTC).isoformat(),
            }
        )


def test_source_create_accepts_only_supported_provider() -> None:
    source = SourceConnectionCreate.model_validate(
        {
            "company_id": str(uuid4()),
            "provider": "greenhouse",
            "external_account_key": "acme",
        }
    )

    assert source.provider is SourceProvider.GREENHOUSE

    with pytest.raises(ValidationError):
        SourceConnectionCreate.model_validate(
            {
                "company_id": str(uuid4()),
                "provider": "lever",
                "external_account_key": "acme",
            }
        )


def test_read_schemas_validate_orm_objects() -> None:
    now = datetime.now(UTC)
    company_id = uuid4()
    company = Company(
        id=company_id,
        name="Acme",
        slug="acme",
        domain="acme.example",
        careers_url="https://careers.acme.example",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    source = SourceConnection(
        id=uuid4(),
        company_id=company_id,
        provider=SourceProvider.GREENHOUSE.value,
        external_account_key="acme",
        configuration={"include_content": True},
        is_active=True,
        last_successful_sync_at=None,
        last_attempted_sync_at=None,
        created_at=now,
        updated_at=now,
    )

    company_read = CompanyRead.model_validate(company)
    source_read = SourceConnectionRead.model_validate(source)

    assert company_read.id == company_id
    assert str(company_read.careers_url) == "https://careers.acme.example/"
    assert source_read.provider is SourceProvider.GREENHOUSE
    assert source_read.configuration == {"include_content": True}
