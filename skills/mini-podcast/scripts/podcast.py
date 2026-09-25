#!/usr/bin/env python3
"""podcast.py — мини-подкаст двумя голосами: сценарий JSON → ElevenLabs Text to Dialogue → один mp3.

    python3 podcast.py script.json out.mp3 [--key-file ~/work/secrets/elevenlabs.key] [--stability 0.5] [--dry]

script.json — список реплик: [{"speaker": "Надя", "voice": "<voice_id>", "text": "..."}, ...]
  voice — voice_id из библиотеки ElevenLabs (или из своего аккаунта). speaker — только для чтения человеком.

Что делает:
  • режет сценарий на куски ≤ 1900 знаков по границам реплик (лимит API 2000 на вызов);
  • каждый кусок — один вызов /v1/text-to-dialogue, модель eleven_v3 (понимает [laughs], [thoughtful]);
  • склеивает куски ffmpeg без перекодирования, печатает длительность и громкость.
--dry — только посчитать знаки и куски, ничего не тратить.
Ключ: переменная ELEVENLABS_API_KEY или файл --key-file (по умолчанию ~/work/secrets/elevenlabs.key). Не печатается.
Только stdlib + ffmpeg/ffprobe.
"""
import json, os, re, subprocess, sys, tempfile, urllib.request

API = "https://api.elevenlabs.io/v1/text-to-dialogue?output_format=mp3_44100_128"
LIMIT = 1900


def arg(a, flag, default=None):
    return a[a.index(flag) + 1] if flag in a else default


def chunks(items):
    out, cur, n = [], [], 0
    for it in items:
        L = len(it["text"])
        if L > LIMIT:
            sys.exit("🔴 реплика длиннее %d знаков — раздели её: %s…" % (LIMIT, it["text"][:60]))
        if cur and n + L > LIMIT:
            out.append(cur); cur, n = [], 0
        cur.append(it); n += L
    if cur:
        out.append(cur)
    return out


def key(a):
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if k:
        return k
    path = os.path.expanduser(arg(a, "--key-file", "~/work/secrets/elevenlabs.key"))
    if not os.path.exists(path):
        sys.exit("🔴 нет ключа ElevenLabs (ни ELEVENLABS_API_KEY, ни %s)" % path)
    return open(path).read().strip()


def call(k, part, stability):
    body = {"inputs": [{"text": it["text"], "voice_id": it["voice"]} for it in part], "model_id": "eleven_v3"}
    if stability is not None:
        body["settings"] = {"stability": float(stability)}
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                 headers={"xi-api-key": k, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def probe(path):
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", path], capture_output=True, text=True).stdout.strip()
    vol = subprocess.run(["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    mean = re.search(r"mean_volume: (-?[\d.]+)", vol)
    peak = re.search(r"max_volume: (-?[\d.]+)", vol)
    return float(dur or 0), mean and float(mean.group(1)), peak and float(peak.group(1))


def main(a):
    if len(a) < 2:
        sys.exit(__doc__)
    items = json.load(open(a[0], encoding="utf-8"))
    out = a[1]
    parts = chunks(items)
    total = sum(len(i["text"]) for i in items)
    voices = {i["voice"] for i in items}
    print("реплик %d · знаков %d · кусков %d · голосов %d" % (len(items), total, len(parts), len(voices)))
    if "--dry" in a:
        return
    k = key(a)
    tmp = tempfile.mkdtemp(prefix="podcast-")
    files = []
    for n, part in enumerate(parts, 1):
        f = os.path.join(tmp, "part%02d.mp3" % n)
        open(f, "wb").write(call(k, part, arg(a, "--stability")))
        files.append(f)
        print("кусок %d готов, %d знаков" % (n, sum(len(i["text"]) for i in part)))
    if len(files) == 1:
        os.replace(files[0], out)
    else:
        lst = os.path.join(tmp, "list.txt")
        open(lst, "w").write("".join("file '%s'\n" % f for f in files))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c", "copy", out], check=True)
    dur, mean, peak = probe(out)
    print("ok %s · %.1f с · средняя %s дБ · пик %s дБ" % (out, dur, mean, peak))
    if mean is not None and mean < -30:
        print("⚠️ тихо: средняя громкость ниже −30 дБ")
    if peak is not None and peak > -0.1:
        print("⚠️ пик у нуля — возможен клиппинг")


if __name__ == "__main__":
    main(sys.argv[1:])
