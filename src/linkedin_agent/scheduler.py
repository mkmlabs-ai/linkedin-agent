"""macOS launchd jobs: one LaunchAgent per slot, generated from config."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .settings import SLOTS, Config, Paths

LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


def label(cfg: Config, slot: str) -> str:
    return f"{cfg.label_prefix}.{slot}"


def build_plist(paths: Paths, cfg: Config, slot: str, env_path: str) -> bytes:
    hour, minute = cfg.schedule_times[slot]
    return plistlib.dumps(
        {
            "Label": label(cfg, slot),
            "ProgramArguments": [sys.executable, str(paths.root / "bin" / "li"), "run", slot],
            "WorkingDirectory": str(paths.root),
            # launchd starts jobs with a bare PATH; keep the installer's PATH so
            # `claude`, the browser CLI and the notify command resolve.
            "EnvironmentVariables": {"PATH": env_path, "LINKEDIN_AGENT_HOME": str(paths.root)},
            "StartCalendarInterval": {"Hour": hour, "Minute": minute},
            "StandardOutPath": str(paths.logs / f"launchd-{slot}.out"),
            "StandardErrorPath": str(paths.logs / f"launchd-{slot}.err"),
        }
    )


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=False)


def uninstall(cfg: Config, agents_dir: Path = LAUNCH_AGENTS) -> None:
    domain = f"gui/{os.getuid()}"
    for slot in SLOTS:
        _launchctl("bootout", f"{domain}/{label(cfg, slot)}")
        (agents_dir / f"{label(cfg, slot)}.plist").unlink(missing_ok=True)


def install(paths: Paths, cfg: Config, agents_dir: Path = LAUNCH_AGENTS) -> list[str]:
    uninstall(cfg, agents_dir)
    paths.logs.mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)
    domain = f"gui/{os.getuid()}"
    installed = []
    for slot in cfg.schedule_times:
        plist = agents_dir / f"{label(cfg, slot)}.plist"
        plist.write_bytes(build_plist(paths, cfg, slot, os.environ.get("PATH", "/usr/bin:/bin")))
        res = _launchctl("bootstrap", domain, str(plist))
        if res.returncode != 0:
            raise RuntimeError(f"launchctl bootstrap {plist.name} failed: {res.stderr.strip()}")
        installed.append(label(cfg, slot))
    return installed


def loaded(cfg: Config) -> list[str]:
    out = _launchctl("list").stdout
    return [line.split()[-1] for line in out.splitlines() if cfg.label_prefix in line]
