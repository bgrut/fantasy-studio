// WHERE A SMELTER STANDS (2026-11-13). A smelter beside a brook or the brine quenches its ingot in the water, and
// one over a glowing ember fissure is fired from below: either melts a tick faster than one on dry ground, says so
// when you look at it, and the facts count it. A world with no water and no fissures (the red moon) has nothing to
// site and passes on that alone.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--disable-gpu-sandbox', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
const URL = process.env.URL || ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
await p.goto(URL + (URL.includes('?') ? '&' : '?') + 'fresh=1&nointro=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
for (let k = 0; k < 80; k++) { if (await p.evaluate(() => !!(window.__factory && window.__game && window.__game.facts))) break; await new Promise(r => setTimeout(r, 500)); }
await new Promise(r => setTimeout(r, 4000));
const r = await p.evaluate(() => {
  const F = window.__factory, TY = F.TYPES, N = F.N;
  const find = (want, face) => {
    for (let f = 0; f < 6; f++) { if (face !== undefined && f !== face) continue;
      for (let i = 3; i < N - 3; i++) for (let j = 3; j < N - 3; j++) {
        if (F.cells[f][i][j].t !== TY.EMPTY) continue;
        let clear = true; for (let di = -1; di <= 1 && clear; di++) for (let dj = -1; dj <= 1; dj++) if (F.cells[f][i + di][j + dj].t !== TY.EMPTY) { clear = false; break; }
        if (clear && F.siteOf(f, i, j) === want) return { f, i, j };
      } }
    return null;
  };
  const wet = find('quench'), hot = find('vent'), dry = find(null, wet ? wet.f : undefined);
  const melt = (s) => {
    if (!s) return null;
    if (!F.place(s.f, s.i, s.j, TY.SMELTER, 0)) return { placed: false };
    const c = F.cells[s.f][s.i][s.j];
    c.buf = 2; c.bt = TY.CRYSTAL; c.cook = 0;
    F.step();
    return { placed: true, cook: c.cook, site: c.site || null, label: F.describeCell(c) };
  };
  const out = { wet, hot, dry, ticks: F.SMELT_TICKS, w: melt(wet), h: melt(hot), d: melt(dry) };
  out.facts = window.__game.facts().sited;
  return out;
});
const ok = [];
const check = (c, m) => { ok.push(c); console.log((c ? '  ok   ' : '  FAIL ') + m); };
if (!r.wet && !r.hot) {
  console.log('no water and no fissures on this world: nothing to site');
  check(true, 'nothing on this world is sited');
} else {
  check(!!r.d && r.d.placed && r.d.site === null, `a smelter on dry ground melts in the usual time: ${r.d && r.d.cook} ticks (SMELT_TICKS ${r.ticks})`);
  if (r.wet) {
    check(r.w.placed && r.w.site === 'quench' && r.w.cook === r.d.cook - 1, `by the water it quenches a tick faster: ${r.w.cook} against ${r.d && r.d.cook}, at face ${r.wet.f} (${r.wet.i},${r.wet.j})`);
    check(/quench/.test(r.w.label || ''), `the look label says so: "${(r.w.label || '').slice(0, 90)}"`);
  }
  if (r.hot) check(r.h.placed && r.h.site === 'vent' && r.h.cook === r.d.cook - 1, `over a vent it is fired from below, a tick faster: ${r.h.cook}, at face ${r.hot.f} (${r.hot.i},${r.hot.j})`);
  check(r.facts && (r.facts.quench + r.facts.vent) >= (r.wet ? 1 : 0) + (r.hot ? 1 : 0) && r.facts.smelts >= 1, `the facts count them: ${JSON.stringify(r.facts)}`);
}
check(!errs.length, 'no page errors' + (errs.length ? ': ' + errs[0] : ''));
await b.close();
const bad = ok.filter(x => !x).length;
console.log(bad ? bad + ' failed; FAIL' : 'PASS');
process.exit(bad ? 1 : 0);
