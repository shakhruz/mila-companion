#!/usr/bin/env python3
"""Холст в духе Excalidraw: spec.json -> out.html (+ out.excalidraw для правки на excalidraw.com).
SVG + rough.js (jsdelivr), панорама/зум, клик по узлу — подробности. Без сервера, открывается из file://.
Использование: canvas.py spec.json out.html
spec: {"title","subtitle","footer",
 "legend":[{"kind":"рождена","color":"#0f766e","dash":null,"label":"рождена"}],   # виды стрелок
 "groups":[{"id","title","x","y","w","h","color"}],
 "nodes":[{"id","icon":"🧸","title","sub","x","y","w":200,"h":80,"color","big":false,
           "details":{"Роль":"...","Владелец":"..."},"note":"текст"}],
 "edges":[{"from","to","kind":"рождена","label":"..."}]}
Координаты — в пикселях холста (x,y — левый верх). """
import sys, json, html, pathlib, random

def wrap(s, n):
    out, cur = [], ""
    for w in str(s).split():
        if len(cur) + len(w) + 1 > n and cur: out.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    if cur: out.append(cur)
    return out

def clip(n, tx, ty):
    """точка на границе прямоугольника узла n в направлении (tx,ty)"""
    cx, cy = n["x"] + n["w"] / 2, n["y"] + n["h"] / 2
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0: return cx, cy
    k = min((n["w"] / 2) / abs(dx) if dx else 1e9, (n["h"] / 2) / abs(dy) if dy else 1e9)
    return cx + dx * k, cy + dy * k

