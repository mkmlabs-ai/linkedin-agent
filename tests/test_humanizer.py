import importlib.util
import json
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "li-human"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SKILL / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lexicon():
    return json.loads((SKILL / "slop.json").read_text(encoding="utf-8"))


def test_polish_words_are_counted_whole():
    detect = load("detect")
    assert detect.words("Zażółć gęślą jaźń") == ["Zażółć", "gęślą", "jaźń"]
    assert "Łodzi" in detect.proper_nouns("Byłem wczoraj w Łodzi. Super.")


def test_humanize_strips_em_dash_and_invisible_chars_keeps_urls():
    humanize = load("humanize")
    text, report = humanize.humanize("Działa — serio​. https://ex.com/a—b", lexicon())
    assert "— serio" not in text and "​" not in text
    assert "https://ex.com/a—b" in text
    assert report["invisible"]


def test_short_comment_can_pass_when_clean():
    detect = load("detect")
    results, _, verdict = detect.run(
        "Mieliśmy to samo u klienta w Łodzi. Pomogło przepisanie promptu od zera.", lexicon()
    )
    assert results["BURSTINESS"][1] == detect.TOO_SHORT
    assert verdict != "FLAGGED"
    judged_only = detect.run("Krótko.", lexicon())
    assert judged_only[2] in {"PASS", "REVIEW", "FLAGGED"}
