// The whole arc, shot beat by beat: the starter line, a built factory, the
// forge unlock and the second act, the overhead at scale, a meltdown and its
// core, travel to Ember Reach and Frostline, the works, and the end card.
// Same harness tricks the gates use.   URL=... TAG=... node tourarc.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/', TAG = process.env.TAG || 'demo';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
const wait = ms => new Promise(r => setTimeout(r, ms));
const shot = async (n) => { await p.screenshot({ path: 'renders/arc_' + TAG + '_' + n + '.png' }); console.log('shot', n); };
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
await wait(8000);
await p.evaluate(() => { document.getElementById('tutor')?.classList.remove('on'); const F = window.__factory; if (F.ageHints) F.ageHints(); });
// 1. a built factory: two lines on the home face, laid the way a player would (belts from a rig to a smelter to the hub)
await p.evaluate(() => { const F = window.__factory; F.hold = true; F.addValue(600); });
await wait(500);
const built = await p.evaluate(() => { const F = window.__factory, T = F.TYPES; let n = 0;
  const f = 0; const N = F.N; const mid = Math.floor(N / 2);
  const lay = (i, j, t, d) => { const c = F.cells[f][i][j]; if (c.t === T.EMPTY || (c.t === T.NODE && t === T.MINER)) { try { F.place(f, i, j, t, d); n++; } catch (e) {} } };
  // three lines, each from a real seam on the home face to a smelter and on to the hub's side
  const seams = []; for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) if (F.cells[f][i][j].t === T.NODE) seams.push([i, j]);
  const hub = []; for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) if (F.cells[f][i][j].t === T.HUB) hub.push([i, j]);
  const [hi, hj] = hub[0] || [mid, mid];
  for (const [si, sj] of seams.slice(0, 4)) {
    const di = Math.sign(hi - si) || 1, dj = Math.sign(hj - sj) || 1; const dirI = di > 0 ? 1 : 3, dirJ = dj > 0 ? 2 : 0;
    lay(si, sj, T.MINER, dirI); let i = si + di, j = sj; let steps = 0;
    while (i !== hi && steps++ < 40) { lay(i, j, T.BELT, dirI); if (steps === 3) { lay(i, j, T.SMELTER, dirI); } i += di; }
    while (j !== hj && steps++ < 80) { lay(i, j, T.BELT, dirJ); j += dj; }
  }
  return { n, seams: seams.length, hub: hub[0], api: !!F.place }; });
console.log('built     :', JSON.stringify(built));
await wait(3000); await shot('1_built');
// 2. the forge unlock and the second act
await p.evaluate(() => { const F = window.__factory; F.goalIdx = Math.min(F.GOALS.length, 6); if (F.startAct2) F.startAct2(); });
await wait(2500); await shot('2_second_act');
// 3. the overhead at scale
await p.keyboard.press('Tab'); await wait(1500); await shot('3_overhead'); await p.keyboard.press('Tab'); await wait(600);
// 4. the meltdown and the core it leaves
await p.evaluate(() => { const F = window.__factory; F.goalIdx = F.GOALS.length; F.addValue(5000); });
await wait(400);
const melted = await p.evaluate(() => { const F = window.__factory; const before = window.__game.facts().cores; if (F.meltdown) F.meltdown(); return { before, api: !!F.meltdown }; });
console.log('meltdown  :', JSON.stringify(melted));
await wait(1200); await shot('4_meltdown'); await wait(6000); await shot('4b_after_meltdown');
// 5. travel: Ember Reach, then Frostline
await p.evaluate(() => { const F = window.__factory; F.addCores(6); F.travelTo(1); });
await wait(4000); await shot('5_ember');
await p.evaluate(() => { const F = window.__factory; const k = F.WORLDS.findIndex(w => /frost/i.test(w.id || w.name || '')); if (k > 0) F.travelTo(k); });
await wait(4000); await shot('6_frost');
// 6. the works and the end card
const works = await p.evaluate(() => { const F = window.__factory; if (F.showWorksCard) F.showWorksCard(); return !!F.showWorksCard; });
await wait(2500); await shot('7_works'); await wait(9000); await shot('8_after_works');
const facts = await p.evaluate(() => { const f = window.__game.facts(); return { cores: f.cores, world: f.world, lifetime: f.lifetime && { works: f.lifetime.works, worlds: (f.lifetime.worlds || []).length } }; });
console.log('facts     :', JSON.stringify(facts));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();
