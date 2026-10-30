---
name: setup
description: >-
  First-run wizard for linkedin-agent. Installs what is missing, asks the
  owner a few clickable questions (how many sessions a day, how often to
  post, how active, topics, voice), writes data/, shows sample texts, turns
  the schedule on. Use when the user says "setup", "skonfiguruj agenta",
  "zainstaluj agenta", "pierwsze uruchomienie", "konfiguracja", or right
  after the repository was downloaded.
---

# setup: the first-run wizard

The person in front of you is probably not technical. They should finish
with a working agent and the feeling that they built it themselves.

## How to talk

- Speak the user's language (Polish if they wrote in Polish). Short
  sentences, no jargon. Say "folder", not "repo"; "harmonogram", not "launchd".
- Ask with the **AskUserQuestion** tool so the user clicks answers. One or
  two questions per call, never a wall of questions. Put the recommended
  option first and mark it "(polecane)" / "(Recommended)".
- Before each step, one line on what happens and why. After each step, one
  line on what is done, ticked: "✓ Python jest", "✓ Ego Lite działa".
- Show progress as "Krok 3 z 9".
- Commands need the user's approval in Claude Code. Tell them once at the
  start: "Claude będzie pytał o zgodę na polecenia, klikaj Tak/Yes."
- Never type, read aloud or store the user's LinkedIn password. They log in
  themselves in Ego Lite.
- Never publish anything during setup.

All commands run in the project folder (the one with `bin/li`). If you were
started elsewhere, `cd` there first.

## Step 1. Check the computer

Run `bin/li doctor --json` (if Python is missing, run `python3 --version`
first) and fix what is missing, one item at a time, asking before
installing anything:

| Missing | What to do |
| --- | --- |
| `python` | macOS asks to install the Command Line Tools on first `python3` run: tell the user to click "Install" and wait. Or run `xcode-select --install`. |
| `claude` | You are running inside Claude Code, but the scheduled sessions need the `claude` command. Run `curl -fsSL https://claude.ai/install.sh | bash`, then `claude --version`. |
| `ego_lite` | If `ego-browser` exists, the `ego-browser` skill's install guide applies. Otherwise send the user to https://lite.ego.app/ to download and install Ego Lite, open it and finish its onboarding (it adds the `ego-browser` command). Wait until they say it is done, then check again. If the command is still not found, try `export PATH="$HOME/.local/bin:$PATH"`. |
| `macos` false | Scheduling works only on macOS. Explain they can still run sessions by hand with `bin/li run morning --now`. |

`config`, `voice.md`, `topics.md`, `schedule` are filled in by the next
steps; ignore them here. Then run `bin/li init`.

## Step 2. LinkedIn login in Ego Lite

Run `ego-browser skill` and follow its guide. Keep Ego in the background
(`open -g -j -a '/Applications/ego lite.app'` if it is not running; never
activate its window yourself). Open `https://www.linkedin.com/feed/` in one
TaskSpace named `linkedin-agent` and check whether the feed is visible.

- Logged in: "✓ LinkedIn jest zalogowany w Ego Lite." Note the profile name
  and URL shown in the top bar (Me / Ja) for step 4.
- Not logged in: hand the tab to the user (`task.handOff()`), ask them to
  log in in the Ego Lite window and click "Gotowe" (AskUserQuestion), then
  check again.

Finish the TaskSpace when this step is done.

## Step 3. Rhythm (clickable)

Ask:

1. **Ile razy dziennie agent ma zaglądać na LinkedIna?**
   - 3 razy: rano, w południe, wieczorem (polecane)
   - 2 razy: rano i wieczorem
   - 1 raz: rano
2. **Jak często publikować własny post?**
   - 3 razy w tygodniu: pon, śr, pt (polecane)
   - Codziennie w dni robocze
   - Codziennie
   - Wcale, tylko komentarze i odpowiedzi
3. **Jak aktywnie komentować?**
   - Normalnie: do 5 komentarzy na sesję, 12 dziennie (polecane)
   - Spokojnie: do 3 na sesję, 6 dziennie
   - Aktywnie: do 8 na sesję, 22 dziennie
4. **Godziny:** propose 08:05 / 12:35 / 18:15 (only the chosen sessions),
   options "Pasują (polecane)" / "Chcę inne". For "inne", ask for HH:MM
   per session. The agent adds a random 0-35 min delay anyway.

Mapping to `data/config.json`:

| Answer | Config |
| --- | --- |
| 3 / 2 / 1 sessions | `schedule.times` = `{morning, midday, evening}` / `{morning, evening}` / `{morning}` |
| pon-śr-pt / dni robocze / codziennie | `post_days` = `["mon","wed","fri"]` / `["mon".."fri"]` / all 7 |
| wcale | `limits_per_day.post` = 0, `limits_per_session.post` = 0 |
| spokojnie | comment 3/6, reply 10/20, like 8/20 (session/day) |
| normalnie | comment 5/12, reply 15/30, like 12/35 |
| aktywnie | comment 8/22, reply 15/40, like 20/55 |

