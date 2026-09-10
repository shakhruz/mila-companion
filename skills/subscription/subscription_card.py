#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""subscription_card — картинка-дэшборд подписок (rich media для Telegram), mila-companion.

Вход — state из subscription.py (--json): accounts[] с windows[] (percent = израсходовано,
resets_at, exhausts_at), plan, profile.email, age_seconds/stale, name. Рисует HTML в
фирменном стиле и печатает PNG через Chrome/Chromium. Chrome нет (контейнер) — берёт
свежий общий PNG, который кладёт старшая (поле "card" в accounts.json: путь и срок
свежести), иначе возвращает None — тогда агент шлёт текстовый блок --telegram.
Использование из кода: card_for(state, out_path=None) -> путь к PNG | None.
"""
import json, os, shutil, subprocess, sys, time
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome",
          "/usr/bin/chromium", "/usr/bin/chromium-browser", shutil.which("chromium") or "", shutil.which("google-chrome") or ""]
DAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
TZ = datetime.now().astimezone().tzinfo


def _p(ts):
    if not ts: return None
    try: return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception: return None


def fmt_dt(dt):
    dt = dt.astimezone(TZ); today = datetime.now(TZ).date()
    if dt.date() == today: return "сегодня %s" % dt.strftime("%H:%M")
    if dt.date() == today + timedelta(days=1): return "завтра %s" % dt.strftime("%H:%M")
    return "%s %s %s" % (DAYS[dt.weekday()], dt.strftime("%d.%m"), dt.strftime("%H:%M"))


def countdown(dt):
    s = int((dt - datetime.now(timezone.utc)).total_seconds())
    if s <= 0: return "уже прошёл, данные устарели"
    d, h, m = s // 86400, (s % 86400) // 3600, (s % 3600) // 60
    return ("%d дн %d ч" % (d, h)) if d else ("%d ч %02d мин" % (h, m))


def color(left): return "#2E9E6B" if left >= 60 else ("#E0A800" if left >= 30 else "#D9534F")


def word(left):
    return "с запасом" if left >= 60 else ("ровно" if left >= 30 else ("тает" if left >= 10 else ("на исходе" if left >= 5 else "пусто")))


def build_html(state):
    accts = state.get("accounts") or []
    cards, rows = [], []
    for a in accts:
        name = a.get("name") or "?"; em = (a.get("profile") or {}).get("email") or ""
        plan = a.get("plan") or "Max"; age = a.get("age_seconds"); agent = a.get("agent") or ""
        status = "🟡 данным %.0f ч" % (age / 3600) if age and age > 5400 else ("🔴 нет данных" if a.get("error") else "🟢 работает")
        bars, resets, warn = [], [], []
        left_by = {}
        for w in a.get("windows") or []:
            left = max(0, min(100, int(round(100 - float(w.get("percent") or 0))))); left_by[w["label"]] = left
            reset = _p(w.get("resets_at")); exh = _p(w.get("exhausts_at"))
            bars.append('<div class="r"><div class="l">%s</div><div class="bar"><i style="width:%d%%;background:%s"></i></div><div class="p" style="color:%s">%d%%</div><div class="w">%s</div></div>'
                        % (w["label"], left, color(left), color(left), left, word(left)))
            if reset: resets.append((w["label"], reset))
            if exh and reset and exh < reset and w["label"] != "5 часов" and left < 60:
                warn.append("%s кончится %s, сброс только %s" % (w["label"], fmt_dt(exh), fmt_dt(reset)))
        rs = ""
        for lab in ("5 часов", "неделя"):
            r = [x for x in resets if x[0] == lab]
            if r: rs += '<div class="rs"><span>%s</span><b>%s</b><em>через %s</em></div>' % (lab, fmt_dt(r[0][1]), countdown(r[0][1]))
        cards.append('<section class="card"><div class="hd"><div><div class="k">Подписка</div><h2>%s <small>%s</small></h2><div class="who">%s%s</div></div><div class="st">%s</div></div><div class="rows">%s</div><div class="resets">%s</div>%s</section>'
                     % (name, plan, em, (" · " + agent) if agent else "", status, "".join(bars), rs,
                        ('<div class="warn">⚠ ' + " · ".join(warn) + "</div>") if warn else '<div class="ok">✓ при текущем темпе до сброса хватает</div>'))
        wk = left_by.get("неделя", 0); fb = next((v for k, v in left_by.items() if "Fable" in k or "Opus" in k), None); h5 = left_by.get("5 часов", 100)
        st = "🔴 стоит" if h5 < 3 else (("🟡 %s пуст" % ("Fable" if fb is not None else "модель")) if fb is not None and fb < 5 else "🟢 работает")
        rows.append("<tr><td><b>%s</b></td><td>%s</td><td style='color:%s'>%d%%</td><td style='color:%s'>%s</td><td>%s</td></tr>"
                    % (agent or name, name, color(wk), wk, color(fb or 0), ("%d%%" % fb) if fb is not None else "—", st))
    fbs = []
    for a in accts:
        for w in a.get("windows") or []:
            if "Fable" in w["label"] or "Opus" in w["label"]: fbs.append((a.get("name"), 100 - float(w.get("percent") or 0)))
    if len(fbs) >= 2 and all(v < 15 for _, v in fbs): advice = "Совет: сильная модель пуста на всех подписках — тяжёлые задачи на Sonnet до сброса."
    elif len(fbs) >= 2 and any(v < 15 for _, v in fbs):
        low = [n for n, v in fbs if v < 15][0]; ok = [n for n, v in fbs if v >= 15][0]
        advice = "Совет: задачи на сильной модели с «%s» переносить на «%s»." % (low, ok)
    else: advice = "Совет: переключать никого не нужно."
    html = open(os.path.join(HERE, "card.html"), encoding="utf-8").read()
    return (html.replace("@@CARDS@@", "".join(cards)).replace("@@TRS@@", "".join(rows)).replace("@@ADV@@", advice)
            .replace("@@TS@@", datetime.now(TZ).strftime("%d.%m %H:%M")).replace("@@N@@", str(len(accts))))


def render_png(html, out):
    chrome = next((c for c in CHROME if c and os.path.exists(c)), None)
    if not chrome: return None
    hp = out[:-4] + ".html"; open(hp, "w", encoding="utf-8").write(html)
    subprocess.run([chrome, "--headless", "--disable-gpu", "--hide-scrollbars", "--window-size=1200,700", "--screenshot=" + out, "file://" + hp],
                   capture_output=True, timeout=60)
    return out if os.path.exists(out) and os.path.getsize(out) > 10_000 else None


def shared_card(max_age_min=75):
    """Общий PNG от старшей (accounts.json → "card": {"path": "...", "max_age_min": 75})."""
    try:
        cfg = json.load(open(os.path.join(HERE, "accounts.json")))
    except Exception: return None
    c = cfg.get("card") or {}
    path = os.path.expanduser(c.get("path") or os.environ.get("SUBSCRIPTION_CARD", ""))
    if not path or not os.path.exists(path): return None
    if time.time() - os.path.getmtime(path) > 60 * int(c.get("max_age_min") or max_age_min): return None
    return path


def card_for(state, out_path=None):
    out = out_path or os.path.join(os.path.expanduser(os.environ.get("SUBSCRIPTION_STATE", "~/.claude/state")), "subscription-card.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    png = render_png(build_html(state), out)
    return png or shared_card()


if __name__ == "__main__":
    st = json.load(sys.stdin) if not sys.stdin.isatty() else json.load(open(sys.argv[1]))
    print(card_for(st, sys.argv[2] if len(sys.argv) > 2 else None) or "")