def excalidraw(s):
    els, rnd = [], random.Random(7)
    def base(t, x, y, w, h, **k):
        e = dict(id=f"e{len(els)+1}", type=t, x=x, y=y, width=w, height=h, angle=0, strokeColor="#1e1e1e",
                 backgroundColor="transparent", fillStyle="solid", strokeWidth=1, strokeStyle="solid", roughness=1,
                 opacity=100, groupIds=[], frameId=None, roundness=None, seed=rnd.randint(1, 2**31), version=1,
                 versionNonce=rnd.randint(1, 2**31), isDeleted=False, boundElements=None, updated=1, link=None, locked=False)
        e.update(k); els.append(e); return e
    def text(x, y, t, size=16, color="#1e1e1e", w=None, align="left"):
        lines = str(t).split("\n"); w = w or max(len(l) for l in lines) * size * 0.6
        return base("text", x, y, w, len(lines) * size * 1.25, text=str(t), fontSize=size, fontFamily=1,
                    textAlign=align, verticalAlign="top", baseline=int(size), containerId=None,
                    originalText=str(t), lineHeight=1.25, strokeColor=color)
    for g in s.get("groups", []):
        base("rectangle", g["x"], g["y"], g["w"], g["h"], strokeColor=g.get("color", "#888"), strokeStyle="dashed",
             roundness={"type": 3}, backgroundColor=g.get("fill", "transparent"), opacity=60)
        text(g["x"] + 14, g["y"] + 10, g["title"], 20, g.get("color", "#555"))
    N = {n["id"]: n for n in s["nodes"]}
    for n in N.values():
        n.setdefault("w", 200); n.setdefault("h", 80)
        base("rectangle", n["x"], n["y"], n["w"], n["h"], strokeColor=n.get("color", "#0f766e"),
             backgroundColor=n.get("fill", "#ffffff"), roundness={"type": 3}, strokeWidth=2)
        text(n["x"] + 10, n["y"] + 12, n.get("icon", ""), 28)
        text(n["x"] + 50, n["y"] + 12, "\n".join(wrap(n["title"], int((n["w"] - 60) / 9))[:2]) +
             ("\n" + "\n".join(wrap(n["sub"], int((n["w"] - 60) / 7.5))[:2]) if n.get("sub") else ""), 15)
    K = {l["kind"]: l for l in s.get("legend", [])}
    for e in s["edges"]:
        a, b = N[e["from"]], N[e["to"]]
        ca = (a["x"] + a["w"] / 2, a["y"] + a["h"] / 2); cb = (b["x"] + b["w"] / 2, b["y"] + b["h"] / 2)
        p1, p2 = clip(a, *cb), clip(b, *ca); kd = K.get(e.get("kind"), {})
        base("arrow", p1[0], p1[1], p2[0] - p1[0], p2[1] - p1[1], points=[[0, 0], [p2[0] - p1[0], p2[1] - p1[1]]],
             strokeColor=kd.get("color", "#555"), strokeStyle="dotted" if kd.get("dash") == "dot" else ("dashed" if kd.get("dash") else "solid"),
             strokeWidth=2, startBinding=None, endBinding=None, startArrowhead=None, endArrowhead="arrow", lastCommittedPoint=None)
        if e.get("label"): text((p1[0] + p2[0]) / 2 - 30, (p1[1] + p2[1]) / 2 - 10, e["label"], 13, kd.get("color", "#555"))
    return {"type": "excalidraw", "version": 2, "source": "naglyadno", "elements": els,
            "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}}

TPL = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><title>__TITLE__</title>
<style>
:root{--bg:#fbfaf6;--card:#fff;--ink:#1e2a28;--mut:#5d6b69;--line:#d9d4c7;--acc:#0f766e;--dot:#e4dfd2}
:root[data-theme=dark]{--bg:#111917;--card:#1a2522;--ink:#e8efec;--mut:#9bb0aa;--line:#2f3f3a;--acc:#2dd4bf;--dot:#1f2c28}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111917;--card:#1a2522;--ink:#e8efec;--mut:#9bb0aa;--line:#2f3f3a;--acc:#2dd4bf;--dot:#1f2c28}}
*{box-sizing:border-box}html,body{height:100%;margin:0}body{background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,sans-serif;overflow:hidden}
#bar{position:fixed;top:0;left:0;right:0;z-index:5;display:flex;gap:10px;align-items:center;padding:10px 14px;pointer-events:none}
#bar>*{pointer-events:auto}.ttl{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:6px 12px;max-width:60vw}
.ttl b{display:block;font-size:16px}.ttl span{color:var(--mut);font-size:12px}
.btn{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:10px;padding:7px 11px;cursor:pointer;font:inherit}
.sp{flex:1;pointer-events:none!important}
svg#cv{width:100vw;height:100vh;display:block;cursor:grab;touch-action:none;background-image:radial-gradient(var(--dot) 1.2px,transparent 1.2px);background-size:24px 24px}
svg#cv.drag{cursor:grabbing}.node{cursor:pointer}.node:hover .hl{opacity:1}.hl{opacity:0;transition:.15s}
#side{position:fixed;top:0;right:0;bottom:0;width:min(360px,100vw);background:var(--card);border-left:1px solid var(--line);z-index:6;padding:56px 18px 18px;overflow:auto;transform:translateX(105%);transition:.2s}
#side.on{transform:none}#side h3{margin:0 0 4px;font-size:20px}#side .ic{font-size:40px}
#side dl{margin:14px 0 0}#side dt{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em;margin-top:10px}#side dd{margin:2px 0 0}
#x{position:absolute;top:10px;right:12px}
#leg{position:fixed;left:12px;bottom:12px;z-index:5;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 12px;font-size:13px}
#leg i{display:inline-block;width:26px;border-top:3px solid;vertical-align:middle;margin-right:6px}
#foot{position:fixed;right:14px;bottom:10px;color:var(--mut);font-size:12px;z-index:4}
</style></head><body>
<div id="bar"><div class="ttl"><b>__TITLE__</b><span>__SUB__</span></div><div class="sp"></div>
<button class="btn" id="zi">＋</button><button class="btn" id="zo">−</button><button class="btn" id="fit">⤢ Всё</button>
<button class="btn" id="dl">⬇ .excalidraw</button><button class="btn" id="th">◐</button></div>
<svg id="cv" xmlns="http://www.w3.org/2000/svg"><g id="vp"></g></svg>
<aside id="side"><button class="btn" id="x">✕</button><div id="sc"></div></aside>
<div id="leg"></div><div id="foot">Колесо — масштаб · тащить — двигать · клик по карточке — подробности · __FOOT__</div>
<script id="scene" type="application/json">__SCENE__</script>
<script id="exc" type="application/json">__EXC__</script>
<script src="https://cdn.jsdelivr.net/npm/roughjs@4.6.6/bundled/rough.js"></script>
<script>
const S=JSON.parse(document.getElementById('scene').textContent);
const svg=document.getElementById('cv'),vp=document.getElementById('vp'),NS='http://www.w3.org/2000/svg',root=document.documentElement;
const FONT='"Comic Sans MS","Chalkboard SE","Segoe Print",system-ui,sans-serif';
function dark(){const t=root.dataset.theme;return t?t==='dark':matchMedia('(prefers-color-scheme:dark)').matches}
function el(n,a,p){const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);(p||vp).appendChild(e);return e}
function wrap(s,n){const o=[];let c='';String(s).split(/\s+/).forEach(w=>{if((c+' '+w).trim().length>n&&c){o.push(c);c=w}else c=(c+' '+w).trim()});if(c)o.push(c);return o}
function txt(p,x,y,t,sz,fill,wt,anchor){const e=el('text',{x,y,'font-size':sz,fill,'font-weight':wt||400,'font-family':FONT,'text-anchor':anchor||'start'},p);e.textContent=t;return e}
function col(c){return dark()&&c==='#1e1e1e'?'#e8efec':c}
const N={};S.nodes.forEach(n=>{n.w=n.w||200;n.h=n.h||80;N[n.id]=n});
const K={};(S.legend||[]).forEach(l=>K[l.kind]=l);
function clip(n,tx,ty){const cx=n.x+n.w/2,cy=n.y+n.h/2,dx=tx-cx,dy=ty-cy;if(!dx&&!dy)return[cx,cy];
 const k=Math.min(dx?(n.w/2)/Math.abs(dx):1e9,dy?(n.h/2)/Math.abs(dy):1e9);return[cx+dx*k,cy+dy*k]}
function draw(){
  vp.innerHTML='';const rc=rough.svg(svg),ink=getComputedStyle(root).getPropertyValue('--ink').trim(),
   card=getComputedStyle(root).getPropertyValue('--card').trim(),mut=getComputedStyle(root).getPropertyValue('--mut').trim();
  (S.groups||[]).forEach(g=>{const c=g.color||'#888';
   vp.appendChild(rc.rectangle(g.x,g.y,g.w,g.h,{stroke:c,strokeWidth:2,roughness:1.6,seed:11,fill:c,fillStyle:'solid',strokeLineDash:[10,8]}));
   const r=vp.lastChild;r.setAttribute('opacity',dark()?.14:.08);
   vp.appendChild(rc.rectangle(g.x,g.y,g.w,g.h,{stroke:c,strokeWidth:2,roughness:1.6,seed:11,strokeLineDash:[10,8]}));
   });
  S.edges.forEach((e,i)=>{const a=N[e.from],b=N[e.to];if(!a||!b)return;const kd=K[e.kind]||{color:mut};
   const p1=clip(a,b.x+b.w/2,b.y+b.h/2),p2=clip(b,a.x+a.w/2,a.y+a.h/2);
   const o={stroke:kd.color,strokeWidth:2.2,roughness:1.2,seed:30+i};if(kd.dash==='dash')o.strokeLineDash=[9,7];if(kd.dash==='dot')o.strokeLineDash=[2,7];
   vp.appendChild(rc.line(p1[0],p1[1],p2[0],p2[1],o));
   const ang=Math.atan2(p2[1]-p1[1],p2[0]-p1[0]),L=14;
   vp.appendChild(rc.linearPath([[p2[0]-L*Math.cos(ang-.45),p2[1]-L*Math.sin(ang-.45)],[p2[0],p2[1]],[p2[0]-L*Math.cos(ang+.45),p2[1]-L*Math.sin(ang+.45)]],{stroke:kd.color,strokeWidth:2.2,roughness:.6,seed:50+i}));
   if(e.label){const mx=(p1[0]+p2[0])/2,my=(p1[1]+p2[1])/2,w=e.label.length*7.2+12;
    el('rect',{x:mx-w/2,y:my-11,width:w,height:20,rx:6,fill:card,opacity:.92});txt(vp,mx,my+4,e.label,12.5,kd.color,600,'middle')}});
  (S.groups||[]).forEach(g=>{const w=g.title.length*13+20;el('rect',{x:g.x+8,y:g.y+8,width:w,height:30,rx:8,fill:card,opacity:.9});txt(vp,g.x+16,g.y+31,g.title,22,g.color||'#888',700)});
  S.nodes.forEach((n,i)=>{const g=el('g',{class:'node','data-id':n.id});const c=n.color||'#0f766e';
   const fill=dark()?(n.fillDark||'#22302c'):(n.fill||'#ffffff');
   g.appendChild(rc.rectangle(n.x,n.y,n.w,n.h,{stroke:c,strokeWidth:n.big?3.2:2,roughness:1.3,seed:100+i,fill:fill,fillStyle:'solid'}));
   const h=rc.rectangle(n.x-3,n.y-3,n.w+6,n.h+6,{stroke:c,strokeWidth:2,roughness:1.5,seed:200+i});h.setAttribute('class','hl');g.appendChild(h);
   const fs=n.big?20:15,lines=wrap(n.title,Math.floor((n.w-62)/(fs*.62))).slice(0,2),sub=n.sub?wrap(n.sub,Math.floor((n.w-62)/7.4)).slice(0,2):[];
   txt(g,n.x+12,n.y+n.h/2+10,n.icon||'',n.big?38:30);
   let y=n.y+n.h/2-((lines.length+sub.length)*17)/2+15;
   lines.forEach(l=>{txt(g,n.x+54,y,l,fs,ink,700);y+=fs+3});sub.forEach(l=>{txt(g,n.x+54,y,l,12,mut);y+=15})});
  const leg=document.getElementById('leg');leg.innerHTML=(S.legend||[]).map(l=>`<div><i style="border-color:${l.color};border-top-style:${l.dash==='dot'?'dotted':l.dash?'dashed':'solid'}"></i>${l.label}</div>`).join('');
}
// камера
let cam={x:0,y:0,k:1};function apply(){vp.setAttribute('transform',`translate(${cam.x} ${cam.y}) scale(${cam.k})`)}
function fit(){const xs=[],ys=[];(S.groups||[]).forEach(g=>{xs.push(g.x,g.x+g.w);ys.push(g.y,g.y+g.h)});S.nodes.forEach(n=>{xs.push(n.x,n.x+n.w);ys.push(n.y,n.y+n.h)});
 const x0=Math.min(...xs)-30,x1=Math.max(...xs)+30,y0=Math.min(...ys)-30,y1=Math.max(...ys)+30,W=innerWidth,H=innerHeight-50;
 cam.k=Math.min(W/(x1-x0),H/(y1-y0));cam.x=(W-(x1-x0)*cam.k)/2-x0*cam.k;cam.y=50+(H-(y1-y0)*cam.k)/2-y0*cam.k;apply()}
function zoom(f,cx,cy){cx=cx??innerWidth/2;cy=cy??innerHeight/2;const nk=Math.max(.12,Math.min(5,cam.k*f));cam.x=cx-(cx-cam.x)*nk/cam.k;cam.y=cy-(cy-cam.y)*nk/cam.k;cam.k=nk;apply()}
svg.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?1.12:1/1.12,e.clientX,e.clientY)},{passive:false});
const ptr=new Map();let moved=0,pd=0;
svg.addEventListener('pointerdown',e=>{ptr.set(e.pointerId,[e.clientX,e.clientY]);moved=0;svg.classList.add('drag');pd=0});
svg.addEventListener('pointermove',e=>{if(!ptr.has(e.pointerId))return;const o=ptr.get(e.pointerId);
 if(ptr.size===2){const ps=[...ptr.values()],d0=Math.hypot(ps[0][0]-ps[1][0],ps[0][1]-ps[1][1]);ptr.set(e.pointerId,[e.clientX,e.clientY]);const ps2=[...ptr.values()],d1=Math.hypot(ps2[0][0]-ps2[1][0],ps2[0][1]-ps2[1][1]);if(d0)zoom(d1/d0,(ps2[0][0]+ps2[1][0])/2,(ps2[0][1]+ps2[1][1])/2);moved+=9;return}
 const dx=e.clientX-o[0],dy=e.clientY-o[1];moved+=Math.abs(dx)+Math.abs(dy);cam.x+=dx;cam.y+=dy;ptr.set(e.pointerId,[e.clientX,e.clientY]);apply()});
