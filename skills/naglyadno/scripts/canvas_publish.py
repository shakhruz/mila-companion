#!/usr/bin/env python3
"""Опубликовать холст на свой сервер Excalidraw-холстов и напечатать ссылку.
  canvas_publish.py spec.json|file.excalidraw [--title "Название"] [--update <id>]
Вход spec.json (как у canvas.py) конвертируется в сцену Excalidraw. Ссылка = доступ, открывается на телефоне и компьютере,
правки сохраняются на сервере.
Адрес сервера — переменная MILA_CANVAS_URL (например https://canvas.example.com); CANVAS_API — необязательный
внутренний адрес того же API (из контейнера). Сервер API: POST /api/scene → {"id"}, PUT /api/scene/<id>.
MILA_CANVAS_URL не задан → холст публиковать некуда: рядом со входом кладётся файл .excalidraw (открыть на
excalidraw.com → Open) и печатается его путь."""
import json, os, sys, urllib.request, importlib.util
from pathlib import Path

PUBLIC = os.environ.get("MILA_CANVAS_URL", "").rstrip("/")
APIS = [os.environ.get("CANVAS_API", "").rstrip("/"), PUBLIC]

def load_scene(p):
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    if d.get("type") == "excalidraw" and isinstance(d.get("elements"), list):
        return d
    spec = importlib.util.spec_from_file_location("canvas", Path(__file__).with_name("canvas.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.excalidraw(d)

def call(base, method, path, body):
    req = urllib.request.Request(base + path, data=body, method=method, headers={"content-type": "application/json", "user-agent": "canvas-publish"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("-"): sys.exit(__doc__)
    src = a[0]; title = None; upd = None
    if "--title" in a: title = a[a.index("--title") + 1]
    if "--update" in a: upd = a[a.index("--update") + 1]
    sc = load_scene(src)
    if title: sc["title"] = title
    if not PUBLIC:
        out = Path(src).with_suffix(".excalidraw")
        if out.resolve() != Path(src).resolve():
            out.write_text(json.dumps(sc, ensure_ascii=False), encoding="utf-8")
        print(f"MILA_CANVAS_URL не задан — ссылки нет, отправьте файл: {out}"); return
    body = json.dumps(sc, ensure_ascii=False).encode()
    if len(body) > 5 * 1024 * 1024: sys.exit("сцена больше 5 МБ")
    err = []
    for b in [x for x in APIS if x]:
        try:
            if upd: call(b, "PUT", f"/api/scene/{upd}", body); sid = upd
            else: sid = call(b, "POST", "/api/scene", body)["id"]
            print(f"{PUBLIC}/#{sid}"); return
        except Exception as e: err.append(f"{b}: {e}")
    sys.exit("не вышло: " + "; ".join(err))
main()
