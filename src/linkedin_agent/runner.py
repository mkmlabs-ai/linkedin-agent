"""One scheduled session: guard rails around a headless Claude Code run.

Order: STOP file -> random jitter -> STOP again -> exclusive lock -> start the
browser -> run the operator agent with a hard timeout -> make sure a report
exists -> render HTML -> optional notification command.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import random
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import IO

from .report import fallback_text, parse_notes, render_html
from .settings import Config, Paths, find_cli
from .state import Store, now_iso

TIMEOUT_RC = 124


@contextmanager
def exclusive_lock(path: Path) -> Iterator[bool]:
    """Non-blocking flock. The kernel drops it when the process dies, so a
    crashed or killed run can never leave a stale lock behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def build_prompt(slot: str, report_path: Path, paths: Paths) -> str:
    return (
        f"Run the linkedin-session skill for slot={slot}. "
        f"Write the end-of-session report to {report_path.relative_to(paths.root)}."
    )


def claude_command(cfg: Config, prompt: str) -> list[str]:
    r = cfg.runner
    return [
        find_cli(r.claude_bin) or r.claude_bin,
        "-p",
        prompt,
        "--agent",
        r.agent,
        "--model",
        r.model,
        "--effort",
        r.effort,
        # Unattended run: the agent's own rules (skill + agent file) are the
        # guard rails. Never point this at a checkout you do not trust.
        "--dangerously-skip-permissions",
    ]


def notify_command(cfg: Config, subject: str, body_file: Path, html_file: Path) -> list[str] | None:
    if not cfg.notify_command:
        return None
    values = {"subject": subject, "body_file": str(body_file), "html_file": str(html_file)}
    return [arg.format(**values) for arg in cfg.notify_command]


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_group(proc: subprocess.Popen, grace: float = 10.0) -> None:
    """SIGTERM the whole group, wait until every member is gone (not just the
    leader), then SIGKILL whatever is left."""
    pgid = proc.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        proc.poll()  # reap the leader so its zombie does not keep the group "alive"
        if not _group_alive(pgid):
            return
        time.sleep(0.1)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pgid, signal.SIGKILL)
    proc.wait()


def run_agent(cmd: list[str], *, cwd: Path, stdout: IO[str], timeout: float, grace: float = 10.0) -> int:
    """Run the agent in its own process group and, whatever happens, kill the
    whole group before returning, so no browser or shell tool it spawned can
    keep acting after the session lock is released."""
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=stdout, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        return proc.wait(timeout=timeout)
    finally:
        _kill_group(proc, grace)


def _tail(path: Path, lines: int = 25) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except FileNotFoundError:
        return ""


class SessionRunner:
    def __init__(
        self,
        paths: Paths,
        cfg: Config,
        *,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        run_agent: Callable[..., int] = run_agent,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.paths, self.cfg = paths, cfg
        self._run, self._run_agent, self._sleep, self._clock = run, run_agent, sleep, clock

    def _log(self, fh: IO[str], msg: str) -> None:
        fh.write(f"{self._clock().isoformat(timespec='seconds')} {msg}\n")
        fh.flush()

    def __call__(self, slot: str, now: bool = False) -> int:
        started = self._clock()
        day = started.date().isoformat()
        self.paths.logs.mkdir(parents=True, exist_ok=True)
        logfile = self.paths.logs / f"{day}-{slot}.log"
        with logfile.open("a", encoding="utf-8") as log:
            if self.paths.stop.exists():
                self._log(log, "STOP file present, skipping")
                return 0
            if not now and self.cfg.runner.jitter_minutes:
                self._sleep(random.uniform(0, self.cfg.runner.jitter_minutes * 60))
                if self.paths.stop.exists():
                    self._log(log, "STOP file appeared during jitter, skipping")
                    return 0
            with exclusive_lock(self.paths.lock) as acquired:
                if not acquired:
                    self._log(log, "another session is running, skipping")
                    return 0
                return self._session(slot, day, log, logfile)

    def _ensure_browser(self, log: IO[str]) -> None:
        r = self.cfg.runner
        # `open -g -j -a` is macOS-only; elsewhere start the browser yourself.
        if not r.browser_app or sys.platform != "darwin":
            return
        if r.browser_process:
            running = self._run(["pgrep", "-qf", r.browser_process], check=False).returncode == 0
            if running:
                return
        # -g -j: launch hidden in the background, never steal focus.
        self._run(["open", "-g", "-j", "-a", r.browser_app], check=False)
        self._log(log, f"started {r.browser_app}")

    def _session(self, slot: str, day: str, log: IO[str], logfile: Path) -> int:
        self.paths.reports.mkdir(parents=True, exist_ok=True)
        report = self.paths.reports / f"{day}-{slot}.txt"
        html = report.with_suffix(".html")
        self._ensure_browser(log)

        self._log(log, f"=== start slot={slot} mode={self.cfg.mode}")
        since = now_iso(self._clock())
        begin = time.time()
        try:
            rc = self._run_agent(
                claude_command(self.cfg, build_prompt(slot, report, self.paths)),
                cwd=self.paths.root,
                stdout=log,
                timeout=self.cfg.runner.timeout_minutes * 60,
            )
        except subprocess.TimeoutExpired:
            rc = TIMEOUT_RC
            self._log(log, f"timeout after {self.cfg.runner.timeout_minutes:g} min, agent and its tools killed")
        except FileNotFoundError:
            rc = 127
            self._log(log, f"{self.cfg.runner.claude_bin!r} not found on PATH")
        self._log(log, f"=== end exit={rc}")

        # A report from an earlier run of the same slot does not count.
        if not report.exists() or report.stat().st_mtime < begin or not report.read_text(encoding="utf-8").strip():
            report.write_text(fallback_text(slot, rc, _tail(logfile), self.cfg.language), encoding="utf-8")

        rows = [r for r in Store(self.paths).entries() if str(r["ts"]) >= since]
        notes = parse_notes(report.read_text(encoding="utf-8"), self.cfg.language)
        html.write_text(render_html(slot, self.cfg.mode, since, rows, notes, self.cfg.language), encoding="utf-8")

        subject = f"LinkedIn agent: {slot} {self._clock().strftime('%Y-%m-%d %H:%M')}"
        cmd = notify_command(self.cfg, subject, report, html)
        if cmd:
            try:
                res = self._run(cmd, cwd=self.paths.root, stdout=log, stderr=subprocess.STDOUT, check=False)
                if res.returncode != 0:
                    self._log(log, f"notify failed exit={res.returncode}")
            except OSError as exc:
                self._log(log, f"notify failed: {exc}")
        return rc
