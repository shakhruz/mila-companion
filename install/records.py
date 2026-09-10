#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Учёт: что было сказано и что было потрачено.

Две базы, два разных вопроса.

  conversations.db · таблица turns — ЧТО происходило. Один ход = один обмен:
  сообщение человека и ответ агента, с моделью, настройками, токенами, кэшем,
  длительностью и ценой. Схема — та же, что у директоров флота (`turns` с
  полями id, ts, brand, account_id, bot_slug, chat_id, message_id, user_text,
  bot_text, model, prompt_tokens, completion_tokens, latency_ms,
  idempotency_key), плюс колонки, которых у директоров нет. Совместимость не
  ради красоты: аналитика по флоту и по Компаньону должна считаться одним
  запросом, иначе её никто не будет считать.

  external-spend.db · таблица external_calls — СКОЛЬКО ушло наружу. Картинка,
  голос, видео, чужая модель: всё, за что платит не подписка, а счёт у
  провайдера. Сегодня Компаньон наружу не ходит вовсе, и именно поэтому леджер
  нужен завести сейчас: первый навык с генерацией картинки начнёт тратить
  молча, и заметит это выписка, а не мы.

🔴 ГЛАВНОЕ ПРО ДЕНЬГИ. Поле usd_cost в turns — это НЕ списание. Работа по
подписке Claude Code не оплачивается этими долларами; цифра отвечает на другой
вопрос: во сколько тот же объём обошёлся бы по прейскуранту API. Это мера того,
что подписка отдаёт. Что именно означает цифра в конкретной строке — говорит
поле paid_by:

    paid_by = "subscription" → справочно, никто ничего не списал
    paid_by = "api_key"      → настоящий расход, его и сверяют с выпиской

Настоящие деньги живут в external_calls: там каждая строка — это счёт, и
поэтому request_id обязателен. Без него строку не с чем сверить, и леджер
превращается в вторую версию правды.

Тексты разговоров — персональные данные и коммерческая тайна клиента. Что из
них попадает в базу, решает выключатель MILA_RECORD_TEXT:

    full   — тексты целиком (по умолчанию: это личный агент владельца)
    length — только длина в символах, самих текстов нет
    none   — ни текста, ни длины

Выбор пишется в каждую строку полем text_policy, чтобы пустой user_text нельзя
было спутать с потерянными данными.

Где лежит: ~/.claude/analytics/ (MILA_RECORDS_DIR перекрывает). Каталог 700,
базы 600 — внутри переписка.

Как позвать из навыка одной строкой:

    from records import record_external
    record_external(provider="fal", service="lyria-3", model="lyria-3-pro",
                    usd=0.08, units=2, unit_kind="треки", request_id="fal-7c1a")

Из оболочки — тем же одним вызовом:

    records.py external --provider fal --service lyria-3 --usd 0.08 \\
        --units 2 --unit-kind треки --request-id fal-7c1a

Посмотреть:

    records.py show turns --days 7
    records.py show external --days 30
    records.py check            # то, что спрашивает doctor.py
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))
RECORDS_DIR = os.environ.get("MILA_RECORDS_DIR",
                             os.path.join(CLAUDE_DIR, "analytics"))
TURNS_DB = os.path.join(RECORDS_DIR, "conversations.db")
EXTERNAL_DB = os.path.join(RECORDS_DIR, "external-spend.db")
WATERMARK = os.path.join(RECORDS_DIR, "records-watermark.json")

TEXT_POLICIES = ("full", "length", "none")
AGENT_KINDS = ("director", "companion", "admin")
PAID_BY = ("subscription", "api_key")


def text_policy():
    """Выключатель текстов. Незнакомое значение — не повод писать всё подряд."""
    p = (os.environ.get("MILA_RECORD_TEXT") or "full").strip().lower()
    return p if p in TEXT_POLICIES else "full"


# ── схема ─────────────────────────────────────────────────────────────────
#
# Первые четырнадцать колонок повторяют схему директоров дословно, включая
# типы и значения по умолчанию. Ниже — то, чего у директоров нет и о чём
# просил владелец. Добавляются они через ALTER TABLE, а не пересозданием:
# базу директора можно открыть этим модулем, и она дополнится, не потеряв ни
# строки. Обратная совместимость держится с той же стороны: старый инструмент
# читает первые четырнадцать колонок и не замечает остальных.

