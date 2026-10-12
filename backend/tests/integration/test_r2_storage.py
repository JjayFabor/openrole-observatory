import asyncio
import os
from typing import cast
from uuid import uuid4

import boto3  # type: ignore[import-untyped]
import pytest

from app.config import Settings
from app.storage.errors import ObjectAlreadyExistsError
from app.storage.r2 import R2ObjectStorage, S3Client

RUN_R2_INTEGRATION_TESTS = os.getenv("RUN_R2_INTEGRATION_TESTS", "").lower() == "true"

pytestmark = pytest.mark.skipif(
    not RUN_R2_INTEGRATION_TESTS,
    reason="Set RUN_R2_INTEGRATION_TESTS=true to run against a private R2 test bucket",
)


@pytest.mark.asyncio
async def test_r2_storage_contract_against_real_bucket() -> None:
    settings = Settings()
    assert settings.r2_endpoint_url is not None
    assert settings.r2_access_key_id is not None
    assert settings.r2_secret_access_key is not None
    assert settings.r2_bucket_name is not None

    client = cast(
        S3Client,
        boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.r2_secret_access_key.get_secret_value(),
            region_name=settings.r2_region,
        ),
    )
    storage = R2ObjectStorage(client=client, bucket_name=settings.r2_bucket_name)
    key = f"integration-tests/{uuid4()}/test-object.json"
    data = b'{"hello":"r2"}'
    object_created = False

    try:
        assert await storage.exists(key=key) is False
        await storage.put_bytes(
            key=key,
            data=data,
            content_type="application/json",
        )
        object_created = True
        assert await storage.exists(key=key) is True
        assert await storage.get_bytes(key=key) == data

        with pytest.raises(ObjectAlreadyExistsError):
            await storage.put_bytes(
                key=key,
                data=b"replacement",
                content_type="application/json",
            )
    finally:
        if object_created:
            await asyncio.to_thread(
                client.delete_object,
                Bucket=settings.r2_bucket_name,
                Key=key,
            )
