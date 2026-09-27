// Two genres the studio could not make until 2026-09-27, held to their verbs.
//
// A TOWER DEFENCE (TD=<job>): the waves sleep until called, a tower costs
// gold and shoots on its own, the creatures walk the road to the keep and not
// at the player, an undefended keep takes the blow, and a tower kills. One
// page, in that order: a first wave with no towers, then a wave against them.
//
// A PLATFORMER (PF=<job>): side view, floating islands along the lane, every
// step up inside the jump's reach, every gap one a running jump clears, the
// pickups sitting on the islands, and a drop onto an island stopping on it.
//
//   TD=<job> PF=<job> node fgenres.mjs
import puppeteer from 'puppeteer-core';
const TD = process.env.TD, PF = process.env.PF;
if (!TD && !PF) { console.log('fgenres: TD=<job> and/or PF=<job> needed; FAIL'); process.exit(1); }
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,760'] });
const wait = ms => new Promise(r => setTimeout(r, ms));
const url = j => 'http://127.0.0.1:8789/games/job_' + j + '/dist/?noguide=1';
const fails = [];
const check = (ok, what) => { console.log((ok ? '  ok   ' : '  FAIL ') + what); if (!ok) fails.push(what); };
async function open(j) {
  const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
  const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
  await p.goto(url(j), { waitUntil: 'domcontentloaded', timeout: 120000 });
  for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(1000); }
  const btn = await p.$('#startbtn'); if (btn) await btn.click();
  await wait(1500);
  return { p, errs };
}

if (TD) {
  // ONE PAGE, IN ORDER. Two copies of a defence side by side (dozens of
  // skinned attackers each) starved the headless GPU and the page stopped
  // answering. The same checks run in sequence on one page: first a wave with
  // no towers, which must reach the keep; then towers, which must kill.
  console.log('tower defence, job ' + TD);
  const { p, errs } = await open(TD);
  const s0 = await p.evaluate(() => window.__game.facts().defend);
  check(!!s0, 'the game is a defence (facts carry a keep)');
  if (s0) {
    check(s0.waves >= 3 && s0.pool >= Math.min(20, 2 * s0.waves + 1), `waves ${s0.waves}, a pool of ${s0.pool} for the biggest wave`);
    check(s0.alive === 0 && s0.wave === 0, 'nothing is awake before the first wave');
    check(Math.hypot(s0.keep_at[0] - s0.gate_at[0], s0.keep_at[1] - s0.gate_at[1]) > 25, `the gate is far down the road from the keep: ${Math.hypot(s0.keep_at[0] - s0.gate_at[0], s0.keep_at[1] - s0.gate_at[1]).toFixed(0)} m`);
    check(s0.gold >= 30, `gold to build with: ${s0.gold}`);
    const poor = await p.evaluate(() => { const g = window.__game.facts().defend.gold; window.__defend.gold(0); const ok = window.__defend.build(0, 0); window.__defend.gold(g); return ok; });
    check(!poor, 'a tower is refused without the gold for it');
    // the hero stands well off the road: this measures the towers and the keep,
    // and a wave that stops to fight him measures neither
    await p.evaluate(() => {
      const q = window.__game.facts().defend, [kx, kz] = q.keep_at, [rx, rz] = q.road_in;
      const L = Math.hypot(rx - kx, rz - kz) || 1, ux = (rx - kx) / L, uz = (rz - kz) / L;
      window.__game.tp(kx + uz * 28, kz - ux * 28);
    });
    await wait(800);
    // 1. an undefended wave walks the road and the keep takes the blow
    await p.evaluate(() => window.__defend.call());
    await wait(1500);
    const d = async () => p.evaluate(() => {
      const q = window.__game.facts().defend, [kx, kz] = q.keep_at;
      const live = window.__game.npcs().filter(n => n.behavior === 'hostile' && !n.dead && !n.dormant);
      return { alive: live.length, dist: live.length ? live.reduce((s, n) => s + Math.hypot(n.pos[0] - kx, n.pos[2] - kz), 0) / live.length : null, q };
    });
    const m1 = await d();
    check(m1.alive > 0 && m1.q.wave === 1, `the first wave walked out of the gate: ${m1.alive} attackers`);
    await wait(5000);
    const m2 = await d();
    check(m1.dist !== null && m2.dist !== null && m2.dist < m1.dist - 3, `they walk the road to the keep: ${m1.dist && m1.dist.toFixed(1)} m -> ${m2.dist && m2.dist.toFixed(1)} m`);
    let q = m2.q;
    for (let t = 0; t < 90 && !(q.breaches > 0 && q.alive === 0); t++) { await wait(1000); q = await p.evaluate(() => window.__game.facts().defend); }
    check(q.breaches > 0 && q.keep < q.keep_max, `an undefended keep takes the blow: ${q.breaches} through, keep ${q.keep}/${q.keep_max}`);
    const lostYet = await p.evaluate(() => window.__game.combat().lost);
    check(!lostYet, 'the hero is still standing (the wave went for the keep, not him)');
    // 2. towers beside the road, a few metres out from the keep, then the next wave
    const built = await p.evaluate(() => {
      window.__defend.gold(500);
      const q = window.__game.facts().defend, [kx, kz] = q.keep_at, [rx, rz] = q.road_in;
      const L = Math.hypot(rx - kx, rz - kz) || 1, ux = (rx - kx) / L, uz = (rz - kz) / L;
      const a = window.__defend.build(kx + ux * 9 + uz * 4, kz + uz * 9 - ux * 4);
      const c = window.__defend.build(kx + ux * 9 - uz * 4, kz + uz * 9 + ux * 4);
      const e = window.__defend.build(kx + ux * 15, kz + uz * 15 + 4.5);
      return [a, c, e, window.__game.facts().defend.towers, window.__game.facts().defend.gold];
    });
    check(built[0] && built[1] && built[3] >= 2, `towers raised with gold: ${built[3]}, ${built[4]} gold left`);
    await p.evaluate(() => window.__defend.call());
    let kills = 0, gold = built[4];
    for (let t = 0; t < 90 && kills === 0; t++) {
      await wait(1000);
      const q2 = await p.evaluate(() => window.__game.facts().defend);
      kills = q2.tower_kills; gold = q2.gold;
    }
    check(kills > 0, `a tower kills on its own: ${kills}`);
    check(gold > built[4], `kills pay: ${built[4]} -> ${gold} gold`);
  }
  check(errs.length === 0, 'no page errors' + (errs.length ? ': ' + errs[0] : ''));
  await p.screenshot({ path: 'renders/genre_td_' + TD + '.png' });
  await p.close();
}

