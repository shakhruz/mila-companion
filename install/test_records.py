#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверки учёта. Временные базы, никакой сети, ничего в ~/.claude.

  python3 install/test_records.py
  python3 -m unittest discover -s install -p 'test_*.py'

Здесь проверяется ровно то, что ломается молча: дубли, миграция чужой базы,
выключатель текстов и разбор транскрипта. Ошибка в любом из четырёх мест не
падает — она просто даёт неправильную цифру, и её замечают через месяц.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mila-records-")
        os.environ["MILA_RECORDS_DIR"] = self.dir
        os.environ.pop("MILA_RECORD_TEXT", None)
        os.environ.pop("MILA_AGENT", None)
        # Модуль читает пути на импорте — перезагружаем под временный каталог.
        import importlib
        import records
        importlib.reload(records)
        self.records = records

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        os.environ.pop("MILA_RECORDS_DIR", None)
        os.environ.pop("MILA_RECORD_TEXT", None)


class TestSchema(Base):
    def test_init_creates_both(self):
        a, b = self.records.init()
        self.assertTrue(os.path.exists(a))
        self.assertTrue(os.path.exists(b))
        self.assertEqual(os.stat(a).st_mode & 0o777, 0o600,
                         "в базе переписка — права должны быть 600")

    def test_init_is_idempotent(self):
        self.records.init()
        self.records.record_turn(model="claude-opus-5", idempotency_key="k1")
        self.records.init()
        self.assertEqual(len(self.records.read_turns()), 1,
                         "повторный init не должен ничего терять")

    def test_directors_columns_kept_verbatim(self):
        """Первые четырнадцать колонок обязаны совпадать со схемой директоров.

        Иначе общая аналитика по флоту и Компаньону перестаёт быть общей —
        а ради неё всё и затевалось.
        """
        con = self.records.open_turns()
        cols = [r[1] for r in con.execute("PRAGMA table_info(turns)")]
        con.close()
        self.assertEqual(cols[:14], [
            "id", "ts", "brand", "account_id", "bot_slug", "chat_id",
            "message_id", "user_text", "bot_text", "model", "prompt_tokens",
            "completion_tokens", "latency_ms", "idempotency_key"])

    def test_migrates_a_directors_database(self):
        """Базу директора можно открыть этим модулем, не потеряв строк."""
        import sqlite3
        path = os.path.join(self.dir, "director.db")
        con = sqlite3.connect(path)
        con.execute(self.records.TURNS_BASE)
        con.execute("INSERT INTO turns (ts, bot_slug, chat_id, message_id, "
                    "user_text, bot_text, model, prompt_tokens, "
                    "completion_tokens, idempotency_key) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (1783753740.4, "demo-director", "77001122", "127",
                     "привет", "здравствуйте", "deepseek/deepseek-chat",
                     24348, 470, "demo-director:77001122:127"))
        con.commit()
        con.close()

        con = self.records.open_turns(path)
        cols = {r[1] for r in con.execute("PRAGMA table_info(turns)")}
        for name, _decl in self.records.TURNS_EXTRA:
            self.assertIn(name, cols)
        rows = self.records.read_turns(con)
        con.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user_text"], "привет")
        self.assertEqual(rows[0]["bot_slug"], "demo-director")


