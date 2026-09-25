#!/usr/bin/env python3
"""vo_build.py — видеопрезентация из сценария (аналог Video Overview в NotebookLM, только лучше).

Только стандартная библиотека: работает в контейнере компаньона без Node, Chrome и ffmpeg.
Рендер mp4/png делает хост через очередь ~/work/render-queue (HyperFrames).

    vo_build.py plan    scenario.json          сцены, знаки, длительность, цена — ничего не тратит
    vo_build.py voice   scenario.json WORKDIR  озвучка сцен ElevenLabs (кэш по тексту)
    vo_build.py images  scenario.json WORKDIR  картинки сцен genimage (только style=sketch, кэш)
    vo_build.py compose scenario.json WORKDIR  проекты HyperFrames на каждый формат + .srt + главы
                                               + заявки в очередь рендера (mp4 и обложка png)
    vo_build.py all     scenario.json WORKDIR  voice → images → compose
    --redo 16:9:2,9:16:5   перерисовать только эти картинки (готовые не трогаются, деньги зря не уходят)

WORKDIR должен лежать внутри ~/work (очередь берёт пути от ~/work). Формат сценария — SKILL.md.
"""
import hashlib, html, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
HOME = os.path.expanduser("~")
EL = os.path.join(HOME, ".claude/skills/elevenlabs/el.py")
GENIMAGE = os.path.join(HOME, ".claude/skills/genimage/genimage.py")
QUEUE = os.path.join(HOME, "work/render-queue")

INTRO = 2.2      # титульный кадр в начале, без голоса
GAP = 0.35       # воздух после реплики сцены
END = 3.8        # концовка с призывом
CPS = 14.0       # знаков в секунду без голоса (оценка темпа речи)
KBPS = 128       # el.py пишет mp3_44100_128 CBR: длительность = размер * 8 / 128000

SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
SUB_MAX = {"16:9": 46, "9:16": 30}

PALETTES = {
    "teal": {"bg1": "#0b2f2c", "bg2": "#134e4a", "ink": "#fbfbf8", "accent": "#5eead4", "muted": "#99f6e4"},
    "sand": {"bg1": "#fbfbf8", "bg2": "#eefaf6", "ink": "#16302d", "accent": "#0d9488", "muted": "#a9752e"},
    "night": {"bg1": "#0f172a", "bg2": "#1e293b", "ink": "#f8fafc", "accent": "#f2c98a", "muted": "#cbd5e1"},
}

SKETCH_STYLE = open(os.path.join(SKILL, "prompts/style-sketch.txt"), encoding="utf-8").read().strip()


# ---------------------------------------------------------------- сценарий
def load(path):
    sc = json.load(open(path, encoding="utf-8"))
    sc.setdefault("name", re.sub(r"[^a-z0-9-]+", "-", os.path.basename(path).rsplit(".", 1)[0].lower()))
    sc.setdefault("lang", "ru")
    sc.setdefault("style", "brand")
    sc.setdefault("aspects", ["16:9", "9:16"])
    sc.setdefault("voice", "none")
    scenes = []
    for ci, ch in enumerate(sc["chapters"]):
        for si, s in enumerate(ch["scenes"]):
            s = dict(s)
            s["chapter"], s["chapter_title"], s["first_in_chapter"] = ci, ch["title"], si == 0
            s["n"] = len(scenes) + 1
            scenes.append(s)
    sc["_scenes"] = scenes
    for a in sc["aspects"]:
        if a not in SIZES:
            sys.exit("🔴 формат %r: только 16:9 и 9:16" % a)
    return sc


def key(*parts):
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def aslug(a):
    return a.replace(":", "x")


