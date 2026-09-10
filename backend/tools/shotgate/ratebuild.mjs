// A built factory: every free seam on the top face gets a rig and a smelter,
// and its ingots are routed by belt into the starter line. The rate it holds
// is the number a player can actually reach on one hub.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded' }); await new Promise(r=>setTimeout(r,4500));
const r = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES, w = ms => new Promise(r => setTimeout(r, ms));
  const cell = (i, j) => F.cells[0][i] && F.cells[0][i][j];
  let hub = null; F.cells[0].forEach((col, i) => col.forEach((c, j) => { if (c.t === TY.HUB && !hub) hub = [i, j]; }));
  // a belt from `from` toward `to`, Manhattan, stopping when it meets a belt (a merge) or the target
  function route(from, to) {
    let [i, j] = from, laid = 0;
    for (let guard = 0; guard < 80; guard++) {
      const di = Math.sign(to[0] - i), dj = Math.sign(to[1] - j);
      let ni = i, nj = j, d;
      if (dj !== 0 && Math.abs(to[1] - j) >= Math.abs(to[0] - i)) { nj = j + dj; d = dj > 0 ? 1 : 3; }
      else if (di !== 0) { ni = i + di; d = di > 0 ? 0 : 2; }
      else return laid;
      const here = cell(i, j);
      if (here && (here.t === TY.BELT || here.t === TY.MINER || here.t === TY.SMELTER)) { here.d = d; F.beltsDirty = true; }
      const next = cell(ni, nj);
      if (!next) return laid;
      if (next.t === TY.BELT) return laid;             // merged into an existing line
      if (next.t === TY.EMPTY) { F.place(0, ni, nj, TY.BELT, d); laid++; }
      else if (next.t !== TY.HUB) return laid;
      i = ni; j = nj;
      if (i === to[0] && j === to[1]) return laid;
    }
    return laid;
  }
  const nodes = []; F.cells[0].forEach((col, i) => col.forEach((c, j) => { if (c.t === TY.NODE) nodes.push([i, j]); }));
  let rigs = 0, belts = 0;
  for (const [i, j] of nodes) {
    // rig, then a smelter one tile toward the hub, then belts from the smelter to the hub
    const di = Math.sign(hub[0] - i) || 1, dj = Math.sign(hub[1] - j);
    const sd = Math.abs(hub[0] - i) >= Math.abs(hub[1] - j) ? [di, 0] : [0, dj];
    const s = [i + sd[0], j + sd[1]];
    if (!cell(s[0], s[1]) || cell(s[0], s[1]).t !== TY.EMPTY) continue;
    const dir = sd[0] > 0 ? 0 : sd[0] < 0 ? 2 : sd[1] > 0 ? 1 : 3;
    F.place(0, i, j, TY.MINER, dir); F.place(0, s[0], s[1], TY.SMELTER, dir); rigs++;
    belts += route(s, hub);
  }
  await w(3000);
  const a = window.__game.facts().value;
  await w(40000);
  const f = window.__game.facts();
  let hubTook = 0; F.cells[0].forEach(col => col.forEach(c => { if (c.t === TY.HUB) hubTook = c.took | 0; }));
  return { seams: nodes.length, rigs, belts, perMin: +((f.value - a) / 40 * 60).toFixed(0), rate_now: f.rate_now, machines: f.machines, hubTook, tier: f.goal_index, goal: f.goal };
});
console.log(JSON.stringify(r));
await b.close();
