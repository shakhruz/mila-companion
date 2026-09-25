#!/usr/bin/env python3
"""deck.py — колода флэшкарточек MILAGPT из deck.json: проверка, карточки PNG, печать, тренажёр, Anki, квизы.

    python3 deck.py check  deck.json                 # проверка до сборки (обязательна)
    python3 deck.py build  deck.json out/ [--lang ru] # карточки HTML, print.html, trainer.html, anki-*.txt, polls-*.json
    python3 deck.py render out/                       # PNG и PDF: локальный Chrome, иначе заявки в ~/work/render-queue
    python3 deck.py polls  out/polls-ru.json --chat <id> [--send]   # квиз-опросы в Telegram (без --send — показать)

Формат deck.json и правила — SKILL.md. Сеть не нужна: шрифты встроены (assets/fonts.css).
"""
import hashlib, html, json, os, random, re, shutil, subprocess, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from translit_uz import latn2cyrl  # noqa: E402

TPL = open(os.path.join(ROOT, "templates", "card.html"), encoding="utf-8").read()
FONTS = os.path.join(ROOT, "assets", "fonts.css")

L10N = {
    "ru": {"qa": "вопрос", "cloze": "пропуск", "explain": "объясните", "src": "Источник", "why": "Почему важно:",
           "flip_f": "ответ на обороте →", "flip_b": "← вопрос на лицевой", "explain_front": "Объясните своими словами:",
           "know": "Знаю", "hard": "Трудно", "miss": "Не вспомнил(а)", "due": "к повторению", "all": "Все",
           "missed": "Только ошибки", "shuffle": "Перемешать", "show": "Показать ответ", "done": "Колода пройдена",
           "ask": "Спросить подробнее", "copied": "Вопрос скопирован — вставьте в чат с Милой", "next": "Следующая повторка"},
    "uz_latn": {"qa": "savol", "cloze": "boʻsh joy", "explain": "tushuntiring", "src": "Manba", "why": "Nega muhim:",
                "flip_f": "javob orqa tomonda →", "flip_b": "← savol old tomonda", "explain_front": "Oʻz soʻzlaringiz bilan tushuntiring:",
                "know": "Bilaman", "hard": "Qiyin", "miss": "Eslay olmadim", "due": "takrorlash", "all": "Hammasi",
                "missed": "Faqat xatolar", "shuffle": "Aralashtirish", "show": "Javobni koʻrsatish", "done": "Toʻplam tugadi",
                "ask": "Batafsil soʻrash", "copied": "Savol nusxalandi — Mila bilan chatga qoʻying", "next": "Keyingi takrorlash"},
    "en": {"qa": "question", "cloze": "fill the gap", "explain": "explain", "src": "Source", "why": "Why it matters:",
           "flip_f": "answer on the back →", "flip_b": "← question on the front", "explain_front": "Explain in your own words:",
           "know": "I know it", "hard": "Hard", "miss": "Missed it", "due": "due", "all": "All",
           "missed": "Missed only", "shuffle": "Shuffle", "show": "Show answer", "done": "Deck complete",
           "ask": "Ask for more", "copied": "Question copied — paste it into your chat with Mila", "next": "Next review"},
}
L10N["uz_cyrl"] = {k: latn2cyrl(v) for k, v in L10N["uz_latn"].items()}
LANG_NAMES = {"ru": "Русский", "uz_latn": "Oʻzbekcha", "uz_cyrl": "Ўзбекча", "en": "English"}
CLOZE = re.compile(r"\{\{(?:c\d+::)?(.+?)(?:::(.+?))?\}\}")
TYPES = ("qa", "cloze", "explain")
DIFF = {"easy": 1, "medium": 2, "hard": 3}


def tr(deck, key, lg):
    """Поле колоды (title, subtitle, kicker) — строка или словарь по языкам; uz_cyrl выводится из uz_latn."""
    v = deck.get(key)
    if isinstance(v, dict):
        if lg in v:
            return v[lg]
        if lg == "uz_cyrl" and "uz_latn" in v:
            return latn2cyrl(v["uz_latn"])
        return v.get("ru") or next(iter(v.values()), "")
    return v or ""


