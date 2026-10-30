"""Action log, session state and rate limits.

Every public action is one JSON line in ``data/log.jsonl``. Limits and
duplicate checks are computed from that log only, so it stays the single
source of truth. Dry-run rows never count against limits.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .settings import ACTIONS, Config, Paths

ENGAGEMENTS = ("comment", "reply")


def now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now()).isoformat(timespec="seconds")


TRACKING_PARAMS = frozenset({"trk", "trackingid", "refid", "lipi", "rcm", "originalsubdomain", "original_referer"})


def _is_tracking(key: str) -> bool:
    key = key.lower()
    return key.startswith("utm_") or key in TRACKING_PARAMS


def normalize_url(url: str) -> str:
    """Canonical key for a post or comment URL.

    LinkedIn adds ``utm_*``, ``trk`` and similar to shared URLs, so the same
    post shows up under many spellings. Those are dropped; meaningful
    parameters such as ``commentUrn`` stay (sorted), so two comments under one
    post remain different targets. The fragment is kept because replies may
    be keyed as ``<post-url>#<commenter>``.
    """
    url = url.strip()
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url
    path = parts.path.rstrip("/") or "/"
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking(k)))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, parts.fragment))


def normalize_author(name: str | None) -> str:
    return " ".join((name or "").split()).casefold()


@dataclass(frozen=True)
class Store:
    paths: Paths

    def entries(self) -> list[dict[str, Any]]:
        if not self.paths.log.exists():
            return []
        rows = []
        with self.paths.log.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    print(f"warning: {self.paths.log}:{lineno} is not valid JSON, skipped", file=sys.stderr)
                    continue
                if isinstance(row, dict) and "ts" in row and "action" in row:
                    rows.append(row)
        return rows

    def append(self, row: dict[str, Any]) -> None:
        self.paths.data.mkdir(parents=True, exist_ok=True)
        with self.paths.log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def session(self) -> dict[str, Any]:
        try:
            data = json.loads(self.paths.session.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def start_session(self, slot: str, now: datetime | None = None) -> dict[str, Any]:
        session = {"slot": slot, "started": now_iso(now)}
        self.paths.data.mkdir(parents=True, exist_ok=True)
        tmp = self.paths.session.with_suffix(".tmp")
        tmp.write_text(json.dumps(session), encoding="utf-8")
        tmp.replace(self.paths.session)
        return session


def counts(rows: list[dict[str, Any]], day: str | None = None, since: str | None = None) -> dict[str, int]:
    """Live actions per type, filtered to ``day`` (YYYY-MM-DD) and/or from ``since`` on."""
    out = dict.fromkeys(ACTIONS, 0)
    for r in rows:
        if r.get("dry") or r["action"] not in out:
            continue
        ts = str(r["ts"])
        if (day is None or ts[:10] == day) and (since is None or ts >= since):
            out[r["action"]] += 1
    return out


@dataclass(frozen=True)
class Usage:
    today: dict[str, int]
    session: dict[str, int]
    remaining: dict[str, int]

    def allows(self, action: str) -> bool:
        return self.remaining[action] > 0


def usage(cfg: Config, rows: list[dict[str, Any]], session: dict[str, Any], now: datetime | None = None) -> Usage:
    day = (now or datetime.now()).date().isoformat()
    today = counts(rows, day)
    # A session that crosses midnight keeps its count; without a session
    # window, fall back to today's actions.
    started = session.get("started")
    ses = counts(rows, since=started) if started else today
    remaining = {a: max(0, min(cfg.limits_per_session[a] - ses[a], cfg.limits_per_day[a] - today[a])) for a in ACTIONS}
    return Usage(today, ses, remaining)


def check_target(
    cfg: Config, rows: list[dict[str, Any]], url: str, author: str | None, now: datetime | None = None
) -> tuple[bool, str]:
    """Return (ok, reason). A target is refused when we already engaged with
    that URL, or commented on the same author within the cooldown window."""
    live = [r for r in rows if not r.get("dry")]
    key = normalize_url(url)
    if any(r["action"] in ENGAGEMENTS and normalize_url(r.get("url") or "") == key for r in live):
        return False, "already engaged"
    name = normalize_author(author)
    if name:
        cut = now_iso((now or datetime.now()) - timedelta(days=cfg.author_cooldown_days))
        if any(
            r["action"] == "comment" and normalize_author(r.get("author")) == name and str(r["ts"]) >= cut for r in live
        ):
            return False, "author cooldown"
    return True, "OK"


def make_row(
    cfg: Config,
    session: dict[str, Any],
    action: str,
    url: str,
    author: str | None = None,
    text: str = "",
    dry: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    return {
        "ts": now_iso(now),
        "action": action,
        "url": url,
        "author": author,
        "text": text,
        "dry": dry or not cfg.live,
        "slot": session.get("slot"),
    }


def read_text(path: str | None) -> str:
    return Path(path).read_text(encoding="utf-8").strip() if path else ""
