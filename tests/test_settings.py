import json

import pytest

from linkedin_agent.settings import ConfigError, load_config, parse_config


def test_template_config_is_valid(paths):
    cfg = load_config(paths)
    assert cfg.mode == "dry_run"
    assert not cfg.live
    assert cfg.schedule_times["morning"] == (8, 5)
    assert cfg.notify_command is None


def test_defaults_fill_missing_keys():
    cfg = parse_config({"mode": "live"})
    assert cfg.live
    assert cfg.limits_per_day["post"] == 1
    assert cfg.runner.timeout_minutes == 90


@pytest.mark.parametrize(
    "data, message",
    [
        ({"mode": "yolo"}, "mode"),
        ({"limits_per_day": {"comment": -1}}, "limits_per_day.comment"),
        ({"limits_per_session": {"like": "5"}}, "limits_per_session.like"),
        ({"pause_seconds": {"min": 10, "max": 5}}, "pause_seconds"),
        ({"schedule": {"times": {"morning": "25:00"}}}, "schedule.times.morning"),
        ({"slots": {"night": ["post"]}}, "unknown slot"),
        ({"slots": {"morning": ["dm"]}}, "unknown tasks"),
        ({"notify": {"command": "mail me"}}, "notify.command"),
        ({"runner": {"timeout_minutes": 0}}, "runner"),
    ],
)
def test_invalid_config_is_rejected(data, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(data)


def test_missing_config_points_to_init(paths):
    paths.config.unlink()
    with pytest.raises(ConfigError, match="bin/li init"):
        load_config(paths)


def test_broken_json_is_reported(paths):
    paths.config.write_text("{nope")
    with pytest.raises(ConfigError, match="invalid JSON"):
        load_config(paths)


def test_partial_nested_override_keeps_other_keys(paths):
    paths.config.write_text(json.dumps({"limits_per_day": {"comment": 3}}))
    cfg = load_config(paths)
    assert cfg.limits_per_day == {"comment": 3, "like": 55, "reply": 40, "post": 1}
