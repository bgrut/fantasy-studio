// The hero's new verbs: lift a prop (E), throw it at a hostile (attack), and
// climb a ledge by jumping at it. Shoots each and reports the counters.
//   J=job_N OUT=<dir> node actshot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--window-size=1400,800'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)); });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 800));
await p.evaluate(() => { window.__cbt.iframes = 1e9; });
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const shoot = (n) => p.screenshot({ path: `${OUT}/act_${J}_${n}.jpg`, type: 'jpeg', quality: 86 });
const out = {};
// 1. lift: stand beside the nearest prop and press E
const prop = await p.evaluate(() => {
  const g = window.__game, pp = g.pos(), ps = g.props();
  if (!ps.length) return null;
  ps.sort((a, b) => Math.hypot(a[0] - pp[0], a[2] - pp[2]) - Math.hypot(b[0] - pp[0], b[2] - pp[2]));
  const q = ps[0];
  g.tp(q[0] - 1.2, q[2]);
  return q;
});
out.prop = prop;
if (prop) {
  await sleep(700);
  await p.keyboard.press('KeyE');
  await sleep(600);
  out.afterE = await p.evaluate(() => window.__game.facts().actions);
  await shoot('carry');
  // 2. throw it at a hostile if there is one in the world, else into the open
  const tgt = await p.evaluate(() => {
    const g = window.__game, all = g.npcs();
    const i = all.findIndex(n => n.behavior === 'hostile' && !n.dead && !n.dormant);
    if (i < 0) return null;
    const [x, y, z] = all[i].pos;
    g.tp(x - 5, z);
    g.look(Math.atan2(-(x - (x - 5)), -(z - z)));      // the camera looks at it; a throw follows the view
    return { i, pos: all[i].pos };
  });
  out.target = tgt;
  await sleep(500);
  await p.evaluate(() => window.__game.throwIt());
  await sleep(250); await shoot('throw');
  await sleep(1200);
  out.afterThrow = await p.evaluate(() => window.__game.facts().actions);
}
// 3. climb: a ledge of each height in front of the hero; run at it and jump
out.climb = [];
for (const h of [1.0, 1.6, 2.1]) {
  const r = await p.evaluate((h) => {
    const g = window.__game, pp = g.pos();
    const x = pp[0] + 12, z = pp[2];
    g.block(x, z + 3.2, 2.4, h);
    g.tp(x, z);
    g.look(Math.PI);                         // W walks toward +z, into the block
    return { x, z };
  }, h);
  await sleep(600);
  const y0 = await p.evaluate(() => window.__game.pos()[1]);
  await p.keyboard.down('KeyW'); await sleep(420);
  await p.keyboard.down('Space'); await sleep(200); await p.keyboard.up('Space');
  await sleep(330); if (h === 1.6) await shoot('climb');
  await sleep(700); await p.keyboard.up('KeyW'); await sleep(300);
  const y1 = await p.evaluate(() => window.__game.pos()[1]);
  if (h === 1.6) await shoot('ontop');
  out.climb.push({ h, rose: +(y1 - y0).toFixed(2), mantles: await p.evaluate(() => window.__game.facts().actions.mantles) });
}
await b.close();
console.log(JSON.stringify({ ...out, errs: errs.slice(0, 5) }));
