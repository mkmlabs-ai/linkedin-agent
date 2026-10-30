"""Session report: plain-text fallback and the HTML e-mail body."""

from __future__ import annotations

from html import escape
from typing import Any

STRINGS = {
    "en": {
        "labels": {"post": "📝 Post", "comment": "💬 Comment", "reply": "↩️ Reply", "like": "👍 Reaction"},
        "open": "open",
        "draft": "[draft]",
        "mode": "mode",
        "empty": "No posts, comments or replies in this run.",
        "likes": "Plus {n} reactions.",
        "notes": "Notes",
        "note_prefixes": ("skipped", "problems", "notes", "checkpoint"),
        "fallback": "Slot {slot} | exit {rc} | the agent wrote no report, end of log:",
    },
    "pl": {
        "labels": {"post": "📝 Post", "comment": "💬 Komentarz", "reply": "↩️ Odpowiedź", "like": "👍 Reakcja"},
        "open": "otwórz",
        "draft": "[szkic]",
        "mode": "tryb",
        "empty": "Brak postów, komentarzy i odpowiedzi w tym runie.",
        "likes": "Do tego {n} reakcji.",
        "notes": "Uwagi",
        "note_prefixes": ("pominięte", "problemy", "uwagi", "checkpoint"),
        "fallback": "Slot {slot} | exit {rc} | agent nie zapisał raportu, koniec logu:",
    },
}


def strings(language: str) -> dict[str, Any]:
    return STRINGS.get(language, STRINGS["en"])


def parse_notes(report_text: str, language: str) -> list[str]:
    """Pick the agent's 'Skipped:' / 'Problems:' lines from its text report."""
    prefixes = tuple({*strings(language)["note_prefixes"], *STRINGS["en"]["note_prefixes"]})
    return [ln.strip() for ln in report_text.splitlines() if ln.strip().lower().startswith(prefixes)]


def fallback_text(slot: str, rc: int, log_tail: str, language: str) -> str:
    return strings(language)["fallback"].format(slot=slot, rc=rc) + "\n" + log_tail


def _card(row: dict[str, Any], s: dict[str, Any]) -> str:
    url = str(row.get("url") or "")
    link = f'<a href="{escape(url)}" style="color:#0a66c2">{s["open"]}</a>' if url.startswith("https://") else ""
    who = escape(str(row.get("author") or ""))
    quote = escape(str(row.get("text") or "")).replace("\n", "<br>")
    dry = f' <span style="color:#b45309">{s["draft"]}</span>' if row.get("dry") else ""
    label = escape(s["labels"].get(row["action"], str(row["action"])))
    meta = "".join(f" · {part}" for part in (who, link) if part)
    q = (
        '<blockquote style="margin:8px 0 0;padding:8px 12px;border-left:3px solid #0a66c2;'
        f'background:#f3f6f8;color:#333;font-style:italic">{quote}</blockquote>'
        if quote
        else ""
    )
    return (
        '<div style="margin:0 0 14px;padding:12px;border:1px solid #e5e7eb;border-radius:8px">'
        f"<b>{label}</b>{dry}{meta}{q}</div>"
    )


def render_html(slot: str, mode: str, started: str, rows: list[dict[str, Any]], notes: list[str], language: str) -> str:
    s = strings(language)
    counts = {a: sum(1 for r in rows if r["action"] == a) for a in s["labels"]}
    stats = " · ".join(f"{escape(s['labels'][a])}: <b>{n}</b>" for a, n in counts.items())
    cards = "".join(_card(r, s) for r in rows if r["action"] != "like") or f"<p>{s['empty']}</p>"
    likes = f"<p style='color:#666'>{s['likes'].format(n=counts['like'])}</p>" if counts["like"] else ""
    notes_html = (
        f"<h3 style='margin:16px 0 6px'>{s['notes']}</h3><ul>"
        + "".join(f"<li>{escape(n)}</li>" for n in notes)
        + "</ul>"
        if notes
        else ""
    )
    return (
        '<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:640px;font-size:14px;color:#111">'
        f'<h2 style="margin:0 0 4px">LinkedIn agent · {escape(slot)}</h2>'
        f'<div style="color:#666;margin-bottom:12px">{escape(started[:16].replace("T", " "))}'
        f" · {s['mode']} <b>{escape(mode)}</b></div>"
        f'<div style="padding:10px 12px;background:#f3f6f8;border-radius:8px;margin-bottom:16px">{stats}</div>'
        f"{cards}{likes}{notes_html}</div>"
    )