TURNS_BASE = """
CREATE TABLE IF NOT EXISTS turns (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                REAL    NOT NULL,
    brand             TEXT    NOT NULL DEFAULT '',
    account_id        TEXT    NOT NULL DEFAULT '',
    bot_slug          TEXT    NOT NULL DEFAULT '',
    chat_id           TEXT    NOT NULL DEFAULT '',
    message_id        TEXT    NOT NULL DEFAULT '',
    user_text         TEXT    NOT NULL DEFAULT '',
    bot_text          TEXT    NOT NULL DEFAULT '',
    model             TEXT    NOT NULL DEFAULT '',
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms        INTEGER NOT NULL DEFAULT 0,
    idempotency_key   TEXT    UNIQUE
)
"""

# (имя, объявление) — порядок важен только для читаемости.
TURNS_EXTRA = [
    # кто говорил
    ("agent",              "TEXT    NOT NULL DEFAULT ''"),
    ("agent_kind",         "TEXT    NOT NULL DEFAULT ''"),   # director|companion|admin
    ("session_id",         "TEXT    NOT NULL DEFAULT ''"),
    ("turn_source",        "TEXT    NOT NULL DEFAULT ''"),   # откуда пришёл ход
    # настройки модели: чем именно был сделан этот ход
    ("temperature",        "REAL"),
    ("max_tokens",         "INTEGER"),
    ("reasoning_mode",     "TEXT    NOT NULL DEFAULT ''"),
    ("reasoning_tokens",   "INTEGER NOT NULL DEFAULT 0"),
    ("tool_calls",         "INTEGER NOT NULL DEFAULT 0"),
    ("tools_used",         "TEXT    NOT NULL DEFAULT ''"),
    # кэш: без него дорогой день и длинный день выглядят одинаково
    ("cache_write_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("cache_read_tokens",  "INTEGER NOT NULL DEFAULT 0"),
    # деньги
    ("usd_cost",           "REAL"),
    ("cost_basis",         "TEXT    NOT NULL DEFAULT ''"),
    ("paid_by",            "TEXT    NOT NULL DEFAULT ''"),   # subscription|api_key
    # тексты и то, что от них осталось
    ("text_policy",        "TEXT    NOT NULL DEFAULT ''"),
    ("user_len",           "INTEGER NOT NULL DEFAULT 0"),
    ("bot_len",            "INTEGER NOT NULL DEFAULT 0"),
    ("meta_json",          "TEXT    NOT NULL DEFAULT ''"),
]

TURNS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_turns_acct  ON turns(brand, account_id)",
    "CREATE INDEX IF NOT EXISTS idx_turns_bot   ON turns(bot_slug)",
    "CREATE INDEX IF NOT EXISTS idx_turns_ts    ON turns(ts)",
    "CREATE INDEX IF NOT EXISTS idx_turns_agent ON turns(agent, ts)",
    "CREATE INDEX IF NOT EXISTS idx_turns_chat  ON turns(chat_id, ts)",
]

EXTERNAL_BASE = """
CREATE TABLE IF NOT EXISTS external_calls (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL    NOT NULL,
    agent      TEXT    NOT NULL DEFAULT '',
    agent_kind TEXT    NOT NULL DEFAULT '',
    provider   TEXT    NOT NULL DEFAULT '',
    service    TEXT    NOT NULL DEFAULT '',
    model      TEXT    NOT NULL DEFAULT '',
    usd        REAL    NOT NULL DEFAULT 0,
    units      REAL    NOT NULL DEFAULT 0,
    unit_kind  TEXT    NOT NULL DEFAULT '',
    request_id TEXT    NOT NULL,
    meta_json  TEXT    NOT NULL DEFAULT '',
    UNIQUE(provider, request_id)
)
"""

EXTERNAL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ext_ts       ON external_calls(ts)",
    "CREATE INDEX IF NOT EXISTS idx_ext_provider ON external_calls(provider, ts)",
    "CREATE INDEX IF NOT EXISTS idx_ext_agent    ON external_calls(agent, ts)",
]


