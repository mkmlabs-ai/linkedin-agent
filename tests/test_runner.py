import os
import subprocess
import sys
import time
from datetime import datetime

import pytest

from linkedin_agent.runner import (
    TIMEOUT_RC,
    SessionRunner,
    claude_command,
    exclusive_lock,
    notify_command,
    run_agent,
)
from linkedin_agent.settings import load_config
from linkedin_agent.state import Store, make_row

NOW = datetime(2026, 10, 30, 8, 30, 0)


class FakeRun:
    """Records commands; the claude call can write a report or misbehave."""

    def __init__(self, paths, claude=None):
        self.paths, self.claude, self.calls = paths, claude, []

    def agent(self, cmd, **kw):
        self.calls.append(cmd)
        if self.claude:
            return self.claude(cmd, **kw).returncode
        return 0

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[0] == "pgrep":
            return subprocess.CompletedProcess(cmd, 0)
        if cmd[0] == "claude" and self.claude:
            return self.claude(cmd, **kw)
        return subprocess.CompletedProcess(cmd, 0)

    def names(self):
        return [c[0] for c in self.calls]


@pytest.fixture(autouse=True)
def _no_real_claude(monkeypatch):
    monkeypatch.setattr("linkedin_agent.runner.find_cli", lambda name: None)


def runner(paths, fake, **kw):
    return SessionRunner(
        paths, load_config(paths), run=fake, run_agent=fake.agent, sleep=lambda s: None, clock=lambda: NOW, **kw
    )


def test_stop_file_skips_everything(paths):
    paths.stop.touch()
    fake = FakeRun(paths)
    assert runner(paths, fake)("morning") == 0
    assert fake.calls == []
    assert "STOP" in (paths.logs / "2026-10-30-morning.log").read_text()


def test_stop_file_created_during_jitter(paths):
    fake = FakeRun(paths)
    r = SessionRunner(
        paths, load_config(paths), run=fake, run_agent=fake.agent, sleep=lambda s: paths.stop.touch(), clock=lambda: NOW
    )
    assert r("midday") == 0
    assert fake.calls == []


def test_busy_lock_skips(paths):
    fake = FakeRun(paths)
    with exclusive_lock(paths.lock) as got:
        assert got
        assert runner(paths, fake)("morning", now=True) == 0
    assert fake.calls == []
    assert "another session" in (paths.logs / "2026-10-30-morning.log").read_text()


def test_lock_is_released_after_run(paths):
    runner(paths, FakeRun(paths))("morning", now=True)
    with exclusive_lock(paths.lock) as got:
        assert got


def test_agent_report_is_used_and_html_lists_this_runs_actions(paths):
    store, cfg = Store(paths), load_config(paths)
    store.append(make_row(cfg, {}, "comment", "https://old", text="old", now=datetime(2026, 10, 29, 9)))

    def claude(cmd, **kw):
        report = paths.root / cmd[2].split("report to ")[1].rstrip(".")
        report.write_text("Slot morning | mode dry_run\nSkipped: nothing fresh\n")
        store.append(make_row(cfg, {}, "comment", "https://new", author="Ann", text="new", now=NOW))
        return subprocess.CompletedProcess(cmd, 0)

    assert runner(paths, FakeRun(paths, claude))("morning", now=True) == 0
    html = (paths.reports / "2026-10-30-morning.html").read_text()
    assert "https://new" in html and "https://old" not in html
    assert "Skipped: nothing fresh" in html


def test_timeout_writes_fallback_report(paths):
    def claude(cmd, **kw):
        assert kw["timeout"] == 90 * 60
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    assert runner(paths, FakeRun(paths, claude))("evening", now=True) == TIMEOUT_RC
    report = (paths.reports / "2026-10-30-evening.txt").read_text()
    assert report.startswith(f"Slot evening | exit {TIMEOUT_RC}")
    assert "timeout after 90 min" in report


def test_stale_report_from_earlier_run_is_replaced(paths):
    paths.reports.mkdir(parents=True)
    old = paths.reports / "2026-10-30-morning.txt"
    old.write_text("Slot morning | from the previous run\n")
    os.utime(old, (0, 0))
    runner(paths, FakeRun(paths))("morning", now=True)
    assert "exit 0" in old.read_text()