const up=e=>{ptr.delete(e.pointerId);svg.classList.remove('drag')};svg.addEventListener('pointerup',up);svg.addEventListener('pointercancel',up);
// клик по узлу
svg.addEventListener('click',e=>{if(moved>6)return;const g=e.target.closest('.node');if(g)show(N[g.dataset.id]);else side.classList.remove('on')});
const side=document.getElementById('side'),sc=document.getElementById('sc');
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function show(n){let h=`<div class="ic">${n.icon||''}</div><h3>${esc(n.title)}</h3>${n.sub?`<div style="color:var(--mut)">${esc(n.sub)}</div>`:''}`;
 if(n.details)h+='<dl>'+Object.entries(n.details).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')+'</dl>';
 const rel=S.edges.filter(e=>e.from===n.id||e.to===n.id).map(e=>{const o=N[e.from===n.id?e.to:e.from];return `${e.from===n.id?'→':'←'} ${esc(e.label||e.kind||'')}: ${esc(o.title)}`});
 if(rel.length)h+='<dl><dt>Связи</dt>'+rel.map(r=>`<dd>${r}</dd>`).join('')+'</dl>';
 if(n.note)h+=`<p style="margin-top:14px">${esc(n.note)}</p>`;sc.innerHTML=h;side.classList.add('on')}
