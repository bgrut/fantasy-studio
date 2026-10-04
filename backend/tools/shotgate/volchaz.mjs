// The lava hazard: inLava is true in a channel and false at the spawn; a hero
// who steps from safe ground into a channel loses a heart and is put back on
// that ground.      J=job_517 node volchaz.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1000, height: 600 });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 1500));
const pick = await p.evaluate(() => {
  const L = window.__spec.world.level, n = L.grid_n, sz = L.size_m, V = window.__volc;
  const at = (x, z) => L.heights[Math.round((z / sz + 0.5) * (n - 1)) * n + Math.round((x / sz + 0.5) * (n - 1))];
  const pp = window.__game.pos();
  let deep = null;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const x = (j / (n - 1) - 0.5) * sz, z = (i / (n - 1) - 0.5) * sz;
    if (L.heights[i * n + j] < -1.3) { const d = Math.hypot(x - pp[0], z - pp[2]); if (!deep || d < deep.d) deep = { x, z, d }; }
  }
  // safe ground 4 to 8 m from that lava, on the field's own level
  let safe = null;
  for (let a = 0; a < 64 && !safe; a++) for (const r of [6, 8, 10]) {
    const x = deep.x + Math.cos(a / 64 * 6.283) * r, z = deep.z + Math.sin(a / 64 * 6.283) * r;
    if (V.edgeDist(x, z) > 3 && !V.inLava(x, z) && at(x, z) > -0.2 && at(x, z) < 1.5) { safe = { x, z }; break; }
  }
  return { deep, safe, inDeep: V.inLava(deep.x, deep.z), inSpawn: V.inLava(pp[0], pp[2]) };
});
console.log(JSON.stringify(pick));
await p.evaluate(s => window.__game.tp(s.x, s.z), pick.safe);
await new Promise(r => setTimeout(r, 1500));
const hp0 = await p.evaluate(() => window.__game.combat().hp);
await p.evaluate(d => window.__game.tpy(d.x, -1.2, d.z), pick.deep);
await new Promise(r => setTimeout(r, 1200));
const after = await p.evaluate(() => ({ hp: window.__game.combat().hp, pos: window.__game.pos(), lost: window.__game.combat().lost }));
const back = Math.hypot(after.pos[0] - pick.safe.x, after.pos[2] - pick.safe.z);
console.log(JSON.stringify({ hp0, after, back: +back.toFixed(2) }));
const ok = pick.inDeep && !pick.inSpawn && after.hp < hp0 && back < 3;
console.log(ok ? 'PASS lava burns and puts you back' : 'FAIL');
await b.close();
process.exit(ok ? 0 : 1);