# ---------------------------------------------------------------- plan
def cmd_plan(sc):
    chars = sum(len(s["say"]) for s in sc["_scenes"])
    dur = INTRO + END + sum(max(3.0, len(s["say"]) / CPS) + GAP for s in sc["_scenes"])
    imgs = len(sc["_scenes"]) * len(sc["aspects"]) if sc["style"] == "sketch" else 0
    print("сцен %d · глав %d · знаков озвучки %d · ≈%d с · форматы %s · стиль %s"
          % (len(sc["_scenes"]), len(sc["chapters"]), chars, dur, ",".join(sc["aspects"]), sc["style"]))
    print("цена: ElevenLabs %d знаков из квоты · картинок %d × ≈$0.14 = ≈$%.2f · рендер на хосте бесплатно"
          % (chars if sc["voice"] != "none" else 0, imgs, imgs * 0.14))
    for s in sc["_scenes"]:
        if len(s.get("headline", "")) > 70:
            print("🟡 сцена %d: заголовок %d знаков — длинно для кадра, лучше ≤ 70" % (s["n"], len(s["headline"])))
        if not s.get("source"):
            print("🟡 сцена %d: нет source — откуда факт?" % s["n"])


# ---------------------------------------------------------------- voice
def mp3_dur(path):
    return round(os.path.getsize(path) * 8 / (KBPS * 1000), 2)


def cmd_voice(sc, wd):
    if sc["voice"] == "none":
        print("голос: none — сцены по темпу чтения, озвучки нет")
        return
    if not os.path.exists(EL):
        sys.exit("🔴 нет навыка elevenlabs (%s) — голос none или попросите старшую поставить навык" % EL)
    d = os.path.join(wd, "audio")
    os.makedirs(d, exist_ok=True)
    mf = os.path.join(d, "manifest.json")
    man = json.load(open(mf)) if os.path.exists(mf) else {}
    vs = sc.get("voice_settings", {})
    opts = []
    for k in ("speed", "stability", "style", "similarity"):
        if k in vs:
            opts += ["--" + k, str(vs[k])]
    if sc.get("voice_model"):
        opts += ["--model", sc["voice_model"]]
    for s in sc["_scenes"]:
        k = key(s["say"], sc["voice"], opts)
        out = os.path.join(d, "s%02d.mp3" % s["n"])
        if man.get(str(s["n"])) == k and os.path.exists(out):
            continue
        txt = os.path.join(d, "s%02d.txt" % s["n"])
        open(txt, "w", encoding="utf-8").write(s["say"])
        r = subprocess.run(["python3", EL, "tts", sc["voice"], "@" + txt, out] + opts, capture_output=True, text=True)
        if r.returncode or not os.path.exists(out):
            sys.exit("🔴 озвучка сцены %d: %s" % (s["n"], (r.stderr or r.stdout)[-300:]))
        man[str(s["n"])] = k
        json.dump(man, open(mf, "w"), indent=1)
        print("ok голос сцена %d · %.1f с" % (s["n"], mp3_dur(out)))


# ---------------------------------------------------------------- images
def sketch_prompt(sc, s, aspect):
    lines = [SKETCH_STYLE, "",
             "Aspect: %s %s." % (aspect, "vertical" if aspect == "9:16" else "horizontal"),
             "Place the headline at the TOP of the frame. Keep the lower 22% of the frame calm and empty "
             "(plain paper, no text, no drawings) — subtitles go there.",
             "", s.get("visual") or ("A clear explanatory illustration of: " + s.get("headline", s["say"][:120]))]
    if s.get("headline"):
        lang = {"ru": "Russian Cyrillic", "uz-cyrl": "Uzbek Cyrillic", "uz": "Uzbek Latin", "en": "English"}.get(sc["lang"], sc["lang"])
        lines += ["", "Render this exact text, legibly, correct %s spelling, nothing cropped:" % lang,
                  '- HEADLINE: "%s"' % s["headline"]]
        for p in (s.get("labels") or [])[:4]:
            lines.append('- label: "%s"' % p)
    lines += ["", "STRICT: no other words anywhere in the image — no extra captions, notes, labels on objects, "
              "title blocks, signatures, names, dates, figure numbers or scale marks with text. "
              "If an object would normally carry text, leave it blank. Count of drawn objects must match "
              "the description exactly."]
    return "\n".join(lines)


