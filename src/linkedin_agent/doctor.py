"""Environment check used by `bin/li doctor` and the setup wizard."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from . import scheduler
from .settings import ConfigError, Paths, load_config


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""


def _which(cmd: str) -> str | None:
    # Installers often put CLIs in ~/.local/bin, which a fresh shell may not have on PATH yet.
    extra = os.pathsep.join([str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin", "/usr/local/bin"])
    return shutil.which(cmd) or shutil.which(cmd, path=extra)


def _version(cmd: str) -> str:
    try:
        out = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr).strip() else ""


def _is_template(paths: Paths, name: str, template: str) -> bool:
    target, source = paths.data / name, paths.templates / template
    return not target.exists() or (source.exists() and target.read_text() == source.read_text())


def run_checks(paths: Paths) -> list[Check]:
    checks = [
        Check(
            "python",
            sys.version_info >= (3, 9),
            sys.version.split()[0],
            "Install Python 3.9 or newer.",
        ),
        Check(
            "macos",
            sys.platform == "darwin",
            sys.platform,
            "Scheduling needs macOS (launchd). Sessions can still be run by hand.",
        ),
    ]

    claude = _which("claude")
    checks.append(
        Check(
            "claude",
            bool(claude),
            _version(claude) if claude else "not found",
            "Install Claude Code: curl -fsSL https://claude.ai/install.sh | bash",
        )
    )

    ego = _which("ego-browser")
    app = next(
        (p for p in (Path("/Applications/ego lite.app"), Path.home() / "Applications" / "ego lite.app") if p.exists()),
        None,
    )
    checks.append(
        Check(
            "ego_lite",
            bool(ego and app),
            f"app: {app or 'not found'}, cli: {ego or 'not found'}",
            "Install Ego Lite from https://lite.ego.app/ and finish its onboarding (it adds `ego-browser`).",
        )
    )

    try:
        cfg = load_config(paths)
        checks.append(Check("config", True, f"mode={cfg.mode}, language={cfg.language}"))
    except ConfigError as exc:
        cfg = None
        checks.append(Check("config", False, str(exc), "Run `bin/li init`, then the setup wizard."))

    for name, template in (("voice.md", "voice.example.md"), ("topics.md", "topics.example.md")):
        empty = _is_template(paths, name, template)
        checks.append(
            Check(
                name,
                not empty,
                "still the template" if empty else "filled in",
                f"Fill in data/{name} (the setup wizard does it for you).",
            )
        )

    if cfg and sys.platform == "darwin":
        loaded = scheduler.loaded(cfg)
        checks.append(
            Check(
                "schedule",
                len(loaded) == len(cfg.schedule_times),
                ", ".join(loaded) or "not installed",
                "Run `bin/li schedule on`.",
            )
        )

    checks.append(
        Check(
            "stop_file",
            not paths.stop.exists(),
            "present: sessions are paused" if paths.stop.exists() else "absent",
            "Run `bin/li resume` when you want the agent to work again.",
        )
    )
    return checks


def as_dicts(checks: list[Check]) -> list[dict]:
    return [asdict(c) for c in checks]
