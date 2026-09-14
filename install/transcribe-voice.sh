#!/bin/bash
# transcribe-voice.sh <audiofile> — расшифровка голосового в контейнере Компаньона (14.09.2026).
# Groq whisper-large-v3 с автоопределением языка и вторым проходом на узбекском —
# та же схема, что у старшей на Маке и у директоров. Ключ — GROQ_API_KEY из env контейнера.
# Никогда не печатает ключ. Пусто → "[empty]" (приёмник покажет «расшифровка пустая»).
set -euo pipefail
[ -n "${1:-}" ] || { echo "usage: transcribe-voice.sh <audiofile>" >&2; exit 1; }
KEY="${GROQ_API_KEY:-}"
[ -n "$KEY" ] || { echo "[нет ключа Groq в env]" >&2; exit 1; }
API="https://api.groq.com/openai/v1/audio/transcriptions"
SRC="$1"
case "$SRC" in
  *.oga) TMP="$(mktemp -t voiceXXXX).ogg"; cp "$SRC" "$TMP"; trap 'rm -f "$TMP"' EXIT; SRC="$TMP" ;;
esac
ask() {
  if [ -n "${2:-}" ]; then
    curl -s --max-time 90 -X POST "$API" -H "Authorization: Bearer $KEY" -F "file=@$1" -F "model=whisper-large-v3" -F "language=$2" -F "response_format=verbose_json"
  else
    curl -s --max-time 90 -X POST "$API" -H "Authorization: Bearer $KEY" -F "file=@$1" -F "model=whisper-large-v3" -F "response_format=verbose_json"
  fi
}
pick() { python3 -c '
import sys, json
try: d = json.load(sys.stdin)
except Exception: print("\t"); sys.exit()
print((d.get("language") or "") + "\t" + (d.get("text") or "").strip())'; }
OUT=$(ask "$SRC" "" | pick)
LANG="${OUT%%$'\t'*}"; TEXT="${OUT#*$'\t'}"
case "$LANG" in
  uzbek|uz|azerbaijani|az|kazakh|kk|kyrgyz|ky|turkmen|tk|tatar|tt|turkish|tr|bashkir|ba|tajik|tg|uighur|ug|chuvash|cv|"")
    OUT2=$(ask "$SRC" "uz" | pick); TEXT2="${OUT2#*$'\t'}"; [ -n "$TEXT2" ] && TEXT="$TEXT2" ;;
esac
[ -n "$TEXT" ] && printf '%s\n' "$TEXT" || echo "[empty]"
