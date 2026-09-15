"""The Jarvis window: a small GTK4 app for the voice session.

The daemon is the engine; this is the face — a real window with a real close
button. It reads the same ``state.json`` and ``level`` files the bar widget and
the orb read, and it drives the same control socket the keybinding drives, so the
window can never disagree with what the assistant is actually doing.

Lifecycle. The window is not a child of whoever asked for it: it is started as
its own transient systemd user unit (``jarvis-voice-window``). That gives two
things at once — the graphical environment the toolkit expects (a bare
``Gtk.Application`` registration inside an agent shell fails with "the name is
not activatable"), and single-instance behaviour for free: a second request
finds the unit already running, raises the window, and exits.

Session semantics, which the keybinding relies on:

* ``start``  — open a session and listen. The microphone is live.
* ``pause``  — close the recorder, keep the session. The take survives, so
  coming back is a resume rather than a new conversation.
* ``resume`` — open the recorder again, in that same session.
* ``stop``   — end the session. Closing the window does this too.

A paused session still costs Live time, so the daemon closes it by itself after
``live_paused_idle_seconds`` idle. A session with no window on screen and nobody
listening is exactly the silent cost this should not have.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import LEVEL_FILE, STATE_FILE, Config, load
from .session import daemon_running, send_control

UNIT = "jarvis-voice-window"
PROGRAM = "jarvis-voice"
TICK_MS = 200

STATUS_TEXT = {"idle": "Idle", "listening": "Listening", "thinking": "Working",
               "paused": "Paused", "error": "Error"}
STATUS_COLOR = {"idle": "#7a7a7a", "listening": "#22aa88", "thinking": "#e0b341",
                "paused": "#b08040", "error": "#cc4444"}
STATUS_HINT = {
    "idle": "Press SUPER + SHIFT + V to listen",
    "listening": "Say something — the key pauses, the same key resumes",
    "thinking": "Working on it…",
    "paused": "Paused — the session is kept warm for two minutes",
    "error": "Something failed — see the log",
}


def read_status() -> tuple[str, str, float]:
    try:
        payload = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return "idle", "", 0.0
    return (str(payload.get("status", "idle")), str(payload.get("text", "")),
            float(payload.get("updated", 0.0)))


def read_levels() -> tuple[float, float]:
    try:
        parts = LEVEL_FILE.read_text().split()
    except OSError:
        return 0.0, 0.0
    try:
        return float(parts[0]), float(parts[1]) if len(parts) > 1 else 0.0
    except (ValueError, IndexError):
        return 0.0, 0.0


# --- daemon control ---------------------------------------------------------

def ensure_daemon(config: Config, wait: float = 15.0) -> bool:
    if daemon_running():
        return True
    subprocess.run(["systemctl", "--user", "start", "jarvis-voice.service"],
                   capture_output=True)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if daemon_running():
            return True
        time.sleep(0.25)
    return False


def control(config: Config, command: str) -> str:
    """One control command, starting a sleeping daemon first if need be."""
    for attempt in (0, 1):
        try:
            return send_control(command)
        except (ConnectionError, OSError):
            if attempt or not ensure_daemon(config):
                break
    return json.dumps({"error": "the voice daemon is not running"})


def resolve_toggle() -> str:
    """What the key means right now: start, pause, or resume.

    It has to be read from the live state, not assumed: the daemon's own `toggle`
    opens and closes sessions, and using that here would end the take instead of
    pausing it — the opposite of one key that starts, pauses and resumes.
    """
    status, _, _ = read_status()
    return {"listening": "pause", "thinking": "pause", "paused": "resume"}.get(status, "start")


def describe(reply: str) -> str:
    try:
        payload = json.loads(reply)
    except (ValueError, TypeError):
        return str(reply)[:200]
    if payload.get("error"):
        return str(payload["error"])[:200]
    return str(payload.get("queued") or payload.get("status") or "ok")[:200]


# --- window lifecycle (systemd unit, not a child process) -------------------

def unit_active() -> bool:
    result = subprocess.run(["systemctl", "--user", "is-active", f"{UNIT}.service"],
                            capture_output=True, text=True)
    return result.stdout.strip() == "active"


def focus_window() -> bool:
    result = subprocess.run(
        ["hyprctl", "dispatch", "focuswindow", f"class:^({PROGRAM})$"],
        capture_output=True, text=True)
    return "ok" in result.stdout.lower()


def launcher_path() -> str:
    candidate = Path(sys.argv[0]).resolve()
    if candidate.exists():
        return str(candidate)
    return shutil.which("jarvis-voice-app") or "jarvis-voice-app"


def open_window() -> str:
    """Start the window unit, or raise the window if it is already up."""
    if unit_active():
        focus_window()
        return "window already open"
    result = subprocess.run(
        ["systemd-run", "--user", "--collect", f"--unit={UNIT}",
         f"--description=Jarvis voice window",
         "--", launcher_path(), "window"],
        capture_output=True, text=True)
    if result.returncode != 0:
        return (result.stderr or result.stdout).strip()[:200]
    return "window opened"


def close_window() -> None:
    subprocess.run(["systemctl", "--user", "stop", f"{UNIT}.service"],
                   capture_output=True)


# --- the window itself ------------------------------------------------------

def run_window(config: Config) -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk

    # The Wayland app id, used by the compositor and by focus_window above.
    GLib.set_prgname(PROGRAM)

    class JarvisWindow(Gtk.Window):
        def __init__(self):
            super().__init__(title="Jarvis")
            self.config = config
            self.status = "idle"
            self.set_default_size(430, 250)

            header = Gtk.HeaderBar()
            self.dot = Gtk.Label(label="●")
            title = Gtk.Label(label="Jarvis")
            title.set_markup("<b>Jarvis</b>")
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.append(self.dot)
            box.append(title)
            header.set_title_widget(box)
            end = Gtk.Button(label="End session")
            end.connect("clicked", lambda *_: self._control("stop"))
            header.pack_end(end)
            self.set_titlebar(header)

            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
            for edge in ("top", "bottom", "start", "end"):
                getattr(body, f"set_margin_{edge}")(22)

            self.status_label = Gtk.Label(label="Idle", xalign=0)
            self.status_label.set_markup("<span size='xx-large'>Idle</span>")
            body.append(self.status_label)

            self.detail_label = Gtk.Label(label=STATUS_HINT["idle"], xalign=0)
            self.detail_label.set_wrap(True)
            body.append(self.detail_label)

            levels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            self.you = self._meter(levels, "you")
            self.her = self._meter(levels, "her")
            body.append(levels)

            self.primary = Gtk.Button(label="Start listening")
            self.primary.connect("clicked", lambda *_: self._control("toggle"))
            body.append(self.primary)

            hint = Gtk.Label(label="Pause keeps the session · closing ends it",
                             xalign=0)
            hint.add_css_class("dim-label")
            body.append(hint)

            self.set_child(body)
            self.connect("close-request", self._on_close)
            GLib.timeout_add(TICK_MS, self._tick)

        def _meter(self, parent, name: str) -> Gtk.ProgressBar:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            label = Gtk.Label(label=name, width_chars=3, xalign=0)
            label.add_css_class("dim-label")
            bar = Gtk.ProgressBar(hexpand=True)
            row.append(label)
            row.append(bar)
            parent.append(row)
            return bar

        def _control(self, command: str) -> None:
            action = resolve_toggle() if command == "toggle" else command
            self.detail_label.set_text(describe(control(self.config, action)))
            self._tick()

        def _on_close(self, *_args) -> bool:
            # Closing the window ends the session: a paid session with no face on
            # screen is the silent cost this is supposed to avoid.
            control(self.config, "stop")
            return False

        def _tick(self) -> bool:
            status, text, updated = read_status()
            self.status = status
            stale = updated > 0 and (time.time() - updated) > 900
            shown = "idle" if stale else status
            label = STATUS_TEXT.get(shown, shown.title())
            self.status_label.set_markup(
                f"<span size='xx-large' foreground='{STATUS_COLOR.get(shown, '#7a7a7a')}'>"
                f"{label}</span>")
            if text:
                self.detail_label.set_text(text)
            elif not self.detail_label.get_text():
                self.detail_label.set_text(STATUS_HINT.get(shown, ""))
            elif text == "" and shown in STATUS_HINT:
                self.detail_label.set_text(STATUS_HINT[shown])
            self.primary.set_label({"listening": "Pause", "thinking": "Pause",
                                    "paused": "Resume"}.get(shown, "Start listening"))
            you, her = read_levels()
            self.you.set_fraction(min(1.0, you))
            self.her.set_fraction(min(1.0, her))
            return True

    win = JarvisWindow()
    win.present()
    loop = GLib.MainLoop()
    win.connect("destroy", lambda *_: loop.quit())
    loop.run()
    return 0


# --- entry point ------------------------------------------------------------

ACTIONS = ("open", "window", "toggle", "start", "pause", "resume", "stop", "quit")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    action = argv[0] if argv and not argv[0].startswith("-") else "open"
    if action not in ACTIONS:
        print(f"jarvis-voice-app: unknown action {action!r}; one of {', '.join(ACTIONS)}",
              file=sys.stderr)
        return 2
    config = load()
    if action == "window":
        return run_window(config)
    if action == "quit":
        control(config, "stop")
        close_window()
        return 0
    if action in ("open",):
        print(open_window())
        return 0
    # toggle/start/pause/resume/stop: act on the session, then make sure the
    # window is there to show it.
    if action == "toggle":
        action = resolve_toggle()
    if action in ("toggle", "start") and not daemon_running():
        if not ensure_daemon(config):
            print("jarvis-voice-app: the voice daemon is not running", file=sys.stderr)
            return 1
    print(describe(control(config, action)))
    open_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
