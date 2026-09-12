#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reply-required.py — Stop-хук Компаньона (12.09.2026, дефект первого клиентского Компаньона).

Хозяин читает Telegram, а не терминал. Если последнее сообщение хозяина пришло
конвертом <channel …>, а с тех пор сессия ни разу не вызвала инструмент reply
плагина, ход завершать нельзя: текст без reply никуда не уходит. Хук отдаёт
decision=block с причиной — Claude продолжает ход и отправляет ответ.

Читает транскрипт по transcript_path из stdin (Claude Code даёт его хуку Stop).
Ограничитель: не блокирует второй раз подряд (stop_hook_active), чтобы не
зациклиться, если ответить действительно нечем.
"""
import json
import sys


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("stop_hook_active"):
        return 0
    path = data.get("transcript_path") or ""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except Exception:
        return 0
    last_channel_idx = -1
    last_reply_idx = -1
    chat_id = ""
    for i, ln in enumerate(lines):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        m = r.get("message") or {}
        c = m.get("content")
        if r.get("type") == "user" and m.get("role") == "user":
            s = c if isinstance(c, str) else " ".join(
                (x.get("text", "") if isinstance(x, dict) else str(x)) for x in (c or []))
            if "<channel" in s and "source=\"telegram\"" in s:
                last_channel_idx = i
                j = s.find("chat_id=\"")
                if j >= 0:
                    chat_id = s[j + 9:].split("\"", 1)[0]
        if r.get("type") == "assistant" and isinstance(c, list):
            for x in c:
                if isinstance(x, dict) and x.get("type") == "tool_use" and "telegram__reply" in str(x.get("name", "")):
                    last_reply_idx = i
    if last_channel_idx >= 0 and last_reply_idx < last_channel_idx:
        reason = ("Ответ хозяину НЕ отправлен: он читает Telegram, а не этот текст. Вызови инструмент "
                  "mcp__plugin_mila-telegram_telegram__reply с chat_id=\"%s\" и текстом ответа "
                  "(одно сообщение, до 1000 знаков). Если ответить нечем — reply с одной строкой, что делаешь."
                  % (chat_id or "<из тега channel>"))
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