if (PF) {
  console.log('platformer, job ' + PF);
  const { p, errs } = await open(PF);
  const f = await p.evaluate(() => ({ n: window.__game.facts().platforms, spans: window.__platformSpans || [],
                                      reach: window.__platformReach || 3.3,
                                      left: window.__game.objectives().left }));
  check(f.n >= 6, `floating islands along the lane: ${f.n}`);
  let worstUp = 0, worstGap = 0;
  for (let k = 1; k < f.spans.length; k++) {
    worstUp = Math.max(worstUp, f.spans[k][2] - f.spans[k - 1][2]);
    worstGap = Math.max(worstGap, Math.abs(f.spans[k][0] - f.spans[k - 1][1]));
  }
  check(worstUp <= 1.9, `every step up inside the jump: highest ${worstUp.toFixed(2)} m`);
  check(worstGap <= f.reach + 0.05, `every gap clears at the hero's run: widest ${worstGap.toFixed(2)} m, reach ${f.reach} m`);
  const onTop = f.left.filter(q => f.spans.some(s => q[0] >= Math.min(s[0], s[1]) - 0.5 && q[0] <= Math.max(s[0], s[1]) + 0.5 && q[1] > s[2] + 0.5 && q[1] < s[2] + 2.5)).length;
  check(f.left.length > 0 && onTop >= Math.min(f.left.length, f.n) * 0.8, `the pickups sit on the islands: ${onTop} of ${f.left.length}`);
  if (f.spans.length > 2) {
    const s = f.spans[2], mx = (s[0] + s[1]) / 2;
    await p.evaluate((x, y) => window.__game.tpy(x, y, 0), mx, s[2] + 3);
    await wait(2500);
    const y = await p.evaluate(() => window.__game.pos()[1]);
    check(Math.abs(y - s[2]) < 1.6, `a drop onto an island stops on it: feet near ${s[2].toFixed(2)}, body at ${Number(y).toFixed(2)}`);
  }
  check(errs.length === 0, 'no page errors' + (errs.length ? ': ' + errs[0] : ''));
  await p.screenshot({ path: 'renders/genre_pf_' + PF + '.png' });
  await p.close();
}
await b.close();
console.log(fails.length ? `${fails.length} failed; FAIL` : 'PASS');
process.exit(fails.length ? 1 : 0);
