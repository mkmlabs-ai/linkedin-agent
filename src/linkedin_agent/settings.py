"""Project paths and validated configuration.

The project root is the repository checkout (``LINKEDIN_AGENT_HOME`` overrides
it with another full checkout, used by the tests). All private, per-account files live in ``<root>/data`` and
are never committed; ``<root>/templates`` holds the public examples.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ACTIONS = ("comment", "like", "reply", "post")
SLOTS = ("morning", "midday", "evening")
MODES = ("dry_run", "live")
SLOT_TASKS = ("post", "comments", "reactions", "replies")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

DEFAULTS: dict[str, Any] = {
    "mode": "dry_run",
    "language": "en",
    "ego_task_space": "linkedin-agent",
    "slots": {
        "morning": ["post", "comments", "reactions", "replies"],
        "midday": ["comments", "reactions", "replies"],
        "evening": ["replies", "comments", "reactions"],
    },
    "limits_per_session": {"comment": 8, "like": 20, "reply": 15, "post": 1},
    "limits_per_day": {"comment": 22, "like": 55, "reply": 40, "post": 1},
    "author_cooldown_days": 5,
    "post_days": list(WEEKDAYS),
    "pause_seconds": {"min": 45, "max": 190},
    "typing_delay_ms": {"min": 35, "max": 110},
    "feed_search_queries": ["AI", "AI agents", "automation"],
    "min_post_reactions_to_comment": 0,
    "max_post_age_hours": 168,
    "runner": {
        "claude_bin": "claude",
        "agent": "linkedin-operator",
        "model": "claude-sonnet-5-5",
        "effort": "high",
        "timeout_minutes": 90,
        "jitter_minutes": 35,
        "browser_app": "/Applications/ego lite.app",
        "browser_process": "ego lite",
    },
    "schedule": {
        "label_prefix": "com.mkmlabs.linkedin-agent",
        "times": {"morning": "08:05", "midday": "12:35", "evening": "18:15"},
    },
    "notify": {"command": None},
}

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


# Installers put CLIs here; a fresh shell or launchd may not have them on PATH.
EXTRA_BIN_DIRS = (str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin", "/usr/local/bin")


def find_cli(cmd: str) -> str | None:
    """Absolute path of ``cmd`` from PATH or the usual install locations."""
    return shutil.which(cmd) or shutil.which(cmd, path=os.pathsep.join(EXTRA_BIN_DIRS))


def with_extra_bin_dirs(path: str) -> str:
    parts = [p for p in path.split(os.pathsep) if p]
    return os.pathsep.join(parts + [d for d in EXTRA_BIN_DIRS if d not in parts])


class ConfigError(ValueError):
    """Raised when data/config.json is missing or invalid."""


def project_root() -> Path:
    env = os.environ.get("LINKEDIN_AGENT_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def templates(self) -> Path:
        return self.root / "templates"

    @property
    def config(self) -> Path:
        return self.data / "config.json"

    @property
    def log(self) -> Path:
        return self.data / "log.jsonl"

    @property
    def session(self) -> Path:
        return self.data / "session.json"

    @property
    def stop(self) -> Path:
        return self.data / "STOP"

    @property
    def lock(self) -> Path:
        return self.data / ".session.lock"

    @property
    def drafts(self) -> Path:
        return self.data / "drafts"

    @property
    def reports(self) -> Path:
        return self.data / "reports"

    @property
    def logs(self) -> Path:
        return self.data / "logs"


@dataclass(frozen=True)
class Range:
    min: float
    max: float


@dataclass(frozen=True)
class Runner:
    claude_bin: str
    agent: str
    model: str
    effort: str
    timeout_minutes: float
    jitter_minutes: float
    browser_app: str | None
    browser_process: str | None


@dataclass(frozen=True)
class Config:
    mode: str
    language: str
    slots: dict[str, list[str]]
    limits_per_session: dict[str, int]
    limits_per_day: dict[str, int]
    author_cooldown_days: int
    post_days: tuple[str, ...]
    pause_seconds: Range
    typing_delay_ms: Range
    runner: Runner
    schedule_times: dict[str, tuple[int, int]]
    label_prefix: str
    notify_command: list[str] | None
    raw: dict[str, Any]

    @property
    def live(self) -> bool:
        return self.mode == "live"

    def is_post_day(self, day: date) -> bool:
        return WEEKDAYS[day.weekday()] in self.post_days


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _range(raw: dict[str, Any], key: str) -> Range:
    r = raw[key]
    try:
        lo, hi = float(r["min"]), float(r["max"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"{key}: needs numeric 'min' and 'max'") from exc
    if lo < 0 or hi < lo:
        raise ConfigError(f"{key}: need 0 <= min <= max, got {lo}..{hi}")
    return Range(lo, hi)


def _limits(raw: dict[str, Any], key: str) -> dict[str, int]:
    limits = raw[key]
    out = {}
    for action in ACTIONS:
        value = limits.get(action)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ConfigError(f"{key}.{action}: must be a non-negative integer")
        out[action] = value
    return out


def parse_config(data: dict[str, Any]) -> Config:
    raw = _merge(DEFAULTS, data)
    if raw["mode"] not in MODES:
        raise ConfigError(f"mode: must be one of {MODES}, got {raw['mode']!r}")

    slots = raw["slots"]
    for slot, tasks in slots.items():
        if slot not in SLOTS:
            raise ConfigError(f"slots: unknown slot {slot!r}")
        bad = [t for t in tasks if t not in SLOT_TASKS]
        if bad:
            raise ConfigError(f"slots.{slot}: unknown tasks {bad}")

    # The user's own schedule replaces the default one instead of merging
    # into it, so leaving a slot out really means "no session at that time".
    user_times = (data.get("schedule") or {}).get("times")
    if user_times is not None:
        raw["schedule"]["times"] = user_times
    if not raw["schedule"]["times"]:
        raise ConfigError("schedule.times: needs at least one session")
    times: dict[str, tuple[int, int]] = {}
    for slot, value in raw["schedule"]["times"].items():
        m = _TIME_RE.match(str(value))
        if slot not in SLOTS or not m:
            raise ConfigError(f"schedule.times.{slot}: expected a known slot and HH:MM")
        times[slot] = (int(m.group(1)), int(m.group(2)))

    cooldown = raw["author_cooldown_days"]
    if not isinstance(cooldown, int) or cooldown < 0:
        raise ConfigError("author_cooldown_days: must be a non-negative integer")

    post_days = raw["post_days"]
    if not isinstance(post_days, list) or any(d not in WEEKDAYS for d in post_days):
        raise ConfigError(f"post_days: must be a list of {WEEKDAYS}")

    command = raw["notify"].get("command")
    if command is not None and (
        not isinstance(command, list) or not command or not all(isinstance(a, str) for a in command)
    ):
        raise ConfigError("notify.command: must be null or a non-empty list of strings")

    r = raw["runner"]
    runner = Runner(
        claude_bin=str(r["claude_bin"]),
        agent=str(r["agent"]),
        model=str(r["model"]),
        effort=str(r["effort"]),
        timeout_minutes=float(r["timeout_minutes"]),
        jitter_minutes=float(r["jitter_minutes"]),
        browser_app=r.get("browser_app") or None,
        browser_process=r.get("browser_process") or None,
    )
    if runner.timeout_minutes <= 0 or runner.jitter_minutes < 0:
        raise ConfigError("runner: timeout_minutes must be > 0 and jitter_minutes >= 0")

    return Config(
        mode=raw["mode"],
        language=str(raw["language"]),
        slots=slots,
        limits_per_session=_limits(raw, "limits_per_session"),
        limits_per_day=_limits(raw, "limits_per_day"),
        author_cooldown_days=cooldown,
        post_days=tuple(post_days),
        pause_seconds=_range(raw, "pause_seconds"),
        typing_delay_ms=_range(raw, "typing_delay_ms"),
        runner=runner,
        schedule_times=times,
        label_prefix=str(raw["schedule"]["label_prefix"]),
        notify_command=command,
        raw=raw,
    )


def load_config(paths: Paths) -> Config:
    try:
        text = paths.config.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"{paths.config} not found. Run `bin/li init` first.") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{paths.config}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{paths.config}: top level must be an object")
    return parse_config(data)
