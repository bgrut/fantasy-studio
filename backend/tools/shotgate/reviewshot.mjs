// What a player sees of a generated game: the title card (title, mission,
// controls), the first play view, and a wide look over the level; plus the
// spec's own reading of the sentence (genre, style, hero, cast, objectives).
//   J=job_N OUT=<dir> TAG=<name> node reviewshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || J;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 160)); });
const base = `http://127.0.0.1:8789/games/${J}/dist/`;
await p.goto(base + 'index.html', { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 12000));
await p.screenshot({ path: `${OUT}/${TAG}_1_title.jpg`, type: 'jpeg', quality: 88 });
const spec = await p.evaluate(async () => { try { return await (await fetch('spec.json')).json(); } catch (e) { return null; } });
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 3500));
await p.screenshot({ path: `${OUT}/${TAG}_2_play.jpg`, type: 'jpeg', quality: 88 });
await p.keyboard.press('g').catch(() => {});
const ok = await p.evaluate(() => {
  const g = window.__game; if (!g || !g.pos) return false;
  const pp = g.pos(), yaw = g.heading ? g.heading() : 0, fx = -Math.sin(yaw), fz = -Math.cos(yaw);
  window.__camPin = { pos: [pp[0] - fx * 14, pp[1] + 12, pp[2] - fz * 14], look: [pp[0] + fx * 20, pp[1], pp[2] + fz * 20] };
  return true;
});
await new Promise(r => setTimeout(r, 1200));
if (ok) await p.screenshot({ path: `${OUT}/${TAG}_3_wide.jpg`, type: 'jpeg', quality: 88 });
// CLOSE=1: the detail a sheet of wide views hides (2026-10-06). The HUD is
// hidden; 4 is the hero's portrait from the front, 5 a low three-quarter
// view past the hero into the level, 6 the nearest other character.
if (ok && process.env.CLOSE === '1') {
  await p.evaluate(() => { for (const el of document.body.children) if (el.tagName !== 'CANVAS' && !el.querySelector('canvas')) el.style.visibility = 'hidden'; });
  const H = (spec && spec.player && spec.player.height_m) || 1.7;
  const pin = async (fn, file, wait) => {
    const done = await p.evaluate(fn, H);
    if (!done) return;
    await new Promise(r => setTimeout(r, wait || 1400));
    await p.screenshot({ path: `${OUT}/${TAG}_${file}.jpg`, type: 'jpeg', quality: 92 });
  };
  await pin((H) => { const g = window.__game, pp = g.pos(), yaw = g.heading ? g.heading() : 0, fx = -Math.sin(yaw), fz = -Math.cos(yaw);
    const d = Math.max(1.6, H * 1.25);
    window.__camPin = { pos: [pp[0] + fx * d + fz * 0.5, pp[1] + H * 0.78, pp[2] + fz * d - fx * 0.5], look: [pp[0], pp[1] + H * 0.62, pp[2]] }; return true; }, '4_hero');
  await pin((H) => { const g = window.__game, pp = g.pos(), yaw = g.heading ? g.heading() : 0, fx = -Math.sin(yaw), fz = -Math.cos(yaw);
    const sx = fz, sz = -fx, d = Math.max(3.2, H * 2.2);
    window.__camPin = { pos: [pp[0] - fx * d * 0.6 + sx * d * 0.8, pp[1] + H * 0.35, pp[2] - fz * d * 0.6 + sz * d * 0.8], look: [pp[0] + fx * 8, pp[1] + H * 0.5, pp[2] + fz * 8] }; return true; }, '5_low');
  await pin(() => { const g = window.__game, pp = g.pos(); const ns = (g.npcRefs ? g.npcRefs() : []).filter(n => n && n.obj && !n.gone && !n.dead && n.obj.visible !== false);
    if (!ns.length) return false;
    let best = null, bd = 1e9;
    for (const n of ns) { const q = n.obj.position, d = Math.hypot(q.x - pp[0], q.z - pp[2]); if (d > 1 && d < bd) { bd = d; best = n; } }
    if (!best) return false;
    const q = best.obj.position, h = Math.max(0.3, (best.height_m || best.height || (best.spec && best.spec.height_m) || 1.6));
    const vx = pp[0] - q.x, vz = pp[2] - q.z, L = Math.hypot(vx, vz) || 1;
    const d = Math.max(1.4, h * 1.5);
    window.__camPin = { pos: [q.x + vx / L * d, q.y + h * 0.8, q.z + vz / L * d], look: [q.x, q.y + h * 0.55, q.z] }; return true; }, '6_npc');
}
const sum = spec ? {
  genre: spec.genre, title: spec.title, style: spec.style, skin: spec.skin || (spec.ui && spec.ui.skin),
  world: spec.world && { name: spec.world.name, sky: spec.world.sky, archetype: spec.world.archetype, setting: spec.world.setting },
  hero: spec.player && { kind: spec.player.kind || spec.player.name, mode: spec.player.mode, role: spec.player.role },
  cast: (spec.entities || []).slice(0, 8).map(e => (e.kind || e.name) + (e.role ? ':' + e.role : '') + (e.count ? 'x' + e.count : '')),
  objectives: (spec.objectives || []).map(o => o.kind + ' ' + (o.count || '') + ' ' + (o.label || '')),
  intro: spec.intro,
} : null;
console.log(TAG, JSON.stringify(sum), 'errors', JSON.stringify(errs.slice(0, 3)));
await b.close();
