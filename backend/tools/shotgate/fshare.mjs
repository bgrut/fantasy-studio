// A link that carries a factory, and the Long Drift's rule. The link has to
// round-trip a real factory into a fresh page and then drop out of the URL;
// the drift's seams must not grow back and its meltdown must pay double.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
p.on('console', m => { const u = (m.location() && m.location().url) || '';
  if (m.type()==='error' && !/favicon/i.test(u)) errs.push('console: '+m.text().slice(0,160)); });
const URL = process.env.URL ||
  ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
const q = URL.includes('?') ? '&' : '?';
const wait = ms => new Promise(r => setTimeout(r, ms));

// 1. build something distinctive, then take the link
await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const made = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  window.__share = null; addEventListener('message', e => { if (e.data && e.data.type === 'fs-share') window.__share = e.data; });
  for (let i = 3; i < F.N - 3; i++) if (F.cells[2][i][7].t === TY.EMPTY) F.place(2, i, 7, TY.BELT, 0);   // a belt run on face 2
  F.addValue(123);
  const link = F.shareLink();
  await new Promise(r => setTimeout(r, 200));          // the message to the studio is asynchronous
  const f = window.__game.facts();
  const m = window.__share || {};
  return { link, len: link.length, machines: f.machines, value: Math.round(f.value), told: !!window.__share,
           card: { thumb: typeof m.thumb === 'string' && m.thumb.startsWith('data:image/jpeg'), world: m.world, machines: m.machines,
                   value: m.value, mode: m.mode, sky: m.sky },
           caption: document.getElementById('facecap').textContent };
});
console.log('shared    :', made.machines, 'machines, value', made.value, '| link', Math.round(made.len / 1024) + ' KB',
            '| studio told', made.told, '| said:', JSON.stringify(made.caption));
console.log('the card  : thumb', made.card.thumb, '| world', JSON.stringify(made.card.world), '| machines', made.card.machines,
            '| value', made.card.value, '| mode', made.card.mode, '| sky', made.card.sky);

// 2. a fresh page opened on the link is that factory; the parameter is gone; a reload keeps it
await p.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
await p.goto(made.link + '&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const back = await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES, f = window.__game.facts();
  let belts2 = 0; for (let i = 0; i < F.N; i++) for (let j = 0; j < F.N; j++) if (F.cells[2][i][j].t === TY.BELT) belts2++;
  return { shared: f.shared, machines: f.machines, value: Math.round(f.value), belts2, url: location.search };
});
console.log('opened    : shared', back.shared, '| machines', back.machines, '| value', back.value, '| belts on face 2', back.belts2,
            '| url now', JSON.stringify(back.url));
await p.evaluate(() => window.__factory.save());
await p.goto(URL + q + 'nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const kept = await p.evaluate(() => { const f = window.__game.facts(); return { shared: f.shared, machines: f.machines, value: Math.round(f.value) }; });
console.log('reloaded  : machines', kept.machines, '| value', kept.value, '| shared flag', kept.shared);

// 3. the drift: seams do not grow back, a meltdown pays double
await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const drift = await p.evaluate(async () => {
  const F = window.__factory;
  const k = F.WORLDS.findIndex(w => w.id === 'drift');
  if (k < 0) return { offered: false };
  F.goalIdx = F.GOALS.length; F.addCores(9);
  F.travelTo(k); F.endIntro();
  await new Promise(r => setTimeout(r, 500));
  const f = window.__game.facts();
  // a seam with no rig on it: the starter rig's own seam is being worked and
  // would fall, which is depletion, not regrowth
  let seam = null;
  F.cells.forEach((face, fi) => face.forEach((col, i) => col.forEach((c, j) => { if (c.mesh && c.t === F.TYPES.NODE && !seam) seam = c; })));
  seam.rich = 0.3;
  await new Promise(r => setTimeout(r, 2500));
  const grew = seam.rich;
  const cores0 = window.__game.facts().cores;
  F.addValue(F.MELT_MIN + 2000);
  // the meltdown pays on the RUN's value, which addValue does not count
  const expect = Math.max(1, F.coresFor(window.__game.facts().run_value)) * f.core_mult;
  F.meltdown(); F.endIntro();
  await new Promise(r => setTimeout(r, 300));
  return { offered: true, world: f.world, finite: f.finite, mult: f.core_mult, grew: +grew.toFixed(3), won: window.__game.facts().cores - cores0, expect };
});
console.log('the drift :', drift.offered ? ('world ' + drift.world + ' | finite ' + drift.finite + ' | seam at 0.3 after 2.5s: ' + drift.grew +
            ' | meltdown paid ' + drift.won + ' cores (x' + drift.mult + ', expected ' + drift.expect + ')') : 'not offered from this home');
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'share.png' });
await b.close();

const ok = made.machines >= 8 && made.told && /LINK COPIED/.test(made.caption)
  && made.card.thumb && typeof made.card.world === 'string' && made.card.machines === made.machines && made.card.mode === 'survival' && /^#[0-9a-f]{6}$/.test(made.card.sky)
  && back.shared && back.machines === made.machines && back.value >= made.value && back.belts2 >= 8 && !/share=/.test(back.url)
  && kept.machines === made.machines && !kept.shared
  && (!drift.offered || (drift.finite && drift.mult === 2 && drift.grew <= 0.3 && drift.won === drift.expect && drift.won >= 2))
  && errs.length === 0;
process.exit(ok ? 0 : 1);
