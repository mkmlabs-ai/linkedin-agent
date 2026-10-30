"""Command line entry point: ``bin/li <command>``.

init                              copy templates/ into data/ (never overwrites)
status                            mode, today's counters, remaining limits
can ACTION                        exit 0 if ACTION is within limits
target URL [--author NAME]        exit 0 if URL is new and author not in cooldown
log ACTION --url U [--author A] [--text-file F] [--dry]
pause                             sleep a random human-like pause
typing-delay                      print a random per-key delay in ms
session-start SLOT / session-end  mark the session window
run SLOT [--now]                  one scheduled session (used by launchd)
schedule on|off|status            install or remove the launchd jobs
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
from collections.abc import Sequence

from . import scheduler
from .runner import SessionRunner
from .settings import ACTIONS, SLOTS, ConfigError, Paths, load_config, project_root
from .state import Store, check_target, make_row, read_text, usage

TEMPLATES = {
    "config.example.json": "config.json",
    "voice.example.md": "voice.md",
    "topics.example.md": "topics.md",
    "plan.example.md": "plan.md",
}


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=1))


def cmd_init(paths: Paths, _: argparse.Namespace) -> int:
    for sub in (paths.data, paths.drafts, paths.reports, paths.logs):
        sub.mkdir(parents=True, exist_ok=True)
    for src, dst in TEMPLATES.items():
        target = paths.data / dst
        if target.exists():
            print(f"keep    {target.relative_to(paths.root)}")
        else:
            shutil.copyfile(paths.templates / src, target)
            print(f"created {target.relative_to(paths.root)}")
    return 0


def cmd_status(paths: Paths, _: argparse.Namespace) -> int:
    cfg, store = load_config(paths), Store(paths)
    session = store.session()
    u = usage(cfg, store.entries(), session)
    _print_json(
        {
            "mode": cfg.mode,
            "stop_file": paths.stop.exists(),
            "session": session,
            "today": u.today,
            "this_session": u.session,
            "remaining_session": u.remaining,
        }
    )
    return 0


def cmd_can(paths: Paths, a: argparse.Namespace) -> int:
    cfg, store = load_config(paths), Store(paths)
    u = usage(cfg, store.entries(), store.session())
    if u.allows(a.action):
        print("OK")
        return 0
    print(f"LIMIT {a.action}: session {u.session[a.action]}, day {u.today[a.action]}")
    return 1


def cmd_target(paths: Paths, a: argparse.Namespace) -> int:
    ok, reason = check_target(load_config(paths), Store(paths).entries(), a.url, a.author)
    print("OK" if ok else f"SKIP {reason}")
    return 0 if ok else 1


def cmd_log(paths: Paths, a: argparse.Namespace) -> int:
    cfg, store = load_config(paths), Store(paths)
    row = make_row(cfg, store.session(), a.action, a.url, a.author, read_text(a.text_file), a.dry)
    store.append(row)
    print("LOGGED", row["action"], "dry" if row["dry"] else "live")
    return 0


def cmd_pause(paths: Paths, _: argparse.Namespace) -> int:
    p = load_config(paths).pause_seconds
    seconds = random.uniform(p.min, p.max)
    time.sleep(seconds)
    print(f"paused {seconds:.0f}s")
    return 0


def cmd_typing(paths: Paths, _: argparse.Namespace) -> int:
    t = load_config(paths).typing_delay_ms
    print(random.randint(int(t.min), int(t.max)))
    return 0


def cmd_session_start(paths: Paths, a: argparse.Namespace) -> int:
    Store(paths).start_session(a.slot)
    return cmd_status(paths, a)


def cmd_session_end(paths: Paths, _: argparse.Namespace) -> int:
    cfg, store = load_config(paths), Store(paths)
    session, rows = store.session(), store.entries()
    started = session.get("started")
    drafts = sum(1 for r in rows if r.get("dry") and started and str(r["ts"]) >= started)
    _print_json({"session": session, "done": usage(cfg, rows, session).session, "dry_run_drafts": drafts})
    return 0


def cmd_run(paths: Paths, a: argparse.Namespace) -> int:
    return SessionRunner(paths, load_config(paths))(a.slot, now=a.now)


def cmd_schedule(paths: Paths, a: argparse.Namespace) -> int:
    cfg = load_config(paths)
    if a.state == "on":
        for name in scheduler.install(paths, cfg):
            print("loaded", name)
    elif a.state == "off":
        scheduler.uninstall(cfg)
        print("removed")
    else:
        print("\n".join(scheduler.loaded(cfg)) or "no jobs loaded")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="li", description="LinkedIn agent state and runner.")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("init", help="create data/ from templates").set_defaults(f=cmd_init)
    sp.add_parser("status").set_defaults(f=cmd_status)
    p = sp.add_parser("can")
    p.add_argument("action", choices=ACTIONS)
    p.set_defaults(f=cmd_can)
    p = sp.add_parser("target")
    p.add_argument("url")
    p.add_argument("--author")
    p.set_defaults(f=cmd_target)
    p = sp.add_parser("log")
    p.add_argument("action", choices=ACTIONS)
    p.add_argument("--url", required=True)
    p.add_argument("--author")
    p.add_argument("--text-file")
    p.add_argument("--dry", action="store_true")
    p.set_defaults(f=cmd_log)
    sp.add_parser("pause").set_defaults(f=cmd_pause)
    sp.add_parser("typing-delay").set_defaults(f=cmd_typing)
    p = sp.add_parser("session-start")
    p.add_argument("slot", choices=SLOTS)
    p.set_defaults(f=cmd_session_start)
    sp.add_parser("session-end").set_defaults(f=cmd_session_end)
    p = sp.add_parser("run", help="run one scheduled session")
    p.add_argument("slot", choices=SLOTS)
    p.add_argument("--now", action="store_true", help="skip the random start delay")
    p.set_defaults(f=cmd_run)
    p = sp.add_parser("schedule", help="manage launchd jobs (macOS)")
    p.add_argument("state", choices=("on", "off", "status"))
    p.set_defaults(f=cmd_schedule)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.f(Paths(project_root()), args)
    except (ConfigError, FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
