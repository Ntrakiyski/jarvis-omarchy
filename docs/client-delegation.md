# Client delegation: GPT-Live speaks, a local agent thinks

This fork's voice path. Upstream's Live backend uses **Responses delegation** —
OpenAI runs the backend model and calls the desktop tools. Here the session is
created with **client delegation**, so every request GPT-Live would delegate
arrives in this process, and this process hands it to a local agent.

```toml
[openai]
engine = "client"

[backend]
command = "hermes"
session = "jarvis-voice"
timeout_seconds = 120
```

## What changes against upstream

| | Upstream (`engine = "live"`) | This fork (`engine = "client"`) |
| --- | --- | --- |
| Session config | `delegation.responses.{model,instructions,tools}` | `delegation: {"type": "client"}` |
| Who chooses tools | the hosted backend model | the backend agent, on this machine |
| Who executes them | this process, via `tools.py` | the backend agent, with its own tools |
| Result path | `response.item.create` + `response.create` | `session.commentary.append` |
| Task state | `tasks.py` workers | the backend's work plane (Paperclip) |
| Cloud sees | prompts, tools, results | audio, and the text it is asked to say |

`realtime.py` and `live.py` are untouched, so `engine = "realtime"` and
`engine = "live"` still behave exactly as upstream documents them.

## The loop

```
mic ──► session.input_audio.append ──► GPT-Live
                                        │  session.delegation.created
                                        ▼
                        backend.ask(utterance)  →  hermes -z … --continue jarvis-voice
                                        │            (one turn, verified text only)
                                        ▼
   speaker ◄── session.output_audio.delta ◄── session.commentary.append
```

Code: [`live_client.py`](../src/omarchy_voice/live_client.py) (transport),
[`backend.py`](../src/omarchy_voice/backend.py) (the agent turn).

## The backend contract

Each delegation is one turn in a named Hermes session. The turn is prefixed with a
short contract — answer for speech, at most two sentences, plain words, say only
what a tool result confirmed, ask for a go-ahead before anything irreversible —
and the last few exchanges are carried as context so pronouns resolve.

Rules that the implementation enforces rather than trusts:

- **A result is data.** `session.commentary.append` content is *paraphrased* by the
  voice model, not read aloud. Because a hedge can be dropped and a negative can be
  flipped, every failure path returns a sentence that survives paraphrase:
  "The backend did not answer in time, so nothing was done."
- **Never raise into the voice loop.** A timeout, a non-zero exit, an empty answer,
  or a command that is not on `PATH` each come back as `ok = False` with a spoken-able
  fact. The process running the conversation must not die because a turn failed.
- **Create the session on demand.** `-z … --continue NAME` refuses a session that does
  not exist. On that error the adapter bootstraps once with
  `chat --continue NAME --create-if-missing --cli` and retries the turn.
- **Bound everything.** `timeout_seconds` per turn, `live.max_session_seconds` for the
  session, `MAX_APPEND_CHARS` for one append (the API caps appends at 500 tokens).

## Routing: what the backend decides

The voice layer relays; the backend decides, because it is the only part that can see
task state. One verb per request:

| Request | Verb | Where it lands |
| --- | --- | --- |
| desktop action, quick answer, screen read | **act / read** | the agent's own tools, verified before it is spoken |
| "also handle unicode" | **steer** | a message into the running task |
| "start that after the current one" | **queue** | a new task, dependency-linked |
| "forget it" | **stop** | cancel the task |
| unrelated new goal | **create** | a new task |

The voice model carries no task list of its own: it asks, the backend answers.

## Typed path

`jarvis-voice listen say "which workspace am I on?"` skips the microphone: the text
goes straight to the backend and the answer is appended as commentary, so it is spoken
back. Useful for testing without speaking, and for exact strings (paths, IDs).

## Testing

```sh
# transport only: does the account accept client delegation? (paid, ~30 s)
ffmpeg -i phrase.mp3 -ar 24000 -ac 1 -f s16le /tmp/phrase.pcm
python tools/check_client_delegation.py --connect --pcm /tmp/phrase.pcm

# the backend adapter, offline, no key needed
python -m unittest tests.test_backend -v
```

The adapter's tests never call Hermes: they run throwaway shell scripts as the
backend command, covering the verified answer, the timeout, the non-zero exit, the
empty answer, the missing session retry and the unavailable command.

## The window and the key

`jarvis-voice-app` is the face: a GTK4 window (status, both loudness meters, a
Listen/Pause/Resume button, an End session button, and a real close button) that
launches from the app menu and runs as its own transient systemd user unit — a
bare `Gtk.Application` inside an agent shell fails to register ("the name is not
activatable"), and the unit gives single-instance for free.

One key, three meanings, resolved from live state rather than assumed:

| state | `jarvis-voice-app toggle` does |
| --- | --- |
| no session | **start** — open a session and listen |
| listening / thinking | **pause** — close the recorder, keep the session |
| paused | **resume** — reopen the recorder in that same session |

Pause must not end the take: the daemon's own `toggle` opens and closes sessions,
so using it here would kill the conversation on a pause. Closing the window ends
the session, and a session left paused is closed by the daemon after
`live_paused_idle_seconds` — connected time bills whether or not anyone speaks.

Note on Hyprland (Omarchy 4, Lua config): `hyprctl keyword` is refused
("keyword can't work with non-legacy parsers"), and a new binding only enters the
running compositor after `hyprctl reload` — the Lua is re-evaluated then, not on
file change. `hyprctl eval` executes Lua against the live compositor if a
one-off is needed.

## The jobs board

`jobs.py` reads the local Paperclip company (`GET /api/companies/{id}/issues`, no
auth on loopback) and maps its statuses onto four columns: working (todo, backlog,
in_progress), needs-you (blocked, in_review), done, cancelled. Cards show the real
status word, an age, the assigned agent, and sort newest-first; the board refreshes
every three seconds behind a five-second cache. An unreachable server keeps the last
good board and says so in the header line rather than emptying itself.

## Failure semantics worth keeping

- Muting stops the recorder; it does not end the session, so a delegated turn keeps
  running while the microphone is closed.
- Interrupting speech does not cancel backend work. The session keeps its task; the
  voice model is told, in its prompt, that a result is an answer and not a new request.
- Session close is graceful (`session.close`), so final usage is reported; a lost
  connection can leave the last usage unconfirmed.
- Reconnects are bounded (`realtime.RECONNECT_ATTEMPTS`) and a session that dropped
  mid-work does not replay that work: it must be asked again.