def cmd_images(sc, wd, redo=()):
    if sc["style"] != "sketch":
        print("стиль %s — картинки не нужны, кадры вёрстаются HTML" % sc["style"])
        return
    if not os.path.exists(GENIMAGE):
        sys.exit("🔴 нет навыка genimage — стиль brand или попросите старшую поставить навык")
    model = sc.get("image_model", "gemini-3-pro")
    for a in sc["aspects"]:
        d = os.path.join(wd, "img", aslug(a))
        os.makedirs(d, exist_ok=True)
        for s in sc["_scenes"]:
            out = os.path.join(d, "s%02d.png" % s["n"])
            p = sketch_prompt(sc, s, a)
            kf = out + ".key"
            if os.path.exists(out) and "%s:%d" % (a, s["n"]) not in redo:
                if not os.path.exists(kf) or open(kf).read() != key(p, model):
                    print("🟡 сцена %d %s: промпт изменился, картинка старая — перегенерировать: --redo %s:%d"
                          % (s["n"], a, a, s["n"]))
                continue
            r = subprocess.run(["python3", GENIMAGE, "--prompt", p, "--model", model, "--size", a,
                                "--quality", "2K", "--out", out], capture_output=True, text=True)
            if r.returncode or not os.path.exists(out):
                sys.exit("🔴 картинка сцены %d (%s): %s" % (s["n"], a, (r.stderr or r.stdout)[-300:]))
            open(kf, "w").write(key(p, model))
            print("ok картинка сцена %d %s — посмотрите глазами (Read) перед сборкой" % (s["n"], a))