def esc(s):
    return html.escape(str(s or ""), quote=True)


def words(s):
    return len(re.findall(r"\w+", CLOZE.sub(r"\1", s or "")))


def load(path):
    deck = json.load(open(path, encoding="utf-8"))
    langs = deck.get("langs") or ["ru"]
    for c in deck["cards"]:
        if "uz_cyrl" in langs and "uz_cyrl" not in c and "uz_latn" in c:
            c["uz_cyrl"] = _cyrl_side(c["uz_latn"])
            c["_auto_cyrl"] = True
    return deck


def _cyrl_side(side):
    out = {}
    for k, v in side.items():
        if isinstance(v, str):
            out[k] = latn2cyrl(v)
        elif isinstance(v, list):
            out[k] = [latn2cyrl(x) for x in v]
    return out


# ----------------------------------------------------------------------------- check
def check(deck):
    errs, warns = [], []
    langs = deck.get("langs") or ["ru"]
    seen = {}
    for i, c in enumerate(deck.get("cards", []), 1):
        tag = "карта %d (%s)" % (i, c.get("id", "?"))
        t = c.get("type", "qa")
        if t not in TYPES:
            errs.append("%s: тип %r, нужен один из %s" % (tag, t, TYPES))
        src = c.get("source") or {}
        if not src.get("section") or not src.get("quote"):
            errs.append("%s: нет источника (section и quote обязательны)" % tag)
        elif words(src["quote"]) > 30:
            warns.append("%s: цитата длиннее 30 слов — сократите до фразы" % tag)
        for lg in langs:
            s = c.get(lg)
            if not s:
                errs.append("%s: нет языка %s" % (tag, lg)); continue
            if not s.get("front"):
                errs.append("%s/%s: пустая лицевая сторона" % (tag, lg))
            if t == "explain":
                if not isinstance(s.get("points"), list) or len(s["points"]) < 2:
                    errs.append("%s/%s: у «объясните» нужен список points из 2–4 мыслей" % (tag, lg))
            elif not s.get("back") and t != "cloze":
                errs.append("%s/%s: пустой оборот" % (tag, lg))
            if t == "cloze" and not CLOZE.search(s.get("front", "")):
                errs.append("%s/%s: у пропуска нет {{…}} в лицевой стороне" % (tag, lg))
            if words(s.get("front")) > 30:
                warns.append("%s/%s: лицевая сторона %d слов (норма ≤30)" % (tag, lg, words(s.get("front"))))
            if words(s.get("back")) > 45:
                warns.append("%s/%s: оборот %d слов (норма ≤45)" % (tag, lg, words(s.get("back"))))
            ch = s.get("choices")
            if ch is not None and (not s.get("answer") or len(ch) < 2 or any(len(x) > 100 for x in ch + [s["answer"]])):
                warns.append("%s/%s: для квиза нужны answer и 2–9 choices по ≤100 знаков" % (tag, lg))
        key = re.sub(r"\W+", " ", (c.get(langs[0]) or {}).get("front", "").lower()).strip()
        if key in seen:
            errs.append("%s: дубль карты %s" % (tag, seen[key]))
        seen[key] = tag
    n = len(deck.get("cards", []))
    if not 4 <= n <= 60:
        warns.append("карт %d — разумно 8–30 на колоду" % n)
    mix = {t: sum(1 for c in deck["cards"] if c.get("type", "qa") == t) for t in TYPES}
    auto = sum(1 for c in deck["cards"] if c.get("_auto_cyrl"))
    return errs, warns, mix, auto