def _connect(path):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, mode=0o700, exist_ok=True)
    fresh = not os.path.exists(path)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 15000")
    con.execute("PRAGMA foreign_keys = ON")
    if fresh:
        # 600 ставим сразу, до первой записи: в базе переписка.
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return con


def _columns(con, table):
    return {r[1] for r in con.execute("PRAGMA table_info(%s)" % table)}


def open_turns(path=None):
    """Открыть (и при нужде дополнить) базу разговоров.

    Дополнение — только ALTER TABLE ADD COLUMN. Ни одна существующая строка не
    трогается, ни одна колонка не удаляется: сюда можно навести этот модуль на
    живую базу директора.
    """
    con = _connect(path or TURNS_DB)
    con.execute(TURNS_BASE)
    have = _columns(con, "turns")
    for name, decl in TURNS_EXTRA:
        if name not in have:
            con.execute("ALTER TABLE turns ADD COLUMN %s %s" % (name, decl))
    for sql in TURNS_INDEXES:
        con.execute(sql)
    con.commit()
    return con


def open_external(path=None):
    con = _connect(path or EXTERNAL_DB)
    con.execute(EXTERNAL_BASE)
    for sql in EXTERNAL_INDEXES:
        con.execute(sql)
    con.commit()
    return con


def init(turns_path=None, external_path=None):
    """Завести обе базы. Идемпотентно."""
    open_turns(turns_path).close()
    open_external(external_path).close()
    return turns_path or TURNS_DB, external_path or EXTERNAL_DB


# ── цены ──────────────────────────────────────────────────────────────────

