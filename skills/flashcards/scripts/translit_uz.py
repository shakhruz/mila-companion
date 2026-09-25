#!/usr/bin/env python3
"""translit_uz.py — узбекская латиница (2021+) → кириллица, для второй версии карточек.

Правила — официальное соответствие алфавитов: sh→ш, ch→ч, oʻ→ў, gʻ→ғ, yo→ё, yu→ю, ya→я,
ye→е в начале слова и после гласной, e→э в начале слова и после гласной, ʼ→ъ, q→қ, h→ҳ, x→х.
Адреса сайтов, @имена и слова с цифрами не трогает. Итог наружу вычитывает носитель:
у заимствований бывают исключения (ts→ц, «е» в середине), их правят полем uz_cyrl вручную.

    python3 translit_uz.py "Oʻzbekiston Respublikasi"  →  Ўзбекистон Республикаси
"""
import re, sys

TURNED = "ʻ‘`'ʼ’"   # все варианты апострофа, какие встречаются в латинице
ONE = {"a": "а", "b": "б", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "ҳ", "i": "и", "j": "ж",
       "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ", "r": "р", "s": "с",
       "t": "т", "u": "у", "v": "в", "x": "х", "y": "й", "z": "з", "c": "с", "w": "в"}
# слова, где кириллица пишется не по буквам латиницы (заимствования, месяцы)
EXCEPT = {"korrupsiya": "коррупция", "sentabr": "сентябрь", "oktabr": "октябрь", "noyabr": "ноябрь",
          "dekabr": "декабрь", "yanvar": "январь", "fevral": "февраль", "aprel": "апрель", "iyun": "июнь",
          "iyul": "июль", "avgust": "август", "internet": "интернет", "telegram": "телеграм"}
KEEP = re.compile(r"(https?://\S+|\S+\.(?:uz|ru|com|org|net|io)\S*|@\w+|\w*\d\w*)")


def _case(src, dst):
    if src.isupper() and (len(src) > 1 or not dst):
        return dst.upper()
    if src[:1].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


def _word(w):
    low = w.lower()
    if re.search(r"c(?!h)|w", low) or (not w.isupper() and any(ch.isupper() for ch in w[1:])):
        return w      # c без h, w и ВнутренниеЗаглавные в узбекской латинице не бывают: CPR, Claude, ChatGPT

    for stem, cyr in EXCEPT.items():          # точное слово или слово с окончанием
        if low.startswith(stem) and (low == stem or low[len(stem):].isalpha()):
            rest = _word(w[len(stem):]) if len(w) > len(stem) else ""
            if stem.endswith(("abr", "var", "ral", "rel", "yun", "yul")) and rest:
                cyr = cyr.rstrip("ь")          # сентябрда, октябрнинг — мягкий знак уходит перед окончанием
            return _case(w[:len(stem)], cyr) + rest
    out, i, n = [], 0, len(w)
    while i < n:
        c, lo = w[i], w[i].lower()
        nxt = w[i + 1] if i + 1 < n else ""
        prev = w[i - 1].lower() if i else ""
        start = i == 0 or not prev.isalpha()
        after_vowel = prev in "aeiou"
        if lo in "og" and nxt and nxt in TURNED:
            out.append(_case(c, "ў" if lo == "o" else "ғ")); i += 2; continue
        pair = (lo + nxt.lower()) if nxt else ""
        if pair in ("sh", "ch"):
            out.append(_case(w[i:i + 2], "ш" if pair == "sh" else "ч")); i += 2; continue
        if pair == "ts" and low[i + 2:i + 4] in ("iy", "io"):
            out.append(_case(c, "ц")); i += 2; continue      # -tsiya, -tsion: информатсия → информация
        if pair in ("yo", "yu", "ya") and not (pair == "yo" and i + 2 < n and w[i + 2] in TURNED):
            out.append(_case(w[i:i + 2], {"yo": "ё", "yu": "ю", "ya": "я"}[pair])); i += 2; continue
        if pair == "ye" and (start or after_vowel):
            out.append(_case(w[i:i + 2], "е")); i += 2; continue
        if lo == "e":
            out.append(_case(c, "э" if (start or after_vowel) else "е")); i += 1; continue
        if c in TURNED:
            out.append("ъ" if (prev.isalpha() and nxt.isalpha()) or prev in "aeiou" else c); i += 1; continue
        if lo in ONE:
            out.append(_case(c, ONE[lo])); i += 1; continue
        out.append(c); i += 1
    return "".join(out)


def latn2cyrl(text):
    parts = KEEP.split(text or "")
    res = []
    for k, part in enumerate(parts):
        if k % 2:                      # защищённый кусок: адрес, @имя, слово с цифрами
            res.append(part); continue
        res.append(re.sub(r"[A-Za-z" + re.escape(TURNED) + r"]+", lambda m: _word(m.group(0)), part))
    return "".join(res)


if __name__ == "__main__":
    print(latn2cyrl(" ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()))
