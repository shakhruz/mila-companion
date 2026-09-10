#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборщик ходов: разговор из транскрипта Claude Code в таблицу turns.

usage_collect.py отвечает на вопрос «сколько стоил день». Этот — на вопрос
«что вообще происходило»: один ход = один обмен, сообщение человека и ответ
агента, со всеми токенами, кэшем, длительностью, инструментами и ценой. Без
такой таблицы разбор любой жалобы начинается с «покажи, что она ему написала»,
и заканчивается чтением стомегабайтного jsonl глазами.

Как режется на ходы. У каждой строки транскрипта, пришедшей от человека, есть
promptId — он один на весь ход, включая все ответы модели и все возвраты
инструментов между ними. Смена promptId и есть граница хода. Резать по «строке
от пользователя» нельзя: возврат инструмента и вставки оболочки приходят тем же
типом user, и ход разваливался бы на два десятка кусков.

Разбор usage взят из usage_collect.py (usage_fields, response_key) — тем же
кодом, а не переписанным заново. Там же лежит и таблица цен. Один ответ модели
занимает в транскрипте несколько строк с повторяющимся usage; дедуп по
response_key делает и то и другое одинаково, иначе два инструмента давали бы
две разные правды про один и тот же день.

Чего в транскрипте НЕТ: температуры и потолка токенов. Claude Code их не
записывает, поэтому temperature и max_tokens у собранных ходов пусты — это
честный пробел, а не ноль. Колонки существуют для директоров, чей движок эти
настройки знает, и для навыков, которые зовут модель сами. Режим рассуждения
записан (поле effort) и попадает в reasoning_mode.

🔴 Про деньги: paid_by у сессии по подписке — subscription, и это значит, что
usd_cost СПРАВОЧНАЯ величина. Никто эти доллары не списывал; цифра показывает,
во сколько тот же объём обошёлся бы по прейскуранту API. Настоящий расход
живёт в другой базе — external-spend.db.

Тексты подчиняются выключателю MILA_RECORD_TEXT (full | length | none),
описанному в records.py и в docs/uchet.md.

  turns_collect.py                     # ходы за сегодня во всех проектах
  turns_collect.py --days 7            # за неделю
  turns_collect.py --project -Users-milagpt
  turns_collect.py --session <id>
  turns_collect.py --dry-run --show 5  # посмотреть, ничего не записывая
