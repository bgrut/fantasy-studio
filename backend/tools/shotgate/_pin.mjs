// a pinned shot of a job: J=job_N PIN='<json or a named view>' OUT=file.jpg node _pin.mjs
// named views: "fwd", "face", "sea", "arena", "smithy", {"poi": k}, or {pos:[..], look:[..]}
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 9000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500)); await p.keyboard.press('g');
await p.evaluate(v => {
  const pos = () => window.__game.pos();
  if (v && v.poi !== undefined) { const q = window.__spec.world.level.pois[v.poi], y = pos()[1]; v = { pos: [q.x + 7, y + 4, q.z + 7], look: [q.x, y + 1, q.z] }; }
  else if (v === 'face') { const p0 = pos(), hd = window.__game.heading ? window.__game.heading() : 0, fx = Math.sin(hd), fz = Math.cos(hd); v = { pos: [p0[0] - fx * 1.1, p0[1] + 1.62, p0[2] - fz * 1.1], look: [p0[0], p0[1] + 1.6, p0[2]] }; }
  else if (v === 'sea') { const p0 = pos(), a = window.__spec.world.level.coast.axis, nx = -a[1], nz = a[0]; v = { pos: [p0[0] + nx * 3 - a[0] * 6, p0[1] + 3.2, p0[2] + nz * 3 - a[1] * 6], look: [p0[0] + nx * 16 + a[0] * 10, p0[1] - 0.5, p0[2] + nz * 16 + a[1] * 10] }; }
  else if (v === 'goalfar') { const g = window.__spec.world.level.goal, gl = Math.hypot(g[0], g[1]) || 1, ux = g[0] / gl, uz = g[1] / gl, y = pos()[1];
    v = { pos: [g[0] - ux * 46 + uz * 18, y + 14, g[1] - uz * 46 - ux * 18], look: [g[0] - ux * 8, y + 6, g[1] - uz * 8] }; }
  else if (v && v.rel) { const y = pos()[1]; v = { pos: [v.rel[0], y + v.rel[1], v.rel[2]], look: [v.at[0], y + v.at[1], v.at[2]] }; }
  else if (v === 'fwd') { const p0 = pos(); v = { pos: [p0[0], p0[1] + 1.9, p0[2] + 2], look: [p0[0], p0[1] + 1.1, p0[2] + 12] }; }
  else if (v === 'arena') { const g = window.__spec.world.level.goal, gl = Math.hypot(g[0], g[1]), ux = g[0] / gl, uz = g[1] / gl, cx = ux * 14, cz = uz * 14, y = pos()[1]; v = { pos: [cx - ux * 70 - uz * 60, y + 22, cz - uz * 70 + ux * 60], look: [cx, y + 14, cz] }; }
  else if (v === 'smithy') { const s = window.__smithy, fx = Math.sin(s.ry), fz = Math.cos(s.ry); v = { pos: [s.at[0] + fx * 7 + fz * 2, 2.4 + pos()[1], s.at[1] + fz * 7 - fx * 2], look: [s.at[0], 1.2 + pos()[1], s.at[1]] }; }
  window.__camPin = v;
}, JSON.parse(process.env.PIN));
await new Promise(r => setTimeout(r, 2500));
await p.screenshot({ path: process.env.OUT, type: 'jpeg', quality: 88 }); await b.close();
