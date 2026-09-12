# Live backend

Live handles voice conversation while a separate Responses model chooses desktop
tools. Those tools run locally through the same executor and policy as Realtime.
Realtime remains the default; Live requires account access to its configured
voice and backend models.

## Select an engine

Stop the existing daemon before running another one in the foreground:

```sh
omarchy-voice listen quit
omarchy-voice run --engine live
```

Use `--engine realtime` to switch back. To choose persistently, edit
`~/.config/omarchy-voice/config.toml` and restart the idle user service:

```toml
[openai]
engine = "live"
```

See `[live]` in the [configuration example](../share/config.example.toml) for
model, voice, reasoning, playback, and task limits. `omarchy-voice doctor` reports
the configured backend and available devices.

The Live daemon starts muted and opens no paid voice session at boot. Realtime
also starts muted, but opens its connection at startup and keeps it while muted;
Live's session/idle limits do not apply to Realtime. Toggle listening
with the keybinding, bar widget, or `omarchy-voice listen start`.
`omarchy-voice listen say "which workspace am I on?"` sends a typed request to the
running engine without enabling a muted microphone; it does not mute an already
active microphone. The separate `omarchy-voice say`
command uses the one-shot planner.

## Usage and session limits

Live voice sessions, delegated model calls, and hosted tools can have separate
charges. Consult [current OpenAI pricing](https://developers.openai.com/api/docs/pricing)
and your account's model access. Connected silence can incur session charges.
The application does not enforce an account-wide spending cap.

| Setting | Effect |
| --- | --- |
| `live.max_session_seconds` | Stops a session at its time limit; listening must be enabled again |
| `live.typed_idle_seconds` | Closes an inactive typed session when backend work and queued input are clear; received non-silent audio resets the timer |
| `openai.max_turns` | Bounds tool rounds for a request |
| `live.max_output_tokens` | Limits each backend response |
| `live.service_tier` | Selects standard or priority backend processing |
| `live.browser_max_turns` / `live.browser_timeout_seconds` | Bounds delegated browser work |

Toggling off closes the Live session and stops microphone capture and playback.
Already-started desktop actions and independent background tasks can continue.
Logs record final voice usage and separate backend token usage; a lost connection
can leave final billing unconfirmed.

The typed idle timer measures protocol activity, not the local playback queue.
Very short idle limits can interrupt buffered speech. `listen cancel` drops a held
confirmation in either engine; Live also invalidates unstarted calls from the
current request and tells the voice model to stop that request. It does not cancel
durable task workers.

## Desktop and browser behavior

Selected independent read-only calls, distinct native application launches, and
exactly addressed window closes can run concurrently. Focus, typing, scrolling,
and other layout changes remain ordered.
Duplicate targets are serialized. A failed dependency prevents dependent actions
from proceeding; already-started independent calls retain their results.

New speech pauses unstarted calls and forwards the correction after outstanding
results drain. This does not undo completed actions. Transcript fragments are not
an authoritative signal that speech has finished, so ambiguous confirmations are
best handled with `omarchy-voice listen confirm` or `listen cancel`.

Browser reading tries selectable text before OCR, checks focus and visibility,
and preserves supported clipboard data. A focused input can yield only that
field's text. Complex browser requests may use a separate computer-use worker
with `gpt-6-astra`, sending screenshots and incurring additional API usage. Its
model is currently set in `browser.py`, independently of the configurable camera
model. Disable that route with
`live.browser_enabled = false` if you do not need it.

URL-based research navigates one normal browser window in place and can reuse
that window across requests when its identity and workspace still match. It
stops if focus or geometry changes during computer use. See
[browser diagnostics](diagnostics.md#browser-and-worker-recovery) for reuse limits.

## Audio and recovery

Playback uses a small jitter buffer with paced audio frames. With
`ears.barge_in = false`, microphone samples are replaced with silence while OMA
speaks and during its echo tail. Use headphones or PipeWire echo cancellation
before enabling interruptions. Muting stops the recorder entirely.

Bounded conversation history and action outcomes persist in owner-only
`live-state.json` under the application state directory. On restart, unfinished
actions are marked uncertain and are not automatically replayed. Pending
confirmations are not restored across daemon restarts. Inspect actual desktop
state before retrying interrupted work.

Server conversation storage is disabled in requests, but prompts, audio, and tool
results still go to the provider for processing. Local saved history and logs are
private data. See [security](../SECURITY.md) and [diagnostics](diagnostics.md).

## Verify setup

First run the offline regression tests from a clone:

```sh
python3 -m unittest discover -s tests -p test_live.py
```

An optional paid protocol probe sends synthetic silence and exposes only a
harmless function. It does not capture a microphone, play audio, or read the
desktop:

```sh
python3 tools/check_live.py --connect
```

For a manual device check, enable listening, ask which workspace is active, try
one ordinary window action, then mute. Check that the indicator clears and that
session logs record closure. This verifies your devices and model access; an
offline test cannot establish microphone quality or service availability.
