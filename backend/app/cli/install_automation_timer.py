"""Install the current user's external Greenhouse scheduler on Linux."""

import argparse
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

from app.config import PROJECT_ROOT

SERVICE_NAME = "openrole-greenhouse-automation.service"
TIMER_NAME = "openrole-greenhouse-automation.timer"
MANAGED_MARKER = "# Managed by OpenRole install_automation_timer"
CALENDAR = "*-*-* 00,06,12,18:00:00 Asia/Manila"


def unit_argument(value: Path) -> str:
    text = str(value)
    if any(ord(character) < 32 for character in text):
        raise ValueError("Unit paths must not contain control characters.")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def render_units(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    backend = root / "backend"
    executable = backend / ".venv/bin/python"
    service = f"""{MANAGED_MARKER}
[Unit]
Description=Discover and synchronize OpenRole Greenhouse sources

[Service]
Type=oneshot
WorkingDirectory={str(backend).replace("%", "%%")}
ExecStart={unit_argument(executable)} -m app.cli.automate_greenhouse
TimeoutStartSec=0
UMask=0077
"""
    # Settings reads PROJECT_ROOT/.env, as it does for the API and manual CLI.
    # Avoid EnvironmentFile's different parsing rules and duplicated secrets.
    timer = f"""{MANAGED_MARKER}
[Unit]
Description=Check OpenRole Greenhouse sources every six hours

[Timer]
OnCalendar={CALENDAR}
Persistent=true
Unit={SERVICE_NAME}

[Install]
WantedBy=timers.target
"""
    return {SERVICE_NAME: service, TIMER_NAME: timer}


def install_units(project_root: Path, unit_directory: Path) -> list[Path]:
    if not (project_root / "backend/.venv/bin/python").is_file():
        raise ValueError("Run uv sync in backend before installing the timer.")
    units = render_units(project_root)
    paths = [unit_directory / name for name in units]
    # Check both before writing either; preserve unrelated units and symlinks.
    for path in paths:
        if path.is_symlink() or (
            path.exists() and not path.read_text().startswith(MANAGED_MARKER + "\n")
        ):
            raise ValueError(f"Refusing to overwrite an unmanaged unit: {path}")
    unit_directory.mkdir(parents=True, exist_ok=True)
    for name, content in units.items():
        path = unit_directory / name
        path.write_text(content)
        path.chmod(0o600)
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-now", action="store_true")
    args = parser.parse_args(argv)
    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    try:
        paths = install_units(PROJECT_ROOT, config_root / "systemd/user")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", TIMER_NAME], check=True
        )
        if args.start_now:
            subprocess.run(
                ["systemctl", "--user", "start", "--no-block", SERVICE_NAME], check=True
            )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Timer installation failed: {error}")
        return 1
    print("Installed: " + ", ".join(str(path) for path in paths))
    print("Schedule: 00:00, 06:00, 12:00, 18:00 Asia/Manila.")
    print(f"Inspect: systemctl --user status {TIMER_NAME}")
    print(f"Logs: journalctl --user -u {SERVICE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
