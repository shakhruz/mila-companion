#!/usr/bin/env bash
# Mila Companion — installs the assistant kit into an existing Claude Code setup.
#
# What it does, in order, and nothing else:
#   1. copies the skills into ~/.claude/skills/
#   2. installs the `mila` launcher into ~/.local/bin/
#   3. installs the inbox hook and registers it in ~/.claude/settings.json
#
# It does NOT install the Telegram plugin — that is a separate step you run
# inside Claude Code (see README). It does not touch your bot token, your
# access list, or anything under ~/.claude/channels/.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
STATE_DIR="${TELEGRAM_STATE_DIR:-$CLAUDE_DIR/channels/telegram}"
BIN_DIR="$HOME/.local/bin"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

# Every backup this run actually made (or, in --dry-run, would make), for the
# summary printed at the end — the point of a backup nobody can find is the
# same as having none.
declare -a BACKUPS=()

say() { printf '  %s\n' "$*"; }
run() { if [[ $DRY -eq 1 ]]; then say "would: $*"; else "$@"; fi; }

# Copies $1 (source) over $2 (destination), keeping a timestamped backup of
# whatever was already at the destination — unless it is byte-identical to
# what's about to replace it, in which case there is nothing worth keeping
# and nothing worth copying. Honours --dry-run: announces, writes nothing.
install_file() {
  local src="$1" dst="$2" label="${3:-$(basename "$2")}"
  if [[ -e "$dst" ]]; then
    if cmp -s "$src" "$dst" 2>/dev/null; then
      say "$label — unchanged, no copy needed"
      return
    fi
    local backup="$dst.bak-$(date +%Y%m%d-%H%M%S)"
    if [[ $DRY -eq 1 ]]; then
      say "would back up existing $label to $(basename "$backup")"
      BACKUPS+=("$backup")
    else
      cp -p "$dst" "$backup"
      BACKUPS+=("$backup")
      say "$label — exists, keeping a copy at $(basename "$backup")"
    fi
  fi
  run cp "$src" "$dst"
}

echo "Mila Companion installer"
echo "  target: $CLAUDE_DIR"
[[ $DRY -eq 1 ]] && echo "  DRY RUN — nothing will be written"
echo

