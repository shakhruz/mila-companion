#!/usr/bin/env bash
# api.sh METHOD PATH [JSON] — вызов companion-api через unix-сокет (или TCP для стенда).
# Токен — только из env, в чат не печатать. Ответ — JSON.
set -u
M="${1:-GET}"; P="${2:-/directors}"; B="${3:-}"
TOK="${COMPANION_API_TOKEN:-}"
SOCK="${COMPANION_API_SOCK:-/run/companion/api.sock}"
BASE="${COMPANION_API_BASE:-http://companion}"
[ -z "$TOK" ] && { echo '{"error":"нет токена companion-api в окружении"}'; exit 2; }
if [ -S "$SOCK" ]; then
  CURL=(curl -sS -m 25 --unix-socket "$SOCK")
else
  BASE="${COMPANION_API_BASE:-http://127.0.0.1:8994}"
  CURL=(curl -sS -m 25)
fi
if [ "$M" = "GET" ]; then
  "${CURL[@]}" -H "Authorization: Bearer $TOK" "$BASE$P"
else
  "${CURL[@]}" -X "$M" -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
    --data "${B:-{\}}" "$BASE$P"
fi
echo
