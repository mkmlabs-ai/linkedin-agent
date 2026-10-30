import json

from linkedin_agent.cli import main


def test_init_creates_private_files_without_overwriting(paths, capsys):
    paths.config.write_text('{"mode": "live"}')
    assert main(["init"]) == 0
    assert json.loads(paths.config.read_text()) == {"mode": "live"}
    for name in ("voice.md", "topics.md", "plan.md"):
        assert (paths.data / name).exists()


def test_full_session_flow(paths, capsys, write_config, tmp_path):
    write_config(mode="live", limits_per_session={"comment": 1})
    assert main(["session-start", "morning"]) == 0
    assert main(["can", "comment"]) == 0
    draft = tmp_path / "d.md"
    draft.write_text("Good point.\n")
    url = "https://www.linkedin.com/posts/a"
    assert main(["target", url, "--author", "Ann"]) == 0
    assert main(["log", "comment", "--url", url, "--author", "Ann", "--text-file", str(draft)]) == 0
    assert main(["can", "comment"]) == 1
    assert main(["target", url + "?utm_source=share"]) == 1
    capsys.readouterr()
    assert main(["session-end"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["done"]["comment"] == 1


def test_bad_config_exits_2_with_message(paths, capsys):
    paths.config.write_text('{"mode": "yolo"}')
    assert main(["status"]) == 2
    assert "error: mode" in capsys.readouterr().err


def test_typing_delay_in_range(paths, capsys):
    main(["typing-delay"])
    assert 35 <= int(capsys.readouterr().out) <= 110
