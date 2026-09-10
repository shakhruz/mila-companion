#!/usr/bin/env python3
"""Состояние подписок Claude: окна лимитов с сервера Anthropic плюс местный расход.

Механизм повторяет провайдер Claude из OpenUsage (MIT, github.com/robinebers/openusage),
реализация своя. Только чтение: токен читается из файла входа, уходит одним заголовком
на api.anthropic.com и никуда больше — ни в кэш, ни в лог, ни в вывод.

Несколько подписок описываются в accounts.json рядом со скриптом:

    {"accounts": [
       {"name": "Шахруз",  "credentials": "~/.claude/.credentials.json"},
       {"name": "Вторая",  "credentials": "~/work/tools/accounts/vtoraya.json"}
    ]}

Без этого файла ведётся одна подписка — та, на которой работает сам агент.

    subscription.py                # отчёт человеку
    subscription.py --telegram     # то же, готовое к отправке в Telegram
    subscription.py --json         # машине
    subscription.py --force        # спросить сервер, не глядя на возраст кэша
    subscription.py --local        # только местный расход, без сети
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

BASE = "https://api.anthropic.com"
USAGE_URL = f"{BASE}/api/oauth/usage"
PROFILE_URL = f"{BASE}/api/oauth/profile"
BETA_HEADER = "oauth-2025-04-20"
USER_AGENT = "claude-code/2.1.69"

HERE = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_PATH = os.path.join(HERE, "accounts.json")
STATE_DIR = (os.environ.get("MILA_STATE_DIR") or os.environ.get("SUBSCRIPTION_STATE")
             or ("/home/companion/state" if os.path.isdir("/home/companion") else os.path.expanduser("~/.claude/state")))
CACHE_PATH = os.path.join(STATE_DIR, "subscription-usage.json")
DAILY_PATH = os.path.join(STATE_DIR, "usage-daily.json")

FRESH_SECONDS = 15 * 60          # эндпоинт злой на частые запросы
PROFILE_FRESH_SECONDS = 24 * 3600
BACKOFF_START = 5 * 60
BACKOFF_MAX = 60 * 60

TZ_OFFSET_HOURS = int(os.environ.get("MILA_TZ_OFFSET", "5"))  # Asia/Tashkent
TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))

WINDOW_SECONDS = {"5 часов": 5 * 3600}
WEEK_SECONDS = 7 * 24 * 3600

MONTHS = ("января февраля марта апреля мая июня июля августа сентября "
          "октября ноября декабря").split()


# --- мелочи --------------------------------------------------------------

def plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def spaced(n):
    return f"{int(n):,}".replace(",", " ")


def format_plan(subscription_type, tier):
    """«max» + «default_claude_max_20x» -> «Max 20x», без повтора слова."""
    tier_text = (tier or "").replace("default_claude_", "").replace("_", " ").strip()
    base = (subscription_type or "").strip()
    if tier_text and base and base.lower() in tier_text.lower().split():
        text = tier_text
    else:
        text = " ".join(x for x in (base, tier_text) if x)
    if not text:
        return None
    return text[0].upper() + text[1:]


def now_local():
    return datetime.now(timezone.utc).astimezone(TZ)


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


# --- учётные записи ------------------------------------------------------

def load_accounts():
    try:
        with open(ACCOUNTS_PATH) as fh:
            listed = (json.load(fh) or {}).get("accounts") or []
    except (OSError, ValueError):
        listed = []
    if not listed:
        listed = [{"name": "своя", "credentials": "~/.claude/.credentials.json"}]
    return listed


def read_credentials(entry):
    """(token, subscription_type, rate_limit_tier, expires_at_ms). Бросает RuntimeError."""
    env_name = entry.get("env")
    if env_name:
        token = os.environ.get(env_name, "").strip()
        if not token:
            raise RuntimeError(f"переменная {env_name} пуста")
        return token, None, None, None

    raw = entry.get("credentials") or "~/.claude/.credentials.json"
    if raw.startswith("~/.claude/") and os.environ.get("CLAUDE_CONFIG_DIR"):
        raw = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], raw.split("/", 2)[2])
    path = os.path.expanduser(raw)
    data = None
    try:
        with open(path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        # macOS: Claude Code держит вход в связке ключей, файла нет (Мила Админ, 09.09.2026)
        if sys.platform == "darwin":
            import subprocess
            try:
                out = subprocess.run(["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                                     capture_output=True, text=True, timeout=10).stdout.strip()
                data = json.loads(out) if out else None
            except Exception:
                data = None
        if data is None:
            raise RuntimeError(f"нет файла входа {path}")
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"файл входа не читается: {exc}")

    oauth = data.get("claudeAiOauth") or {}
    token = (oauth.get("accessToken") or "").strip()
    if not token:
        raise RuntimeError("в файле входа нет accessToken")
    return token, oauth.get("subscriptionType"), oauth.get("rateLimitTier"), oauth.get("expiresAt")


# --- кэш -----------------------------------------------------------------

def load_cache():
    try:
        with open(CACHE_PATH) as fh:
            cache = json.load(fh)
    except (OSError, ValueError):
        cache = {}
    return cache if isinstance(cache, dict) else {}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, CACHE_PATH)


# --- сеть ----------------------------------------------------------------

def _get(url, token, timeout=15):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "anthropic-beta": BETA_HEADER,
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        retry_after = None
        if exc.headers and exc.headers.get("retry-after"):
            try:
                retry_after = int(exc.headers["retry-after"])
            except ValueError:
                retry_after = None
        kind = {
            401: "вход просрочен — нужен повторный логин",
            403: "у токена нет доступа к профилю",
            429: "сервер режет частые запросы",
        }.get(exc.code, f"сервер ответил {exc.code}")
        return None, {"kind": kind, "code": exc.code, "retry_after": retry_after}
    except urllib.error.URLError as exc:
        return None, {"kind": f"сеть недоступна ({exc.reason})", "code": None, "retry_after": None}
    except (ValueError, OSError) as exc:
        return None, {"kind": f"ответ не разобран ({exc})", "code": None, "retry_after": None}


# --- разбор ответа -------------------------------------------------------

def _window(obj, label):
    if not isinstance(obj, dict) or obj.get("utilization") is None:
        return None
    return {"label": label, "percent": float(obj["utilization"]), "resets_at": obj.get("resets_at")}


def parse_windows(payload):
    lines = []
    for key, label in (
        ("five_hour", "5 часов"),
        ("seven_day", "неделя"),
        ("seven_day_opus", "нед · Opus"),
        ("seven_day_sonnet", "нед · Sonnet"),
    ):
        w = _window(payload.get(key), label)
        if w:
            lines.append(w)

    # Помодельные недельные окна Anthropic унесла из seven_day_<модель> в массив limits.
    for entry in payload.get("limits") or []:
        if not isinstance(entry, dict) or entry.get("kind") != "weekly_scoped":
            continue
        model = ((entry.get("scope") or {}).get("model") or {}).get("display_name")
        pct = entry.get("percent")
        if model and pct is not None:
            lines.append({"label": f"нед · {model}", "percent": float(pct),
                          "resets_at": entry.get("resets_at")})

    extra = payload.get("extra_usage")
    if isinstance(extra, dict) and extra.get("utilization") is not None:
        lines.append({"label": "докуплено", "percent": float(extra["utilization"]),
                      "resets_at": extra.get("resets_at")})
    return lines


def enrich(window):
    """Дописывает темп: сколько окна прошло против того, сколько израсходовано."""
    resets = parse_iso(window.get("resets_at"))
    if not resets:
        return window
    duration = WINDOW_SECONDS.get(window["label"], WEEK_SECONDS)
    start = resets - timedelta(seconds=duration)
    now = datetime.now(timezone.utc)
    elapsed = (now - start).total_seconds() / duration
    window["elapsed"] = max(0.0, min(1.0, elapsed))
    window["lead"] = window["percent"] - window["elapsed"] * 100
    if elapsed > 0.05 and window["percent"] > 0:
        pace = window["percent"] / elapsed          # процентов на всё окно при этом темпе
        # прогноз показываем только при заметном перерасходе и пока окно не выбрано
        if pace >= 110 and window["percent"] < 95:
            hit = start + timedelta(seconds=duration * (100.0 / pace))
            if hit > now:
                window["exhausts_at"] = hit.astimezone(TZ).isoformat()
        window["projected"] = pace
    return window


# --- местный расход ------------------------------------------------------

def local_spend():
    try:
        with open(DAILY_PATH) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    days = data.get("days") or []
    if not days:
        return None
    today = days[-1]
    t = today.get("total") or {}
    week = [d for d in days[-7:]]
    return {
        "day": today.get("day"),
        "cost_usd": today.get("cost_usd") or 0.0,
        "basis": data.get("basis"),
        "turns": t.get("turns") or 0,
        "out": t.get("out") or 0,
        "cache_read": t.get("cache_read") or 0,
        "cache_write": t.get("cache_write") or 0,
        "models": [m.get("model") for m in (today.get("models") or [])],
        "week_cost": sum(d.get("cost_usd") or 0.0 for d in week),
        "week_days": len(week),
    }


# --- сборка --------------------------------------------------------------

def collect_from_report(entry):
    """Подписка, до входа которой мы не дотягиваемся: её отчёт кладут нам файлом.

    Формат — вывод этого же скрипта с --json. Чужой вход остаётся у чужого агента,
    к нам приезжают только проценты и время сброса.
    """
    acc = {"name": entry.get("name") or "чужая", "borrowed": True}
    path = os.path.expanduser(entry["report"])
    try:
        with open(path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        acc["error"] = "отчёт не приходил"
        acc["windows"] = []
        return acc
    except (OSError, ValueError) as exc:
        acc["error"] = f"отчёт не разобран ({exc})"
        acc["windows"] = []
        return acc

    inner = (data.get("accounts") or [{}])[0]
    acc["windows"] = inner.get("windows") or []
    acc["plan"] = inner.get("plan")
    acc["profile"] = inner.get("profile")
    acc["reported_by"] = inner.get("name")

    generated = parse_iso(data.get("generated_at"))
    if generated:
        age = (datetime.now(timezone.utc) - generated).total_seconds()
        acc["age_seconds"] = int(max(0, age))
        if age > 3600:
            acc["stale"] = True
    else:
        acc["age_seconds"] = None
    return acc


def collect_account(entry, cache, force=False):
    if entry.get("report"):
        return collect_from_report(entry)

    key = entry.get("name") or "своя"
    now = int(time.time())
    slot = cache.setdefault(key, {})
    acc = {"name": key}

    try:
        token, sub_type, tier, expires_at = read_credentials(entry)
    except RuntimeError as exc:
        acc["error"] = str(exc)
        acc["windows"] = slot.get("windows") or []
        acc["profile"] = slot.get("profile")
        return acc

    acc["plan"] = format_plan(sub_type, tier) or slot.get("plan")
    if expires_at and expires_at / 1000 < now:
        acc["token_stale"] = True

    # профиль меняется редко — держим сутки
    profile = slot.get("profile")
    if force or not profile or now - slot.get("profile_at", 0) > PROFILE_FRESH_SECONDS:
        payload, err = _get(PROFILE_URL, token)
        if payload:
            account = payload.get("account") or {}
            org = payload.get("organization") or {}
            profile = {
                "display_name": account.get("display_name") or account.get("full_name"),
                "email": account.get("email"),
                "org_type": org.get("organization_type"),
                "tier": org.get("rate_limit_tier"),
                "status": org.get("subscription_status"),
                "extra_usage": org.get("has_extra_usage_enabled"),
            }
            slot["profile"] = profile
            slot["profile_at"] = now
    acc["profile"] = profile
    if profile and profile.get("tier") and not acc.get("plan"):
        acc["plan"] = format_plan(profile.get("org_type"), profile["tier"])

    fetched_at = slot.get("fetched_at", 0)
    blocked_until = slot.get("blocked_until", 0)
    age = now - fetched_at if fetched_at else None

    if not force and slot.get("windows") and age is not None and age < FRESH_SECONDS:
        acc.update({"windows": slot["windows"], "age_seconds": age, "from_cache": True})
        return acc
    if now < blocked_until and slot.get("windows"):
        acc.update({"windows": slot["windows"], "age_seconds": age, "from_cache": True,
                    "note": f"жду до {datetime.fromtimestamp(blocked_until, TZ):%H:%M} — сервер режет запросы"})
        return acc

    payload, err = _get(USAGE_URL, token)
    if err:
        acc["error"] = err["kind"]
        if err["code"] == 429:
            step = min(max(BACKOFF_START, slot.get("backoff", 0) * 2), BACKOFF_MAX)
            if err.get("retry_after"):
                step = max(step, err["retry_after"])
            slot["backoff"] = step
            slot["blocked_until"] = now + step
            acc["error"] += f", жду {step // 60} мин"
        if slot.get("windows"):
            acc.update({"windows": slot["windows"], "age_seconds": age,
                        "from_cache": True, "stale": True})
        else:
            acc["windows"] = []
        return acc

    windows = parse_windows(payload)
    slot.update({"fetched_at": now, "windows": windows, "backoff": 0,
                 "blocked_until": 0, "plan": acc.get("plan")})
    acc.update({"windows": windows, "age_seconds": 0, "from_cache": False})
    return acc


def collect(force=False, local_only=False):
    cache = load_cache()
    state = {"local": local_spend(), "accounts": [], "generated_at": now_local().isoformat()}
    if local_only:
        state["note"] = "сеть не спрашивали (--local)"
        return state
    for entry in load_accounts():
        acc = collect_account(entry, cache, force=force)
        acc["windows"] = [enrich(dict(w)) for w in (acc.get("windows") or [])]
        state["accounts"].append(acc)
    save_cache(cache)
    return state


# --- отчёт ---------------------------------------------------------------

BAR_W = 12


def bar(percent):
    filled = max(0, min(BAR_W, int(round(percent / 100 * BAR_W))))
    if percent > 0 and filled == 0:
        filled = 1
    return "█" * filled + "░" * (BAR_W - filled)


def when(dt_iso, short=False):
    dt = parse_iso(dt_iso)
    if not dt:
        return ""
    dt = dt.astimezone(TZ)
    today = now_local().date()
    if dt.date() == today:
        return f"{dt:%H:%M}"
    if dt.date() == today + timedelta(days=1):
        return f"завтра {dt:%H:%M}"
    if short:
        return f"{dt.day}.{dt.month:02d} {dt:%H:%M}"
    return f"{dt.day} {MONTHS[dt.month - 1]} в {dt:%H:%M}"


WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def exact(dt_iso):
    """Точные дата и время сброса: «сегодня 18:50», «сб 12.09 08:00»."""
    dt = parse_iso(dt_iso)
    if not dt:
        return ""
    dt = dt.astimezone(TZ)
    today = now_local().date()
    if dt.date() == today:
        return f"сегодня {dt:%H:%M}"
    if dt.date() == today + timedelta(days=1):
        return f"завтра {dt:%H:%M}"
    return f"{WEEKDAYS[dt.weekday()]} {dt.day:02d}.{dt.month:02d} {dt:%H:%M}"


def countdown(dt_iso):
    """Сколько осталось до сброса: «2 дн 16 ч», «3 ч 05 мин», «12 мин»."""
    dt = parse_iso(dt_iso)
    if not dt:
        return ""
    left = (dt - datetime.now(timezone.utc)).total_seconds()
    if left <= 0:
        return "вот-вот"
    days, rem = divmod(int(left), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} дн {hours} ч"
    if hours:
        return f"{hours} ч {minutes:02d} мин"
    return f"{minutes} мин"


def verdict(w):
    """Короткая оценка темпа для правой колонки. Считаем в остатке, а не в расходе."""
    if w["percent"] >= 95:
        return "пусто"
    lead = w.get("lead")          # + = тратим быстрее, чем идёт время
    if lead is None:
        return ""
    if lead > 15:
        return "тает быстро"
    if lead < -15:
        return "с запасом"
    return "ровно"


def render(state, width=44):
    out = []
    accounts = state.get("accounts") or []

    for acc in accounts:
        prof = acc.get("profile") or {}
        title = prof.get("display_name") or acc["name"]
        out.append(f"ПОДПИСКА · {title}")
        sub = []
        if prof.get("email"):
            sub.append(prof["email"])
        if acc.get("plan"):
            sub.append(acc["plan"])
        if prof.get("status") and prof["status"] != "active":
            sub.append(f"статус {prof['status']}")
        if sub:
            out.append(" · ".join(sub))
        out.append("")

        windows = acc.get("windows") or []
        if windows:
            out.append("бак · осталось")
            for w in windows:
                left = max(0.0, 100.0 - w["percent"])
                out.append(
                    f"{w['label']:<12} {bar(left)} {left:>3.0f}%  {verdict(w)}".rstrip()
                )
            out.append("")
            # Окна с общим временем сброса (неделя и помодельные) — одной строкой.
            groups, order = {}, []
            for w in windows:
                stamp = w.get("resets_at")
                if not stamp:
                    continue
                dt = parse_iso(stamp)
                # ключ по минуте: у окон одного срока метки расходятся на микросекунды
                key = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M") if dt else stamp
                if key not in groups:
                    groups[key] = (w["label"], stamp)
                    order.append(key)
            if order:
                out.append("сброс")
                for key in order:
                    label, stamp = groups[key]
                    out.append(f"{label:<12} {exact(stamp)} — через {countdown(stamp)}")
                out.append("")

            burn = [w for w in windows if w.get("exhausts_at")]
            for w in burn:
                out.append(f"при этом темпе {w['label']} кончится {when(w['exhausts_at'])}")
            if acc.get("age_seconds"):
                mins = acc["age_seconds"] // 60
                if mins >= 1:
                    ago = f"{mins} {plural(mins, 'минуту', 'минуты', 'минут')} назад"
                    if acc.get("borrowed"):
                        hours = mins // 60
                        ago = (f"{hours} {plural(hours, 'час', 'часа', 'часов')} назад"
                               if hours else ago)
                        out.append(("отчёт устарел, снят " if acc.get("stale")
                                    else "снят ") + ago)
                    else:
                        out.append("данные " + ago)
        if acc.get("error"):
            # Пути наружу не показываем: отчёт уходит человеку в чат.
            if acc["error"].startswith("нет файла входа"):
                out.append("не подключена — вход не передан")
            elif acc["error"].startswith("отчёт не"):
                out.append(f"не подключена — {acc['error']}")
            elif acc["error"].startswith("файл входа не читается"):
                out.append("не подключена — вход испорчен")
            else:
                out.append(f"не прочитано: {acc['error']}")
        if acc.get("note"):
            out.append(acc["note"])
        if acc.get("token_stale"):
            out.append("вход просрочен, Claude Code обновит его сам")
        out.append("")

    spend = state.get("local")
    if spend:
        day = parse_iso(spend["day"] + "T00:00:00+00:00")
        day_text = f"{day.day} {MONTHS[day.month - 1]}" if day else spend["day"]
        out.append(f"РАСХОД · {day_text}")
        out.append(f"${spend['cost_usd']:.2f} по прайсу API — мера, не счёт")
        out.append(
            f"{spend['turns']} {plural(spend['turns'], 'обращение', 'обращения', 'обращений')}"
            f" · выдано {spaced(spend['out'])}"
        )
        out.append(f"кэш {spaced(spend['cache_read'])} чтение / {spaced(spend['cache_write'])} запись")
        if spend["week_days"] > 1:
            out.append(f"за {spend['week_days']} "
                       f"{plural(spend['week_days'], 'день', 'дня', 'дней')}: ${spend['week_cost']:.2f}")
        if spend.get("models"):
            out.append("модели: " + ", ".join(m for m in spend["models"] if m))

    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def render_telegram(state):
    body = render(state)
    body = body.replace("\\", "\\\\").replace("`", "\\`")
    return "```\n" + body + "\n```"


def main():
    ap = argparse.ArgumentParser(description="Состояние подписок Claude")
    ap.add_argument("--force", action="store_true", help="спросить сервер, не глядя на кэш")
    ap.add_argument("--json", action="store_true", help="машинный вывод")
    ap.add_argument("--telegram", action="store_true", help="готовый блок для Telegram")
    ap.add_argument("--local", action="store_true", help="только местный расход, без сети")
    ap.add_argument("--card", nargs="?", const="auto", metavar="PNG",
                    help="картинка-дэшборд (Chrome есть → рисую; нет → беру свежий общий PNG из accounts.json «card»; иначе пусто)")
    args = ap.parse_args()

    state = collect(force=args.force, local_only=args.local)
    if args.card:
        try:
            import subscription_card
            png = subscription_card.card_for(state, None if args.card == "auto" else args.card)
        except Exception as exc:  # картинка — удобство, не условие
            png = None
            print(f"card: {exc}", file=sys.stderr)
        print(png or "")
        return 0
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=1))
    elif args.telegram:
        print(render_telegram(state))
    else:
        print(render(state))

    ok = any(a.get("windows") for a in state.get("accounts", [])) or state.get("local")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
