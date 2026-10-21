// The designer's systems, played: J=job_N OUT=prefix node _designprobe.mjs
// Prints the design and what each system did; shoots the hero's view at the
// start, after moving out, and from above.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(4000);
const O = process.env.OUT || 'design';
const st = () => p.evaluate(() => window.__design && window.__design());
console.log('start ', JSON.stringify(await st()));
console.log('level ', JSON.stringify(await p.evaluate(() => { const L = window.__spec.world.level || {}; return { layout: L.layout, path: (L.path || []).length, goal: L.goal, pts: (L.collect_points || []).length }; })));
await p.screenshot({ path: `${O}_start.jpg`, type: 'jpeg', quality: 85 });
// walk out: halfway toward the next thing, then wait a while out in the world
await p.evaluate(() => { const L = window.__spec.world.level; const t = (L.collect_points && L.collect_points[0]) || L.goal; const q = window.__game.pos();
  window.__game.tp(q[0] + (t[0] - q[0]) * 0.5, q[2] + (t[1] - q[2]) * 0.5); });
await wait(9000);
console.log('out   ', JSON.stringify(await st()));
await p.screenshot({ path: `${O}_out.jpg`, type: 'jpeg', quality: 85 });
// lamps: walk to the first lamp, if there is one
const lamp = await p.evaluate(() => { const s = window.__scene; let L = null; s.traverse(o => { if (!L && o.isGroup && o.children.length === 3 && o.children[2].geometry && o.children[2].geometry.type === 'ConeGeometry') L = [o.position.x, o.position.z]; }); return L; });
if (lamp) { await p.evaluate(l => window.__game.tp(l[0] + 1, l[1] + 1), lamp); await wait(1500); console.log('lamp  ', JSON.stringify(await st())); }
// home again
await p.evaluate(() => window.__game.tp(0.5, 0.5)); await wait(2500);
console.log('home  ', JSON.stringify(await st()));
const geo = await p.evaluate(() => ({ pp: window.__game.pos(), g: window.__spec.world.level.goal }));
await p.evaluate(v => { window.__camPin = v; }, { pos: [geo.pp[0] - 30, geo.pp[1] + 55, geo.pp[2] - 30], look: [geo.g[0] * 0.4, 0, geo.g[1] * 0.4] });
await wait(1800); await p.screenshot({ path: `${O}_high.jpg`, type: 'jpeg', quality: 85 });
console.log('errors', JSON.stringify(errs));
await b.close();
