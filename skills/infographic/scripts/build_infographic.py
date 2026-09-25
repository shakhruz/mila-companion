#!/usr/bin/env python3
"""build_infographic.py — HTML-инфографика в фирменном стиле (запасной путь, без генерации картинки).

Вход: JSON {"kicker","title","lead","takeaway","date","rows":[{"title","desc"}...]}.
Выход: <out>.html и, с --queue, заявка в очередь рендера хоста (PNG появится рядом).

    python3 build_infographic.py data.json ~/work/info/card.html 1080 1350 [--queue]

В контейнере нет Chrome: PNG рисует хост. --queue кладёт ~/work/render-queue/<имя>.json,
результат — <имя>.done рядом с заявкой и PNG по пути "output".
Пути в заявке — от ~/work (без префикса work/). Только stdlib.
"""
import html, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, "..", "templates", "infographic-brand.html")
WORK = os.path.expanduser("~/work")


def esc(s):
    return html.escape(s or "", quote=False)


def main(a):
    data = json.load(open(a[0], encoding="utf-8"))
    out_html = os.path.abspath(os.path.expanduser(a[1]))
    w, h = int(a[2]), int(a[3])
    rows = "\n".join(
        '    <div class="row"><div class="num">%d</div><div class="rowtext">'
        '<div class="rowtitle">%s</div><div class="rowdesc">%s</div></div></div>'
        % (i, esc(r["title"]), esc(r["desc"])) for i, r in enumerate(data["rows"], 1))
    out = (open(TPL, encoding="utf-8").read()
           .replace("__W__", str(w)).replace("__H__", str(h))
           .replace("__KICKER__", esc(data.get("kicker", "")))
           .replace("__TITLE__", data.get("title", ""))        # допускает <em>
           .replace("__LEAD__", esc(data.get("lead", "")))
           .replace("__TAKEAWAY__", data.get("takeaway", ""))  # допускает <em>
           .replace("__ROWS__", rows)
           .replace("__DATE__", esc(data.get("date", ""))))
    os.makedirs(os.path.dirname(out_html), exist_ok=True)
    open(out_html, "w", encoding="utf-8").write(out)
    print("ok", out_html)
    if "--queue" in a:
        if not out_html.startswith(WORK + "/"):
            sys.exit("для очереди HTML должен лежать внутри ~/work")
        rel_dir = os.path.relpath(os.path.dirname(out_html), WORK)
        name = os.path.basename(out_html)
        png = name.rsplit(".", 1)[0] + ".png"
        req = {"project": rel_dir, "html": name, "format": "png", "width": w, "height": h,
               "output": "%s/%s" % (rel_dir, png)}
        q = os.path.join(WORK, "render-queue")
        os.makedirs(q, exist_ok=True)
        qf = os.path.join(q, "info-" + name.rsplit(".", 1)[0] + ".json")
        json.dump(req, open(qf, "w", encoding="utf-8"), ensure_ascii=False)
        print("заявка", qf, "→ ждать", qf[:-5] + ".done")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    main(sys.argv[1:])
