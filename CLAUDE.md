# linkedin-agent

Agent that runs the owner's LinkedIn account 3x a day in Ego Lite. See README.md.

- Skills live only in `.claude/skills/` of this project: `linkedin-session`
  (operator playbook), `li-post`, `li-comment`, `li-reply`, `li-plan`, `li-human`.
- Scheduled agent: `.claude/agents/linkedin-operator.md`.
- CLI: `bin/li` (state, limits, log, runner, schedule). Code in `src/linkedin_agent/`, tests in `tests/`.
- Private state is `data/` (git-ignored): config, voice, topics, plan, log, drafts, reports.
  Never commit anything from `data/` and never copy personal facts into tracked files.
- Mode: `data/config.json` `mode` = `dry_run` or `live`. Emergency stop: `touch data/STOP`.
- No MCP servers, no external posting APIs. Browser = Ego Lite only.
- Before committing: `uv run --no-project --with pytest python -m pytest` and `uvx ruff check .`.
