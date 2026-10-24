// Ejecuta el layout.js de NOVORA contra una API de Plasma simulada (node tests/visual/test_layout.js RUTA).
const fs = require('fs'), vm = require('vm');
const log = { panels: [], desktops: [] };
class Widget { constructor(t){ this.type=t; this.cfg={}; this.currentConfigGroup=[]; }
  writeConfig(k,v){ this.cfg[this.currentConfigGroup.join('/')+'/'+k]=v; } }
class Panel { constructor(){ this.widgets=[]; log.panels.push(this); }
  addWidget(t){ const w=new Widget(t); this.widgets.push(w); return w; } }
const desk = () => { const d=new Widget('desktop'); log.desktops.push(d); return d; };
const ctx = { Panel, gridUnit: 18, desktops: () => [desk(), desk()], Math };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'), ctx);
const ok = (c,m) => { console.log((c?'  PASÓ  ':'  FALLÓ ')+m); if(!c) process.exitCode=1; };
const [barra, dock] = log.panels;
ok(log.panels.length===2, 'crea 2 paneles');
ok(barra.location==='top' && barra.lengthMode==='fill' && !barra.floating, 'barra superior de ancho completo');
ok(barra.widgets.map(w=>w.type).join()==='org.kde.plasma.kickoff,org.kde.plasma.appmenu,org.kde.plasma.panelspacer,org.kde.plasma.systemtray,org.kde.plasma.digitalclock', 'barra: lanzador, menú global, espacio, bandeja, reloj');
ok(dock.location==='bottom' && dock.floating && dock.lengthMode==='fit' && dock.alignment==='center' && dock.hiding==='dodgewindows', 'dock inferior flotante, centrado, ajustado, se aparta de ventanas');
ok(dock.widgets[0].cfg['General/launchers'].includes('applications:novora-atlas.desktop'), 'ATLAS anclado en el dock');
ok(log.desktops.every(d=>d.wallpaperPlugin==='org.kde.image' && d.cfg['Wallpaper/org.kde.image/General/Image']==='file:///usr/share/wallpapers/Novora/'), 'fondo NOVORA en todos los escritorios');