"""
import argparse
import errno
import fcntl
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import records                                    # noqa: E402
import usage_collect as uc                        # noqa: E402

PROJECTS = uc.PROJECTS
LOCK = os.path.join(records.RECORDS_DIR, "turns-collect.lock")
STAMP = os.path.join(records.RECORDS_DIR, "turns-collect-last.json")

# Тег канала, которым плагин Telegram подписывает входящее сообщение. Из него
# берутся настоящие chat_id и message_id — те же, по которым ход найдут в
# таблице директора.
CHANNEL_TAG = re.compile(
    r'<channel\s+[^>]*?source="(?P<source>[^"]*)"[^>]*?>', re.S)
TAG_ATTR = re.compile(r'(\w+)="([^"]*)"')

MAX_TEXT = int(os.environ.get("MILA_RECORD_TEXT_MAX", "100000"))


def acquire_lock(path=None):
    """Замок на время сбора. None означает «уже идёт, уходим».

    Прогон по всем транскриптам занимает секунды, но на большой машине —
    десятки, и часовой таймер способен догнать предыдущий. Две копии, читающие
    одни файлы и пишущие в одну базу, не портят данные (ключ повтора держит),
    но удваивают работу и путают отметку последнего сбора.

    Замок — flock на отдельном файле рядом с базой, а не проверка «есть ли
    файл»: файл от убитого процесса остаётся лежать и блокирует сбор навсегда,
    а flock ядро снимает само, когда процесс умирает.
    """
    path = path or LOCK
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, mode=0o700, exist_ok=True)
    fh = open(path, "a+", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        if e.errno not in (errno.EACCES, errno.EAGAIN):
            raise
        fh.close()
        return None
    fh.seek(0)
    fh.truncate()
    fh.write("%d %s\n" % (os.getpid(),
                          datetime.now().astimezone().isoformat(timespec="seconds")))
    fh.flush()
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return fh


LOG_FILE = os.environ.get("MILA_TURNS_LOG",
                          os.path.join(uc.CLAUDE_DIR, "turns-collect.log"))
LOG_CAP = 1_000_000       # больше этого — режем
LOG_KEEP = 500_000        # столько оставляем с конца


def trim_log(path=None, cap=LOG_CAP, keep=LOG_KEEP):
    """Журнал таймера: оставить хвост, начало отбросить.

    Растёт он медленно — строка только когда что-то записано, — и именно
    поэтому хвост легко оставить незакрытым. Незакрытый хвост закрывается
    самым неудобным образом: о нём узнают ночью и не от себя.

    Режем НА МЕСТЕ (r+b, truncate), а не через временный файл с заменой:
    служба уже держит этот файл открытым, и подмена inode отправила бы вывод
    текущего прогона в удалённый файл. Дескриптор открыт в режиме дозаписи,
    поэтому после укорачивания служба пишет в новый конец, а не в дыру.
    """
    path = path or LOG_FILE
    try:
        if os.path.getsize(path) <= cap:
            return False
        with open(path, "r+b") as f:
            f.seek(-keep, os.SEEK_END)
            tail = f.read()
            f.seek(0)
            f.write(("[журнал укорочен %s — начало отброшено, "
                     "оставлены последние %d КБ]\n"
                     % (datetime.now().astimezone().isoformat(timespec="seconds"),
                        keep // 1000)).encode("utf-8"))
            f.write(tail)
            f.truncate()
        return True
    except OSError:
        return False


def write_stamp(payload, path=None):
    """Отметка последнего сбора — по ней доктор видит, что таймер работает.

    «Таймер загружен» и «сбор произошёл» — разные утверждения: загруженный
    таймер, падающий на старте, выглядит здоровым в любом списке служб.
    """
    path = path or STAMP
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        pass


def clip(text):
    """Длинный текст режется с пометкой: молча обрезанный текст — это ложь."""
    if len(text) <= MAX_TEXT:
        return text
    return text[:MAX_TEXT] + "\n…[обрезано на %d знаках]" % MAX_TEXT


def blocks(msg):
    c = msg.get("content")
    if isinstance(c, list):
        return [b for b in c if isinstance(b, dict)]
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return []


def is_human_start(entry, msg):
    """Строка, которой человек (или входящее событие) начинает ход.

    Возвраты инструментов и вставки оболочки приходят тем же типом user —
    первые опознаются по блоку tool_result, вторые по isMeta.
    """
    if entry.get("type") != "user":
        return False
    if entry.get("isMeta"):
        return False
    bs = blocks(msg)
    if not bs:
        return False
    return all(b.get("type") != "tool_result" for b in bs)


def text_of(bs):
    return "\n\n".join(b.get("text") or "" for b in bs
                       if b.get("type") == "text" and (b.get("text") or "").strip())


def parse_channel(text):
    """chat_id, message_id, отправитель и источник из тега канала."""
    m = CHANNEL_TAG.search(text or "")
    if not m:
        return {}
    attrs = dict(TAG_ATTR.findall(m.group(0)))
    return {k: v for k, v in attrs.items() if v}


def turn_kind(text):
    """Кто начал ход. Уведомление системы и живой человек — разные вещи, и
    складывать их в один счётчик «разговоров» значит завышать его втрое."""
    t = (text or "").lstrip()
    if t.startswith("<channel "):
        return "channel"
    if t.startswith("<task-notification"):
        return "notification"
    if t.startswith("<command-name>") or t.startswith("<local-command"):
        return "command"
    if t.startswith("This session is being continued"):
        return "continuation"
    return "human"


class Turn:
    """Копилка одного хода: всё между двумя сообщениями человека."""

    def __init__(self, entry, msg, path):
        self.path = path
        self.prompt_id = entry.get("promptId") or ""
        self.session_id = entry.get("sessionId") or entry.get("session_id") or ""
        self.started = entry.get("timestamp") or ""
        self.ended = self.started
        self.cwd = entry.get("cwd") or ""
        self.sidechain = bool(entry.get("isSidechain"))
        bs = blocks(msg)
        self.user_text = text_of(bs)
        self.channel = parse_channel(self.user_text)
        self.kind = turn_kind(self.user_text)
        self.assistant_text = []
        self.sent_text = []          # то, что человек реально получил в чат
        self.by_model = defaultdict(uc.blank)
        self.effort = Counter()
        self.tools = []
        self.tool_calls = 0
        self.responses = 0
        self.seen = set()
        self.chat_ids = []
        self.message_ids = []
        self.skills = Counter()
        if self.channel.get("chat_id"):
            self.chat_ids.append(self.channel["chat_id"])
        if self.channel.get("message_id"):
            self.message_ids.append(self.channel["message_id"])

    # ── набор ──
    def add_assistant(self, entry, msg):
        self.ended = entry.get("timestamp") or self.ended
        u = msg.get("usage")
        model = msg.get("model") or "unknown"
        if isinstance(u, dict) and model != "<synthetic>":
            key = uc.response_key(entry, msg)
            if key is None or key not in self.seen:
                if key is not None:
                    self.seen.add(key)
                uc.add(self.by_model[model], uc.usage_fields(u))
                self.responses += 1
                if entry.get("effort"):
                    self.effort[entry["effort"]] += 1
        if entry.get("attributionSkill"):
            self.skills[entry["attributionSkill"]] += 1
        for b in blocks(msg):
            if b.get("type") == "text" and (b.get("text") or "").strip():
                self.assistant_text.append(b["text"])
            elif b.get("type") == "tool_use":
                self.tool_calls += 1
                name = b.get("name") or "?"
                if name not in self.tools:
                    self.tools.append(name)
                self._from_tool(name, b.get("input"))

    def add_user(self, entry, msg):
        self.ended = entry.get("timestamp") or self.ended

    def _from_tool(self, name, inp):
        """Из вызова инструмента берём две вещи: адресата и сказанное вслух.

        Ответ, ушедший в чат, — это и есть то, что человек прочитал. Текстовые
        блоки модели рядом с ним — размышление вслух в терминале, которого
        собеседник не видел. Путать их значит показывать в истории разговора
        не тот текст, что получил клиент.
        """
        if not isinstance(inp, dict):
            return
        cid = inp.get("chat_id")
        if cid is not None and str(cid) not in self.chat_ids:
            self.chat_ids.append(str(cid))
        low = name.lower()
        if ("reply" in low or "send" in low or "say" in low) and inp.get("text"):
            if cid is not None or "telegram" in low or "reply" in low:
                self.sent_text.append(str(inp["text"]))

    # ── вывод ──
    def dominant_model(self):
        if not self.by_model:
            return ""
        return max(self.by_model.items(),
                   key=lambda kv: (kv[1]["out"], kv[1]["turns"]))[0]

    def totals(self):
        t = uc.blank()
        for rec in self.by_model.values():
            uc.add(t, rec)
        return t

    def cost(self):
        """Каждая модель по своей цене. Незнакомая — прочерк, а не чужой тариф."""
        total, basis, unknown = 0.0, "", False
        for model, rec in self.by_model.items():
            usd, b = records.price_turn(model, rec["in"], rec["out"],
                                        rec["cache_write"], rec["cache_read"])
            if usd is None:
                unknown = True
            else:
                total += usd
                basis = basis or b
        if unknown and not basis:
            return None, ""
        return total, basis + (" · есть модель без цены" if unknown else "")

    def latency_ms(self):
        a, b = ts_of(self.started), ts_of(self.ended)
        if a is None or b is None:
            return 0
        return max(0, int((b - a) * 1000))

    def bot_text(self):
        if self.sent_text:
            return "\n\n".join(self.sent_text)
        return "\n\n".join(self.assistant_text)


def ts_of(stamp):
    if not stamp:
        return None
    try:
        dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def iter_turns(path):
    """Ходы одного файла транскрипта, по порядку. Файл читается потоком."""
    cur = None
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    with f:
        for line in f:
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue          # последняя строка живого файла бывает не дописана
            t = d.get("type")
            if t not in ("user", "assistant"):
                continue
            msg = d.get("message")
            if not isinstance(msg, dict):
                continue
            if t == "user":
                pid = d.get("promptId")
                starts = is_human_start(d, msg) and (
                    cur is None or pid != cur.prompt_id or not pid)
                if starts:
                    if cur is not None:
                        yield cur
                    cur = Turn(d, msg, path)
                elif cur is not None:
                    cur.add_user(d, msg)
            elif cur is not None:
                cur.add_assistant(d, msg)
    if cur is not None:
        yield cur


def idem_key(turn, path, used):
    """Ключ повтора: пара «сессия + promptId», а для субагента ещё и файл.

    Транскрипт субагента наследует sessionId И promptId родителя. Ключ из
    одной этой пары складывал в одну строку ход старшей и работу всех её
    агентов: в живой проверке 24 хода из 66 были молча отброшены как дубли —
    вместе со своей ценой, а это самая дорогая часть дня. Дубль внутри учёта
    страшнее пропуска ровно тем, что выглядит как порядок.

    Счётчик на конце нужен для файла субагента, продолженного второй задачей.
    Порядок обхода детерминирован, поэтому повторный прогон даёт те же ключи.
    """
    base = "cc:%s:%s" % (turn.session_id or os.path.basename(path),
                         turn.prompt_id or turn.started)
    if "/subagents/" in path or turn.sidechain:
        base += ":" + os.path.splitext(os.path.basename(path))[0]
    used[base] += 1
    return base if used[base] == 1 else "%s#%d" % (base, used[base])


def transcripts(project=None, session=None):
    if session:
        for root, _dirs, names in os.walk(PROJECTS):
            for n in names:
                if n == session + ".jsonl" or n == session:
                    yield os.path.join(root, n)
        return
    base = PROJECTS
    if project:
        base = project if os.path.isdir(project) else os.path.join(PROJECTS, project)
    for root, _dirs, names in os.walk(base):
        for n in sorted(names):
            if n.endswith(".jsonl"):
                yield os.path.join(root, n)


def human(n):
    return uc.human(n)


def main():
    ap = argparse.ArgumentParser(
        description="Собрать ходы из транскриптов Claude Code в таблицу turns")
    ap.add_argument("--days", type=int, default=1,
                    help="за сколько последних дней (1 = сегодня)")
    ap.add_argument("--project", help="каталог проекта в ~/.claude/projects")
    ap.add_argument("--session", help="id сессии (имя файла без .jsonl)")
    ap.add_argument("--agent", default=os.environ.get("MILA_AGENT", "companion"))
    ap.add_argument("--agent-kind", default="companion",
                    choices=records.AGENT_KINDS)
    ap.add_argument("--brand", default=os.environ.get("MILA_BRAND", ""))
    ap.add_argument("--paid-by", default=os.environ.get("MILA_PAID_BY", "subscription"),
                    choices=records.PAID_BY)
    ap.add_argument("--db", help="другой файл базы (по умолчанию %s)" % records.TURNS_DB)
    ap.add_argument("--dry-run", action="store_true", help="ничего не записывать")
    ap.add_argument("--show", type=int, default=0, help="показать N собранных ходов")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--quiet", action="store_true",
                    help="для таймера: молчать, когда добавлять нечего")
    ap.add_argument("--no-lock", action="store_true",
                    help="не брать замок (для отладки)")
    args = ap.parse_args()

    if not os.path.isdir(PROJECTS):
        print("нет каталога проектов: %s" % PROJECTS, file=sys.stderr)
        return 1

    lock = None
    if not args.no_lock and not args.dry_run:
        lock = acquire_lock()
        if lock is None:
            # Часовой таймер догнал предыдущий сбор. Человеку за терминалом
            # это надо сказать, а в журнал службы — нет: строка раз в час о
            # том, что всё в порядке, делает журнал нечитаемым.
            if sys.stderr.isatty():
                print("сбор уже идёт — выхожу", file=sys.stderr)
            return 0

        trim_log()

    started_at = time.time()

    day0 = (datetime.now().astimezone()
            - timedelta(days=args.days - 1)).strftime("%Y-%m-%d")
    con = None if args.dry_run else records.open_turns(args.db)
    written = skipped = seen = 0
    used = Counter()
    shown = []
    per_day = Counter()
    money = 0.0

    try:
        for path in transcripts(args.project, args.session):
            for turn in iter_turns(path):
                day = uc.local_day(turn.started)
                if not day or day < day0:
                    continue
                if not turn.responses:
                    continue          # ход без единого ответа модели — не ход
                started = ts_of(turn.started)
                if started is None:
                    continue          # без времени ход некуда положить на ось
                seen += 1
                per_day[day] += 1
                tot = turn.totals()
                usd, basis = turn.cost()
                money += usd or 0
                ch = turn.channel
                key = idem_key(turn, path, used)
                meta = {
                    "transcript": path,
                    "kind": turn.kind,
                    "responses": turn.responses,
                    "models": {m: r["turns"] for m, r in turn.by_model.items()},
                    "cwd": turn.cwd,
                }
                if turn.skills:
                    meta["skills"] = dict(turn.skills)
                if ch:
                    meta["channel"] = ch
                if turn.sidechain or "/subagents/" in path:
                    meta["subagent"] = os.path.basename(path)
                row = dict(
                    ts=started,
                    brand=args.brand,
                    account_id=ch.get("user_id") or "",
                    bot_slug=ch.get("source") or "",
                    chat_id=turn.chat_ids[0] if turn.chat_ids else "",
                    message_id=turn.message_ids[0] if turn.message_ids else "",
                    user_text=clip(turn.user_text),
                    bot_text=clip(turn.bot_text()),
                    model=turn.dominant_model(),
                    prompt_tokens=tot["in"],
                    completion_tokens=tot["out"],
                    latency_ms=turn.latency_ms(),
                    idempotency_key=key,
                    agent=args.agent,
                    agent_kind=args.agent_kind,
                    session_id=turn.session_id,
                    turn_source=("claude-code/subagent"
                                 if "/subagents/" in path else "claude-code"),
                    reasoning_mode=(turn.effort.most_common(1)[0][0]
                                    if turn.effort else ""),
                    reasoning_tokens=tot["thinking"],
                    tool_calls=turn.tool_calls,
                    tools_used=",".join(turn.tools[:40]),
                    cache_write_tokens=tot["cache_write"],
                    cache_read_tokens=tot["cache_read"],
                    usd_cost=usd,
                    cost_basis=basis,
                    paid_by=args.paid_by,
                    meta=meta,
                )
                if len(shown) < args.show:
                    shown.append((row, turn))
                if args.dry_run:
                    continue
                # temperature и max_tokens не передаём: Claude Code их не пишет,
                # и ноль здесь читался бы как «модели запретили говорить».
                if records.record_turn(con, price=False, **row):
                    written += 1
                else:
                    skipped += 1
    finally:
        if con is not None:
            con.close()

    if not args.dry_run:
        write_stamp({
            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "finished_ts": time.time(),
            "took_sec": round(time.time() - started_at, 1),
            "since": day0, "seen": seen, "written": written, "skipped": skipped,
            "agent": args.agent,
        })
    if lock is not None:
        lock.close()

    if args.quiet and not args.as_json:
        # Молчим ровно тогда, когда сказать нечего: сбор прошёл, нового нет.
        if not written:
            return 0
        print("Ходы с %s: записано %d (найдено %d)" % (day0, written, seen))
        return 0

    if args.as_json:
        json.dump({"since": day0, "seen": seen, "written": written,
                   "skipped": skipped, "by_day": dict(per_day),
                   "reference_usd": round(money, 4),
                   "db": args.db or records.TURNS_DB,
                   "text_policy": records.text_policy()},
                  sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0

    for row, turn in shown:
        when = datetime.fromtimestamp(row["ts"]).strftime("%d.%m %H:%M:%S")
        print("── %s · %s · %s · %s"
              % (when, row["model"] or "—", row["meta"]["kind"],
                 "$%.4f" % row["usd_cost"] if row["usd_cost"] is not None else "$?"))
        print("   вход %s · выход %s · размышление %s · кэш: запись %s чтение %s"
              % (human(row["prompt_tokens"]), human(row["completion_tokens"]),
                 human(row["reasoning_tokens"]), human(row["cache_write_tokens"]),
                 human(row["cache_read_tokens"])))
        print("   %d ответов модели · %d вызовов инструментов · %.1f с · режим %s"
              % (row["meta"]["responses"], row["tool_calls"],
                 row["latency_ms"] / 1000.0, row["reasoning_mode"] or "—"))
        if row["tools_used"]:
            print("   инструменты: %s" % row["tools_used"][:110])
        print("   человек: %s" % (row["user_text"] or "").replace("\n", " ")[:110])
        print("   агент:   %s" % (row["bot_text"] or "").replace("\n", " ")[:110])
        print()

    print("Ходы с %s: найдено %d%s"
          % (day0, seen, "" if args.dry_run else
             " · записано %d · уже было %d" % (written, skipped)))
    for day in sorted(per_day):
        print("   %s  %d" % (day, per_day[day]))
    if money:
        print("справочно по прейскуранту API: $%.2f — по подписке это не списание,"
              % money)
        print("а мера того, что подписка отдала.")
    if not args.dry_run:
        print("база: %s · тексты: политика «%s»"
              % (args.db or records.TURNS_DB, records.text_policy()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