document.getElementById('x').onclick=()=>side.classList.remove('on');
document.addEventListener('keydown',e=>{if(e.key==='Escape')side.classList.remove('on')});
document.getElementById('zi').onclick=()=>zoom(1.25);document.getElementById('zo').onclick=()=>zoom(.8);document.getElementById('fit').onclick=fit;
document.getElementById('th').onclick=()=>{root.dataset.theme=dark()?'light':'dark';draw()};
document.getElementById('dl').onclick=()=>{const b=new Blob([document.getElementById('exc').textContent],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='__FNAME__.excalidraw';a.click()};
addEventListener('resize',fit);
function boot(){draw();fit();document.body.dataset.ready='1'}
if(window.rough)boot();else window.addEventListener('load',boot);
</script></body></html>'''

def main():
    sp, op = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    s = json.loads(sp.read_text(encoding="utf-8"))
    for n in s["nodes"]: n.setdefault("w", 200); n.setdefault("h", 80)
    exc = excalidraw(s)
    op.with_suffix(".excalidraw").write_text(json.dumps(exc, ensure_ascii=False), encoding="utf-8")
    j = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    h = (TPL.replace("__TITLE__", html.escape(s["title"])).replace("__SUB__", html.escape(s.get("subtitle", "")))
         .replace("__FOOT__", html.escape(s.get("footer", ""))).replace("__FNAME__", op.stem)
         .replace("__SCENE__", j(s)).replace("__EXC__", j(exc)))
    op.write_text(h, encoding="utf-8")
    print(f"ok {op} {op.stat().st_size//1024} КБ; узлов {len(s['nodes'])}, связей {len(s['edges'])}; {op.with_suffix('.excalidraw').name}")

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
