// Crystal Works at eye level, clean, at the things on the ground: the biggest stone, a tree, a brook, a seam.
// OUT=dir [URL=] [SHOTS=stone,tree,brook,seam,fp] [W=1600 H_=900] node _flageye.mjs
// Each is found on the top face (+y) from the scene itself, so the pins follow the world when it changes.
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const W = +(process.env.W || 1600), HT = +(process.env.H_ || 900);
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--disable-gpu-sandbox', `--window-size=${W},${HT}`, '--disable-renderer-backgrounding', '--disable-background-timer-throttling'] });
const p = await b.newPage(); await p.setViewport({ width: W, height: HT });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(URL + '?fresh=1&noguide=1&clean=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(8000);
await p.evaluate(() => { const st = document.createElement('style'); st.textContent = 'body > *:not(canvas):not(script):not(style){visibility:hidden !important}'; document.head.appendChild(st); for (const c of document.querySelectorAll('canvas')) if (c.clientWidth > 600) { c.style.visibility = 'visible'; } });
const pins = await p.evaluate(() => {
  const H = Math.abs(window.__game.facts().player_y), sc = window.__scene, out = {};
  const M = sc.getObjectByName ? null : null; let m4 = null;
  const eye = (x, z, ang, d = 4, y = 1.65) => ({ pos: [x + Math.cos(ang) * d, H + y, z + Math.sin(ang) * d], look: [x, H + 0.35, z] });
  sc.traverse(o => {
    if (!o.isInstancedMesh) return;
    const mx = o.instanceMatrix.array, n = o.count;
    let best = null, bv = -1, cx = 0, cz = 0;
    for (let i = 0; i < n; i++) {
      const k = i * 16, x = mx[k + 12], y = mx[k + 13], z = mx[k + 14];
      if (y < H - 1 || Math.hypot(x, z) < 6) continue;
      const s = Math.hypot(mx[k + 4], mx[k + 5], mx[k + 6]);
      if (s > bv) { bv = s; best = [x, z]; }
    }
    if (!best) return;
    const mat = Array.isArray(o.material) ? o.material[0] : o.material;
    const isRock = mat && mat.customProgramCacheKey && /rock/.test(String(mat.customProgramCacheKey()));
    if (isRock && !out.stone) out.stone = eye(best[0], best[1], 0.8, 3.2);
    const pn = o.parent && o.parent.name;
    if (pn === 'grove' && o.castShadow && !out.tree && bv > 0.25 && bv < 1) out.tree = { pos: [best[0] + 6, H + 1.65, best[1] + 6], look: [best[0], H + 1.4, best[1]] };
  });
  // a brook: the water's colour on the top face's painted map, walked through the box's own uv
  const cube = sc.getObjectByName('cube');
  if (cube) {
    const g = cube.geometry, gr = g.groups.find(q => q.materialIndex === 2), mat = cube.material[2], cv = mat.map && mat.map.image;
    if (cv && cv.getContext) {
      const P = cv.width, d = cv.getContext('2d').getImageData(0, 0, P, P).data, pos = g.attributes.position, uv = g.attributes.uv, ix = g.index.array;
      const v0 = ix[gr.start], vs = [ix[gr.start], ix[gr.start + 1], ix[gr.start + 2], ix[gr.start + 3], ix[gr.start + 4], ix[gr.start + 5]];
      const pts = [...new Set(vs)].map(k => ({ x: pos.getX(k), z: pos.getZ(k), u: uv.getX(k), v: uv.getY(k) }));
      const mnu = Math.min(...pts.map(q => q.u)), mxu = Math.max(...pts.map(q => q.u));
      const A = pts.find(q => q.u === 0 && q.v === 0), Bu = pts.find(q => q.u === 1 && q.v === 0), Bv = pts.find(q => q.u === 0 && q.v === 1);
      const toW = (u, v) => [A.x + (Bu.x - A.x) * u + (Bv.x - A.x) * v, A.z + (Bu.z - A.z) * u + (Bv.z - A.z) * v];
      let best = null, bs = 1e9;
      for (let y = 8; y < P - 8; y += 4) for (let x = 8; x < P - 8; x += 4) {
        const k = (y * P + x) * 4, r = d[k], gg = d[k + 1], bb = d[k + 2];
        if (r < 34 && gg < 50 && bb > r + 6 && bb > gg - 4) { const [wx, wz] = toW(x / P, 1 - y / P), dd = Math.abs(Math.hypot(wx, wz) - 14); if (dd < bs) { bs = dd; best = [wx, wz]; } }
      }
      if (best) { out.brook = eye(best[0], best[1], 2.1, 3.0, 1.65); out.brook.look = [best[0], H, best[1]]; }
    }
  }
  out.fp = { pos: [-2.5, H + 1.65, 6], look: [1, H + 0.3, 1] };
  out.seam = null;
  return { out, H };
});
const S = (process.env.SHOTS || 'stone,tree,brook,fp').split(',');
for (const n of S) {
  const pin = pins.out[n]; if (!pin) { console.log('no pin for', n); continue; }
  await p.evaluate(pn => { window.__camPin = pn; }, pin); await w(2200);
  await p.screenshot({ path: `${process.env.OUT}/eye_${n}.jpg`, type: 'jpeg', quality: 88 });
}
console.log(JSON.stringify(pins.out).slice(0, 400), errs.length ? 'ERR ' + errs[0] : 'no errors', JSON.stringify(await p.evaluate(() => window.__game.stats())));
await b.close();
