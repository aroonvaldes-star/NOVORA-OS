"""Interfaz de ATLAS: panel flotante translúcido, inspirado en el
lenguaje visual de macOS pero original (sin recursos, iconos ni fuentes de
Apple). Sin recursos externos: funciona sin internet."""

PAGE = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ATLAS</title>
<style>
:root{--bg:#e9ecf2;--panel:rgba(255,255,255,.72);--line:rgba(0,0,0,.08);--text:#1d1f24;
--muted:#6b7280;--accent:#3b6cf6;--accent-ink:#fff;--chip:rgba(0,0,0,.05);--code:rgba(0,0,0,.06);
--ok:#1f9d55;--warn:#c27c0e;--bad:#d64545;--shadow:0 30px 80px rgba(20,30,60,.25)}
@media (prefers-color-scheme:dark){:root{--bg:#14161b;--panel:rgba(32,35,42,.74);--line:rgba(255,255,255,.09);
--text:#eceef3;--muted:#9aa1ad;--accent:#5b86ff;--chip:rgba(255,255,255,.07);--code:rgba(255,255,255,.08);
--shadow:0 30px 80px rgba(0,0,0,.55)}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:radial-gradient(1200px 600px at 20% 0%,rgba(91,134,255,.25),transparent),
radial-gradient(900px 500px at 90% 100%,rgba(160,90,255,.18),transparent),var(--bg);
color:var(--text);font:15px/1.5 system-ui,"Inter","Cantarell","Noto Sans",sans-serif;display:flex;justify-content:center;padding:6vh 16px}
.panel{width:min(760px,100%);background:var(--panel);backdrop-filter:blur(28px) saturate(1.6);
-webkit-backdrop-filter:blur(28px) saturate(1.6);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);overflow:hidden}
.bar{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--line)}
.dot{width:26px;height:26px;border-radius:8px;background:linear-gradient(135deg,#5b86ff,#a35bff);flex:none}
.bar input{flex:1;border:0;background:transparent;color:var(--text);font-size:20px;outline:none;min-width:0}
.bar input::placeholder{color:var(--muted)}
.chips{display:flex;gap:8px;flex-wrap:wrap;padding:10px 16px;border-bottom:1px solid var(--line)}
.chip{border:0;background:var(--chip);color:var(--text);border-radius:999px;padding:6px 12px;font:inherit;font-size:13px;cursor:pointer}
.chip:hover,.chip:focus-visible{background:var(--accent);color:var(--accent-ink);outline:none}
.chip.on{background:#e08a1e;color:#fff}
.status{margin-left:auto;font-size:12px;color:var(--muted);align-self:center}
#log{max-height:58vh;overflow:auto;padding:8px 16px 16px}
.msg{margin:12px 0;animation:in .18s ease-out}
@keyframes in{from{opacity:0;transform:translateY(4px)}to{opacity:1}}
@media (prefers-reduced-motion:reduce){.msg{animation:none}}
.me{color:var(--muted);font-size:13px}
.ai{white-space:pre-wrap;overflow-wrap:anywhere}
.ai code,.cmd code{background:var(--code);border-radius:6px;padding:1px 5px;font:13px ui-monospace,"JetBrains Mono","DejaVu Sans Mono",monospace}
pre{background:var(--code);border-radius:10px;padding:10px 12px;overflow:auto;white-space:pre}
.cmd{border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-top:8px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.tag{font-size:11px;border-radius:6px;padding:2px 7px;color:#fff}
.SOLO_LECTURA{background:var(--ok)}.CONFIRMAR{background:var(--warn)}.PROHIBIDO{background:var(--bad)}
.run{margin-left:auto;border:0;border-radius:8px;background:var(--accent);color:var(--accent-ink);padding:6px 12px;cursor:pointer;font:inherit;font-size:13px}
.err{color:var(--bad)}
.badge{display:inline-block;font-size:11px;border-radius:6px;padding:1px 7px;margin-bottom:4px;background:var(--chip);color:var(--muted)}
.sk{cursor:pointer}.sk:hover span{color:var(--accent)}
.list{list-style:none;padding:0;margin:6px 0}.list li{display:flex;gap:8px;align-items:center;padding:4px 0;border-bottom:1px solid var(--line)}
.list li.done span{text-decoration:line-through;color:var(--muted)}
details.steps{font-size:13px;color:var(--muted);margin:4px 0 8px}details.steps summary{cursor:pointer}
details.steps li{margin:3px 0;overflow-wrap:anywhere}.src{font-size:13px;color:var(--muted);margin-top:6px}
.foot{font-size:12px;color:var(--muted);padding:8px 16px;border-top:1px solid var(--line)}
</style></head><body>
<main class="panel" role="application" aria-label="ATLAS">
 <div class="bar"><div class="dot" aria-hidden="true"></div>
  <input id="q" autocomplete="off" placeholder="Pregúntale a ATLAS…" aria-label="Pregunta" autofocus></div>
 <div class="chips">
  <button class="chip" data-a="pantalla" title="Tienes 3 segundos para mostrar la ventana">Ver pantalla (3 s)</button>
  <button class="chip" data-a="region">Ver zona</button>
  <button class="chip" data-a="archivo">Explicar archivo</button>
  <button class="chip" data-a="agente" title="Escribe la tarea y pulsa: ATLAS la resuelve en pasos">Agente</button>
  <button class="chip" data-a="investigar" title="Investiga en tus documentos indexados, con citas">Investigar</button>
  <button class="chip" data-a="memoria" title="Indexar carpetas para investigar en ellas">Memoria</button>
  <button class="chip" data-a="resumen">Resumen del día</button>
  <button class="chip" data-a="organizar">Organizar mi día</button>
  <button class="chip" data-a="notas">Notas</button>
  <button class="chip" data-a="tareas">Tareas</button>
  <button class="chip" data-a="skills">Skills</button>
  <button class="chip" id="nube" data-a="nube" hidden title="Enviar esta conversación a la nube vía OmniRoute">☁ Nube: no</button>
  <button class="chip" data-a="nuevo">Nueva conversación</button>
  <span class="status" id="st">…</span>
 </div>
 <div id="log" aria-live="polite"></div>
 <div class="foot">Sin internet · todo se procesa en este equipo · el modo Agente solo ejecuta por su cuenta órdenes de lectura; lo demás espera tu confirmación</div>
</main>
<script>
const H=(location.hash||"").slice(1).split("&"),T=H[0],CAP=(H[1]||"").startsWith("captura=")?H[1].slice(8):"";history.replaceState(null,"",location.pathname);
const log=document.getElementById("log"),q=document.getElementById("q"),st=document.getElementById("st"),nb=document.getElementById("nube"),foot=document.querySelector(".foot");
let NUBE=false;const FOOT=foot.textContent;
function setNube(v){NUBE=v;nb.classList.toggle("on",v);nb.textContent=v?"☁ Nube: sí":"☁ Nube: no";
 foot.textContent=v?"MODO NUBE: tus preguntas, archivos y texto de pantalla salen hacia OmniRoute · el Agente solo ejecuta por su cuenta órdenes de lectura":FOOT}
async function api(path,body){if(body!==undefined&&NUBE&&typeof body==="object")body=Object.assign({nube:true},body);const r=await fetch(path,{method:body===undefined?"GET":"POST",
 headers:{"X-Atlas-Token":T,"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
 const d=await r.json().catch(()=>({error:"respuesta inválida"}));if(!r.ok)throw new Error(d.error||r.status);return d}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function fmt(s){let h=esc(s);h=h.replace(/```[a-zA-Z0-9]*\n([\s\S]*?)```/g,(m,c)=>"<pre>"+c+"</pre>");
 return h.replace(/`([^`\n]+)`/g,"<code>$1</code>")}
function add(cls,html){const d=document.createElement("div");d.className="msg "+cls;d.innerHTML=html;log.appendChild(d);log.scrollTop=log.scrollHeight;return d}
function show(out){const txt=(out.respuesta||"").split("\n").filter(l=>!/^ORDEN:\s/.test(l)).join("\n").trim();
 let pre="";if(out.pasos&&out.pasos.length){pre='<details class="steps"><summary>'+out.pasos.length+' pasos del agente</summary><ol>'+out.pasos.map(s=>"<li><code>"+esc(s.herramienta)+"</code> "+esc(JSON.stringify(s.argumentos)).slice(0,160)+" → "+esc((s.resultado||"").split("\n")[0]).slice(0,140)+"</li>").join("")+"</ol></details>"}
 const d=add("ai",(out.nube?'<span class="badge">☁ nube</span> ':"")+(out.skill?'<span class="badge">skill: '+esc(out.skill)+'</span>\n':(out.nube?"\n":""))+pre+fmt(txt));
 if(out.aviso)d.insertAdjacentHTML("beforeend",'<div class="src">'+esc(out.aviso)+"</div>");
 if(out.fuentes&&out.fuentes.length)d.insertAdjacentHTML("beforeend",'<div class="src"><b>Fuentes</b><br>'+out.fuentes.map(f=>"["+f.n+"] "+esc(f.ruta)+" · trozo "+f.trozo).join("<br>")+"</div>");
 (out.ordenes||[]).forEach(o=>cmd(d,o))}
function cmd(parent,o){const c=document.createElement("div");c.className="cmd";
 c.innerHTML='<span class="tag '+esc(o.nivel)+'">'+esc(o.nivel.replace("_"," "))+'</span><code>'+esc(o.orden)+'</code><small>'+esc(o.motivo)+'</small>'+(o.vista_previa?'<pre style="width:100%;max-height:220px">'+esc(o.vista_previa)+"</pre>":"");
 if(o.confirmacion){const b=document.createElement("button");b.className="run";b.textContent="Ejecutar";
  b.onclick=async()=>{if(!confirm("¿Ejecutar esta orden?\n\n"+o.orden))return;b.disabled=true;
   try{const r=await api("/api/orden/ejecutar",{confirmacion:o.confirmacion});
    add("ai","<pre>"+esc((r.salida||"")+(r.error?"\n"+r.error:""))+"</pre><small>código "+esc(r.codigo)+"</small>")}
   catch(e){add("err",esc(e.message))}};c.appendChild(b)}
 parent.appendChild(c)}
async function run(label,fn){add("me",esc(label));const w=add("ai","Pensando…");
 try{const out=await fn();w.remove();show(out)}catch(e){w.className="msg err";w.textContent=e.message}}
async function skillsList(){const items=await api("/api/skills");const d=add("ai","<b>Skills</b> · escribe <code>/nombre pregunta</code> o deja que ATLAS elija");
 const ul=document.createElement("ul");ul.className="list";items.forEach(it=>{const li=document.createElement("li");li.className="sk";
  const sp=document.createElement("span");sp.textContent=it.nombre+" — "+it.descripcion;li.appendChild(sp);
  li.onclick=()=>{q.value="/"+it.nombre+" ";q.focus()};ul.appendChild(li)});d.appendChild(ul)}
async function memoriaPanel(){const s=await api("/api/memoria");
 const d=add("ai","<b>Memoria</b> · "+s.documentos+" documentos, "+s.trozos+" trozos"+(s.ultima_indexacion?" · última vez "+esc(s.ultima_indexacion):"")+"\n");
 const b=document.createElement("button");b.className="run";b.textContent="Indexar una carpeta";b.style.marginLeft="0";
 b.onclick=async()=>{const p=prompt("Carpeta o archivo (ej. ~/Documentos o ~/NOVORA-LINK)");if(!p)return;b.disabled=true;b.textContent="Indexando…";
  try{const r=await api("/api/memoria/indexar",{rutas:[p]});add("ai","Indexado "+esc(p)+": "+r.nuevos+" nuevos, "+r.actualizados+" actualizados, "+r.omitidos+" omitidos.")}
  catch(e){add("err",esc(e.message))}finally{b.disabled=false;b.textContent="Indexar una carpeta"}};d.appendChild(b)}
async function list(kind){const items=await api("/api/"+kind);
 const d=add("ai","<b>"+(kind==="notas"?"Notas":"Tareas")+"</b>");const ul=document.createElement("ul");ul.className="list";
 items.forEach(it=>{const li=document.createElement("li");if(it.hecho)li.className="done";
  const cb=document.createElement("input");cb.type="checkbox";cb.checked=it.hecho;
  cb.onchange=()=>api("/api/"+kind+"/hecho",{id:it.id,hecho:cb.checked}).then(()=>li.classList.toggle("done",cb.checked));
  const sp=document.createElement("span");sp.textContent=it.texto+(it.fecha?" · "+it.fecha:"");li.append(cb,sp);ul.appendChild(li)});
 if(!items.length)ul.innerHTML="<li><span>Vacío. Escribe «"+(kind==="notas"?"nota:":"tarea:")+" …»</span></li>";d.appendChild(ul)}
q.addEventListener("keydown",async e=>{if(e.key!=="Enter"||!q.value.trim())return;const t=q.value.trim();q.value="";
 const m=t.match(/^(nota|tarea):\s*(.+)$/i);
 if(m){const kind=m[1].toLowerCase()==="nota"?"notas":"tareas";try{await api("/api/"+kind,{texto:m[2]});add("ai","Guardado en "+kind+".")}catch(err){add("err",esc(err.message))}return}
 if(t.startsWith("$ ")){try{const o=await api("/api/orden/proponer",{orden:t.slice(2)});cmd(add("ai",""),o)}catch(err){add("err",esc(err.message))}return}
 run(t,()=>api("/api/chat",{texto:t}))});
document.querySelectorAll(".chip").forEach(b=>b.onclick=()=>{const a=b.dataset.a;
 if(a==="pantalla")run("Ver pantalla (cambia de ventana: 3 s)",()=>api("/api/pantalla",{pregunta:q.value,espera_ms:3000}));
 else if(a==="region")run("Ver zona",()=>api("/api/pantalla",{pregunta:q.value,region:true}));
 else if(a==="archivo"){const p=prompt("Ruta del archivo (ej. ~/proyecto/main.py)");if(p)run("Explicar "+p,()=>api("/api/archivo",{ruta:p,pregunta:q.value}))}
 else if(a==="organizar")run("Organizar mi día",()=>api("/api/organizar",{}));
 else if(a==="agente"){const t=q.value.trim()||prompt("¿Qué tarea resuelvo en pasos? (ej. revisa los TODO de ~/NOVORA-LINK y crea tareas)");if(t){q.value="";run("Agente: "+t,()=>api("/api/agente",{tarea:t}))}}
 else if(a==="investigar"){const t=q.value.trim()||prompt("¿Qué investigo en tus documentos?");if(t){q.value="";run("Investigar: "+t,()=>api("/api/investigar",{pregunta:t}))}}
 else if(a==="resumen")run("Resumen del día",()=>api("/api/resumen",{}));
 else if(a==="memoria")memoriaPanel().catch(e=>add("err",esc(e.message)));
 else if(a==="nuevo")api("/api/reiniciar",{}).then(()=>{log.innerHTML=""});
 else if(a==="skills")skillsList().catch(e=>add("err",esc(e.message)));
 else if(a==="nube")setNube(!NUBE);
 else list(a)});
document.addEventListener("keydown",e=>{if(e.key==="Escape")window.close()});
if(CAP)run("Lo que había en pantalla",()=>api("/api/pantalla",{captura:CAP}));
api("/api/estado").then(s=>{nb.hidden=!s.nube_disponible;st.textContent=s.modelos.length?(s.modelos[0]+(s.vision?" · visión":"")):"sin modelo instalado"}).catch(e=>{st.textContent=e.message});
</script></body></html>
"""