class TestTurns(Base):
    def test_write_and_read_back(self):
        rid = self.records.record_turn(
            ts=1000.0, chat_id="-100500", message_id="7",
            user_text="сколько стоит", bot_text="590 000 сум",
            model="claude-opus-5", prompt_tokens=1200, completion_tokens=80,
            cache_write_tokens=400, cache_read_tokens=90000,
            latency_ms=4200, reasoning_mode="high", reasoning_tokens=55,
            tool_calls=3, tools_used="Bash,Read,reply",
            agent="mila", agent_kind="companion",
            idempotency_key="mila:-100500:7", meta={"kind": "human"})
        self.assertIsInstance(rid, int)
        rows = self.records.read_turns(since=0)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["user_text"], "сколько стоит")
        self.assertEqual(r["bot_text"], "590 000 сум")
        self.assertEqual(r["cache_read_tokens"], 90000)
        self.assertEqual(r["reasoning_mode"], "high")
        self.assertEqual(r["tools_used"], "Bash,Read,reply")
        self.assertEqual(json.loads(r["meta_json"])["kind"], "human")

    def test_duplicate_key_does_not_double_count(self):
        for _ in range(3):
            self.records.record_turn(idempotency_key="one", model="claude-opus-5",
                                     completion_tokens=10)
        self.assertEqual(len(self.records.read_turns(since=0)), 1,
                         "сборщик, запущенный дважды, не должен удваивать день")

    def test_null_key_is_not_a_duplicate(self):
        """NULL в SQLite не равен NULL — ходы без ключа обязаны записываться все."""
        self.records.record_turn(model="claude-opus-5")
        self.records.record_turn(model="claude-opus-5")
        self.assertEqual(len(self.records.read_turns(since=0)), 2)

    def test_subscription_cost_is_reference_only(self):
        self.records.record_turn(model="claude-opus-5", prompt_tokens=1_000_000,
                                 completion_tokens=0, idempotency_key="p")
        r = self.records.read_turns(since=0)[0]
        self.assertEqual(r["paid_by"], "subscription",
                         "по умолчанию цена справочная, а не списание")
        self.assertAlmostEqual(r["usd_cost"], 15.0, places=4)
        self.assertTrue(r["cost_basis"], "по какой таблице считали — обязано быть")

    def test_unknown_model_has_no_price(self):
        self.records.record_turn(model="совсем-новая-модель",
                                 prompt_tokens=1_000_000, idempotency_key="u")
        r = self.records.read_turns(since=0)[0]
        self.assertIsNone(r["usd_cost"],
                          "незнакомая модель не должна брать чужой тариф")

    def test_filters(self):
        self.records.record_turn(ts=100.0, agent="a", chat_id="1",
                                 idempotency_key="1")
        self.records.record_turn(ts=200.0, agent="b", chat_id="2",
                                 idempotency_key="2")
        self.assertEqual(len(self.records.read_turns(since=0, agent="a")), 1)
        self.assertEqual(len(self.records.read_turns(since=0, chat_id="2")), 1)
        self.assertEqual(len(self.records.read_turns(since=150)), 1)
        self.assertEqual(len(self.records.read_turns(since=0, limit=1)), 1)


class TestTextPolicy(Base):
    def _write(self, policy):
        os.environ["MILA_RECORD_TEXT"] = policy
        self.records.record_turn(user_text="паспорт AA1234567",
                                 bot_text="принято", idempotency_key=policy)
        return [r for r in self.records.read_turns(since=0)
                if r["idempotency_key"] == policy][0]

    def test_full_writes_texts(self):
        r = self._write("full")
        self.assertEqual(r["user_text"], "паспорт AA1234567")
        self.assertEqual(r["text_policy"], "full")
        self.assertEqual(r["user_len"], len("паспорт AA1234567"))

    def test_length_keeps_only_the_size(self):
        r = self._write("length")
        self.assertEqual(r["user_text"], "")
        self.assertEqual(r["bot_text"], "")
        self.assertEqual(r["user_len"], len("паспорт AA1234567"))
        self.assertEqual(r["text_policy"], "length",
                         "пустой текст должен быть отличим от потерянных данных")

    def test_none_keeps_nothing(self):
        r = self._write("none")
        self.assertEqual(r["user_text"], "")
        self.assertEqual(r["user_len"], 0)
        self.assertEqual(r["bot_len"], 0)

    def test_unknown_policy_falls_back_to_full(self):
        os.environ["MILA_RECORD_TEXT"] = "полностью"
        self.assertEqual(self.records.text_policy(), "full")

    def test_explicit_policy_beats_environment(self):
        os.environ["MILA_RECORD_TEXT"] = "none"
        self.records.record_turn(user_text="важное", idempotency_key="x",
                                 policy="full")
        self.assertEqual(self.records.read_turns(since=0)[0]["user_text"], "важное")