# ── skills ────────────────────────────────────────────────────────────────
echo "Skills"
run mkdir -p "$CLAUDE_DIR/skills"
for d in "$ROOT"/skills/*/; do
  name="$(basename "$d")"
  target="$CLAUDE_DIR/skills/$name"
  if [[ -e "$target" ]]; then
    if diff -rq "$d" "$target" >/dev/null 2>&1; then
      say "$name — unchanged, no copy needed"
      continue
    fi
    # Never overwrite silently: a customised skill is someone's work.
    backup="$target.bak-$(date +%Y%m%d-%H%M%S)"
    if [[ $DRY -eq 1 ]]; then
      say "would back up existing $name to $(basename "$backup")"
      BACKUPS+=("$backup")
    else
      mv "$target" "$backup"
      BACKUPS+=("$backup")
      say "$name — exists, keeping a copy at $(basename "$backup")"
    fi
  fi
  run cp -R "$d" "$target"
  say "$name installed"
done
echo

# ── launcher ──────────────────────────────────────────────────────────────
echo "Launcher"
run mkdir -p "$BIN_DIR"
install_file "$HERE/mila" "$BIN_DIR/mila" "mila"
run chmod 755 "$BIN_DIR/mila"
say "mila → $BIN_DIR/mila"
case ":$PATH:" in
  *":$BIN_DIR:"*) say "$BIN_DIR is on PATH" ;;
  *) say "NOTE: $BIN_DIR is not on your PATH — add it to your shell profile:"
     say "      export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac
echo

# ── inbox hook ────────────────────────────────────────────────────────────
echo "Inbox hook"
HOOK_DIR="$CLAUDE_DIR/hooks"
run mkdir -p "$HOOK_DIR"
install_file "$HERE/telegram-inbox-feed.py" "$HOOK_DIR/telegram-inbox-feed.py" "telegram-inbox-feed.py"
run chmod 755 "$HOOK_DIR/telegram-inbox-feed.py"
say "hook → $HOOK_DIR/telegram-inbox-feed.py"
echo

# ── tools the launcher calls ──────────────────────────────────────────────
# The launcher looks for every one of these in $HOOK_DIR. Installing only the
# hook left six of the eight `mila` commands answering "reinstall the kit", and
# the promise watchdog silently returning an empty list — which reads exactly
# like "nothing is due".
echo "Tools"
for f in usage_collect.py turns_collect.py records.py chats_index.py \
         chat_note.py chat_locale.py doctor.py backup.py design_check.py; do
  if [[ -f "$HERE/$f" ]]; then
    install_file "$HERE/$f" "$HOOK_DIR/$f" "$f"
    run chmod 755 "$HOOK_DIR/$f"
    say "$f"
  else
    say "🔴 missing from the kit: $f"
  fi
done

# ── hourly turn collection ────────────────────────────────────────────────
# The books are only worth keeping if they are kept as the day happens. Collected
# once a night, a turn has lost the conversation that produced it — and the point
# of the table is to be able to ask, by the evening, which question cost what.
#
# Not on the hour. Every other timer on these machines fires at :00, and a
# collector that runs in the same second as a cron job records a turn that is
# still in flight as a failure. The minute is derived from the hostname, so the
# fleet spreads itself across the hour instead of stampeding — override with
# MILA_TURNS_MINUTE if you need a specific one.
echo "Hourly turn collection"
TURNS_MIN="${MILA_TURNS_MINUTE:-}"
if [[ -z "$TURNS_MIN" ]]; then
  # 10..49: the top and the bottom of the hour is where everyone else's crons
  # already sit, and :00 is where the daily briefs fire.
  TURNS_MIN=$(python3 -c 'import hashlib,socket;print(10+int(hashlib.sha1(socket.gethostname().encode()).hexdigest(),16)%40)')
fi
PY_BIN="$(command -v python3 || echo /usr/bin/python3)"
COLLECT="$HOOK_DIR/turns_collect.py"
LOG_FILE="$CLAUDE_DIR/turns-collect.log"

if [[ "$(uname -s)" == "Darwin" ]]; then
  LABEL="com.milagpt.turns-collect"
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  if [[ $DRY -eq 1 ]]; then
    say "would: write $PLIST (every hour at :$(printf '%02d' "$TURNS_MIN"))"
  else
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY_BIN</string>
    <string>$COLLECT</string>
    <string>--days</string><string>1</string>
    <string>--quiet</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Minute</key><integer>$TURNS_MIN</integer></dict>
  <key>EnvironmentVariables</key>
  <dict><key>MILA_AGENT</key><string>${MILA_AGENT:-companion}</string></dict>
  <key>StandardOutPath</key><string>$LOG_FILE</string>
  <key>StandardErrorPath</key><string>$LOG_FILE</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
PLISTEOF
    chmod 644 "$PLIST"
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null \
      || launchctl load -w "$PLIST" 2>/dev/null || true
    say "$LABEL — every hour at :$(printf '%02d' "$TURNS_MIN")"
  fi
elif command -v systemctl >/dev/null 2>&1; then
  UNITS="$HOME/.config/systemd/user"
  if [[ $DRY -eq 1 ]]; then
    say "would: write $UNITS/mila-turns-collect.{service,timer} (:$(printf '%02d' "$TURNS_MIN"))"
  else
    mkdir -p "$UNITS"
    cat > "$UNITS/mila-turns-collect.service" <<UNITEOF
[Unit]
Description=Mila Companion — collect turns into conversations.db

[Service]
Type=oneshot
# Имя агента должно совпадать с тем, под которым ходы пишутся руками, иначе
# один и тот же Компаньон разъезжается в отчёте на две строки.
Environment=MILA_AGENT=${MILA_AGENT:-companion}
ExecStart=$PY_BIN $COLLECT --days 1 --quiet
UNITEOF
    cat > "$UNITS/mila-turns-collect.timer" <<UNITEOF
[Unit]
Description=Mila Companion — hourly turn collection

[Timer]
OnCalendar=*:$(printf '%02d' "$TURNS_MIN")
# Persistent catches up after the machine was asleep: a missed hour is a hole
# in the books, and holes are noticed only when someone asks about that day.
Persistent=true

[Install]
WantedBy=timers.target
UNITEOF
    chmod 644 "$UNITS"/mila-turns-collect.*
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable --now mila-turns-collect.timer 2>/dev/null \
      && say "mila-turns-collect.timer — every hour at :$(printf '%02d' "$TURNS_MIN")" \
      || say "NOTE: could not enable the timer — run: systemctl --user enable --now mila-turns-collect.timer"
  fi
else
  say "NOTE: neither launchd nor systemd found — run \`mila turns\` from your own scheduler"
fi
echo

# The permission policy decides what runs without waking anyone. With no file
# at all the code falls back to STRICT — every single tool call becomes a card
# in Telegram, and past twelve a minute they are auto-denied. A first evening
# like that reads as "the assistant is broken".
POLICY="$STATE_DIR/permissions.json"
if [[ -f "$POLICY" ]]; then
  say "permissions.json — exists, left alone"
elif [[ -f "$HERE/permissions.example.json" ]]; then
  run mkdir -p "$STATE_DIR"
  run cp "$HERE/permissions.example.json" "$POLICY"
  run chmod 600 "$POLICY"
  say "permissions.json installed from the example — READ IT before trusting it"
  say "  it decides what runs without asking you: $POLICY"
fi

if [[ $DRY -eq 1 ]]; then
  say "would check $CLAUDE_DIR/settings.json — register the hook, backing up first if it changes"
else
  SETTINGS_OUT="$(python3 - "$CLAUDE_DIR" << 'PY'
import json, os, sys, datetime
cfg_dir = sys.argv[1]
p = os.path.join(cfg_dir, 'settings.json')
hook_cmd = os.path.join(cfg_dir, 'hooks', 'telegram-inbox-feed.py')
try:
    with open(p, encoding='utf-8') as f:
        raw = f.read()
    cfg = json.loads(raw)
except FileNotFoundError:
    raw = None
    cfg = {}
except json.JSONDecodeError:
    print('  settings.json is not valid JSON — hook NOT registered, add it by hand')
    raise SystemExit(0)

hooks = cfg.setdefault('hooks', {})
entries = hooks.setdefault('UserPromptSubmit', [])
already = any(hook_cmd in json.dumps(e) for e in entries)
if already:
    print('  already registered in settings.json')
else:
    entries.append({'hooks': [{'type': 'command', 'command': hook_cmd}]})
    new_raw = json.dumps(cfg, ensure_ascii=False, indent=2)
    if raw is not None and raw != new_raw:
        ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        backup = p + f'.bak-{ts}'
        with open(backup, 'w', encoding='utf-8') as f:
            f.write(raw)
        print(f'BACKUP:{backup}')
        print(f'  registered in settings.json (previous version kept as {os.path.basename(backup)})')
    else:
        print('  registered in settings.json')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(new_raw)
PY
)"
  while IFS= read -r line; do
    if [[ "$line" == BACKUP:* ]]; then
      BACKUPS+=("${line#BACKUP:}")
    else
      printf '%s\n' "$line"
    fi
  done <<< "$SETTINGS_OUT"
fi
echo
if [[ ${#BACKUPS[@]} -gt 0 ]]; then
  if [[ $DRY -eq 1 ]]; then
    echo "Would back up (nothing written — dry run):"
  else
    echo "Existing files kept as backups:"
  fi
  for b in "${BACKUPS[@]}"; do
    say "$b"
  done
  echo
fi
echo "Done. Next, inside Claude Code:"
echo "  /plugin marketplace add shakhruz/mila-telegram"
echo "  /plugin install mila-telegram@mila"
echo "  /telegram:configure <your bot token>"
echo
echo "Then start a session with:  mila"
