import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const logs = []; p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') logs.push(m.text().slice(0, 160)); });
p.on('pageerror', e => logs.push('PAGEERROR ' + e.message.slice(0,160)));
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.A + '/dist/', { waitUntil:'domcontentloaded', timeout:120000 });
await new Promise(r => setTimeout(r, 9000));
const btn = await p.$('#startbtn'); if (btn) await btn.click();
await new Promise(r => setTimeout(r, 2000));
const r = await p.evaluate(() => {
  const sc = window.__scene, cam = window.__camera; let meshes = 0, lights = 0, visible = 0, tris = 0; const names = {};
  if (sc) sc.traverse(o => { if (o.isMesh) { meshes++; if (o.visible) visible++; const g = o.geometry; if (g && g.index) tris += g.index.count / 3; else if (g && g.attributes.position) tris += g.attributes.position.count / 3; const n = (o.name || o.parent?.name || 'anon').split(/[_\d]/)[0]; names[n] = (names[n] || 0) + 1; } if (o.isLight) lights++; });
  const f = window.__game && window.__game.facts ? window.__game.facts() : null;
  return { hasScene: !!sc, meshes, visible, lights, tris: Math.round(tris), cam: cam ? { pos: cam.position.toArray().map(v => +v.toFixed(1)), fov: cam.fov, far: cam.far } : null,
           bg: sc && sc.background ? (sc.background.isColor ? '#' + sc.background.getHexString() : 'tex') : null, fog: sc && sc.fog ? sc.fog.constructor.name : null,
           names: Object.entries(names).sort((a, b) => b[1] - a[1]).slice(0, 14), facts: f ? Object.keys(f).slice(0, 20) : null, style: document.body.className, pr: window.devicePixelRatio, canvas: [document.querySelector('canvas').width, document.querySelector('canvas').height] };
});
console.log(JSON.stringify(r, null, 0)); console.log('logs:', logs.slice(0, 8).join(' | ') || 'none');
await b.close();
