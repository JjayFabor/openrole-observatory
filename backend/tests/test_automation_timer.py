import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.cli.install_automation_timer import (
    CALENDAR,
    MANAGED_MARKER,
    SERVICE_NAME,
    TIMER_NAME,
    install_units,
    render_units,
)


def test_units_use_absolute_quoted_paths_and_external_six_hour_calendar(
    tmp_path: Path,
) -> None:
    root = tmp_path / "space and %specifier"
    units = render_units(root)
    service, timer = units[SERVICE_NAME], units[TIMER_NAME]
    assert (
        'ExecStart="'
        + str(root).replace("%", "%%")
        + '/backend/.venv/bin/python" -m app.cli.automate_greenhouse'
        in service
    )
    assert "TimeoutStartSec=0" in service
    assert "WorkingDirectory=" + str(root).replace("%", "%%") + "/backend\n" in service
    assert "UMask=0077" in service
    assert f"OnCalendar={CALENDAR}" in timer
    assert "Persistent=true" in timer
    assert f"Unit={SERVICE_NAME}" in timer


def test_installer_preserves_unmanaged_units_before_writing_anything(
    tmp_path: Path,
) -> None:
    root, units = tmp_path / "repo", tmp_path / "units"
    executable = root / "backend/.venv/bin/python"
    executable.parent.mkdir(parents=True)
    executable.touch()
    units.mkdir()
    (units / TIMER_NAME).write_text("user's existing timer\n")
    with pytest.raises(ValueError, match="unmanaged"):
        install_units(root, units)
    assert not (units / SERVICE_NAME).exists()
    assert (units / TIMER_NAME).read_text() == "user's existing timer\n"
    (units / TIMER_NAME).write_text(MANAGED_MARKER + "\nold managed timer")
    assert len(install_units(root, units)) == 2
    assert (units / TIMER_NAME).read_text() == render_units(root)[TIMER_NAME]
    assert (units / SERVICE_NAME).stat().st_mode & 0o777 == 0o600


def _systemd_user_manager_available() -> bool:
    """`systemd-analyze --user verify` needs a running user manager, not just the binary."""
    if shutil.which("systemd-analyze") is None or shutil.which("systemctl") is None:
        return False
    result = subprocess.run(
        ["systemctl", "--user", "show-environment"],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


@pytest.mark.skipif(
    not _systemd_user_manager_available(),
    reason="systemd user manager is unavailable",
)
def test_systemd_parses_generated_units_without_starting_them(tmp_path: Path) -> None:
    root = tmp_path / "repo space%"
    executable = root / "backend/.venv/bin/python"
    executable.parent.mkdir(parents=True)
    executable.symlink_to(sys.executable)
    paths = install_units(root, tmp_path / "units")
    result = subprocess.run(
        ["systemd-analyze", "--user", "--man=no", "verify", *map(str, paths)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
