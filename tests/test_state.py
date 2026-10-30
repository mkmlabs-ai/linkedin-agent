from datetime import datetime, timedelta

import pytest

from linkedin_agent.settings import parse_config
from linkedin_agent.state import Store, check_target, counts, make_row, normalize_url, usage

NOW = datetime(2026, 10, 30, 12, 0, 0)


def row(action, ts, url="https://www.linkedin.com/posts/a", author=None, dry=False):
    return {"ts": ts.isoformat(timespec="seconds"), "action": action, "url": url, "author": author, "dry": dry}


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "https://www.linkedin.com/feed/update/urn:li:activity:1/",
            "https://www.linkedin.com/feed/update/urn:li:activity:1",
        ),
        ("https://WWW.LinkedIn.com/posts/x?utm_source=share&rcm=1", "https://www.linkedin.com/posts/x"),
        ("https://www.linkedin.com/posts/x#jan-kowalski", "https://www.linkedin.com/posts/x#jan-kowalski"),
        ("draft", "draft"),
        (
            "https://www.linkedin.com/feed/update/urn:li:activity:1?commentUrn=c1&trk=x&utm_medium=y",
            "https://www.linkedin.com/feed/update/urn:li:activity:1?commentUrn=c1",
        ),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_counts_skip_dry_runs_other_days_and_rows_before_session():
    rows = [
        row("comment", NOW),
        row("comment", NOW, dry=True),
        row("comment", NOW - timedelta(days=1)),
        row("like", NOW - timedelta(hours=3)),
    ]
    assert counts(rows, "2026-10-30") == {"comment": 1, "like": 1, "reply": 0, "post": 0}
    since = (NOW - timedelta(hours=1)).isoformat(timespec="seconds")
    assert counts(rows, "2026-10-30", since)["like"] == 0


def test_usage_takes_the_tighter_of_session_and_day_limit():
    cfg = parse_config({"limits_per_session": {"comment": 8}, "limits_per_day": {"comment": 3}})
    rows = [row("comment", NOW - timedelta(hours=h)) for h in (5, 6)]
    u = usage(cfg, rows, {"started": NOW.isoformat()}, NOW)
    assert u.remaining["comment"] == 1
    assert u.allows("comment")
    u = usage(cfg, [*rows, row("comment", NOW)], {"started": NOW.isoformat()}, NOW)
    assert not u.allows("comment")


def test_target_rejects_same_post_under_another_spelling():
    cfg = parse_config({})
    rows = [row("comment", NOW, url="https://www.linkedin.com/posts/x")]
    ok, reason = check_target(cfg, rows, "https://www.linkedin.com/posts/x/?utm_source=share", None, NOW)
    assert (ok, reason) == (False, "already engaged")


def test_target_ignores_likes_and_dry_runs():
    cfg = parse_config({})
    rows = [row("like", NOW), row("comment", NOW, dry=True)]
    assert check_target(cfg, rows, "https://www.linkedin.com/posts/a", None, NOW) == (True, "OK")


def test_author_cooldown_window():
    cfg = parse_config({"author_cooldown_days": 5})
    recent = [row("comment", NOW - timedelta(days=2), url="u1", author="Jan  Kowalski")]
    old = [row("comment", NOW - timedelta(days=6), url="u1", author="Jan Kowalski")]
    assert check_target(cfg, recent, "u2", "jan kowalski", NOW) == (False, "author cooldown")
    assert check_target(cfg, old, "u2", "Jan Kowalski", NOW) == (True, "OK")


def test_store_round_trip_and_corrupt_line(paths, capsys):
    store = Store(paths)
    cfg = parse_config({"mode": "live"})
    session = store.start_session("morning", NOW)
    store.append(make_row(cfg, session, "post", "https://x", text="hi", now=NOW))
    with paths.log.open("a") as fh:
        fh.write("{broken\n\n")
    rows = store.entries()
    assert len(rows) == 1
    assert rows[0]["slot"] == "morning" and rows[0]["dry"] is False
    assert "not valid JSON" in capsys.readouterr().err


def test_rows_are_dry_outside_live_mode():
    assert make_row(parse_config({"mode": "dry_run"}), {}, "comment", "u")["dry"] is True
    assert make_row(parse_config({"mode": "live"}), {}, "comment", "u", dry=True)["dry"] is True


def test_two_comments_under_one_post_are_different_targets():
    cfg = parse_config({})
    post = "https://www.linkedin.com/feed/update/urn:li:activity:1"
    rows = [row("reply", NOW, url=post + "?commentUrn=c1")]
    assert check_target(cfg, rows, post + "?commentUrn=c2&trk=n", None, NOW) == (True, "OK")
    assert check_target(cfg, rows, post + "?trk=n&commentUrn=c1", None, NOW) == (False, "already engaged")


def test_session_crossing_midnight_keeps_its_count():
    cfg = parse_config({"limits_per_session": {"comment": 2}})
    started = datetime(2026, 10, 30, 23, 50)
    rows = [row("comment", started + timedelta(minutes=m)) for m in (2, 5)]
    u = usage(cfg, rows, {"started": started.isoformat()}, datetime(2026, 10, 31, 0, 10))
    assert u.session["comment"] == 2
    assert not u.allows("comment")