# ---------------------------------------------------------------- compose
def chunks(text, maxc):
    """Субтитры: куски ≤ maxc знаков, рвём по концу фразы или по словам."""
    out, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > maxc:
            # короткий предлог или союз в конце куска («о», «и», «в», «на») переносим в следующий
            tail = cur.rsplit(" ", 1)
            if len(tail) == 2 and len(tail[1]) <= 2 and not re.search(r"[.,!?…:;]$", tail[1]):
                out.append(tail[0])
                cur = tail[1] + " " + w
            else:
                out.append(cur)
                cur = w
        else:
            cur = (cur + " " + w).strip()
        if re.search(r"[.!?…]$", w) and len(cur) > maxc * 0.45:
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def srt_t(t):
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def yt_t(t):
    t = int(t)
    return "%d:%02d:%02d" % (t // 3600, t // 60 % 60, t % 60) if t >= 3600 else "%d:%02d" % (t // 60, t % 60)


def esc(s):
    return html.escape(s or "", quote=True)


def timeline(sc, wd):
    """Раскладка по времени, общая для всех форматов."""
    t, rows = INTRO, []
    for s in sc["_scenes"]:
        a = os.path.join(wd, "audio", "s%02d.mp3" % s["n"])
        talk = mp3_dur(a) if (sc["voice"] != "none" and os.path.exists(a)) else max(3.0, len(s["say"]) / CPS)
        rows.append({"s": s, "start": round(t, 2), "talk": talk, "dur": round(talk + GAP, 2),
                     "audio": a if sc["voice"] != "none" and os.path.exists(a) else None})
        t += talk + GAP
    return rows, round(t + END, 2)


def pal(sc):
    b = sc.get("brand", {})
    p = dict(PALETTES.get(b.get("palette", "teal"), PALETTES["teal"]))
    p.update({k: v for k, v in b.items() if k in ("bg1", "bg2", "ink", "accent", "muted")})
    return p


def build_css(sc, aspect):
    w, h = SIZES[aspect]
    v = aspect == "9:16"
    p = pal(sc)
    fonts = open(os.path.join(SKILL, "fonts/fonts.css"), encoding="utf-8").read()
    return fonts + """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:%(w)dpx;height:%(h)dpx;overflow:hidden;background:%(bg1)s}
#root{position:relative;width:%(w)dpx;height:%(h)dpx;overflow:hidden;font-family:'Noto Sans',sans-serif;color:%(ink)s;
  background:linear-gradient(160deg,%(bg1)s 0%%,%(bg2)s 100%%)}
.clip{position:absolute;inset:0;overflow:hidden}
.wrap{position:absolute;inset:0}
.bgimg{position:absolute;inset:0;width:100%%;height:100%%;object-fit:cover}
.glow{position:absolute;inset:0;background:radial-gradient(%(gw)dpx %(gh)dpx at 82%% 14%%,%(accent)s22,transparent 62%%)}
.kicker{position:absolute;left:%(padx)dpx;top:%(ktop)dpx;font:800 %(kfs)dpx/1.2 'Montserrat',sans-serif;letter-spacing:.06em;color:%(muted)s}
.stack{position:absolute;left:%(padx)dpx;right:%(padx)dpx;top:%(htop)dpx}
.headline{font:800 %(hfs)dpx/1.12 'Montserrat',sans-serif;color:%(ink)s}
.points{list-style:none;margin-top:%(ptop)dpx}
.points li{font:600 %(pfs)dpx/1.3 'Noto Sans',sans-serif;margin-bottom:%(pgap)dpx;padding-left:%(pind)dpx;position:relative;opacity:0}
.points li:before{content:'';position:absolute;left:0;top:.45em;width:%(dot)dpx;height:%(dot)dpx;border-radius:50%%;background:%(accent)s}
.sub{position:absolute;left:50%%;bottom:%(sbot)dpx;width:%(sw)dpx;margin-left:-%(shw)dpx;text-align:center;opacity:0}
.sub span{display:inline-block;background:rgba(0,0,0,.62);color:#fff;font:600 %(sfs)dpx/1.3 'Noto Sans',sans-serif;
  padding:%(spy)dpx %(spx)dpx;border-radius:14px}
.chapter{position:absolute;left:%(padx)dpx;top:%(ctop)dpx;opacity:0;background:%(accent)s;color:%(bg1)s;
  font:800 %(cfs)dpx/1 'Montserrat',sans-serif;padding:16px 26px;border-radius:999px}
.bar{position:absolute;left:0;top:0;height:8px;width:100%%;background:%(accent)s;transform-origin:0 50%%;z-index:50}
.brandmark{position:absolute;right:%(padx)dpx;bottom:%(bmb)dpx;font:800 %(bfs)dpx/1 'Montserrat',sans-serif;opacity:.7;letter-spacing:.08em;z-index:40}
.title-card,.end-card{display:flex;flex-direction:column;justify-content:center;padding:0 %(padx)dpx}
.title-card h1,.end-card h1{font:800 %(tfs)dpx/1.08 'Montserrat',sans-serif;color:%(ink)s}
.title-card p,.end-card p{font:600 %(tsub)dpx/1.3 'Noto Sans',sans-serif;color:%(muted)s;margin-top:34px}
.end-card .cta{display:inline-block;margin-top:48px;background:%(accent)s;color:%(bg1)s;font:800 %(cfs)dpx/1 'Montserrat',sans-serif;
  padding:26px 40px;border-radius:999px;align-self:flex-start}
.sketch .sub span{background:rgba(22,48,45,.82)}
.sketch .chapter{top:auto;bottom:%(chb)dpx}
.sketch-root .brandmark{color:#16302d}
""" % dict(p, w=w, h=h, gw=w, gh=h, padx=90 if v else 140,
           ktop=260 if v else 120, kfs=34 if v else 30, htop=330 if v else 180, hfs=86 if v else 92,
           ptop=90 if v else 70, pfs=46 if v else 44, pgap=30 if v else 24, pind=52 if v else 48, dot=20 if v else 18,
           sbot=360 if v else 70, sw=w - (120 if v else 320), shw=(w - (120 if v else 320)) // 2,
           sfs=46 if v else 44, spy=12, spx=22, ctop=150 if v else 60, cfs=34 if v else 30,
           bmb=250 if v else 36, chb=470 if v else 160, bfs=28 if v else 26, tfs=104 if v else 110, tsub=44 if v else 42)


def compose_one(sc, wd, aspect, rows, total):
    w, h = SIZES[aspect]
    out = os.path.join(wd, "out-" + aslug(aspect))
    shutil.rmtree(out, ignore_errors=True)
    for sub in ("assets", "fonts", "vendor"):
        os.makedirs(os.path.join(out, sub))
    for f in os.listdir(os.path.join(SKILL, "fonts")):
        if f.endswith(".woff2"):
            shutil.copy(os.path.join(SKILL, "fonts", f), os.path.join(out, "fonts", f))
    shutil.copy(os.path.join(SKILL, "vendor/gsap.min.js"), os.path.join(out, "vendor/gsap.min.js"))
    sketch = sc["style"] == "sketch"
    brand = sc.get("brand", {})
    body, js, srt, chap = [], [], [], []
    # титульный кадр
    body.append('<section id="intro" class="clip title-card" data-start="0" data-duration="%s" data-track-index="0">'
                '<div class="glow"></div><h1 id="intro-h">%s</h1><p id="intro-p">%s</p></section>'
                % (INTRO, esc(sc["title"]), esc(sc.get("subtitle", ""))))
    js.append('tl.fromTo("#intro-h",{y:40,opacity:0},{y:0,opacity:1,duration:.7,ease:"power2.out"},0.1);')
    js.append('tl.fromTo("#intro-p",{y:30,opacity:0},{y:0,opacity:1,duration:.6,ease:"power2.out"},0.45);')
    sub_i = 0
    for r in rows:
        s, n, st = r["s"], r["s"]["n"], r["start"]
        inner = []
        if sketch:
            src = os.path.join(wd, "img", aslug(aspect), "s%02d.png" % n)
            if not os.path.exists(src):
                sys.exit("🔴 нет картинки %s — сначала vo_build.py images" % src)
            shutil.copy(src, os.path.join(out, "assets", "s%02d.png" % n))
            inner.append('<img id="img-%d" class="bgimg" src="assets/s%02d.png" />' % (n, n))
            js.append('tl.fromTo("#img-%d",{scale:1.0},{scale:1.06,duration:%s,ease:"none"},%s);' % (n, r["dur"], st))
        else:
            inner.append('<div class="glow"></div>')
            inner.append('<div class="kicker">%s</div>' % esc(s.get("kicker") or s["chapter_title"]))
            pts = s.get("points") or []
            inner.append('<div class="stack"><div id="h-%d" class="headline">%s</div>%s</div>' % (
                n, esc(s.get("headline", "")), '<ul class="points">%s</ul>' % "".join(
                    '<li id="p-%d-%d">%s</li>' % (n, i, esc(p)) for i, p in enumerate(pts)) if pts else ""))
            js.append('tl.fromTo("#h-%d",{y:36,opacity:0},{y:0,opacity:1,duration:.6,ease:"power2.out"},%s);' % (n, st + 0.1))
            for i in range(len(pts)):
                at = st + 0.6 + r["talk"] * (i + 0.3) / (len(pts) + 0.3)
                js.append('tl.fromTo("#p-%d-%d",{x:-30,opacity:0},{x:0,opacity:1,duration:.45,ease:"power2.out"},%.2f);' % (n, i, at))
        if s["first_in_chapter"] and sketch:
            inner.append('<div id="ch-%d" class="chapter">%s</div>' % (n, esc(s["chapter_title"])))
            js.append('tl.fromTo("#ch-%d",{opacity:0,y:-16},{opacity:1,y:0,duration:.4},%s);' % (n, st + 0.05))
            js.append('tl.to("#ch-%d",{opacity:0,duration:.4},%s);' % (n, st + 2.6))
        if s["first_in_chapter"]:
            chap.append("%s %s" % (yt_t(0 if not chap else st), s["chapter_title"]))
        # субтитры
        parts = chunks(s["say"], SUB_MAX[aspect])
        tot = sum(len(p) for p in parts) or 1
        t0 = st
        for p in parts:
            d = r["talk"] * len(p) / tot
            sub_i += 1
            inner.append('<div id="sub-%d" class="sub"><span>%s</span></div>' % (sub_i, esc(p)))
            js.append('tl.set("#sub-%d",{opacity:1},%.2f);tl.set("#sub-%d",{opacity:0},%.2f);' % (sub_i, t0, sub_i, t0 + d))
            srt.append("%d\n%s --> %s\n%s\n" % (sub_i, srt_t(t0), srt_t(t0 + d), p))
            t0 += d
        body.append('<section id="scene-%d" class="clip%s" data-start="%s" data-duration="%s" data-track-index="0">'
                    '<div id="w-%d" class="wrap">%s</div></section>'
                    % (n, " sketch" if sketch else "", st, r["dur"], n, "".join(inner)))
        js.append('tl.fromTo("#w-%d",{opacity:0},{opacity:1,duration:.35},%s);' % (n, st))
        if r["audio"]:
            shutil.copy(r["audio"], os.path.join(out, "assets", "s%02d.mp3" % n))
            body.append('<audio id="a-%d" src="assets/s%02d.mp3" data-start="%s" data-duration="%s" '
                        'data-track-index="10" data-volume="1"></audio>' % (n, n, st, r["talk"]))
    end_st = rows[-1]["start"] + rows[-1]["dur"]
    end = sc.get("end", {})
    body.append('<section id="end" class="clip end-card" data-start="%s" data-duration="%s" data-track-index="0">'
                '<div class="glow"></div><h1 id="end-h">%s</h1><p>%s</p>%s</section>'
                % (round(end_st, 2), round(total - end_st, 2), esc(end.get("headline", sc["title"])),
                   esc(end.get("text", "")), '<div class="cta">%s</div>' % esc(end["cta"]) if end.get("cta") else ""))
    js.append('tl.fromTo("#end-h",{y:40,opacity:0},{y:0,opacity:1,duration:.6},%.2f);' % (end_st + 0.1))
    if sc.get("music") and os.path.exists(os.path.join(wd, sc["music"])):
        shutil.copy(os.path.join(wd, sc["music"]), os.path.join(out, "assets", "music.mp3"))
        body.append('<audio id="music" src="assets/music.mp3" data-start="0" data-duration="%s" data-track-index="11" '
                    'data-volume="%s"></audio>' % (total, sc.get("music_volume", 0.12)))
    js.append('tl.fromTo("#bar",{scaleX:0},{scaleX:1,duration:%s,ease:"none"},0);' % total)
    doc = """<!doctype html>
<html lang="%(lang)s">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=%(w)d, height=%(h)d" />
<title>%(title)s</title>
<script src="vendor/gsap.min.js"></script>
<style>%(css)s</style>
</head>
<body>
  <div id="root" class="%(rootcls)s" data-composition-id="main" data-start="0" data-width="%(w)d" data-height="%(h)d" data-duration="%(total)s">
    <div id="bar" class="bar"></div>
    <div class="brandmark">%(mark)s</div>
    %(body)s
  </div>
  <script>
    const tl = gsap.timeline({ paused: true });
    %(js)s
    window.__timelines["main"] = tl;
  </script>
</body>
</html>
""" % {"lang": sc["lang"][:2], "w": w, "h": h, "title": esc(sc["title"]), "css": build_css(sc, aspect),
       "total": total, "mark": esc(brand.get("handle", "MILAGPT")), "body": "\n    ".join(body),
       "js": "\n    ".join(js), "rootcls": "sketch-root" if sketch else ""}
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(doc)
    open(os.path.join(out, "subtitles.srt"), "w", encoding="utf-8").write("\n".join(srt))
    open(os.path.join(out, "chapters.txt"), "w", encoding="utf-8").write("\n".join(chap) + "\n")
    # обложка: титульный кадр отдельной страницей, для sketch — первая картинка фоном
    cover_bg = ""
    if sketch:
        cover_bg = ('<img class="bgimg" src="assets/s01.png" /><div style="position:absolute;inset:0;'
                    'background:linear-gradient(180deg,rgba(11,47,44,.15) 0%,rgba(11,47,44,.88) 70%)"></div>')
    cover = ('<!doctype html><html><head><meta charset="UTF-8"><style>%s .title-card{position:absolute;inset:0;z-index:2;'
             'justify-content:flex-end;padding-bottom:%dpx} .title-card h1{color:#fff}</style></head><body><div id="root">'
             '%s<div class="glow"></div><div class="title-card"><h1>%s</h1><p>%s</p></div>'
             '<div class="brandmark" style="color:#fff">%s</div></div></body></html>'
             % (build_css(sc, aspect), 420 if aspect == "9:16" else 140, cover_bg, esc(sc["title"]),
                esc(sc.get("subtitle", "")), esc(brand.get("handle", "MILAGPT"))))
    open(os.path.join(out, "cover.html"), "w", encoding="utf-8").write(cover)
    return out


def queue(sc, out, aspect, chat):
    rel = os.path.relpath(out, os.path.join(HOME, "work"))
    if rel.startswith(".."):
        print("🟡 %s вне ~/work — очередь рендера его не увидит; перенесите WORKDIR в ~/work" % out)
        return
    os.makedirs(QUEUE, exist_ok=True)
    name = "%s-%s" % (sc["name"], aslug(aspect))
    w, h = SIZES[aspect]
    # crf 28: ролик 80 с ≈ 10–20 МБ — лезет в Telegram; для YouTube-мастера поставьте "crf": 20 в сценарии
    jobs = {name: {"project": rel, "output": rel + "/" + name + ".mp4", "quality": "standard",
                   "crf": int(sc.get("crf", 28))},
            name + "-cover": {"project": rel, "html": "cover.html", "format": "png", "width": w, "height": h,
                              "output": rel + "/" + name + "-cover.png"}}
    for jn, j in jobs.items():
        if chat:
            j["chat"] = chat
        qf = os.path.join(QUEUE, jn + ".json")
        for old in (qf, qf[:-5] + ".done"):
            if os.path.exists(old):
                os.remove(old)
        json.dump(j, open(qf, "w", encoding="utf-8"), ensure_ascii=False)
        print("ok заявка в очередь:", qf)


def cmd_compose(sc, wd, chat=None):
    rows, total = timeline(sc, wd)
    for a in sc["aspects"]:
        out = compose_one(sc, wd, a, rows, total)
        print("ok проект %s · %.1f с · %d сцен → %s" % (a, total, len(rows), out))
        queue(sc, out, a, chat)


def main(a):
    if len(a) < 2 or a[0] not in ("plan", "voice", "images", "compose", "all"):
        sys.exit(__doc__)
    sc = load(a[1])
    if a[0] == "plan":
        return cmd_plan(sc)
    if len(a) < 3:
        sys.exit("🔴 нужен WORKDIR")
    wd = os.path.abspath(os.path.expanduser(a[2]))
    os.makedirs(wd, exist_ok=True)
    chat = a[a.index("--chat") + 1] if "--chat" in a else None
    if a[0] in ("voice", "all"):
        cmd_voice(sc, wd)
    redo = set(a[a.index("--redo") + 1].split(",")) if "--redo" in a else set()
    if a[0] in ("images", "all"):
        cmd_images(sc, wd, redo)
    if a[0] in ("compose", "all"):
        cmd_compose(sc, wd, chat)


if __name__ == "__main__":
    main(sys.argv[1:])
