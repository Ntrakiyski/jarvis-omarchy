#!/usr/bin/env bash
# jarvis-voice installer. Safe to re-run; every step is idempotent.
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local/share/jarvis-voice}"
BINDIR="${BINDIR:-$HOME/.local/bin}"
PLUGINDIR="$HOME/.config/omarchy/plugins"
CONFIGDIR="$HOME/.config/jarvis-voice"
UNITDIR="$HOME/.config/systemd/user"
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SOURCE/share/install-paths.sh"
validate_install_prefix "$PREFIX" "$SOURCE"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
step() { printf '\033[1;34m::\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
ask()  { read -rp "   $1 [y/N] " reply; [[ "$reply" =~ ^[Yy] ]]; }

bold "jarvis-voice installer"
echo "OpenAI Live or Realtime voice control for Omarchy."
echo

# --- sanity ----------------------------------------------------------------
if ! command -v hyprctl >/dev/null; then
  warn "hyprctl not found — this add-on drives Hyprland and needs it."
  exit 1
fi
if ! command -v omarchy >/dev/null; then
  warn "the omarchy CLI was not found. Things will mostly work, but the"
  warn "assistant loses half of what it can do."
fi

# --- files -----------------------------------------------------------------
step "installing to $PREFIX"
mkdir -p "$PREFIX" "$BINDIR" "$CONFIGDIR"
rm -rf "$PREFIX/src" "$PREFIX/bin" "$PREFIX/share" "$PREFIX/omarchy"
cp -r "$SOURCE/src" "$SOURCE/bin" "$SOURCE/share" "$SOURCE/omarchy" "$PREFIX/"
touch "$PREFIX/.jarvis-voice-install"
chmod +x "$PREFIX/bin/jarvis-voice"
chmod +x "$PREFIX/bin/jarvis-vision"
ln -sf "$PREFIX/bin/jarvis-voice" "$BINDIR/jarvis-voice"
ln -sf "$PREFIX/bin/jarvis-vision" "$BINDIR/jarvis-vision"
mkdir -p "$HOME/.local/share/applications"
cp "$SOURCE/share/jarvis-vision.desktop" "$HOME/.local/share/applications/"
echo "   jarvis-voice -> $BINDIR/jarvis-voice"

if [[ ! -f "$CONFIGDIR/config.toml" ]]; then
  cp "$SOURCE/share/config.example.toml" "$CONFIGDIR/config.toml"
  echo "   wrote $CONFIGDIR/config.toml"
else
  echo "   kept your existing $CONFIGDIR/config.toml"
fi

# Empty env file, mode 600. Never copy a key out of the current shell.
ENVFILE="$CONFIGDIR/env"
if [[ ! -f "$ENVFILE" ]]; then
  umask 077
  cat > "$ENVFILE" <<'EOF'
# Keys for the systemd user service and for `jarvis-voice` run from a
# terminal. chmod 600. A key exported in your shell does not reach systemd.
# OPENAI_API_KEY=sk-...
EOF
  chmod 600 "$ENVFILE"
  echo "   wrote $ENVFILE (mode 600) — put OPENAI_API_KEY here"
else
  chmod 600 "$ENVFILE" 2>/dev/null || true
  echo "   kept your existing $ENVFILE"
fi

case ":$PATH:" in
  *":$BINDIR:"*) ;;
  *) warn "$BINDIR is not on your PATH — add it, or the keybindings will not work." ;;
esac

# --- python environment ----------------------------------------------------
# The launcher prefers a private environment beside the install root, so the
# daemon never depends on whichever python3 is first on PATH: a systemd user
# service and an interactive shell resolve PATH differently, and a mise/uv
# python bump would otherwise break voice silently. No pacman, no sudo.
echo
step "python environment"
if [[ ! -x "$PREFIX/.venv/bin/python" ]]; then
  python3 -m venv "$PREFIX/.venv" || warn "could not create $PREFIX/.venv"
fi
if [[ -x "$PREFIX/.venv/bin/python" ]]; then
  if "$PREFIX/.venv/bin/python" -c "import websockets" 2>/dev/null; then
    echo "   websockets already present in $PREFIX/.venv"
  else
    "$PREFIX/.venv/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
    if "$PREFIX/.venv/bin/python" -m pip install --quiet 'websockets>=14,<17'; then
      echo "   installed websockets into $PREFIX/.venv"
    else
      warn "could not install websockets — the daemon cannot connect without it"
    fi
  fi