class TestExternal(Base):
    def test_write_and_read_back(self):
        rid = self.records.record_external(
            "fal", "lyria-3", 0.08, request_id="fal-7c1a",
            model="lyria-3-pro", units=2, unit_kind="треки",
            agent="mila", meta={"chat": "-100500"})
        self.assertIsInstance(rid, int)
        rows = self.records.read_external(since=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provider"], "fal")
        self.assertEqual(rows[0]["request_id"], "fal-7c1a")
        self.assertEqual(rows[0]["unit_kind"], "треки")
        self.assertAlmostEqual(rows[0]["usd"], 0.08)

    def test_request_id_is_required(self):
        with self.assertRaises(ValueError):
            self.records.record_external("openrouter", "image", 0.24,
                                         request_id="")
        with self.assertRaises(ValueError):
            self.records.record_external("openrouter", "image", 0.24,
                                         request_id="   ")

    def test_provider_is_required(self):
        with self.assertRaises(ValueError):
            self.records.record_external("", "image", 0.1, request_id="r1")

    def test_same_request_is_not_billed_twice(self):
        self.records.record_external("fal", "x", 1.0, request_id="r1")
        self.assertIsNone(self.records.record_external("fal", "x", 1.0,
                                                       request_id="r1"))
        self.assertEqual(len(self.records.read_external(since=0)), 1)

    def test_same_id_from_another_provider_is_a_different_call(self):
        self.records.record_external("fal", "x", 1.0, request_id="r1")
        self.records.record_external("openrouter", "y", 2.0, request_id="r1")
        self.assertEqual(len(self.records.read_external(since=0)), 2)

    def test_filters_and_sum(self):
        self.records.record_external("fal", "a", 0.5, request_id="1", ts=100.0)
        self.records.record_external("openrouter", "b", 1.5, request_id="2",
                                     ts=200.0)
        rows = self.records.read_external(since=0, provider="openrouter")
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(sum(r["usd"] for r in
                                   self.records.read_external(since=0)), 2.0)


class TestState(Base):
    def test_state_reports_missing_databases(self):
        st = self.records.state()
        self.assertFalse(st["turns"]["exists"])
        self.assertFalse(st["external"]["exists"])

    def test_shrink_is_noticed(self):
        self.records.record_turn(idempotency_key="a")
        self.records.record_turn(idempotency_key="b")
        self.records.save_watermark()
        con = self.records.open_turns()
        con.execute("DELETE FROM turns WHERE idempotency_key = 'b'")
        con.commit()
        con.close()
        st = self.records.state()
        self.assertTrue(st["shrunk"],
                        "усохшая база выглядит здоровой — это ловится только эталоном")

    def test_growth_is_not_a_complaint(self):
        self.records.record_turn(idempotency_key="a")
        self.records.save_watermark()
        self.records.record_turn(idempotency_key="b")
        self.assertFalse(self.records.state()["shrunk"])


# ── разбор транскрипта ────────────────────────────────────────────────────

def _asst(ts, mid, req, model, blocks, usage, effort="high"):
    return {"type": "assistant", "timestamp": ts, "requestId": req,
            "effort": effort, "sessionId": "sess-1",
            "message": {"id": mid, "model": model, "content": blocks,
                        "usage": usage}}


def _usage(i=0, o=0, cw=0, cr=0, think=0, iterations=None):
    u = {"input_tokens": i, "output_tokens": o,
         "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr,
         "output_tokens_details": {"thinking_tokens": think}}
    if iterations is not None:
        u["iterations"] = iterations
    return u


class TestTurnsCollect(Base):
    """Транскрипт собирается из словарей — ни одного настоящего файла сессии."""

    def setUp(self):
        super().setUp()
        import importlib
        import turns_collect
        importlib.reload(turns_collect)
        self.tc = turns_collect
        self.path = os.path.join(self.dir, "sess-1.jsonl")

    def write(self, rows):
        with open(self.path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return list(self.tc.iter_turns(self.path))

    def test_one_exchange_is_one_turn(self):
        turns = self.write([
            {"type": "user", "timestamp": "2026-09-10T05:00:00.000Z",
             "promptId": "p1", "sessionId": "sess-1",
             "message": {"role": "user", "content": "привет"}},
            _asst("2026-09-10T05:00:04.000Z", "m1", "r1", "claude-opus-5",
                  [{"type": "text", "text": "здравствуйте"}],
                  _usage(i=10, o=5, cr=1000, think=2)),
        ])
        self.assertEqual(len(turns), 1)
        t = turns[0]
        self.assertEqual(t.user_text, "привет")
        self.assertEqual(t.bot_text(), "здравствуйте")
        self.assertEqual(t.latency_ms(), 4000)
        self.assertEqual(t.totals()["cache_read"], 1000)
        self.assertEqual(t.totals()["thinking"], 2)

    def test_one_response_in_many_blocks_counts_once(self):
        """Главная ловушка формата: usage повторяется в каждой строке ответа."""
        u = _usage(i=10, o=500, cr=9981)
        turns = self.write([
            {"type": "user", "timestamp": "2026-09-10T05:00:00.000Z",
             "promptId": "p1", "message": {"role": "user", "content": "logs"}},
            _asst("2026-09-10T05:00:01.000Z", "m1", "r1", "claude-opus-5",
                  [{"type": "thinking"}], u),
            _asst("2026-09-10T05:00:01.100Z", "m1", "r1", "claude-opus-5",
                  [{"type": "text", "text": "смотрю"}], u),
            _asst("2026-09-10T05:00:01.200Z", "m1", "r1", "claude-opus-5",
                  [{"type": "tool_use", "name": "Bash", "input": {}}], u),
        ])
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].responses, 1)
        self.assertEqual(turns[0].totals()["out"], 500,
                         "три строки одного ответа — это один ответ")
        self.assertEqual(turns[0].tool_calls, 1)
        self.assertEqual(turns[0].tools, ["Bash"])

    def test_tool_results_do_not_start_a_new_turn(self):
        turns = self.write([
            {"type": "user", "timestamp": "2026-09-10T05:00:00.000Z",
             "promptId": "p1", "message": {"role": "user", "content": "сделай"}},
            _asst("2026-09-10T05:00:01.000Z", "m1", "r1", "claude-opus-5",
                  [{"type": "tool_use", "name": "Bash", "input": {}}],
                  _usage(o=10)),
            {"type": "user", "timestamp": "2026-09-10T05:00:02.000Z",
             "promptId": "p1",
             "message": {"role": "user",
                         "content": [{"type": "tool_result", "content": "ok"}]}},
            {"type": "user", "timestamp": "2026-09-10T05:00:02.100Z",
             "promptId": "p1", "isMeta": True,
             "message": {"role": "user",
                         "content": [{"type": "text", "text": "напоминание"}]}},
            _asst("2026-09-10T05:00:03.000Z", "m2", "r2", "claude-opus-5",
                  [{"type": "text", "text": "готово"}], _usage(o=20)),
            {"type": "user", "timestamp": "2026-09-10T05:00:10.000Z",
             "promptId": "p2", "message": {"role": "user", "content": "спасибо"}},
            _asst("2026-09-10T05:00:11.000Z", "m3", "r3", "claude-opus-5",
                  [{"type": "text", "text": "пожалуйста"}], _usage(o=3)),
        ])
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0].responses, 2)
        self.assertEqual(turns[0].totals()["out"], 30)
        self.assertEqual(turns[0].bot_text(), "готово")
        self.assertEqual(turns[1].user_text, "спасибо")

    def test_zero_usage_falls_back_to_iterations(self):
        turns = self.write([
            {"type": "user", "timestamp": "2026-09-10T05:00:00.000Z",
             "promptId": "p1", "message": {"role": "user", "content": "?"}},
            _asst("2026-09-10T05:00:01.000Z", "m1", "r1", "claude-opus-5",
                  [{"type": "text", "text": "!"}],
                  _usage(iterations=[{"input_tokens": 2, "output_tokens": 3241,
                                      "cache_read_input_tokens": 988663,
                                      "cache_creation_input_tokens": 4393}])),
        ])
        self.assertEqual(turns[0].totals()["out"], 3241)
        self.assertEqual(turns[0].totals()["cache_read"], 988663)

    def test_channel_tag_gives_chat_and_message(self):
        tag = ('<channel source="telegram" chat_id="-987654321" '
               'message_id="372" user="takhir" ts="2026-09-10T05:00:00Z">'
               'соберите тур</channel>')
        turns = self.write([
            {"type": "user", "timestamp": "2026-09-10T05:00:00.000Z",
             "promptId": "p1", "message": {"role": "user", "content": tag}},
            _asst("2026-09-10T05:00:02.000Z", "m1", "r1", "claude-opus-5",
                  [{"type": "tool_use", "name": "mcp__telegram__reply",
                    "input": {"chat_id": -987654321, "text": "беру"}}],
                  _usage(o=9)),
        ])
        t = turns[0]
        self.assertEqual(t.kind, "channel")
        self.assertEqual(t.chat_ids[0], "-987654321")
        self.assertEqual(t.message_ids[0], "372")
        self.assertEqual(t.channel["user"], "takhir")
        self.assertEqual(t.bot_text(), "беру",
                         "в историю идёт то, что человек получил, "
                         "а не размышление в терминале")

    def test_costs_are_summed_per_model(self):
        turns = self.write([
            {"type": "user", "timestamp": "2026-09-10T05:00:00.000Z",
             "promptId": "p1", "message": {"role": "user", "content": "?"}},
            _asst("2026-09-10T05:00:01.000Z", "m1", "r1", "claude-opus-5",
                  [{"type": "text", "text": "a"}], _usage(i=1_000_000)),
            _asst("2026-09-10T05:00:02.000Z", "m2", "r2", "claude-haiku-4-5",
                  [{"type": "text", "text": "b"}], _usage(i=1_000_000)),
        ])
        usd, _basis = turns[0].cost()
        self.assertAlmostEqual(usd, 15.0 + 0.8, places=4)

    def test_subagent_turn_gets_its_own_key(self):
        """Транскрипт субагента наследует sessionId и promptId родителя.

        Ключ без имени файла складывал ход старшей и работу её агентов в одну
        строку: в живой проверке 24 хода из 66 молча исчезли вместе с ценой.
        """
        from collections import Counter
        rows = [
            {"type": "user", "timestamp": "2026-09-10T05:00:00.000Z",
             "promptId": "p1", "sessionId": "s1",
             "message": {"role": "user", "content": "сделай"}},
            _asst("2026-09-10T05:00:01.000Z", "m1", "r1", "claude-opus-5",
                  [{"type": "text", "text": "ок"}], _usage(o=1)),
        ]
        turns = self.write(rows)
        used = Counter()
        main = self.tc.idem_key(turns[0], "/p/s1.jsonl", used)
        sub = self.tc.idem_key(turns[0], "/p/s1/subagents/agent-a1.jsonl", used)
        sub2 = self.tc.idem_key(turns[0], "/p/s1/subagents/agent-a2.jsonl", used)
        self.assertEqual(len({main, sub, sub2}), 3)
        self.assertIn("agent-a1", sub)
        # тот же файл со вторым ходом того же promptId — счётчик на конце
        again = self.tc.idem_key(turns[0], "/p/s1/subagents/agent-a1.jsonl", used)
        self.assertNotEqual(again, sub)

    def test_second_collector_does_not_start(self):
        """Часовой таймер способен догнать предыдущий сбор.

        Замок — flock, а не «есть ли файл»: файл от убитого процесса лежал бы
        вечно и остановил сбор навсегда, а flock ядро снимает само.
        """
        path = os.path.join(self.dir, "turns-collect.lock")
        first = self.tc.acquire_lock(path)
        self.assertIsNotNone(first)
        self.assertIsNone(self.tc.acquire_lock(path),
                          "второй сбор обязан уйти, а не работать параллельно")
        first.close()
        second = self.tc.acquire_lock(path)
        self.assertIsNotNone(second, "после закрытия замок обязан отпускать")
        second.close()

    def test_stamp_is_written_atomically(self):
        path = os.path.join(self.dir, "turns-collect-last.json")
        self.tc.write_stamp({"seen": 7, "written": 3}, path)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["seen"], 7)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_broken_line_is_skipped(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "user", "timestamp": "2026-09-10T05:00:00.000Z",
                "promptId": "p1",
                "message": {"role": "user", "content": "раз"}}) + "\n")
            f.write(json.dumps(_asst("2026-09-10T05:00:01.000Z", "m1", "r1",
                                     "claude-opus-5",
                                     [{"type": "text", "text": "два"}],
                                     _usage(o=1))) + "\n")
            f.write('{"type": "assistant", "message": {"id"')   # не дописана
        turns = list(self.tc.iter_turns(self.path))
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].bot_text(), "два")


if __name__ == "__main__":
    unittest.main(verbosity=2)
