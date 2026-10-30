# linkedin-agent

Agent that runs the owner's LinkedIn account 3x a day in Ego Lite. See README.md.

## When a person opens Claude Code in this folder

- If `data/config.json` does not exist or `bin/li doctor` reports `voice.md`/`topics.md`
  as templates, offer to run the `setup` skill (the first-run wizard) and run it on "yes".
- "zatrzymaj agenta" / "stop the agent" = `bin/li stop`; "wznów" / "resume" = `bin/li resume`.
- "przełącz na live" / "go live" = set `"mode": "live"` in `data/config.json` after one
  confirmation; "tryb próbny" / "dry run" = `"mode": "dry_run"`.
- "co dziś zrobił agent?" / "what did the agent do?" = `bin/li status` plus the latest
  file in `data/reports/`, summarised in plain words.

## Project rules

- Skills live only in `.claude/skills/` of this project: `linkedin-session`
  (operator playbook), `setup` (first-run wizard), `li-post`, `li-comment`, `li-reply`, `li-plan`, `li-human`.
- Scheduled agent: `.claude/agents/linkedin-operator.md`.
- CLI: `bin/li` (state, limits, log, runner, schedule). Code in `src/linkedin_agent/`, tests in `tests/`.
- Private state is `data/` (git-ignored): config, voice, topics, plan, log, drafts, reports.
  Never commit anything from `data/` and never copy personal facts into tracked files.
- Mode: `data/config.json` `mode` = `dry_run` or `live`. Emergency stop: `touch data/STOP`.
- No MCP servers, no external posting APIs. Browser = Ego Lite only.
- Before committing: `uv run --no-project --with pytest python -m pytest` and `uvx ruff check .`.
