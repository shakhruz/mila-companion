#!/usr/bin/env python3
"""Галерея схем и графиков: spec.json -> один самодостаточный HTML (светлая/тёмная тема).
Карточки: mermaid | chart | image | text. Библиотеки — только cdnjs/jsdelivr.
Использование: gallery.py spec.json out.html
spec: {"title","subtitle","footer","cols":2,"cards":[
  {"type":"mermaid","title","code","takeaway","wide":false},
  {"type":"chart","title","chart":{"type":"bar|line|pie|doughnut","labels":[],"datasets":[{"label","data":[]}]},"takeaway"},
  {"type":"image","title","src":"path.png","takeaway"},
  {"type":"text","title","big":"386 → 10","body":"...","takeaway"}]}
"""
import sys, json, html, base64, mimetypes, pathlib

def esc(s): return html.escape(str(s), quote=True)

def card(c, base):
    t = c.get("type", "text"); cls = "card wide" if c.get("wide") else "card"
    h = f'<h2>{esc(c["title"])}</h2>' if c.get("title") else ""
    if t == "mermaid":
        body = f'<div class="mm" data-src="{esc(c["code"])}"></div>'
    elif t == "chart":
        body = f'<div class="cw"><canvas class="ch" data-cfg="{esc(json.dumps(c["chart"], ensure_ascii=False))}"></canvas></div>'
    elif t == "image":
        p = pathlib.Path(c["src"]); p = p if p.is_absolute() else base / p
        mt = mimetypes.guess_type(p.name)[0] or "image/png"
        b = base64.b64encode(p.read_bytes()).decode()
        body = f'<img class="pic" alt="{esc(c.get("title",""))}" src="data:{mt};base64,{b}">'
    else:
        body = f'<div class="big">{esc(c.get("big",""))}</div><p class="tx">{esc(c.get("body",""))}</p>'
    tk = f'<p class="take">{esc(c["takeaway"])}</p>' if c.get("takeaway") else ""
    return f'<section class="{cls}">{h}{body}{tk}</section>'

