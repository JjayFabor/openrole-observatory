"""Bounded public catalogue input; job facts still come from the native pipeline."""

import re
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

DEFAULT_DIRECTORY_URL = (
    "https://raw.githubusercontent.com/moonie0201/ats-directory/main/companies.jsonl"
)
MAX_DIRECTORY_BYTES = 2_000_000
MAX_DIRECTORY_ROWS = 20_000
MAX_BOARD_METADATA_BYTES = 1_000_000
TOKEN_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,199}\Z")


class DirectoryError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__("The source directory could not be used.")
        self.code = code


class DirectoryRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    provider: StrictStr
    slug: StrictStr
    status: StrictStr
    region: StrictStr | None = None
    site: StrictStr | None = None


class DirectoryCandidates(BaseModel):
    tokens: list[str] = Field(default_factory=list)
    excluded_rows: int = 0
    invalid_rows: int = 0
    duplicate_rows: int = 0


class NativeBoard(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: StrictStr = Field(min_length=1, max_length=500)


def parse_candidates(data: bytes) -> DirectoryCandidates:
    if len(data) > MAX_DIRECTORY_BYTES:
        raise DirectoryError("DIRECTORY_TOO_LARGE")
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise DirectoryError("DIRECTORY_INVALID_ENCODING") from error
    if len(lines) > MAX_DIRECTORY_ROWS:
        raise DirectoryError("DIRECTORY_TOO_MANY_ROWS")
    result = DirectoryCandidates()
    seen: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        try:
            row = DirectoryRow.model_validate_json(line)
        except ValidationError:
            result.invalid_rows += 1
            continue
        if row.provider != "greenhouse" or row.status != "ok":
            result.excluded_rows += 1
            continue
        if row.region not in (None, "us") or row.site is not None:
            result.excluded_rows += 1
            continue
        if not TOKEN_PATTERN.fullmatch(row.slug):
            result.invalid_rows += 1
            continue
        if row.slug in seen:
            result.duplicate_rows += 1
            continue
        seen.add(row.slug)
        result.tokens.append(row.slug)
    result.tokens.sort()
    return result


def parse_native_board(data: bytes) -> NativeBoard:
    if len(data) > MAX_BOARD_METADATA_BYTES:
        raise DirectoryError("BOARD_METADATA_TOO_LARGE")
    try:
        board = NativeBoard.model_validate_json(data)
        name = board.name.strip()
        if not name or any(ord(character) < 32 for character in name):
            raise ValueError("Invalid native board name")
        return board.model_copy(update={"name": name})
    except (ValidationError, ValueError) as error:
        raise DirectoryError("BOARD_METADATA_INVALID") from error


def validate_directory_url(value: str) -> str:
    try:
        url = urlsplit(value)
        valid = (
            url.scheme == "https"
            and url.hostname == "raw.githubusercontent.com"
            and url.port in (None, 443)
            and url.username is None
            and url.password is None
            and not url.query
            and not url.fragment
            and url.path.endswith(".jsonl")
        )
    except ValueError:
        valid = False
    if not valid:
        raise DirectoryError("DIRECTORY_URL_INVALID")
    return value


async def fetch_directory(client: httpx.AsyncClient, url: str) -> bytes:
    validate_directory_url(url)
    try:
        async with client.stream(
            "GET",
            url,
            follow_redirects=False,
            timeout=httpx.Timeout(30.0, connect=5.0),
            headers={"User-Agent": "OpenRoleObservatory/0.1.0"},
        ) as response:
            if response.status_code != 200:
                raise DirectoryError("DIRECTORY_REQUEST_FAILED")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_DIRECTORY_BYTES:
                    raise DirectoryError("DIRECTORY_TOO_LARGE")
            return bytes(data)
    except httpx.HTTPError as error:
        raise DirectoryError("DIRECTORY_REQUEST_FAILED") from error
