# Third-party notices

The writing skills `li-post`, `li-comment`, `li-reply`, `li-plan` and
`li-human` (including `humanize.py`, `detect.py`, `slop.json` and
`hooks.json`) in `.claude/skills/` are adapted from
[Jakeschincariol/linkedin-agent-skill](https://github.com/Jakeschincariol/linkedin-agent-skill),
MIT License, Copyright (c) 2026 Jake Schincariol. The full license text is in
`.claude/skills/LICENSE-li-skills-MIT`.

Changes: paths made relative to the project root, output language taken from
`data/config.json`, Unicode-aware word counting in `detect.py`, the action log
moved to `data/log.jsonl`, minor file-handling fixes.
