# Jarvis for Omarchy

A voice-driven operator for an Omarchy desktop: **GPT-Live 1 talks, Jarvis thinks,
Paperclip works.** The voice model handles the spoken conversation; a local agent
(Hermes) owns the reasoning, the desktop tools, the safety gate, and durable work.

Built on [`wombatoperator/jarvis-voice`](https://github.com/wombatoperator/jarvis-voice)
(MIT) — same executor, policy gate and desktop toolset — with the voice/backend seam
changed so the brain stays on your machine.

**Experimental · Omarchy with Lua-based Hyprland · Python 3.11+ · MIT**

## Why this fork exists

| | Upstream | This fork |
| --- | --- | --- |
| Voice engine | Realtime default, Live as an evaluated alternative | **Live (`gpt-live-1`) default** — full duplex, `$0.05/min` |
| Delegation | Responses delegation (hosted OpenAI model does the thinking) | **Client delegation** — any agent harness, here: Hermes |
| Backend brain | `gpt-5.6-terra` on the provider's side | **Jarvis** (Hermes Agent, `deepseek-flash`) on your machine |
| Durable work | Built-in task workers | **Paperclip** — create / queue / steer / stop |
| Ship-along kit | — | `bootstrap/` — the skills and files that make it *Jarvis* |

Three reasons that matter:

1. **The brain is local.** Tool calls, files, memory and task state never leave the
   machine. The cloud sees the spoken audio and the delegations it must answer.
2. **One agent, many faces.** Voice and desktop share one Jarvis — same skills, same
   memory, same work plane — instead of a second agent with a duplicated tool layer.
3. **Nothing is decided twice.** Routing, permissions and confirmations live in one
   place (the backend + its policy gate), so a voice request and a typed request
   cannot behave differently.

## How it works

```
   you speak
      │
      ▼
┌─────────────────────────────┐        full duplex, interrupts mid-sentence
│  GPT-Live 1  (voice)        │◄────── session: v1/live/sessions   $0.05/min
│  listens · speaks · relays  │        carries a live task-board summary
└──────────┬──────────────────┘
           │ session.delegation.created  (client delegation)
           ▼
┌─────────────────────────────┐
│  Jarvis  (backend agent)    │        Hermes Agent · deepseek-flash
│  reasons · decides · acts   │        hermes -z … --continue jarvis-voice
└────┬───────────────┬────────┘
     │               │
     │               ▼
     │      ┌──────────────────────┐    create · queue · steer · stop
     │      │  Paperclip           │    durable background work
     │      └──────────────────────┘
     ▼
┌─────────────────────────────┐
│  Desktop tools + policy gate│        Hyprland · Omarchy CLI · tmux
│  hypr_dispatch · send_keys  │        OCR · browser · camera · policy
└──────────┬──────────────────┘
           │ verified result only
           ▼
   session.commentary.append → GPT-Live speaks it
```

The loop in words:

1. **GPT-Live** carries the conversation. It is listening while it speaks, so you can
   interrupt it mid-sentence. It never claims an action happened — it has no hands.
2. Every desktop request is **delegated** to the backend: `session.delegation.created`
   arrives with an id, and the transcript is the task text.
3. **Jarvis** receives it, decides what it is — a quick answer, a desktop action, or
   background work — and executes through the same tools and policy gate it uses
   anywhere else.
4. The result goes back with `session.commentary.append`, and GPT-Live says it out
   loud in one short sentence. Quiet progress (`thinking.append`) is used while work
   is still running, so silence never reads as a crash.

### The routing decision

The backend chooses one verb per request, from the conversation plus live task state:

| You say | Verb | Effect |
| --- | --- | --- |
| "open workspace three and put the browser there" | **act** | desktop tool call, verified before it is spoken |
| "what's on my screen?" | **read** | screen/OCR/terminal read, answer only |
| "also make it handle unicode" | **steer** | message into the running task |
| "start that after the parser finishes" | **queue** | new task, dependency-linked |
| "forget it" | **stop** | cancel the task |
| "now do something else entirely" | **create** | new task |

The voice layer carries a summary of the board (running / queued / blocked) so it can
*ask* the right question out loud — "the parser task is still running, add it there or
start a new one?" — but the decision is made where the state is: in the backend.

### The safety gate

Kept from upstream, unchanged, because it is the right shape:

- **Deny list** — refused outright, whatever the model decides: `rm -rf`, `mkfs`,
  `dd if=`, `sudo`, `pkexec`, `curl … | sh`, `git push`, `ssh`, `close-all`.
- **Confirm list** — held until you say the word: shutdown, reboot, suspend, package
  installs, `omarchy update`.
- **Machine-checked confirmation.** The model must pass the words you *actually said*
  to `confirm_last`; the machine matches them against its own phrase list and refuses
  otherwise. The model cannot confirm on your behalf, and not in the same turn that
  raised the hold.
- Shell execution is off by default (`[hands] allow_shell = false`). On, the model can
  run arbitrary commands on an open microphone — which is exactly as large a hole as
  it sounds.

## Status

| Part | State |
| --- | --- |
| Desktop executor, policy gate, capability discovery, OCR, browser, camera | ✅ from upstream |
| Live transport skeleton | ✅ from upstream |
| Client-delegation mode (`{"type": "client"}`) | ✅ verified end-to-end — paid probe, `tools/check_client_delegation.py` |
| Jarvis backend adapter (`hermes -z … --continue jarvis-voice`) | ✅ implemented — offline tests in `tests/test_backend.py` |
| Routing verbs (act · read · steer · queue · stop · create) | ✅ decided by the backend, executed with its own tools |
| Task-board summary in the voice session | ⏳ next |
| `bootstrap/` kit (skills, SOUL.md, AGENTS.md, SETUP.md, MCP list) | ⏳ next |
| Live session + client delegation | ✅ verified end-to-end (`tools/check_client_delegation.py`) |
| Full microphone run on this machine | ⏳ after install + key |

## Install

Requirements: an Omarchy desktop (Lua-based Hyprland), Python 3.11+, PipeWire with a
working mic and output, `python-websockets` (Arch package), plus `tmux`, `wtype`,
`grim` and `tesseract` for the terminal/OCR paths. Camera vision needs FFmpeg. A
Hermes Agent install (`~/.hermes`) is required for the backend — see the kit.

```sh
git clone https://github.com/Ntrakiyski/jarvis-omarchy.git
cd jarvis-omarchy
git switch jarvis/live-client-delegation   # while the work is in flight
./install.sh
```

Then put your key where the daemon can read it — one line, `chmod 600`:

```sh
# ~/.config/jarvis-voice/env
OPENAI_API_KEY=your-key-with-gpt-live-1-access
```

The backend does **not** read that file: Hermes keeps its own credentials in
`~/.hermes/.env`. `jarvis-voice doctor` reports what it can see.

```sh
jarvis-voice doctor
systemctl --user start jarvis-voice     # if you installed the user service
```

From a clone, without installing anything system-wide:

```sh
python3 -m venv .venv && . .venv/bin/activate && pip install -e .
jarvis-voice run --engine client                     # then `jarvis-voice listen toggle`
jarvis-voice listen say "which workspace am I on?"   # typed, no microphone needed
```

Press **Super + Shift + V** (or click the bar widget) to toggle listening. Listening
starts off and stays off until you turn it on; muting stops the recorder rather than
capturing and discarding.

## Everyday commands

| Command | Purpose |
| --- | --- |
| `jarvis-voice listen toggle` | Start or stop listening in the running daemon |
| `jarvis-voice listen confirm` / `listen cancel` | Confirm or drop a held action locally |
| `jarvis-voice say "open a terminal"` | Type a request instead of speaking it |
| `jarvis-voice map` | Explore the installed desktop's capabilities, no API call |
| `jarvis-voice status --json` | Inspect daemon state |
| `jarvis-voice log -f` | Follow private diagnostic logs |

## Configuration

`~/.config/jarvis-voice/config.toml` — the commented
[configuration example](share/config.example.toml) lists every default.

```toml
[openai]
engine = "live"                     # live (default here) | realtime

[live]
voice = "marin"
max_session_seconds = 1800          # a connected session is billed by time

[backend]                            # this fork: who does the thinking
command = "hermes"
session = "jarvis-voice"
model   = "deepseek-flash"
timeout_seconds = 120

[ears]
barge_in = false                    # headphones or PipeWire AEC before enabling
```

## The kit (`bootstrap/`)

The point of this repo is that a friend can end up with the same assistant, not just
the same daemon. The kit carries the parts that make the setup *ours* — and nothing
that makes it *private*:

- **Identity files**: `SOUL.md`, `AGENTS.md`, `SETUP.md` — the operating contract.
- **Skills we wrote**: the machine-specific ones (foundation, voice pipeline, Hyprland
  control, Paperclip operations, context tooling, web access…). Vendored skills are
  *referenced and installed*, never copied — copies drift and misattribute licences.
- **MCP servers**: `scrapling` (web), `slm-*` (self-hosted memory), `headroom`
  (context compression).
- **Inventory**: packages, cron jobs, `bin/` helpers, the `rtk-rewrite` plugin —
  generated from a live machine.
- **Installer + doctor**: `bootstrap/install.sh` and a checker that reports what a new
  machine is missing.

Deliberately excluded, by construction: `.env` and every credential, `state.db`,
`memories/`, `sessions/`, `logs/`, `state-snapshots/`. Publication rules and the
scanner are upstream's own (`tools/check_public_files.py --staged`, `--history <rev>`,
`git config core.hooksPath .githooks`).

## Documentation

| Guide | Contents |
| --- | --- |
| [Client delegation](docs/client-delegation.md) | This fork's voice path: session config, backend contract, routing, failure semantics |
| [Live backend](docs/live.md) | Upstream's Live path: sessions, limits, audio, engine switching |
| [Task workers](docs/task-workers.md) | Upstream's worker model (this fork routes to Paperclip) |
| [Vision](docs/vision.md) | Camera setup, crop, privacy, latency |
| [Diagnostics](docs/diagnostics.md) | Troubleshooting, latency, private logs |
| [System discovery](docs/omarchy-architecture.md) | How the agent reads the installed desktop |
| [Security](SECURITY.md) | Data sharing, execution boundaries, disclosure |

## Development

```sh
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -e '.[dev]'
python -m unittest discover -s tests
```

Unit tests are offline: synthetic audio, mocked providers, fake desktops. Paid and
real-desktop checks are explicit opt-ins.

## Credits

Fork of [wombatoperator/jarvis-voice](https://github.com/wombatoperator/jarvis-voice)
(MIT) — the executor, policy gate, capability discovery and much of the hard-won
behaviour in this tree are his work. This fork changes the voice/backend seam and
ships the personal-agent kit. Licensed under the [MIT License](LICENSE).
