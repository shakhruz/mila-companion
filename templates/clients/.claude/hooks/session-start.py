#!/usr/bin/env python3
"""session-start.py — SessionStart-хук Компаньона (SESSIONSTART-0509): одна строка контекста —
очередь входящих (журнал receiver против курсора кормильца), возраст последнего входящего,
лимит подписки из limit.json (датчик mila-core limit_watch — здесь только читаем, не считаем),
расход за сегодня из state/usage-daily.json. Никогда не падает и не печатает секретов."""
import json, os, sys, time

H = os.path.expanduser("~")
TG = os.path.join(H, ".claude", "channels", "telegram")
ST = os.path.join(H, "state")
lines = []
try:
    ev = os.path.join(TG, "inbound", "events.jsonl")
    cur = 0
    try:
        cur = int(open(os.path.join(TG, "inbound", "feeder-cursor")).read().strip() or 0)
    except Exception:
        pass
    size = os.path.getsize(ev) if os.path.exists(ev) else 0
    pending = 0
    last_ts = 0
    if size:
        with open(ev, "rb") as f:
            f.seek(max(0, size - 200_000))
            tail = f.read().decode("utf-8", "replace")
        off = max(0, size - 200_000)
        for ln in tail.splitlines(True):
            try:
                e = json.loads(ln)
            except Exception:
                off += len(ln.encode("utf-8")); continue
            if e.get("method") == "notifications/claude/channel":
                last_ts = max(last_ts, int(e.get("ts") or 0))
                if off >= cur:
                    pending += 1
            off += len(ln.encode("utf-8"))
    if pending:
        lines.append("в очереди %d непрочитанных входящих — сначала они, по порядку" % pending)
    if last_ts:
        age_m = int((time.time() * 1000 - last_ts) / 60000)
        lines.append("последнее входящее хозяина %d мин назад" % age_m)
except Exception:
    pass
try:
    lim = json.load(open(os.path.join(TG, "limit.json")))
    if lim.get("limited") or (lim.get("current") or {}).get("limited"):
        cur_ = lim.get("current") or lim
        lines.append("лимит подписки хозяина: %s, сброс %s — на новые дела не берусь, хозяину уже сказано"
                     % (cur_.get("kind", "?"), cur_.get("resets_at_text") or cur_.get("resets_at") or "время неизвестно"))
except Exception:
    pass
try:
    u = json.load(open(os.path.join(ST, "usage-daily.json")))
    cost = u.get("total_cost_usd") or u.get("cost_usd")
    days = u.get("days") or []
    if days and isinstance(days[-1], dict):
        cost = days[-1].get("cost_usd", cost)
    if cost is not None:
        lines.append("расход подписки сегодня ≈ $%.2f по прайсу API (мера, не счёт)" % float(cost))
except Exception:
    pass
if lines:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": "Старт сессии Компаньона: " + " · ".join(lines)}},
                     ensure_ascii=False))
sys.exit(0)