TPL = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>
:root{--bg:#f6f4ee;--card:#fff;--ink:#1d2b2a;--mut:#5d6b69;--line:#d9d4c7;--acc:#0f766e;--acc2:#c2410c;--acc3:#7c5cbf;--acc4:#b08900}
:root[data-theme=dark]{--bg:#101716;--card:#18221f;--ink:#e8efec;--mut:#9bb0aa;--line:#2b3a36;--acc:#2dd4bf;--acc2:#fb923c;--acc3:#a78bfa;--acc4:#facc15}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#101716;--card:#18221f;--ink:#e8efec;--mut:#9bb0aa;--line:#2b3a36;--acc:#2dd4bf;--acc2:#fb923c;--acc3:#a78bfa;--acc4:#facc15}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{max-width:1200px;margin:0 auto;padding:28px 16px 8px;display:flex;gap:12px;align-items:flex-start;justify-content:space-between}
h1{margin:0;font-size:clamp(24px,4vw,36px);line-height:1.15}.sub{color:var(--mut);margin:6px 0 0}
button.th{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:8px 14px;cursor:pointer;font:inherit}
main{max-width:1200px;margin:0 auto;padding:16px;display:grid;grid-template-columns:repeat(__COLS__,minmax(0,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;min-width:0}
.wide{grid-column:1/-1}h2{margin:0 0 12px;font-size:18px}
.mm{overflow:auto;text-align:center}.mm svg{max-width:100%;height:auto}
.cw{position:relative;height:300px}.pic{width:100%;border-radius:10px;display:block}
.big{font-size:clamp(36px,6vw,56px);font-weight:700;color:var(--acc);line-height:1.1}.tx{color:var(--mut);margin:8px 0 0}
.take{margin:14px 0 0;padding-top:10px;border-top:1px dashed var(--line);font-weight:600}
footer{max-width:1200px;margin:0 auto;padding:8px 16px 40px;color:var(--mut);font-size:14px}
@media(max-width:760px){main{grid-template-columns:1fr}.cw{height:260px}}
</style></head><body>
<header><div><h1>__TITLE__</h1><p class="sub">__SUB__</p></div><button class="th" id="th" aria-label="Тема">◐ Тема</button></header>
<main>__CARDS__</main><footer>__FOOT__</footer>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
const root=document.documentElement;
function dark(){const t=root.dataset.theme;return t?t==='dark':matchMedia('(prefers-color-scheme:dark)').matches}
function cv(n){return getComputedStyle(root).getPropertyValue(n).trim()}
async function drawMermaid(){
  mermaid.initialize({startOnLoad:false,theme:dark()?'dark':'default',securityLevel:'loose',fontFamily:'system-ui,sans-serif'});
  let i=0;for(const el of document.querySelectorAll('.mm')){
    try{const {svg}=await mermaid.render('m'+(i++)+'_'+Date.now(),el.dataset.src);el.innerHTML=svg}
    catch(e){el.textContent='Ошибка схемы: '+e.message}}
}
const charts=[];
function drawCharts(){
  charts.splice(0).forEach(c=>c.destroy());
  const pal=[cv('--acc'),cv('--acc2'),cv('--acc3'),cv('--acc4')];
  Chart.defaults.color=cv('--ink');Chart.defaults.borderColor=cv('--line');Chart.defaults.font.family='system-ui,sans-serif';
  document.querySelectorAll('canvas.ch').forEach(cn=>{
    const cfg=JSON.parse(cn.dataset.cfg),pie=/pie|doughnut/.test(cfg.type);
    cfg.datasets.forEach((d,i)=>{d.backgroundColor=d.backgroundColor||(pie?cfg.labels.map((_,k)=>pal[k%4]):pal[i%4]);d.borderColor=d.borderColor||(pie?cv('--card'):pal[i%4]);if(cfg.type==='line'){d.tension=.3;d.backgroundColor=pal[i%4]+'33'}});
    charts.push(new Chart(cn,{type:cfg.type,data:{labels:cfg.labels,datasets:cfg.datasets},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:pie||cfg.datasets.length>1}},scales:pie?{}:{y:{beginAtZero:true}}}}))});
}
function all(){drawMermaid();drawCharts()}
document.getElementById('th').onclick=()=>{root.dataset.theme=dark()?'light':'dark';all()};
window.addEventListener('load',()=>{all();document.body.dataset.ready='1'});
</script></body></html>'''

def main():
    spec_p, out_p = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    s = json.loads(spec_p.read_text(encoding="utf-8")); base = spec_p.parent
    cards = "\n".join(card(c, base) for c in s["cards"])
    h = (TPL.replace("__TITLE__", esc(s["title"])).replace("__SUB__", esc(s.get("subtitle", "")))
         .replace("__COLS__", str(s.get("cols", 2))).replace("__FOOT__", esc(s.get("footer", "")))
         .replace("__CARDS__", cards))
    out_p.write_text(h, encoding="utf-8"); print(f"ok {out_p} {out_p.stat().st_size//1024} КБ, карточек {len(s['cards'])}")

def queue(out, w=1280, h=900):
    """В контейнере нет Chrome: заявка в очередь рендера хоста (PNG рядом с HTML), как в infographic."""
    import os
    W = os.path.realpath(os.path.expanduser("~/work")); o = os.path.realpath(str(out))
    if not o.startswith(W + "/"): sys.exit("для --queue HTML должен лежать внутри ~/work")
    rel = os.path.relpath(os.path.dirname(o), W); name = os.path.basename(o)
    req = {"project": rel, "html": name, "format": "png", "width": w, "height": h, "output": f"{rel}/{name.rsplit('.',1)[0]}.png"}
    q = os.path.join(W, "render-queue"); os.makedirs(q, exist_ok=True)
    qf = os.path.join(q, "nag-" + name.rsplit(".", 1)[0] + ".json"); json.dump(req, open(qf, "w", encoding="utf-8"), ensure_ascii=False)
    print("заявка", qf, "-> ждать", qf[:-5] + ".done")

if __name__ == "__main__":
    main()
    if "--queue" in sys.argv:
        a = [x for x in sys.argv[1:] if x != "--queue"]; queue(a[1], *(int(x) for x in a[2:4]))