Keep `post` at 1/1 unless "wcale". The post is written in the morning
session, so with one session a day it is that one.

## Step 4. Who you are and what you write about

1. **Język profilu:** Polski (polecane if they write Polish) / English / Inny.
   Sets `language`.
2. Ask in plain text (one message, not AskUserQuestion): imię i nazwisko,
   czym się zajmujesz w 1-2 zdaniach, do kogo piszesz (np. właściciele
   firm, rekruterzy, programiści), co sprzedajesz albo do czego mają
   prowadzić posty (może być "nic").
3. **Tematy** (AskUserQuestion, multiSelect, 4 options built from what
   they just told you, e.g. "AI w firmach", "automatyzacja procesów",
   "sprzedaż B2B", "rekrutacja"), plus "Other" for their own.
4. **Czego unikać?** multiSelect: Polityka / Religia / Krypto i szybkie
   pieniądze / Oferty pracy i giveawaye (all four preselected in the
   recommendation).

## Step 5. Your voice

Ask: **Skąd mam wziąć Twój styl pisania?**
- Przeczytam Twoje ostatnie posty na LinkedInie (polecane): open their
  profile's recent activity in Ego (read only, one TaskSpace, finish it
  after), read their last 5-10 posts and comments.
- Wkleję 3 swoje posty: wait for the paste.
- Opiszę go słowami: ask 3 short questions (formal or casual, short or
  long sentences, emoji yes/no).

Then write `data/voice.md` following `templates/voice.example.md`: who they
are, how they sound (with 3-5 of their real phrases), what they never say,
their positions, and **Proof**: only facts and numbers the user actually
gave or published. Never invent proof. Write `data/topics.md` following
`templates/topics.example.md`.

Build `feed_search_queries` from the topics: 6-10 short phrases in the
profile language, the way people would write them in posts.

## Step 6. Write the config

Update `data/config.json` (keep keys you did not ask about): `mode`
= `dry_run`, `language`, `schedule.times`, `post_days`, limits,
`feed_search_queries`, `schedule.label_prefix` = `com.linkedin-agent`.

**Powiadomienie po każdej sesji?**
- Powiadomienie na Macu (polecane): `notify.command` =
  `["osascript", "-e", "display notification \"Raport: data/reports\" with title \"{subject}\""]`
- Bez powiadomień: `null`. Reports are still saved in `data/reports/`.
- Mail: only if they already use a mail command line tool; ask for its
  exact command and use `{subject}`, `{body_file}`, `{html_file}`.

Run `bin/li status`; it must print the config without an error. Show the
user a short summary in plain words ("Agent będzie zaglądał 3 razy dziennie,
post w pon, śr i pt, do 12 komentarzy dziennie, tematy: ...").

## Step 7. Taste test

Write, following the `li-post` and `li-comment` skills and `data/voice.md`:

- one sample post on their top topic (no invented facts),
- one sample comment to a typical post in their niche.

Run both through `li-human`. Show them and ask: **Brzmi jak Ty?**
- Tak, zostaw (polecane)
- Bardziej na luzie
- Bardziej konkretnie i krócej
- Poprawię sam (wait for their notes)

Apply the feedback to `data/voice.md` (not only to the sample) and show the
corrected sample once more. Save the samples in `data/drafts/`.

## Step 8. Start mode

Ask: **Jak startujemy?**
- Najpierw próbnie, 1-2 dni (polecane): `mode` stays `dry_run`. The agent
  writes drafts to `data/drafts/` and publishes nothing. Tell them how to
  switch later: say "przełącz agenta LinkedIn na live" to Claude in this
  folder, or set `"mode": "live"` in `data/config.json`.
- Od razu na żywo: set `mode` to `live`. Remind them in one sentence that
  LinkedIn's terms restrict automation and it is their call.

## Step 9. Turn it on

Run `bin/li schedule on`, then `bin/li doctor`. Everything must be OK
except `schedule` if they are not on macOS.

Offer: **Odpalić pierwszą sesję teraz?** (tak, w tle / nie, poczekam na
harmonogram). If yes, run `bin/li run morning --now` in the background and
tell them it takes a while and the result lands in `data/reports/`.

Finish with a short card in their language:

```
✓ Agent LinkedIn działa
  Sesje:      08:05, 12:35, 18:15 (+ losowo do 35 min)
  Posty:      pon, śr, pt
  Komentarze: do 12 dziennie
  Tryb:       próbny (nic nie publikuje)
  Raporty:    data/reports/

Pauza:     powiedz "zatrzymaj agenta LinkedIn" albo: bin/li stop
Wznowienie: bin/li resume
Na żywo:   powiedz "przełącz agenta LinkedIn na live"
```

Keep Ego Lite open (it can stay in the background) and the Mac awake at the
session times; a sleeping Mac runs the missed session when it wakes up.
