from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_script_directory_is_configured_without_credentials() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)

    assert Path(scripts.dir) == BACKEND_ROOT / "migrations"
    assert config.get_main_option("sqlalchemy.url") is None


def test_alembic_has_one_head_for_task_24_schema() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["55c52c19c673"]
    assert scripts.get_revision("55c52c19c673").down_revision == "3e7f3cd24003"
