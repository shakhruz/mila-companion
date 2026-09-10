#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""subscription_watch — часовой сторож подписок Claude (mila-companion).

Берёт все подписки из accounts.json через subscription.py --json, пишет историю (снимок в час),
считает темп по истории, предупреждает ОДИН раз на повод (повтор не чаще раза в 3 ч):
  · неделя / сильная модель: осталось ≤ 20 % или при текущем темпе кончится раньше сброса;
  · 5-часовой бак: осталось ≤ 30 % (сигнал заранее, а не в ноль).
Доставка: --outbox DIR --chat ID (Мила Админ, через sender-демон плагина) или
--tg-token-env VAR --chat ID (Компаньон, прямой Bot API; картинка приложится, если есть).
Состояние: $SUBSCRIPTION_STATE (по умолчанию ~/.claude/state): watch.json, history.jsonl, watch.off.
Запуск: subscription_watch.py [--dry] [--report] [--on|--off]  (launchd/cron раз в час)
"""
import json, os, sys, time, subprocess, urllib.request
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.expanduser(os.environ.get("SUBSCRIPTION_STATE", "~/.claude/state"))
STATE = os.path.join(STATE_DIR, "subscription-watch.json"); HIST = os.path.join(STATE_DIR, "subscription-history.jsonl")
OFF = os.path.join(STATE_DIR, "subscription-watch.off"); LOG = os.path.join(STATE_DIR, "subscription-watch.log")
REPEAT = 3 * 3600
TZ = datetime.now().astimezone().tzinfo


def log(m):
    os.makedirs(STATE_DIR, exist_ok=True)
    open(LOG, "a", encoding="utf-8").write(time.strftime("%Y-%m-%d %H:%M:%S ") + m + "\n")


def parse(ts):
    try: return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception: return None


def fmt(dt):
    return dt.astimezone(TZ).strftime("%d.%m %H:%M")


def collect():
    out = subprocess.run([sys.executable, os.path.join(HERE, "subscription.py"), "--json"], capture_output=True, text=True, timeout=120).stdout
    return json.loads(out)


def rate(name, label, now):
    pts = []
    try:
        for line in open(HIST, encoding="utf-8"):
            e = json.loads(line)
            if e["name"] != name or now - e["ts"] > 6 * 3600: continue
            for w in e["windows"]:
                if w["label"] == label: pts.append((e["ts"], w["percent"], w["resets_at"]))
    except FileNotFoundError:
        return None
    if len(pts) < 2: return None
    pts = [p for p in pts if p[2] == pts[-1][2]]
    if len(pts) < 2 or pts[-1][0] - pts[0][0] < 2 * 3600: return None
    return (pts[-1][1] - pts[0][1]) / ((pts[-1][0] - pts[0][0]) / 3600.0)


def notify(text, png, args):
    if args.outbox:
        os.makedirs(args.outbox, exist_ok=True)
        job = {"chat_id": int(args.chat), "text": text[:3900]}
        if png: job["files"] = [png]
        json.dump(job, open(os.path.join(args.outbox, "subscription-watch-%d.json" % int(time.time())), "w", encoding="utf-8"), ensure_ascii=False)
        return
    tok = os.environ.get(args.tg_token_env or "TELEGRAM_BOT_TOKEN", "")
    if not tok: log("no token"); return
    if png:
        import mimetypes, uuid
        b = uuid.uuid4().hex; data = b""
        for k, v in (("chat_id", str(args.chat)), ("caption", text[:1000])):
            data += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, k, v)).encode()
        data += ("--%s\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"card.png\"\r\nContent-Type: image/png\r\n\r\n" % b).encode() + open(png, "rb").read() + ("\r\n--%s--\r\n" % b).encode()
        req = urllib.request.Request("https://api.telegram.org/bot%s/sendPhoto" % tok, data=data, headers={"Content-Type": "multipart/form-data; boundary=" + b})
    else:
        req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % tok, data=json.dumps({"chat_id": args.chat, "text": text[:3900]}).encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true"); ap.add_argument("--report", action="store_true")
    ap.add_argument("--on", action="store_true"); ap.add_argument("--off", action="store_true")
    ap.add_argument("--outbox"); ap.add_argument("--tg-token-env"); ap.add_argument("--chat")
    args = ap.parse_args()
    os.makedirs(STATE_DIR, exist_ok=True)
    if args.off: open(OFF, "w").write(time.strftime("%F %T")); print("сторож выключен"); return
    if args.on:
        if os.path.exists(OFF): os.remove(OFF)
        print("сторож включён"); return
    if os.path.exists(OFF) and not (args.dry or args.report): log("off"); return
    now = time.time(); state = collect(); accts = [a for a in state.get("accounts", []) if a.get("windows")]
    with open(HIST, "a", encoding="utf-8") as f:
        for a in accts:
            f.write(json.dumps({"ts": int(now), "name": a["name"], "windows": [{"label": w["label"], "percent": w["percent"], "resets_at": w.get("resets_at")} for w in a["windows"]]}, ensure_ascii=False) + "\n")
    try: st = json.load(open(STATE))
    except Exception: st = {}
    told = st.get("told", {}); alerts = []; lines = []
    for a in accts:
        lines.append("%s%s" % (a["name"], (" · данным %.0f ч" % (a["age_seconds"] / 3600)) if a.get("age_seconds") and a["age_seconds"] > 5400 else ""))
        for w in a["windows"]:
            left = 100 - float(w["percent"]); reset = parse(w.get("resets_at")); r = rate(a["name"], w["label"], now)
            exh = parse(w.get("exhausts_at"))
            if r is not None: exh = (datetime.now(timezone.utc) + timedelta(hours=left / r)) if r > 0 else None
            before = bool(exh and reset and exh < reset)
            key = "%s|%s" % (a["name"], w["label"]); reason = None
            if w["label"] == "5 часов":
                if left <= 30: reason = "5-часовой бак на исходе (осталось %d %%), сброс %s" % (left, fmt(reset) if reset else "?")
            elif left <= 20: reason = "осталось %d %% окна «%s», сброс %s" % (left, w["label"], fmt(reset) if reset else "?")
            elif before and left < 60: reason = "при текущем темпе «%s» кончится %s, сброс только %s" % (w["label"], fmt(exh), fmt(reset))
            lines.append("  %-11s осталось %3d %%%s" % (w["label"], left, ("  ⚠ кончится " + fmt(exh)) if before else ""))
            if reason and now - told.get(key, 0) > REPEAT: alerts.append("%s · %s" % (a["name"], reason)); told[key] = now
    st["told"] = told; json.dump(st, open(STATE, "w"), ensure_ascii=False)
    report = "\n".join(lines); log("ok accts=%d alerts=%d" % (len(accts), len(alerts)))
    if args.report or args.dry: print(report); print("ALERTS:", alerts)
    if alerts and not args.dry and args.chat:
        png = None
        try:
            import subscription_card; png = subscription_card.card_for(state)
        except Exception as exc: log("card: %s" % exc)
        notify("🔋 Подписки: " + "; ".join(alerts) + "\n\n" + report, png, args); log("ALERT " + " | ".join(alerts))


if __name__ == "__main__":
    main()
