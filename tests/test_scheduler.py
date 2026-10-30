import plistlib
import sys

from linkedin_agent import scheduler
from linkedin_agent.settings import load_config


def test_plist_runs_the_cli_with_the_configured_time(paths):
    cfg = load_config(paths)
    plist = plistlib.loads(scheduler.build_plist(paths, cfg, "midday", "/opt/bin:/usr/bin"))
    assert plist["Label"] == "com.example.linkedin-agent.midday"
    assert plist["ProgramArguments"] == [sys.executable, str(paths.root / "bin" / "li"), "run", "midday"]
    assert plist["StartCalendarInterval"] == {"Hour": 12, "Minute": 35}
    assert plist["EnvironmentVariables"]["PATH"] == "/opt/bin:/usr/bin"
    assert plist["WorkingDirectory"] == str(paths.root)


def test_install_and_uninstall_write_and_remove_files(paths, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "_launchctl", lambda *a: calls.append(a) or type("R", (), {"returncode": 0})())
    cfg = load_config(paths)
    agents = tmp_path / "LaunchAgents"
    names = scheduler.install(paths, cfg, agents)
    assert len(names) == 3 and len(list(agents.glob("*.plist"))) == 3
    assert any(c[0] == "bootstrap" for c in calls)
    scheduler.uninstall(cfg, agents)
    assert list(agents.glob("*.plist")) == []
