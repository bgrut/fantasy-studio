// Character physics: a hostile struck and then killed, through the harness's
// hurt() hook, the hero kept out of the fight. Shoots the recoil, the fall
// and the body at rest, and reports the hips' height through the fall.
//   J=job_541 OUT=<dir> node ragshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--window-size=1400,800'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error' || /ragdoll/.test(m.text())) errs.push(m.text().slice(0, 200)); });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 800));
const pick = await p.evaluate(() => {
  window.__cbt.iframes = 1e9;                         // the hero is not part of this
  const g = window.__game, all = g.npcs();
  const i = all.findIndex(n => n.behavior === 'hostile' && !n.dead && !n.dormant);
  if (i < 0) return null;
  const [x, y, z] = all[i].pos;
  g.tp(x - 2.2, z - 2.2);                             // the blow comes from here
  window.__camPin = { pos: [x + 3.4, y + 1.8, z - 1.2], look: [x, y + 0.8, z] };
  return { i, pos: all[i].pos, name: all[i].name };
});
if (!pick) { console.log('no hostile'); await b.close(); process.exit(1); }
const shoot = (n) => p.screenshot({ path: `${OUT}/rag_${n}.jpg`, type: 'jpeg', quality: 88 });
const hips = () => p.evaluate((i) => {
  const n = window.__game.npcs()[i]; return n ? { dead: n.dead, x: +n.pos[0].toFixed(2) } : null;
}, pick.i);
await new Promise(r => setTimeout(r, 600));
await shoot('before');
await p.evaluate((i) => window.__game.hurt(i, 0.01), pick.i);   // a glancing blow: it lives, and recoils
await new Promise(r => setTimeout(r, 70));
await shoot('flinch');
await new Promise(r => setTimeout(r, 900));
await p.evaluate((i) => window.__game.hurt(i, 99), pick.i);     // the killing blow
const track = [];
for (let k = 0; k < 8; k++) {
  await new Promise(r => setTimeout(r, 160));
  if (k === 2) await shoot('falling');
  track.push(await p.evaluate(() => {
    let best = null;
    window.__scene.traverse(o => { if (o.isBone && o.name === 'hips') {
      const v = o.getWorldPosition(new (o.position.constructor)()); if (!best || v.y < best) best = +v.y.toFixed(2); } });
    return best;
  }));
}
await new Promise(r => setTimeout(r, 1500));
await shoot('down');
console.log(JSON.stringify({ pick, state: await hips(), lowestHipsY: track, errs: errs.slice(0, 6) }));
await b.close();
