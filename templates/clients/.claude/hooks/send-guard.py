#!/usr/bin/env python3
"""send-guard.py — PreToolUse-хук Компаньона на reply/edit_message (SENDGUARD-0509).
Стоит на пути отправки, потому что правилом текст не лечится (04.08, 25.08, 04.09).
Блокирует: адресат не хозяин · ключи/токены · id чужих чатов · кухня (пути, podman, сырые ошибки провайдера)
· markdown без format=markdownv2. Непонятный вход — не мешаем (exit 0). Секретов не печатает."""
import json, os, re, sys

raw = sys.stdin.read()
try:
    p = json.loads(raw)
except Exception:
    sys.exit(0)
tool = p.get("tool_name") or ""
if not (tool.endswith("__reply") or tool.endswith("__edit_message")):
    sys.exit(0)
args = p.get("tool_input") or {}
text = str(args.get("text") or "")
chat_id = str(args.get("chat_id") or "").strip()
owner = (os.environ.get("OWNER_ID") or "").strip()
fmt = (args.get("format") or "text").lower()
why = []

# 06.09.2026 (Мила Клиенты): кроме хозяина разрешены группы из access.json —
# туда её добавляет человек, и только там она вправе говорить. Прочее режется.
_allowed = set()
try:
    _acc = json.load(open(os.path.expanduser("~/.claude/channels/telegram/access.json"), encoding="utf-8"))
    _allowed = {str(k) for k in (_acc.get("groups") or {}).keys()}
except Exception:
    pass
if owner and chat_id and chat_id != owner and chat_id not in _allowed:
    why.append("адресат %s — не хозяин и не утверждённый чат: говорю только там, куда меня добавили" % chat_id)

SECRETS = [
    (r"\b(?:sk|pk)[-_][A-Za-z0-9\-_]{16,}", "ключ провайдера (sk-/sk_/pk_)"),
    (r"\b\d{6,12}:[A-Za-z0-9_-]{30,50}\b", "токен Telegram-бота"),
    (r"\bAKIA[0-9A-Z]{16}\b", "ключ AWS"),
    (r"\bgh[pous]_[A-Za-z0-9]{20,}\b", "токен GitHub"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}", "токен Slack"),
    (r"\bcmp_[A-Za-z0-9]{16,}\b", "токен companion-api"),
]
for rx, name in SECRETS:
    if re.search(rx, text):
        why.append("в тексте %s — секреты в чат не пишем, хозяину: «перевыпустить»" % name)
if re.search(r"(?<!\d)-100\d{10}(?!\d)", text):
    why.append("в тексте id чата (-100…) — внутренние номера наружу не показываем, называй чат по имени")

KITCHEN = [
    (r"/srv/[a-z]+|/home/companion|/opt/[a-z]+", "серверный путь"),
    (r"\bpodman\b|\bsystemctl\b|api\.sock|stream-json|\.credentials\.json", "устройство контейнера"),
    (r"Traceback \(most recent|Error calling LLM|rate_limit_error|overloaded_error|authentication_error|HTTP/?\s?\d{3}\b.*error", "сырая ошибка провайдера"),
    (r"hookSpecificOutput|tool_use|PreToolUse|PostToolUse", "внутренности хуков"),
]
for rx, name in KITCHEN:
    if re.search(rx, text, re.I):
        why.append("кухня наружу (%s) — скажи результат словами человека" % name)

if fmt != "markdownv2":
    marks = []
    if re.search(r"\*\*[^*\n]+\*\*", text): marks.append("**жирный**")
    if re.search(r"(?m)^\s*[-*] ", text): marks.append("списки через - или *")
    if re.search(r"`[^`\n]+`", text): marks.append("`код`")
    if re.search(r"\[[^\]\n]+\]\([^)\n]+\)", text): marks.append("[ссылки](адрес)")
    if marks:
        why.append("разметка (%s) без format=markdownv2 — получатель увидит сырые звёздочки; "
                   "собери через tg.py умения milagpt-chat или убери разметку" % ", ".join(marks))

if not why:
    sys.exit(0)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                         "permissionDecisionReason": "Не отправляю: " + "; ".join(why)}},
                 ensure_ascii=False))
