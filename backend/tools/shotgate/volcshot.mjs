// The volcano, four ways: as played, the cone from the spawn, a lava channel
// close up, and high over the field. Prints the volcano's facts and any
// errors, and writes volc_<view>.jpg.
//   J=job_509 OUT=<dir> node volcshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 900 });
const errs = [];
p.on('pageerror', e => errs.push(e.message));
p.on('console', m => { if (m.type() === 'error' || /volcano/.test(m.text())) errs.push(m.text()); });
p.on('response', r => { if (r.status() >= 400) errs.push(r.status() + ' ' + r.url().split('/dist/')[1]); });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 2500));
await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 3000));
const info = await p.evaluate(() => {
  const f = window.__game && window.__game.facts ? window.__game.facts() : {};
  return { lava: f.lava, light: f.light, archetype: f.archetype, calls: window.__frameCalls, tris: window.__frameTris };
});
console.log(JSON.stringify(info));
await p.screenshot({ path: `${OUT}/volc_play.jpg`, type: 'jpeg', quality: 90 });
if (!info.lava) { console.log('errors', JSON.stringify(errs.slice(0, 12))); await b.close(); process.exit(1); }
const geo = await p.evaluate(() => {
  const L = window.__spec.world.level, pp = window.__game.pos();
  // the channel sample nearest the spawn, and the bearing of the cone
  let best = null;
  for (const c of L.lava.channels) for (const q of c.pts) {
    const d = Math.hypot(q[0] - pp[0], q[1] - pp[2]);
    if (Math.abs(q[0]) < L.size_m * 0.45 && Math.abs(q[1]) < L.size_m * 0.45 && (!best || d < best.d)) best = { q, d };
  }
  return { pp, cd: L.lava.cone_dir, ch: best.q, size: L.size_m };
});
const shots = {
  cone: { pos: [geo.pp[0] - geo.cd[0] * 6, geo.pp[1] + 2.2, geo.pp[2] - geo.cd[1] * 6],
          look: [geo.pp[0] + geo.cd[0] * 300, geo.pp[1] + 40, geo.pp[2] + geo.cd[1] * 300] },
  channel: { pos: [geo.ch[0] + 7, 3.2, geo.ch[1] + 7], look: [geo.ch[0], -0.5, geo.ch[1]] },
  high: { pos: [geo.pp[0] - geo.cd[0] * 40, 45, geo.pp[2] - geo.cd[1] * 40],
          look: [geo.pp[0] + geo.cd[0] * 150, 0, geo.pp[2] + geo.cd[1] * 150] },
};
for (const [k, v] of Object.entries(shots)) {
  await p.evaluate(v => { window.__camPin = v; }, v);
  await new Promise(r => setTimeout(r, 1800));
  await p.screenshot({ path: `${OUT}/volc_${k}.jpg`, type: 'jpeg', quality: 90 });
}
console.log('errors', JSON.stringify(errs.slice(0, 12)));
await b.close();
