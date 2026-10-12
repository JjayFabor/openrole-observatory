import subprocess
from pathlib import Path

import pytest
from dotenv import dotenv_values
from pydantic import ValidationError

from app.config import PROJECT_ROOT, Settings


def test_production_backend_template_contains_blank_secrets_and_explicit_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    path = PROJECT_ROOT / ".env.production.example"
    values = dotenv_values(path)
    assert values["APP_ENV"] == "production"
    assert values["OBJECT_STORAGE_BACKEND"] == "r2"
    for name in [
        "DATABASE_URL",
        "POSTGRES_PASSWORD",
        "R2_ENDPOINT_URL",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
    ]:
        assert values[name] == ""
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(_env_file=path)


def test_secret_environment_files_are_ignored_but_templates_are_trackable(
    tmp_path: Path,
) -> None:
    # Check real Git semantics without initializing or changing the user's repository.
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text((PROJECT_ROOT / ".gitignore").read_text())
    ignored = [
        ".env",
        ".env.production",
        ".env.production.local",
        "frontend/.env.production",
        "frontend/.env.local",
        "backend/.env.production",
        ".aws/credentials",
        ".agents/settings.json",
        ".codex/config.toml",
    ]
    templates = [
        ".env.example",
        ".env.production.example",
        "frontend/.env.example",
        "frontend/.env.production.example",
    ]
    for path in ignored + templates:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).touch()
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", path], cwd=tmp_path, check=False
        )
        assert result.returncode == (0 if path in ignored else 1), path
