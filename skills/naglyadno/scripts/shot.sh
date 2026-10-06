#!/bin/bash
# Скриншот HTML через headless Chrome (для приёмки глазами и PNG там, где есть Chrome): shot.sh in.html out.png [W] [H] [dark]
IN="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; OUT="$2"; W="${3:-1280}"; H="${4:-900}"
CH="${CHROME:-}"
for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" google-chrome chromium chromium-browser; do
  [ -n "$CH" ] && break; command -v "$c" >/dev/null 2>&1 && CH="$c"; [ -x "$c" ] && CH="$c"
done
[ -z "$CH" ] && { echo "Chrome не найден: задайте CHROME=/путь или используйте --queue"; exit 1; }
EXTRA=(); [ "$5" = dark ] && EXTRA=(--force-dark-mode --enable-features=WebContentsForceDark)
"$CH" --headless=new --disable-gpu --hide-scrollbars --window-size="$W,$H" --virtual-time-budget=15000 "${EXTRA[@]}" --screenshot="$OUT" "file://$IN" 2>/dev/null
ls -la "$OUT"
