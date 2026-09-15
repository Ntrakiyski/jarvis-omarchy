# Setting this up on a fresh machine

Two ways in, same end state:

* **do it yourself** — follow the sections below in order;
* **let your agent do it** — give your Hermes the repo URL and say
  *"set this up for me"*, or paste it [the agent brief](#instructions-for-an-agent) explicitly.
  Everything the brief needs is in this file.

The end state: pressing `SUPER + SHIFT + V` opens a voice session with Jarvis, the orb rises
from the bottom of the screen and breathes while either of you talks, a window in your app
menu shows what he has running, and background jobs land on that window's board instead of
disappearing into a terminal you aren't watching.

---

## 1. Omarchy and Hermes

1. **Omarchy 4.x** — <https://omarchy.org>. This fork is built against 4.0.3 and assumes the
   Lua configuration (`~/.config/hypr/bindings.lua`, `hyprctl`).

2. **Hermes Agent** — <https://hermes-agent.nousresearch.com/docs>. Any provider works; the
   reference machine runs the backend on `deepseek-flash` because it is cheap and fast. Give
   it at least one working provider key before continuing.

   ```sh
   hermes --version
   hermes -z "say ready in one word"     # proves credentials end to end
   ```

3. **An OpenAI API key with GPT-Live access.** The voice model is `gpt-live-1` and access is
   account-gated — a key that works for chat may not work for Live. Check before you build
   anything else:

   ```sh
   python3 - <<'PY'
   import json, urllib.request
   key = input("key: ").strip()
   r = urllib.request.Request("https://api.openai.com/v1/models",
                              headers={"Authorization": f"Bearer {key}"})
   print("gpt-live-1 visible:", "gpt-live-1" in
         [m["id"] for m in json.load(urllib.request.urlopen(r))["data"]])
   PY
   ```

   **Never paste that key into a chat** — not to an agent, not to me. It goes in a file
   (step 3 below).

## 2. System packages

```sh
sudo pacman -S python-gobject gtk4 libadwaita pipewire-audio \
               tmux wtype grim tesseract ffmpeg libnotify
```

`hyprctl` and `omarchy` come with Hyprland and Omarchy. `python-websockets` is *not* needed
here — the installer builds a private virtualenv for the daemon (that is the point of it).

## 3. This repo

```sh
git clone https://github.com/Ntrakiyski/jarvis-omarchy.git
cd jarvis-omarchy
./install.sh
```

The installer asks four questions and is safe to re-run:

| Question | Answer means |
| --- | --- |
| install the bar widget and the voice orb? | the two on-screen faces (bar icon + bottom orb) |
| install the `omarchy voice …` commands into /usr/bin (needs sudo)? | optional alias; answering **no** is fine |
| install the systemd user service? | yes — the daemon then starts with your session |
| bind SUPER + SHIFT + V? | yes — one key: listen / pause / resume |

Then the key, in a file with mode 600:

```sh
install -m 600 /dev/null ~/.config/jarvis-voice/env
echo 'OPENAI_API_KEY=sk-…' >> ~/.config/jarvis-voice/env
```

The backend (Hermes) keeps **its own** credentials in `~/.hermes/.env`; nothing about the
model backend belongs in this file.

```sh
systemctl --user enable --now jarvis-voice
jarvis-voice doctor          # expect ✓ everywhere, and no ✗ in the "ears" block
```

Press **`SUPER + SHIFT + V`**: the orb rises from the bottom of the screen. Say something.
Chat is instant — that is GPT-Live. Anything that needs your desktop, files or memory takes
ten to twenty seconds, because the thinking happens in a full agent turn on your machine.

The window: **"Jarvis" in your app menu**, or `jarvis-voice-app open`. It shows the session
state, a listen/pause/resume button, and the background jobs board.

## 4. What the key actually does

One key, three meanings, resolved from live state:

| Session state | Pressing `SUPER + SHIFT + V` |
| --- | --- |
| nothing open | **start** — opens a session and listens |
| listening or working | **pause** — closes the recorder, keeps the session |
| paused | **resume** — reopens the recorder in the same session |

**New session** in the window is the boundary: it cancels every background job this session
started, forgets them locally, and starts the next conversation with a clean memory.

Cost, plainly: a connected session is billed by the minute — about **$0.05/min** — whether or
not anyone is speaking, and your model provider bills the backend separately. A paused session
is closed automatically after two minutes so it cannot bill in the background.

## 5. The work plane (optional, but this is the board)

The jobs board reads **Paperclip** — a local work plane where every durable job is an issue.

```sh
npm install -g paperclipai      # Node 20+
paperclipai run                 # serves http://127.0.0.1:3100
```

Then give your agent a scoped key so it can create and stop jobs — that is the
`paperclip-task-bridge` skill in the reference setup: create a `task_bridge` key and put
`PAPERCLIP_API_URL`, `PAPERCLIP_BRIDGE_API_KEY`, `PAPERCLIP_COMPANY_ID`, `PAPERCLIP_AGENT_ID`
in `~/.hermes/.env`. Without Paperclip the board says *"Paperclip unreachable"* and voice
still works — you just have no board.

Two conventions the board depends on:

* every job Jarvis starts is titled **`[Jarvis] <topic> · YYYY-MM-DD HH:MM`** — the marker is
  how the window tells his work from everything else in the work plane;
* the board shows only the **current session's** jobs, and cancels them on *New session*.

## 6. The agent half

The voice model only speaks; the work happens in a Hermes session named `jarvis-voice-<n>`,
created on the first connection and rotated on *New session*. Each turn is prefixed with a
short contract (answer for speech, two sentences, never claim an action a tool did not
confirm, name background jobs by the convention above) plus the jobs this session has started.

Optional, and worth it:

| What | Why | Install |
| --- | --- | --- |
| scrapling MCP | so the agent can read the web at all | `uv tool install scrapling` → `hermes mcp add scrapling --command ~/.local/bin/scrapling-mcp` |
| skills | the procedures the agent should follow | ship the ones you want in `~/.hermes/skills/` |

## 7. Traps that cost us time

* **`python3` is not always `/usr/bin/python3`.** On machines with mise/uv, the shell's
  `python3` is a different interpreter without `websockets`. The launcher prefers the private
  venv beside the install for exactly this reason; if the daemon logs
  *"python-websockets is not installed"*, check the venv, not the package.
* **Hyprland's Lua bindings do not reload on file change.** After editing
  `~/.config/hypr/bindings.lua` run `hyprctl reload`; `hyprctl keyword` is refused by the Lua
  parser (*"keyword can't work with non-legacy parsers"*) — `hyprctl eval` exists for one-offs.
* **Microphone gain is the usual reason transcripts are mush.** Two gain stages (`Internal Mic
  Boost` and `Capture`) can both sit at maximum — that is +60 dB of clipping. Set
  `Internal Mic Boost` to 0 and `Capture` to about 65%, then **re-read both**: some tools
  re-pin them when you touch a volume elsewhere.
* **The orb only exists while a session is awake**, and needs its plugin enabled
  (`omarchy plugin enable voice.orb`). After editing its QML:
  `omarchy plugin disable voice.orb && omarchy plugin enable voice.orb`.
* **Diagnostics live in files**: `~/.local/state/jarvis-voice/client-trace.jsonl` (every
  session, delegation, backend turn and append), `~/.local/state/jarvis-voice/session.log`,
  `journalctl --user -u jarvis-voice -f`.
* **Uninstall**: `./uninstall.sh` removes the app; `--purge` also drops
  `~/.config/jarvis-voice` and the state directory.

---

## Instructions for an agent

*For a Hermes (or any capable agent) on a fresh Omarchy machine. The human has cloned this
repo and asked you to set it up. Work in order, verify each step, and stop rather than guess.*

**You are setting up `jarvis-omarchy`** — a voice interface where GPT-Live speaks and you (the
local agent) think and act. Read `README.md` first; it explains the architecture you are
installing. `docs/client-delegation.md` has the protocol detail.

**Ground rules — these are not negotiable:**

1. Write only in user space (`~/.config`, `~/.local`, `~/.hermes`, the repo). **Never** write
   to `/usr/share/omarchy/` or any package-owned path; edits there are destroyed by updates.
2. Never modify Omarchy's source or run `omarchy dev …`.
3. Back up a file before editing it (`<name>.bak.<timestamp>`).
4. Apply and verify every change: `hyprctl reload && hyprctl configerrors` for Hyprland, a
   restart plus a state check for services.
5. Never print a credential, and never ask the human to paste one into chat. Keys go in files
   with mode 600; you verify *presence and permissions*, never the value.
6. If a step cannot be completed, say what failed and what you tried. Do not report success
   for something you did not observe.

**Steps**

1. **Survey.** `omarchy --version`, `hyprctl version`, `python3 --version`,
   `readlink -f "$(command -v python3)"`, `command -v hyprctl tmux wtype grim tesseract ffmpeg`.
   Note what is missing; do not install anything before step 2.

2. **Packages.** Install what step 1 found missing:
   `sudo pacman -S python-gobject gtk4 libadwaita pipewire-audio tmux wtype grim tesseract
   ffmpeg libnotify`. Nothing else is required — the installer builds its own virtualenv for
   `websockets`. Ask the human before any `sudo` if the machine is not theirs.

3. **The app.** From the repo: `./install.sh`. It asks four questions; default to yes for the
   bar widget + orb and the systemd service, yes for the keybinding, and **no** for the
   `/usr/bin` aliases (that one needs sudo and adds nothing).

4. **The key.** The human puts an OpenAI key **with GPT-Live access** into
   `~/.config/jarvis-voice/env` (`OPENAI_API_KEY=…`, mode 600). Do not type it, do not read
   it, do not echo it. Verify only that the file exists, is mode 600, and contains a
   non-empty `OPENAI_API_KEY` line — report those facts, never the value. If their key lacks
   Live access the session will refuse to start; `docs/live.md` explains the failure mode.

5. **Start and check.**
   `systemctl --user enable --now jarvis-voice`, then `jarvis-voice doctor` and
   `systemctl --user is-active jarvis-voice`. Doctor's "ears" block must show no ✗.

6. **The keybinding.** `hyprctl binds` should list `SUPER SHIFT, V` with the description
   *"Jarvis: listen / pause"*. If it is missing, `hyprctl reload` (the Lua file is re-read
   then, not on file change). Do not simulate the keypress to test it.

7. **Prove the transport without a microphone** — this is the honest test, because it needs no
   human:
   ```sh
   jarvis-voice listen start && sleep 8 && jarvis-voice status --json && jarvis-voice listen stop
   ```
   `status` should read `listening` while it is open, and the trace at
   `~/.local/state/jarvis-voice/client-trace.jsonl` should contain a `session.started` line.
   A session costs pennies; stop it when done.

8. **Optional work plane.** If the human wants the jobs board: `npm install -g paperclipai`,
   `paperclipai run`, then create a `task_bridge`-scoped key and put `PAPERCLIP_API_URL`,
   `PAPERCLIP_BRIDGE_API_KEY`, `PAPERCLIP_COMPANY_ID`, `PAPERCLIP_AGENT_ID` in
   `~/.hermes/.env`. Verify with a read, not a write: `GET /api/companies/<id>/issues` on
   `127.0.0.1:3100` should return a list.

9. **Tell the human what to do next**, in their words: press `SUPER + SHIFT + V` and speak;
   chat is instant, work takes ten to twenty seconds; the window is in the app menu; *New
   session* cancels that session's jobs; a connected session bills about $0.05/minute.

**Stop and ask if:** GPT-Live access is missing; `doctor` reports an ✗ you cannot explain; the
machine already runs a different voice stack on the same key (a second daemon holding the
microphone will fight this one); or any step would need a system file changed.