def price_turn(model, prompt_tokens=0, completion_tokens=0,
               cache_write_tokens=0, cache_read_tokens=0):
    """(доллары, по какой таблице) — по прайсу, который уже есть в проекте.

    Таблица живёт в usage_collect.py и перекрывается ~/.claude/prices.json.
    Второй таблицы цен в этом ките быть не должно: два прайса — это два
    разных ответа на один вопрос, и через месяц никто не помнит, какой верный.

    Неизвестная модель возвращает (None, ""): токены посчитаны, деньги — нет.
    Соврать цифрой хуже, чем показать прочерк.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import usage_collect
    except Exception:
        return None, ""
    prices = usage_collect.load_prices()
    price, matched = usage_collect.price_for(prices, model or "")
    if not price:
        return None, ""
    usd = usage_collect.cost({"in": prompt_tokens or 0,
                              "out": completion_tokens or 0,
                              "cache_write": cache_write_tokens or 0,
                              "cache_read": cache_read_tokens or 0}, price)
    basis = prices.get("_basis", "unknown")
    if matched and matched != model:
        basis = "%s (по %s)" % (basis, matched)
    return usd, basis


# ── запись хода ───────────────────────────────────────────────────────────

def record_turn(con=None, *, ts=None, brand="", account_id="", bot_slug="",
                chat_id="", message_id="", user_text="", bot_text="",
                model="", prompt_tokens=0, completion_tokens=0,
                latency_ms=0, idempotency_key=None,
                agent="", agent_kind="companion", session_id="",
                turn_source="", temperature=None, max_tokens=None,
                reasoning_mode="", reasoning_tokens=0,
                tool_calls=0, tools_used="",
                cache_write_tokens=0, cache_read_tokens=0,
                usd_cost=None, cost_basis="", paid_by="subscription",
                meta=None, policy=None, price=True):
    """Записать один ход. Возвращает id или None, если такой уже записан.

    Повтор ловится по idempotency_key — тем же способом, что у директоров
    (`<bot>:<chat>:<message_id>`). Сборщик, запущенный дважды за день, не
    должен удваивать цифры: иначе первое же расхождение с выпиской объясняют
    «наверное, два раза собралось», и на этом учёт заканчивается.

    price=True досчитывает деньги по прайсу проекта, если их не передали.
    paid_by по умолчанию subscription — то есть цифра СПРАВОЧНАЯ.
    """
    own = con is None
    con = con or open_turns()
    try:
        pol = policy or text_policy()
        ut, bt = user_text or "", bot_text or ""
        ul, bl = len(ut), len(bt)
        if pol != "full":
            ut, bt = "", ""
        if pol == "none":
            ul, bl = 0, 0

        if usd_cost is None and price:
            usd_cost, basis = price_turn(model, prompt_tokens, completion_tokens,
                                         cache_write_tokens, cache_read_tokens)
            cost_basis = cost_basis or basis

        row = {
            "ts": float(ts if ts is not None else time.time()),
            "brand": brand or "", "account_id": str(account_id or ""),
            "bot_slug": bot_slug or "", "chat_id": str(chat_id or ""),
            "message_id": str(message_id or ""),
            "user_text": ut, "bot_text": bt,
            "model": model or "",
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "latency_ms": int(latency_ms or 0),
            "idempotency_key": idempotency_key,
            "agent": agent or os.environ.get("MILA_AGENT", ""),
            "agent_kind": agent_kind or "",
            "session_id": session_id or "",
            "turn_source": turn_source or "",
            "temperature": temperature,
            "max_tokens": max_tokens,
            "reasoning_mode": reasoning_mode or "",
            "reasoning_tokens": int(reasoning_tokens or 0),
            "tool_calls": int(tool_calls or 0),
            "tools_used": tools_used or "",
            "cache_write_tokens": int(cache_write_tokens or 0),
            "cache_read_tokens": int(cache_read_tokens or 0),
            "usd_cost": usd_cost,
            "cost_basis": cost_basis or "",
            "paid_by": paid_by or "",
            "text_policy": pol,
            "user_len": ul, "bot_len": bl,
            "meta_json": json.dumps(meta, ensure_ascii=False) if meta else "",
        }
        cols = list(row)
        sql = ("INSERT OR IGNORE INTO turns (%s) VALUES (%s)"
               % (", ".join(cols), ", ".join("?" * len(cols))))
        cur = con.execute(sql, [row[c] for c in cols])
        con.commit()
        return cur.lastrowid if cur.rowcount else None
    finally:
        if own:
            con.close()


# ── запись внешнего вызова ────────────────────────────────────────────────

def record_external(provider, service="", usd=0.0, *, request_id,
                    model="", units=0, unit_kind="", agent="",
                    agent_kind="companion", ts=None, meta=None, con=None):
    """Записать оплаченный наружу вызов. Возвращает id или None (уже записан).

    request_id обязателен и именно поэтому не имеет значения по умолчанию: по
    нему строка сверяется с выпиской провайдера. Леджер, который нельзя
    сверить, — это не леджер, а ощущение.

    unit_kind называет, что считали: «секунды видео», «картинки», «символы»,
    «токены». Единица без имени через месяц не читается.
    """
    if not str(request_id or "").strip():
        raise ValueError("request_id обязателен: без него строку не сверить "
                         "с выпиской провайдера")
    if not str(provider or "").strip():
        raise ValueError("provider обязателен (openrouter|fal|other)")
    own = con is None
    con = con or open_external()
    try:
        row = {
            "ts": float(ts if ts is not None else time.time()),
            "agent": agent or os.environ.get("MILA_AGENT", ""),
            "agent_kind": agent_kind or "",
            "provider": str(provider).strip(),
            "service": service or "",
            "model": model or "",
            "usd": float(usd or 0),
            "units": float(units or 0),
            "unit_kind": unit_kind or "",
            "request_id": str(request_id).strip(),
            "meta_json": json.dumps(meta, ensure_ascii=False) if meta else "",
        }
        cols = list(row)
        sql = ("INSERT OR IGNORE INTO external_calls (%s) VALUES (%s)"
               % (", ".join(cols), ", ".join("?" * len(cols))))
        cur = con.execute(sql, [row[c] for c in cols])
        con.commit()
        return cur.lastrowid if cur.rowcount else None
    finally:
        if own:
            con.close()


# ── чтение ────────────────────────────────────────────────────────────────

def _since_ts(days=None, since=None):
    if since is not None:
        return float(since)
    if days is None:
        return None
    start = datetime.now().astimezone().replace(
        hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    return start.timestamp()


def read_turns(con=None, *, days=None, since=None, until=None, agent=None,
               agent_kind=None, chat_id=None, model=None, paid_by=None,
               limit=None, order="asc"):
    own = con is None
    con = con or open_turns()
    try:
        where, args = [], []
        s = _since_ts(days, since)
        if s is not None:
            where.append("ts >= ?"); args.append(s)
        if until is not None:
            where.append("ts < ?"); args.append(float(until))
        for col, val in (("agent", agent), ("agent_kind", agent_kind),
                         ("chat_id", chat_id), ("model", model),
                         ("paid_by", paid_by)):
            if val is not None:
                where.append("%s = ?" % col); args.append(str(val))
        sql = "SELECT * FROM turns"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts %s, id %s" % (("DESC", "DESC") if order == "desc"
                                           else ("ASC", "ASC"))
        if limit:
            sql += " LIMIT %d" % int(limit)
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        if own:
            con.close()


def read_external(con=None, *, days=None, since=None, until=None,
                  provider=None, agent=None, service=None, limit=None,
                  order="asc"):
    own = con is None
    con = con or open_external()
    try:
        where, args = [], []
        s = _since_ts(days, since)
        if s is not None:
            where.append("ts >= ?"); args.append(s)
        if until is not None:
            where.append("ts < ?"); args.append(float(until))
        for col, val in (("provider", provider), ("agent", agent),
                         ("service", service)):
            if val is not None:
                where.append("%s = ?" % col); args.append(str(val))
        sql = "SELECT * FROM external_calls"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts %s, id %s" % (("DESC", "DESC") if order == "desc"
                                           else ("ASC", "ASC"))
        if limit:
            sql += " LIMIT %d" % int(limit)
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        if own:
            con.close()


def last_key(con, agent=None):
    """Последний записанный idempotency_key — чтобы сборщик знал, где встал."""
    if agent:
        r = con.execute("SELECT MAX(ts) FROM turns WHERE agent = ?",
                        (agent,)).fetchone()
    else:
        r = con.execute("SELECT MAX(ts) FROM turns").fetchone()
    return r[0] if r else None


# ── состояние для doctor.py ───────────────────────────────────────────────

def _table_state(path, table, open_fn):
    st = {"path": path, "exists": os.path.exists(path), "rows": 0,
          "last_ts": None, "missing_columns": [], "mode": None, "error": ""}
    if not st["exists"]:
        return st
    try:
        st["mode"] = os.stat(path).st_mode & 0o777
        con = open_fn(path)
        st["rows"] = con.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]
        r = con.execute("SELECT MAX(ts) FROM %s" % table).fetchone()
        st["last_ts"] = r[0]
        have = _columns(con, table)
        want = ({c[0] for c in TURNS_EXTRA} if table == "turns" else set())
        st["missing_columns"] = sorted(want - have)
        con.close()
    except Exception as e:
        st["error"] = str(e)
    return st


def state():
    """Снимок обеих баз плюс сравнение с прошлым снимком.

    «Не пустеет» проверяется единственным способом, который работает: помнить,
    сколько строк было в прошлый раз. База, которая усохла, выглядит здоровой —
    файл на месте, схема цела, запросы отвечают. Замечают такое через месяц.
    """
    t = _table_state(TURNS_DB, "turns", open_turns)
    e = _table_state(EXTERNAL_DB, "external_calls", open_external)
    prev = {}
    try:
        with open(WATERMARK, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        pass
    out = {"turns": t, "external": e, "previous": prev,
           "shrunk": [], "records_dir": RECORDS_DIR,
           "text_policy": text_policy()}
    for name, cur in (("turns", t), ("external", e)):
        was = (prev.get(name) or {}).get("rows")
        if isinstance(was, int) and cur["exists"] and cur["rows"] < was:
            out["shrunk"].append("%s: было %d, стало %d" % (name, was, cur["rows"]))
    return out


def save_watermark(st=None):
    st = st or state()
    data = {"checked_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    for name in ("turns", "external"):
        data[name] = {"rows": st[name]["rows"], "last_ts": st[name]["last_ts"]}
    try:
        os.makedirs(RECORDS_DIR, mode=0o700, exist_ok=True)
        tmp = WATERMARK + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, WATERMARK)
    except OSError:
        pass
    return data


# ── командная строка ──────────────────────────────────────────────────────

def _ago(ts):
    if not ts:
        return "никогда"
    mins = int((time.time() - ts) // 60)
    if mins < 60:
        return "%d мин назад" % mins
    if mins < 60 * 48:
        return "%d ч назад" % (mins // 60)
    return "%d дн назад" % (mins // 1440)


def _short(text, n):
    text = (text or "").replace("\n", " ").strip()
    return text[:n] + ("…" if len(text) > n else "")


def cmd_show(args):
    if args.what == "turns":
        rows = read_turns(days=args.days, agent=args.agent,
                          chat_id=args.chat, limit=args.limit,
                          order="desc" if args.last else "asc")
        if args.as_json:
            json.dump(rows, sys.stdout, ensure_ascii=False, indent=1)
            print()
            return 0
        if not rows:
            print("Ходов за период нет. База: %s" % TURNS_DB)
            return 0
        ref = sum(r["usd_cost"] or 0 for r in rows if r["paid_by"] == "subscription")
        real = sum(r["usd_cost"] or 0 for r in rows if r["paid_by"] == "api_key")
        print("Ходы · %d · база %s" % (len(rows), TURNS_DB))
        print()
        for r in rows:
            when = datetime.fromtimestamp(r["ts"]).strftime("%d.%m %H:%M")
            money = "$%.4f" % r["usd_cost"] if r["usd_cost"] is not None else "  $?  "
            print("%s  %-16s %-22s %8s  вх %-7d вых %-6d кэш чт %-8d %ss"
                  % (when, r["agent"] or "—", (r["model"] or "—")[:22], money,
                     r["prompt_tokens"], r["completion_tokens"],
                     r["cache_read_tokens"], r["latency_ms"] // 1000))
            if r["text_policy"] == "full":
                print("      человек: %s" % _short(r["user_text"], 96))
                print("      агент:   %s" % _short(r["bot_text"], 96))
            else:
                print("      тексты не пишутся (политика «%s»), длины: %d / %d"
                      % (r["text_policy"], r["user_len"], r["bot_len"]))
        print()
        print("справочно по подписке: $%.2f · настоящий расход по ключу: $%.2f"
              % (ref, real))
        print("Первая цифра — не списание. Это то, во сколько тот же объём")
        print("обошёлся бы по прейскуранту API, то есть мера отдачи подписки.")
        return 0

    rows = read_external(days=args.days, provider=args.provider,
                         limit=args.limit, order="desc" if args.last else "asc")
    if args.as_json:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0
    if not rows:
        print("Внешних вызовов за период нет. База: %s" % EXTERNAL_DB)
        print("Это не поломка: пока ни один навык не ходит наружу, леджер пуст.")
        return 0
    print("Внешние вызовы · %d · база %s" % (len(rows), EXTERNAL_DB))
    print()
    total = 0.0
    for r in rows:
        when = datetime.fromtimestamp(r["ts"]).strftime("%d.%m %H:%M")
        total += r["usd"] or 0
        print("%s  %-11s %-18s %8s  %g %s  %s"
              % (when, r["provider"], (r["service"] or r["model"] or "—")[:18],
                 "$%.4f" % (r["usd"] or 0), r["units"] or 0,
                 r["unit_kind"] or "", r["request_id"]))
    print()
    print("итого $%.2f — это настоящие деньги, сверяются по request_id" % total)
    return 0


def cmd_check(args):
    st = state()
    if args.as_json:
        json.dump(st, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        for name, title in (("turns", "разговоры"), ("external", "внешние вызовы")):
            s = st[name]
            print("%-16s %s · строк %d · последняя %s%s"
                  % (title, "есть" if s["exists"] else "НЕТ", s["rows"],
                     _ago(s["last_ts"]),
                     " · нет колонок: %s" % ", ".join(s["missing_columns"])
                     if s["missing_columns"] else ""))
        if st["shrunk"]:
            print("🔴 база усохла: %s" % "; ".join(st["shrunk"]))
        print("тексты: политика «%s»" % st["text_policy"])
    if args.save:
        save_watermark(st)
    return 1 if (st["shrunk"] or st["turns"]["missing_columns"]) else 0


def main():
    ap = argparse.ArgumentParser(description="Учёт разговоров и внешних трат")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("init", help="завести обе базы")

    t = sub.add_parser("turn", help="записать один ход")
    for name in ("brand", "account-id", "bot-slug", "chat-id", "message-id",
                 "user-text", "bot-text", "model", "agent", "session-id",
                 "reasoning-mode", "tools-used", "cost-basis", "turn-source"):
        t.add_argument("--" + name, default="")
    t.add_argument("--agent-kind", default="companion", choices=AGENT_KINDS)
    t.add_argument("--paid-by", default="subscription", choices=PAID_BY)
    t.add_argument("--prompt-tokens", type=int, default=0)
    t.add_argument("--completion-tokens", type=int, default=0)
    t.add_argument("--cache-write-tokens", type=int, default=0)
    t.add_argument("--cache-read-tokens", type=int, default=0)
    t.add_argument("--reasoning-tokens", type=int, default=0)
    t.add_argument("--latency-ms", type=int, default=0)
    t.add_argument("--tool-calls", type=int, default=0)
    t.add_argument("--temperature", type=float)
    t.add_argument("--max-tokens", type=int)
    t.add_argument("--usd-cost", type=float)
    t.add_argument("--idempotency-key")
    t.add_argument("--meta", help="JSON")

    e = sub.add_parser("external", help="записать внешний оплаченный вызов")
    e.add_argument("--provider", required=True)
    e.add_argument("--request-id", required=True)
    e.add_argument("--service", default="")
    e.add_argument("--model", default="")
    e.add_argument("--agent", default="")
    e.add_argument("--agent-kind", default="companion", choices=AGENT_KINDS)
    e.add_argument("--usd", type=float, default=0.0)
    e.add_argument("--units", type=float, default=0)
    e.add_argument("--unit-kind", default="")
    e.add_argument("--meta", help="JSON")

    s = sub.add_parser("show", help="прочитать записанное")
    s.add_argument("what", choices=("turns", "external"))
    s.add_argument("--days", type=int, default=1)
    s.add_argument("--agent")
    s.add_argument("--chat")
    s.add_argument("--provider")
    s.add_argument("--limit", type=int)
    s.add_argument("--last", action="store_true", help="новые сверху")
    s.add_argument("--json", action="store_true", dest="as_json")

    c = sub.add_parser("check", help="состояние баз (для doctor.py)")
    c.add_argument("--json", action="store_true", dest="as_json")
    c.add_argument("--save", action="store_true",
                   help="запомнить счётчики как эталон")

    args = ap.parse_args()
    if args.cmd in (None, "init"):
        a, b = init()
        print("разговоры:      %s" % a)
        print("внешние траты:  %s" % b)
        print("тексты: политика «%s» (MILA_RECORD_TEXT)" % text_policy())
        return 0
    if args.cmd == "turn":
        meta = json.loads(args.meta) if args.meta else None
        rid = record_turn(
            brand=args.brand, account_id=args.account_id, bot_slug=args.bot_slug,
            chat_id=args.chat_id, message_id=args.message_id,
            user_text=args.user_text, bot_text=args.bot_text, model=args.model,
            prompt_tokens=args.prompt_tokens,
            completion_tokens=args.completion_tokens,
            latency_ms=args.latency_ms, idempotency_key=args.idempotency_key,
            agent=args.agent, agent_kind=args.agent_kind,
            session_id=args.session_id, turn_source=args.turn_source,
            temperature=args.temperature, max_tokens=args.max_tokens,
            reasoning_mode=args.reasoning_mode,
            reasoning_tokens=args.reasoning_tokens,
            tool_calls=args.tool_calls, tools_used=args.tools_used,
            cache_write_tokens=args.cache_write_tokens,
            cache_read_tokens=args.cache_read_tokens,
            usd_cost=args.usd_cost, cost_basis=args.cost_basis,
            paid_by=args.paid_by, meta=meta)
        print("записан ход id=%s" % rid if rid else "уже записан, пропущено")
        return 0
    if args.cmd == "external":
        meta = json.loads(args.meta) if args.meta else None
        rid = record_external(args.provider, args.service, args.usd,
                              request_id=args.request_id, model=args.model,
                              units=args.units, unit_kind=args.unit_kind,
                              agent=args.agent, agent_kind=args.agent_kind,
                              meta=meta)
        print("записан вызов id=%s" % rid if rid
              else "уже записан (provider+request_id), пропущено")
        return 0
    if args.cmd == "show":
        return cmd_show(args)
    if args.cmd == "check":
        return cmd_check(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