else
  warn "no private environment; the daemon will use whatever python3 PATH finds"
fi

if grep -q "^OPENAI_API_KEY=.\+" "$ENVFILE" 2>/dev/null || [[ -n "${OPENAI_API_KEY:-}" ]]; then
  echo "   OPENAI_API_KEY is set"
else
  warn "OPENAI_API_KEY is not set. Put it in $ENVFILE as"
  warn "OPENAI_API_KEY=sk-... — a key exported in your shell does not reach"
  warn "the systemd user service."
fi
warn "while listening is on, room audio streams continuously to OpenAI."
warn "Toggling off stops the recorder, so nothing is captured while muted."

# --- desktop integration ---------------------------------------------------
if ! command -v ffmpeg >/dev/null || ! command -v ffplay >/dev/null; then
  warn "OMA Vision needs FFmpeg (ffmpeg and ffplay); install it to enable camera preview."
fi
echo
step "desktop integration"
if [[ -d "$HOME/.config/omarchy" ]] && ask "install the bar widget plugin?"; then
  mkdir -p "$PLUGINDIR"
  cp -r "$SOURCE/plugin/voice.indicator" "$PLUGINDIR/"
  echo "   installed to $PLUGINDIR"
  if command -v omarchy >/dev/null && omarchy bar put voice.indicator --section right >/dev/null 2>&1; then
    echo "   placed on the bar, right section"
  else
    warn "could not place it automatically. Add it with:"
    echo "     omarchy bar put voice.indicator --section right"
  fi
fi

# The `omarchy voice ...` routes. Optional and off by default: they need a
# directory that `omarchy` itself scans, which is the one holding the omarchy
# binary — /usr/bin, and therefore root. Without this you still have the
# `jarvis-voice` command; you just do not get the omarchy-native spelling.
OMARCHY_BIN=$(dirname "$(command -v omarchy 2>/dev/null || echo /usr/bin/omarchy)")
if [[ -d $OMARCHY_BIN ]] && ask "also install the 'omarchy voice ...' commands into $OMARCHY_BIN (needs sudo)?"; then
  if sudo install -m 755 "$SOURCE"/omarchy/bin/jarvis-voice* "$OMARCHY_BIN/"; then
    echo "   installed. Try: omarchy voice doctor"
  else
    warn "could not install them; 'jarvis-voice' still works on its own."
  fi
fi

if ask "install the systemd user service (starts with your session)?"; then
  mkdir -p "$UNITDIR"
  cp "$SOURCE/share/jarvis-voice.service" "$UNITDIR/"
  systemctl --user daemon-reload
  systemctl --user enable jarvis-voice.service
  echo "   enabled. Start it now with: systemctl --user start jarvis-voice"
fi

# --- keybindings -----------------------------------------------------------
echo
step "keybindings"
BINDINGS="$HOME/.config/hypr/bindings.lua"
if [[ ! -f "$BINDINGS" ]]; then
  warn "$BINDINGS does not exist. Add this by hand:"
  sed 's/^/     /' "$SOURCE/share/bindings.lua.snippet"
elif grep -q 'jarvis-voice' "$BINDINGS"; then
  echo "   already bound in $BINDINGS"
elif ask "bind SUPER + SHIFT + V in $BINDINGS?"; then
  cp "$BINDINGS" "$BINDINGS.bak-voice"
  cat >> "$BINDINGS" <<'LUA'

-- jarvis-voice ------------------------------------------------------------
-- Avoids SUPER + V (Universal paste) and SUPER + CTRL + V (clipboard manager).
-- Listening is off until this key turns it on, and off again when it does.
if o.cmd_present("jarvis-voice") then
  o.bind("SUPER + SHIFT + V", "Toggle voice control", "jarvis-voice listen toggle")
end
LUA
  echo "   appended, backup at $BINDINGS.bak-voice"
  if hyprctl reload >/dev/null 2>&1; then
    echo "   reloaded — SUPER + SHIFT + V is live"
  else
    warn "could not reload Hyprland; the binding applies on next reload"
  fi
else
  echo "   skipped. The snippet is at $SOURCE/share/bindings.lua.snippet"
fi

echo
bold "next"
echo "   edit $ENVFILE                put OPENAI_API_KEY=sk-... in it"
echo "   jarvis-voice doctor              check every moving part"
echo "   jarvis-voice --dry-run say \"...\"  try a command without a microphone"
echo "   systemctl --user start jarvis-voice"