# ----------------------------------------------------------------------------- card faces
def fit(text, big, small, long_at):
    n = len(CLOZE.sub(r"\1", text or ""))
    if n <= long_at // 3:
        return big
    if n >= long_at:
        return small
    return int(big - (big - small) * (n - long_at // 3) / (long_at - long_at // 3))


def cloze_front(s):
    return CLOZE.sub(lambda m: '<span class="gap">%s</span>' % esc(m.group(1)), esc_keep(s))


def cloze_back(s):
    return CLOZE.sub(lambda m: "<mark>%s</mark>" % esc(m.group(1)), esc_keep(s))


def esc_keep(s):
    # экранировать всё, кроме разметки пропуска {{…}}
    parts, last = [], 0
    for m in CLOZE.finditer(s or ""):
        parts.append(esc(s[last:m.start()])); parts.append(m.group(0)); last = m.end()
    parts.append(esc((s or "")[last:]))
    return "".join(parts)


def deckle(seed):
    rnd = random.Random(seed)
    pts, W, H = [], 100.0, 100.0
    steps = lambda a, b, d: [a + k * (b - a) / d for k in range(d + 1)]  # noqa: E731
    for x in steps(0, 100, 25):
        pts.append((x, rnd.uniform(0, .45)))
    for y in steps(0, 100, 33):
        pts.append((W - rnd.uniform(0, .5), y))
    for x in steps(100, 0, 25):
        pts.append((x, H - rnd.uniform(0, .45)))
    for y in steps(100, 0, 33):
        pts.append((rnd.uniform(0, .5), y))
    return "polygon(%s)" % ",".join("%.2f%% %.2f%%" % p for p in pts)


def face(deck, c, lg, idx, total, side, fonts_href):
    L = L10N.get(lg, L10N["ru"])
    s = c[lg]
    t = c.get("type", "qa")
    seed = int(hashlib.md5((c.get("id", "") + lg).encode()).hexdigest()[:6], 16) % 997
    art = ""
    if c.get("image"):
        art = '<img class="art" src="%s" alt="">' % esc(os.path.basename(c["image"]))
    if side == "front":
        if t == "cloze":
            txt = s["front"]
            body = '<div class="front" style="font-size:%dpx">%s</div>' % (fit(txt, 70, 46, 190), cloze_front(txt))
            if s.get("hint"):
                body += '<div class="hint">%s</div>' % esc(s["hint"])
        elif t == "explain":
            body = ('<div class="hint">%s</div><div class="front" style="font-size:%dpx">%s</div>'
                    % (esc(L["explain_front"]), fit(s["front"], 76, 50, 170), esc(s["front"])))
        else:
            body = '<div class="front" style="font-size:%dpx">%s</div>' % (fit(s["front"], 84, 52, 170), esc(s["front"]))
            if s.get("hint"):
                body += '<div class="hint">%s</div>' % esc(s["hint"])
        body = art + body
        src_html, flip = "", L["flip_f"]
    else:
        if t == "cloze":
            body = '<div class="answer" style="font-size:%dpx">%s</div>' % (fit(s["front"], 60, 42, 220), cloze_back(s["front"]))
            if s.get("back"):
                body += '<div class="answer" style="font-size:40px;font-weight:400">%s</div>' % esc(s["back"])
        elif t == "explain":
            body = "<ul class=\"points\">%s</ul>" % "".join("<li>%s</li>" % esc(p) for p in s["points"])
        else:
            body = '<div class="answer" style="font-size:%dpx">%s</div>' % (fit(s["back"], 64, 42, 240), esc(s["back"]))
        if s.get("why"):
            body += '<div class="why">%s %s</div>' % (esc(L["why"]), esc(s["why"]))
        src = c.get("source") or {}
        doc = (deck.get("source_doc") or {}).get("title", "")
        src_html = '<div class="src"><b>%s:</b> %s%s · <i>«%s»</i></div>' % (
            esc(L["src"]), esc(doc + " · " if doc else ""), esc(src.get("section")), esc(src.get("quote")))
        flip = L["flip_b"]
    dots = "".join('<i class="%s"></i>' % ("on" if k < DIFF.get(c.get("difficulty", "medium"), 2) else "") for k in range(3))
    return (TPL.replace("__LANG__", "uz" if lg.startswith("uz") else lg)
               .replace("__TITLE__", esc(tr(deck, "title", lg)))
               .replace("__FONTS__", fonts_href)
               .replace("__DECKLE__", deckle(seed))
               .replace("__SEED__", str(seed))
               .replace("__INDEX__", str(idx)).replace("__TOTAL__", str(total))
               .replace("__KICKER__", esc(tr(deck, "kicker", lg) or tr(deck, "title", lg)))
               .replace("__TYPE__", esc(L[t]))
               .replace("__DOTS__", dots)
               .replace("__BODY__", body)
               .replace("__SRC__", src_html)
               .replace("__FLIP__", esc(flip)))


# ----------------------------------------------------------------------------- print (A4, 8 на лист)
PRINT_CSS = """
@page{size:A4;margin:0}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"PT Sans","DejaVu Sans",Arial,sans-serif;color:#2a2826;background:#fff}
.page{width:210mm;height:297mm;padding:8.5mm 6mm;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:repeat(4,1fr);
  page-break-after:always;break-after:page}
.cell{border:.3mm dashed #b9ae98;padding:6mm 7mm;position:relative;display:flex;flex-direction:column;justify-content:center;
  background:#fbf7ee}
.cell .t{position:absolute;top:3.2mm;left:7mm;font-family:Caveat,cursive;font-size:13pt;color:#8a6440}
.cell .k{position:absolute;top:3.6mm;right:7mm;font-size:7pt;letter-spacing:.1em;font-weight:700;color:#2f6b66}
.cell .f{font-weight:700;font-size:13.5pt;line-height:1.22}
.cell .a{font-weight:700;font-size:11.5pt;line-height:1.25}
.cell .w{font-family:Caveat,cursive;font-size:13pt;color:#2f6b66;margin-top:2mm;line-height:1.05}
.cell .s{position:absolute;left:7mm;right:7mm;bottom:3mm;font-size:6.6pt;color:#8a6440;line-height:1.25}
.cell ul{margin-left:4mm}.cell li{font-size:10.5pt;font-weight:700;margin:.6mm 0}
.gap{display:inline-block;min-width:22mm;border-bottom:.5mm solid #2f6b66;color:transparent}
mark{background:linear-gradient(transparent 58%,rgba(47,107,102,.28) 58%);color:inherit}
.cover{grid-column:1/3;grid-row:1/5;display:flex;flex-direction:column;justify-content:center;padding:20mm;background:#f4eddc}
.cover h1{font-size:30pt;line-height:1.1}.cover p{font-size:12pt;margin-top:6mm;color:#5b5751}
.cover .how{font-family:Caveat,cursive;font-size:17pt;color:#2f6b66;margin-top:12mm;line-height:1.2}
"""


def print_html(deck, lg, fonts_href):
    L = L10N.get(lg, L10N["ru"])
    cards = deck["cards"]
    how = {"ru": "Печать: двусторонняя, переворот по длинному краю. Режьте по пунктиру.",
           "en": "Print double-sided, flip on the long edge. Cut along the dashed lines.",
           "uz_latn": "Ikki tomonlama chop eting, uzun chet boʻyicha aylantiring. Punktir boʻyicha qirqing."}
    how["uz_cyrl"] = latn2cyrl(how["uz_latn"])
    pages = ['<section class="page"><div class="cover"><h1>%s</h1><p>%s</p><p>%s</p><div class="how">%s</div></div></section>'
             '<section class="page"><div class="cover"></div></section>'
             % (esc(tr(deck, "title", lg)), esc(tr(deck, "subtitle", lg)),
                esc(" · ".join(x for x in [(deck.get("source_doc") or {}).get("title"), (deck.get("source_doc") or {}).get("date")] if x)),
                esc(how.get(lg, how["ru"])))]
    for p in range(0, len(cards), 8):
        chunk = cards[p:p + 8] + [None] * (8 - len(cards[p:p + 8]))
        fronts, backs = [], []
        for j, c in enumerate(chunk):
            if not c:
                fronts.append('<div class="cell"></div>'); backs.append('<div class="cell"></div>'); continue
            s, t = c[lg], c.get("type", "qa")
            head = '<div class="t">%d · %s</div><div class="k">%s</div>' % (p + j + 1, esc(L[t]), esc(tr(deck, "kicker", lg)))
            if t == "cloze":
                f = '<div class="f">%s</div>' % cloze_front(s["front"])
                b = '<div class="a">%s</div>' % cloze_back(s["front"])
            elif t == "explain":
                f = '<div class="w">%s</div><div class="f">%s</div>' % (esc(L["explain_front"]), esc(s["front"]))
                b = "<ul>%s</ul>" % "".join("<li>%s</li>" % esc(x) for x in s["points"])
            else:
                f = '<div class="f">%s</div>' % esc(s["front"])
                b = '<div class="a">%s</div>' % esc(s["back"])
            if s.get("why"):
                b += '<div class="w">%s</div>' % esc(s["why"])
            src = c.get("source") or {}
            b += '<div class="s">%s: %s · «%s»</div>' % (esc(L["src"]), esc(src.get("section")), esc(src.get("quote")))
            fronts.append('<div class="cell">%s%s</div>' % (head, f))
            backs.append('<div class="cell">%s%s</div>' % (head, b))
        # оборот: столбцы меняются местами — при перевороте по длинному краю карта совпадает с лицом
        mirrored = []
        for r in range(4):
            mirrored += [backs[r * 2 + 1], backs[r * 2]]
        pages.append('<section class="page">%s</section>' % "".join(fronts))
        pages.append('<section class="page">%s</section>' % "".join(mirrored))
    return ('<!doctype html><html lang="%s"><head><meta charset="utf-8"><title>%s</title><link rel="stylesheet" href="%s">'
            "<style>%s</style></head><body>%s</body></html>"
            % ("uz" if lg.startswith("uz") else lg, esc(tr(deck, "title", lg)), fonts_href, PRINT_CSS, "".join(pages)))


# ----------------------------------------------------------------------------- Anki
def anki(deck, lg, out_dir):
    L = L10N.get(lg, L10N["ru"])
    name = "%s::%s" % (tr(deck, "title", lg) or "MILAGPT", LANG_NAMES.get(lg, lg))
    basic, cloze = [], []
    for c in deck["cards"]:
        s, t = c[lg], c.get("type", "qa")
        src = c.get("source") or {}
        extra = ""
        if s.get("why"):
            extra += "<p><i>%s %s</i></p>" % (esc(L["why"]), esc(s["why"]))
        extra += "<p><small>%s: %s · «%s»</small></p>" % (esc(L["src"]), esc(src.get("section")), esc(src.get("quote")))
        tags = " ".join(["milagpt", c.get("difficulty", "medium")] + [re.sub(r"\s+", "_", x) for x in c.get("tags", [])])
        row = lambda *cols: "\t".join(x.replace("\t", " ").replace("\n", "<br>") for x in cols)  # noqa: E731
        if t == "cloze":
            n = [0]

            def num(m):
                n[0] += 1
                return "{{c%d::%s%s}}" % (n[0], m.group(1), "::" + m.group(2) if m.group(2) else "")
            cloze.append(row(esc_keep(CLOZE.sub(num, s["front"])), (esc(s.get("back", "")) + extra), tags))
        elif t == "explain":
            back = "<ul>%s</ul>" % "".join("<li>%s</li>" % esc(p) for p in s["points"])
            basic.append(row("%s<br><b>%s</b>" % (esc(L["explain_front"]), esc(s["front"])), back + extra, tags))
        else:
            basic.append(row(esc(s["front"]), esc(s["back"]) + extra, tags))
    files = []
    for kind, rows in (("basic", basic), ("cloze", cloze)):
        if not rows:
            continue
        head = "#separator:tab\n#html:true\n#notetype:%s\n#deck:%s\n#tags column:3\n" % ("Basic" if kind == "basic" else "Cloze", name)
        p = os.path.join(out_dir, "anki-%s-%s.txt" % (lg, kind))
        open(p, "w", encoding="utf-8").write(head + "\n".join(rows) + "\n")
        files.append(p)
    return files


# ----------------------------------------------------------------------------- Telegram-квизы
def polls(deck, lg):
    L = L10N.get(lg, L10N["ru"])
    out = []
    for c in deck["cards"]:
        s = c[lg]
        if not s.get("choices") or not s.get("answer"):
            continue
        opts = [s["answer"]] + list(s["choices"])[:9]
        rnd = random.Random(c.get("id", ""))
        order = list(range(len(opts)))
        rnd.shuffle(order)
        q = CLOZE.sub("___", s["front"])
        src = c.get("source") or {}
        expl = ((s.get("why") or "") + " · " + L["src"] + ": " + (src.get("section") or "")).strip(" ·")
        out.append({"question": q[:300], "options": [opts[k][:100] for k in order],
                    "correct_option_id": order.index(0), "explanation": expl[:200], "card": c.get("id")})
    return out


def send_polls(path, chat, really):
    items = json.load(open(path, encoding="utf-8"))
    token = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    for it in items:
        print("•", it["question"][:80], "→", it["options"][it["correct_option_id"]][:40])
    if not really:
        print("\n%d квизов. Это показ; отправка — с --send, и только в чат, где об этом попросили." % len(items))
        return 0
    if not token:
        sys.exit("нет BOT_TOKEN в окружении — отправить не могу")
    for it in items:
        body = {"chat_id": chat, "question": it["question"], "options": json.dumps([{"text": o} for o in it["options"]]),
                "type": "quiz", "correct_option_id": it["correct_option_id"], "explanation": it["explanation"],
                "is_anonymous": "false"}
        r = urllib.request.urlopen(urllib.request.Request(
            "https://api.telegram.org/bot%s/sendPoll" % token, data=urllib.parse.urlencode(body).encode()), timeout=30)
        res = json.load(r)
        print("ok" if res.get("ok") else res)
        time.sleep(1.2)
    return 0


# ----------------------------------------------------------------------------- тренажёр
def trainer(deck, out_dir):
    fonts = open(FONTS, encoding="utf-8").read()
    tpl = open(os.path.join(ROOT, "templates", "trainer.html"), encoding="utf-8").read()
    langs = deck.get("langs") or ["ru"]
    data = {"id": deck.get("id") or hashlib.md5(json.dumps(deck.get("title"), ensure_ascii=False).encode()).hexdigest()[:10],
            "titles": {lg: tr(deck, "title", lg) for lg in langs}, "subtitles": {lg: tr(deck, "subtitle", lg) for lg in langs},
            "ask_bot": deck.get("ask_bot", ""),
            "source_doc": deck.get("source_doc") or {}, "langs": langs,
            "names": {lg: LANG_NAMES.get(lg, lg) for lg in langs},
            "l10n": {lg: L10N.get(lg, L10N["ru"]) for lg in langs},
            "cards": [{k: v for k, v in c.items() if not k.startswith("_")} for c in deck["cards"]]}
    page = (tpl.replace("/*__FONTS__*/", fonts)
               .replace("__TITLE__", esc(tr(deck, "title", langs[0])))
               .replace("/*__DECK__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
    p = os.path.join(out_dir, "trainer.html")
    open(p, "w", encoding="utf-8").write(page)
    return p


# ----------------------------------------------------------------------------- build / render
def build(path, out_dir, only_lang=None):
    deck = load(path)
    errs, warns, _, _ = check(deck)
    if errs:
        sys.exit("колода не прошла проверку:\n  " + "\n  ".join(errs))
    langs = [only_lang] if only_lang else (deck.get("langs") or ["ru"])
    os.makedirs(out_dir, exist_ok=True)
    shutil.copy(FONTS, os.path.join(out_dir, "fonts.css"))
    made = []
    total = len(deck["cards"])
    for lg in langs:
        cdir = os.path.join(out_dir, "cards-" + lg)
        os.makedirs(cdir, exist_ok=True)
        for c in deck["cards"]:
            if c.get("image"):
                src = os.path.join(os.path.dirname(os.path.abspath(path)), c["image"])
                if os.path.exists(src):
                    shutil.copy(src, cdir)
        for i, c in enumerate(deck["cards"], 1):
            for side in ("front", "back"):
                p = os.path.join(cdir, "%02d-%s.html" % (i, side))
                open(p, "w", encoding="utf-8").write(face(deck, c, lg, i, total, side, "../fonts.css"))
                made.append(p)
        pp = os.path.join(out_dir, "print-%s.html" % lg)
        open(pp, "w", encoding="utf-8").write(print_html(deck, lg, "fonts.css"))
        made.append(pp)
        made += anki(deck, lg, out_dir)
        q = polls(deck, lg)
        if q:
            qp = os.path.join(out_dir, "polls-%s.json" % lg)
            json.dump(q, open(qp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            made.append(qp)
    made.append(trainer(deck, out_dir))
    json.dump({"langs": langs, "total": total, "built": time.strftime("%F %T")},
              open(os.path.join(out_dir, "manifest.json"), "w"), ensure_ascii=False)
    for w in warns:
        print("⚠", w)
    print("собрано файлов: %d в %s" % (len(made), out_dir))
    return made


def find_chrome():
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("google-chrome") or "",
              shutil.which("chromium") or "", shutil.which("chrome-headless-shell") or ""):
        if p and os.path.exists(p):
            return p
    return None


def render(out_dir):
    man = json.load(open(os.path.join(out_dir, "manifest.json")))
    chrome = find_chrome()
    jobs = []
    for lg in man["langs"]:
        cdir = os.path.join(out_dir, "cards-" + lg)
        for f in sorted(os.listdir(cdir)):
            if f.endswith(".html"):
                jobs.append(("png", os.path.join(cdir, f), os.path.join(cdir, f[:-5] + ".png")))
        jobs.append(("pdf", os.path.join(out_dir, "print-%s.html" % lg), os.path.join(out_dir, "print-%s.pdf" % lg)))
    if chrome:
        for kind, src, dst in jobs:
            base = [chrome, "--headless", "--disable-gpu", "--hide-scrollbars", "--no-sandbox", "--virtual-time-budget=3000"]
            if kind == "png":
                args = base + ["--force-device-scale-factor=1", "--window-size=1080,1350", "--screenshot=" + dst]
            else:
                args = base + ["--no-pdf-header-footer", "--print-to-pdf=" + dst]
            subprocess.run(args + ["file://" + os.path.abspath(src)], capture_output=True, timeout=120)
            print(("ok " if os.path.exists(dst) else "НЕ ВЫШЛО ") + dst)
        return 0
    # компаньон: браузера нет — заявки в очередь рендера хоста (hf-render, раз в минуту)
    work = os.path.expanduser("~/work")
    ab = os.path.abspath(out_dir)
    if not ab.startswith(work + "/"):
        sys.exit("папка колоды должна лежать внутри ~/work, чтобы её отрендерила очередь")
    rel = ab[len(work) + 1:]
    q = os.path.join(work, "render-queue")
    os.makedirs(q, exist_ok=True)
    stamp = time.strftime("%H%M%S")
    for n, (kind, src, dst) in enumerate(jobs):
        req = {"project": rel, "html": os.path.relpath(src, ab), "format": kind,
               "output": os.path.join(rel, os.path.relpath(dst, ab))}
        if kind == "png":
            req.update({"width": 1080, "height": 1350})
        json.dump(req, open(os.path.join(q, "fc-%s-%03d.json" % (stamp, n)), "w"), ensure_ascii=False)
    print("заявок в очередь рендера: %d (~/work/render-queue/fc-%s-*.json); готовность — файлы .done рядом" % (len(jobs), stamp))
    return 0


def main(a):
    if not a or a[0] not in ("check", "build", "render", "polls"):
        sys.exit(__doc__)
    cmd = a[0]
    if cmd == "check":
        deck = load(a[1])
        errs, warns, mix, auto = check(deck)
        print("карт: %d · типы: %s · языки: %s%s" % (len(deck["cards"]), mix, deck.get("langs"),
              " · uz кириллица выведена автоматически у %d — вычитать носителем" % auto if auto else ""))
        for w in warns:
            print("⚠", w)
        for e in errs:
            print("✗", e)
        print("ПРОВЕРКА ПРОЙДЕНА" if not errs else "НЕ ПРОЙДЕНА: %d ошибок" % len(errs))
        return 1 if errs else 0
    if cmd == "build":
        lang = a[a.index("--lang") + 1] if "--lang" in a else None
        build(a[1], a[2], lang)
        return 0
    if cmd == "render":
        return render(a[1])
    if cmd == "polls":
        chat = a[a.index("--chat") + 1] if "--chat" in a else ""
        return send_polls(a[1], chat, "--send" in a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
