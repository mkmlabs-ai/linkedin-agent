# linkedin-agent

A scheduled agent that keeps your own LinkedIn account active: it publishes
the planned post of the day, comments on relevant posts in your niche,
answers comments under your posts and leaves reactions. It runs three times a
day as a headless [Claude Code](https://claude.com/claude-code) session that
drives a local, logged-in browser (Ego Lite) the way a
person would.

No LinkedIn API, no MCP server, no third-party automation service, no cookies
leave your machine. Everything the agent knows about you lives in a private
`data/` folder that is never committed.

> **Read this first.** LinkedIn's User Agreement restricts automated activity.
> Running this agent on your account is your decision and your risk. Start in
> `dry_run`, keep the limits low, and read every draft before you switch to
> `live`.

## How it works

```
launchd (3x a day, random jitter)
  └─ bin/li run <slot>              Python runner: STOP file, lock, timeout, report, notify
      └─ claude -p --agent linkedin-operator
          └─ skill linkedin-session   the operator playbook
              ├─ skill ego-browser    browser control (your logged-in profile)
              ├─ skills li-post / li-comment / li-reply / li-human   writing
              └─ bin/li can|target|log|pause   limits, de-duplication, audit log
```

Guard rails, enforced in code and in the playbook:

- `dry_run` mode drafts everything and publishes nothing.
- Per-session and per-day limits for posts, comments, replies and reactions.
- Never two engagements on the same post (URLs are normalized), and a
  cooldown before commenting on the same author again.
- Human-like pauses between actions and per-key typing delay.
- Emergency stop: `touch data/STOP`. Any login wall, captcha or
  "unusual activity" warning makes the agent stop and create that file itself.
- Content read from LinkedIn is treated as data, never as instructions.
- One session at a time (kernel file lock), hard timeout per session.
- Every action is appended to `data/log.jsonl`; each run ends with a short
  report (text + HTML) that can be sent to you by any command you configure.

## Requirements

- macOS (scheduling uses launchd; the CLI itself is portable)
- Python 3.10+
- [Claude Code](https://docs.claude.com/en/docs/claude-code) CLI logged in
- Ego Lite with the `ego-browser` skill installed, logged in to LinkedIn

## Setup

```bash
git clone https://github.com/mkmlabs-ai/linkedin-agent.git
cd linkedin-agent
bin/li init            # creates data/ from templates/ (never overwrites)
```

Then fill in your private files:

| File | What goes in |
| --- | --- |
| `data/config.json` | mode, language, limits, search queries, schedule, notify command |
| `data/voice.md` | who you are, how you write, the only facts and numbers the agent may use |
| `data/topics.md` | what to post and comment about, what to avoid |
| `data/plan.md` | optional, owner-approved post plan per day (text, image or video) |

Try one session by hand, without the random start delay:

```bash
bin/li run morning --now
cat data/reports/$(date +%F)-morning.txt
```

When the drafts look right, set `"mode": "live"` and turn on the schedule:

```bash
bin/li schedule on      # installs 3 LaunchAgents from config.schedule
bin/li schedule status
bin/li schedule off
```

### Notifications

`notify.command` is an argv list run after each session; `{subject}`,
`{body_file}` and `{html_file}` are substituted. Example with a mail CLI:

```json
"notify": {"command": ["mail-cli", "send", "--to", "you@example.com",
                       "--subject", "{subject}", "--body-file", "{body_file}",
                       "--html-file", "{html_file}"]}
```

## CLI

```
bin/li init | status | can ACTION | target URL [--author NAME]
bin/li log ACTION --url URL [--author NAME] [--text-file F] [--dry]
bin/li pause | typing-delay | session-start SLOT | session-end
bin/li run SLOT [--now] | schedule on|off|status
```

`ACTION` is `post`, `comment`, `reply` or `like`; `SLOT` is `morning`,
`midday` or `evening`. Set `LINKEDIN_AGENT_HOME` to keep `data/` outside the
checkout.

## Project layout

```
.claude/agents/linkedin-operator.md   the scheduled agent (model, effort, scope)
.claude/skills/                       operator playbook + writing skills
bin/li                                CLI entry point (no install needed)
src/linkedin_agent/
  settings.py   paths, config defaults and validation
  state.py      action log, limits, de-duplication, cooldowns
  runner.py     one guarded session around `claude -p`
  report.py     text fallback and HTML report
  scheduler.py  launchd plists
  cli.py        argument parsing
templates/                            public examples copied by `bin/li init`
tests/                                pytest suite
data/                                 private state, git-ignored
```

## Development

```bash
uv run --no-project --with pytest python -m pytest
uvx ruff check . && uvx ruff format --check .
```

## License

MIT, see [LICENSE](LICENSE). The writing skills are adapted from
[Jakeschincariol/linkedin-agent-skill](https://github.com/Jakeschincariol/linkedin-agent-skill)
(MIT), see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