def test_missing_claude_binary(paths):
    def claude(cmd, **kw):
        raise FileNotFoundError(cmd[0])

    assert runner(paths, FakeRun(paths, claude))("morning", now=True) == 127


def test_notify_command_gets_placeholders(paths, write_config):
    write_config(notify={"command": ["mailer", "--subject", "{subject}", "--html", "{html_file}"]})
    fake = FakeRun(paths)
    runner(paths, fake)("morning", now=True)
    mail = next(c for c in fake.calls if c[0] == "mailer")
    assert mail[2] == "LinkedIn agent: morning 2026-10-30 08:30"
    assert mail[4].endswith("2026-10-30-morning.html")


def test_no_notify_command_means_no_extra_process(paths):
    fake = FakeRun(paths)
    runner(paths, fake)("morning", now=True)
    assert set(fake.names()) <= {"pgrep", "open", "claude"}


def test_claude_command_shape(paths, monkeypatch):
    monkeypatch.setattr("linkedin_agent.runner.find_cli", lambda name: None)
    cmd = claude_command(load_config(paths), "do it")
    assert cmd[:3] == ["claude", "-p", "do it"]
    assert cmd[cmd.index("--agent") + 1] == "linkedin-operator"
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5-5"


def test_notify_disabled(paths):
    assert notify_command(load_config(paths), "s", paths.root, paths.root) is None


@pytest.mark.parametrize("running, opened", [(True, False), (False, True)])
def test_browser_started_only_when_not_running(paths, running, opened, monkeypatch):
    monkeypatch.setattr("linkedin_agent.runner.sys.platform", "darwin")
    fake = FakeRun(paths)
    original = fake.__call__

    def call(cmd, **kw):
        if cmd[0] == "pgrep":
            fake.calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0 if running else 1)
        return original(cmd, **kw)

    r = SessionRunner(
        paths, load_config(paths), run=call, run_agent=fake.agent, sleep=lambda s: None, clock=lambda: NOW
    )
    r("morning", now=True)
    assert ("open" in fake.names()) is opened


def test_browser_never_started_off_macos(paths, monkeypatch):
    monkeypatch.setattr("linkedin_agent.runner.sys.platform", "linux")
    fake = FakeRun(paths)
    runner(paths, fake)("morning", now=True)
    assert fake.names() == ["claude"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_timeout_kills_grandchildren(tmp_path):
    marker = tmp_path / "still-running"
    script = f"(sleep 2; touch {marker}) & sleep 30"
    with (tmp_path / "log").open("w") as log, pytest.raises(subprocess.TimeoutExpired):
        run_agent(["/bin/sh", "-c", script], cwd=tmp_path, stdout=log, timeout=0.5)
    time.sleep(2.5)
    assert not marker.exists()


def test_tools_left_behind_after_normal_exit_are_killed(tmp_path):
    marker = tmp_path / "orphan"
    with (tmp_path / "log").open("w") as log:
        assert run_agent(["/bin/sh", "-c", f"(sleep 1; touch {marker}) &"], cwd=tmp_path, stdout=log, timeout=5) == 0
    time.sleep(1.5)
    assert not marker.exists()


def test_grandchild_ignoring_sigterm_is_killed(tmp_path):
    marker = tmp_path / "survived"
    script = f"(trap '' TERM; sleep 1.5; touch {marker}) & exit 0"
    with (tmp_path / "log").open("w") as log:
        rc = run_agent(["/bin/sh", "-c", script], cwd=tmp_path, stdout=log, timeout=5, grace=0.3)
    assert rc == 0
    time.sleep(2)
    assert not marker.exists()


def test_claude_resolved_to_absolute_path(paths, monkeypatch):  # overrides the autouse stub
    monkeypatch.setattr("linkedin_agent.runner.find_cli", lambda name: f"/home/u/.local/bin/{name}")
    assert claude_command(load_config(paths), "x")[0] == "/home/u/.local/bin/claude"
