from linkedin_agent.report import fallback_text, parse_notes, render_html


def test_html_escapes_untrusted_text_and_skips_non_https_links():
    rows = [
        {
            "action": "comment",
            "author": "<script>x</script>",
            "url": "javascript:alert(1)",
            "text": "a\n<b>",
            "dry": True,
        },
        {"action": "like", "url": "https://www.linkedin.com/posts/a"},
    ]
    html = render_html("morning", "dry_run", "2026-10-30T08:10:00", rows, ["Skipped: <none>"], "en")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "javascript:" not in html
    assert "a<br>&lt;b&gt;" in html
    assert "[draft]" in html
    assert "Plus 1 reactions." in html
    assert "Skipped: &lt;none&gt;" in html


def test_polish_labels_and_notes():
    text = "Slot morning | tryb live\nkomentarz Jan https://x\nPominięte: 2 posty po angielsku\nProblems: none"
    notes = parse_notes(text, "pl")
    assert notes == ["Pominięte: 2 posty po angielsku", "Problems: none"]
    assert "Komentarz" in render_html("m", "live", "", [{"action": "comment"}], [], "pl")


def test_unknown_language_falls_back_to_english():
    assert "No posts" in render_html("m", "live", "", [], [], "xx")
    assert fallback_text("evening", 1, "tail", "xx").startswith("Slot evening | exit 1")
