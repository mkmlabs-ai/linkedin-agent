import json
import shutil
from pathlib import Path

import pytest

from linkedin_agent.settings import Paths, load_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def paths(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "templates", tmp_path / "templates")
    (tmp_path / "data").mkdir()
    shutil.copyfile(ROOT / "templates" / "config.example.json", tmp_path / "data" / "config.json")
    monkeypatch.setenv("LINKEDIN_AGENT_HOME", str(tmp_path))
    return Paths(tmp_path)


@pytest.fixture
def write_config(paths):
    def write(**overrides):
        data = json.loads(paths.config.read_text())
        data.update(overrides)
        paths.config.write_text(json.dumps(data))
        return load_config(paths)

    return write
