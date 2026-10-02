// The forest, three ways: as played, from a hilltop over the land beyond,
// and at eye height inside the trees. Prints the grown-forest counts and
// the frame's draw cost, and writes forest_<view>.jpg.
//   J=job_309 OUT=<dir> [Q=balanced] node forestshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.';
const q = process.env.Q ? `?q=${process.env.Q}` : '';
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 900 });
const errs = [];
p.on('pageerror', e => errs.push(e.message));
p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
p.on('response', r => { if (r.status() >= 400) errs.push(r.status() + ' ' + r.url().split('/dist/')[1]); });
const view = process.env.VIEW ? process.env.VIEW.split(',').map(Number) : null;   // hilltop look direction x,z
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html${q}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 2500));
await p.keyboard.press('g');                       // skip the guide
await new Promise(r => setTimeout(r, 3500));
const info = await p.evaluate(() => ({ flora: window.__flora, tris: window.__frameTris, calls: window.__frameCalls,
  fps: (document.getElementById('fps') || {}).textContent }));
console.log(JSON.stringify(info));
await p.screenshot({ path: `${OUT}/forest_play.jpg`, type: 'jpeg', quality: 90 });
const views = await p.evaluate(() => {
  const pp = window.__game.pos();
  const S = (window.__spec || {}).world || {};
  return { pp };
});
const pp = views.pp;
// a hilltop: high above the spawn, looking out over the land beyond
await p.evaluate((pp, v) => {
  const d = v || [400, 400];
  window.__camPin = { pos: [pp[0] - d[0] * 0.1, pp[1] + 70, pp[2] - d[1] * 0.1], look: [pp[0] + d[0], pp[1] - 10, pp[2] + d[1]] };
}, pp, view);
if (process.env.PASSOFF !== undefined) console.log('passes', await p.evaluate((off) => {
  const c = window.__composer; if (!c) return 'no composer handle';
  const names = c.passes.map((q, i) => i + ':' + (q.name || q.constructor.name) + (q.enabled ? '' : '(off)'));
  for (const i of off.split(',').filter(Boolean).map(Number)) if (c.passes[i]) c.passes[i].enabled = false;
  return names.join(' ');
}, process.env.PASSOFF));
if (process.env.DUMP) console.log('csm census', await p.evaluate(() => {
  const seen = new Set(); let yes = 0; const no = [];
  window.__scene.traverse(o => { if (!o.material) return; for (const m of [].concat(o.material)) { if (seen.has(m) || !(m.isMeshStandardMaterial || m.isMeshPhysicalMaterial)) continue; seen.add(m); if (m.defines && 'USE_CSM' in m.defines) yes++; else no.push((o.name || o.type) + (m.name ? '/' + m.name : '')); } });
  return JSON.stringify({ patched: yes, unpatched: no.length, examples: no.slice(0, 25), frame: window.__csmFrame });
}));
if (process.env.DUMP) console.log('dump', await p.evaluate(() => {
  const o = window.__scene.getObjectByName('outerLand'); const m = o.material;
  return JSON.stringify({ vc: m.vertexColors, color: m.color.getHexString(), em: m.emissive.getHexString(), emI: m.emissiveIntensity,
    envI: m.envMapIntensity, defines: m.defines, obc: String(m.onBeforeCompile).slice(0, 160), lm: !!m.lightMap, aoMap: !!m.aoMap,
    lights: window.__scene.children.filter(c => c.isLight).map(l => l.type + ':' + l.intensity.toFixed(2) + ':' + l.color.getHexString()),
    exp: window.__renderer.toneMappingExposure, envSI: window.__scene.environmentIntensity });
}));
if (process.env.BLACKLAND) await p.evaluate(() => { const m = window.__scene.getObjectByName('outerLand').material; m.vertexColors = false; m.color.set(0xff00ff); m.needsUpdate = true; });
if (process.env.AO0) await p.evaluate(() => { window.__composer.passes[0].configuration.intensity = 0; });
if (process.env.DIRECT) await p.evaluate(() => {   // the scene alone, no post chain
  const c = window.__composer; c.render = () => { window.__renderer.setRenderTarget(null); window.__renderer.render(window.__scene, window.__camera); };
});
if (process.env.BARE) await p.evaluate(() => { const f = window.__scene.getObjectByName('flora'); if (f) f.visible = false; });
if (process.env.NOFOG) console.log('fog', await p.evaluate(() => { const f = window.__scene.fog; const s = f ? [f.near, f.far, f.color.getHexString(), f.isFogExp2 ? 'exp2' : 'lin'] : null; window.__scene.fog = null; return JSON.stringify(s); }));
await new Promise(r => setTimeout(r, 2500));
const vista = await p.evaluate(() => ({ tris: window.__frameTris, calls: window.__frameCalls }));
console.log('vista', JSON.stringify(vista));
await p.screenshot({ path: `${OUT}/forest_vista.jpg`, type: 'jpeg', quality: 90 });
// eye height among the trees, looking along the ground
await p.evaluate((pp) => { window.__camPin = { pos: [pp[0] + 6, pp[1] + 1.7, pp[2] + 6], look: [pp[0] + 60, pp[1] + 6, pp[2] + 20] }; }, pp);
await new Promise(r => setTimeout(r, 2500));
await p.screenshot({ path: `${OUT}/forest_eye.jpg`, type: 'jpeg', quality: 90 });
console.log('errors:', errs.slice(0, 6).join(' | ') || 'none');
await b.close();
