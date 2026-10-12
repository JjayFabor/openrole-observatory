import json

import httpx
import pytest

from app.sources.greenhouse.discovery import (
    DEFAULT_DIRECTORY_URL,
    MAX_DIRECTORY_BYTES,
    MAX_DIRECTORY_ROWS,
    DirectoryError,
    fetch_directory,
    parse_candidates,
    parse_native_board,
    validate_directory_url,
)


def catalogue(*rows: object) -> bytes:
    return "\n".join(json.dumps(row) for row in rows).encode()


def candidate(token: str, **overrides: object) -> dict[str, object]:
    return {"provider": "greenhouse", "slug": token, "status": "ok", **overrides}


def test_candidate_policy_is_bounded_deduplicated_and_provider_specific() -> None:
    data = (
        catalogue(
            candidate("Acme", name="Untrusted catalogue name"),
            candidate("beta"),
            candidate("Acme"),
            candidate("acme"),
            candidate("lever", provider="lever"),
            candidate("dead", status="dead"),
            candidate("regional", region="eu"),
            candidate("site", site="site-key"),
            candidate("../escape"),
            candidate("padded "),
            candidate("wrong", slug=12),
            {},
        )
        + b"\nnot-json\n"
    )
    report = parse_candidates(data)
    assert report.tokens == ["Acme", "acme", "beta"]
    assert report.duplicate_rows == 1
    assert report.excluded_rows == 4
    assert report.invalid_rows == 5


@pytest.mark.parametrize(
    "body, code",
    [
        (b"x" * (MAX_DIRECTORY_BYTES + 1), "DIRECTORY_TOO_LARGE"),
        (b"\n" * (MAX_DIRECTORY_ROWS + 1), "DIRECTORY_TOO_MANY_ROWS"),
        (b"\xff", "DIRECTORY_INVALID_ENCODING"),
    ],
)
def test_directory_limits_fail_visibly(body: bytes, code: str) -> None:
    with pytest.raises(DirectoryError) as error:
        parse_candidates(body)
    assert error.value.code == code


@pytest.mark.parametrize(
    "value",
    [
        "http://raw.githubusercontent.com/owner/repo/main/data.jsonl",
        "https://localhost/data.jsonl",
        "https://raw.githubusercontent.com.evil/data.jsonl",
        "https://user@raw.githubusercontent.com/data.jsonl",
        DEFAULT_DIRECTORY_URL + "?secret=value",
        DEFAULT_DIRECTORY_URL + "#fragment",
        "https://raw.githubusercontent.com:1234/data.jsonl",
        "https://raw.githubusercontent.com:invalid/data.jsonl",
    ],
)
def test_directory_url_disallows_other_hosts_credentials_and_redirect_inputs(
    value: str,
) -> None:
    with pytest.raises(DirectoryError):
        validate_directory_url(value)


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b'{"name":null}',
        b'{"name":123}',
        b'{"name":"   "}',
        b'{"name":"bad\\nname"}',
        b"not-json",
    ],
)
def test_native_metadata_requires_a_usable_official_name(body: bytes) -> None:
    with pytest.raises(DirectoryError) as error:
        parse_native_board(body)
    assert error.value.code == "BOARD_METADATA_INVALID"


def test_native_name_is_trimmed_without_inventing_company_data() -> None:
    assert (
        parse_native_board(b'{"name":"  Native Company  ","content":"ignored"}').name
        == "Native Company"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, content, code",
    [
        (302, b"", "DIRECTORY_REQUEST_FAILED"),
        (503, b"private response", "DIRECTORY_REQUEST_FAILED"),
        (200, b"x" * (MAX_DIRECTORY_BYTES + 1), "DIRECTORY_TOO_LARGE"),
    ],
)
async def test_directory_http_rejects_redirects_and_caps_stream(
    status: int, content: bytes, code: str
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                status,
                content=content,
                headers={"Location": "http://localhost/private"},
            )
        )
    ) as client:
        with pytest.raises(DirectoryError) as error:
            await fetch_directory(client, DEFAULT_DIRECTORY_URL)
    assert error.value.code == code


@pytest.mark.asyncio
async def test_directory_fetch_preserves_bytes_and_normalizes_transport_failure() -> (
    None
):
    body = catalogue(candidate("acme"))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    ) as client:
        assert await fetch_directory(client, DEFAULT_DIRECTORY_URL) == body

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private transport error", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(DirectoryError) as error:
            await fetch_directory(client, DEFAULT_DIRECTORY_URL)
    assert error.value.code == "DIRECTORY_REQUEST_FAILED"
