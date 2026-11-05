// Crystal Works' wildflowers close: OUT=prefix [URL=] node _flagflowers.mjs
// the camera pinned low over the meadow by the start, looking along the ground at a drift
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--disable-gpu-sandbox', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(URL + '?fresh=1&noguide=1&clean=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(7000);
await p.evaluate(() => { const st = document.createElement('style'); st.textContent = 'body > *:not(canvas):not(script):not(style){visibility:hidden !important}'; document.head.appendChild(st); for (const c of document.querySelectorAll('canvas')) if (c.clientWidth < 900) c.style.visibility = 'hidden'; });
const f = await p.evaluate(() => { const f = window.__game.facts(); return [f.player_x ?? 0, f.player_y, f.player_z ?? 0]; });
const [x, y, z] = f; const up = y > 0 ? 1 : -1;
for (const [n, pos, look] of [['near', [x + 0.4, y + up * 0.55, z + 4.2], [x + 0.4, y, z + 2.6]],
                               ['knee', [x, y + up * 0.9, z + 3], [x - 1, y, z - 1]]]) {
  await p.evaluate((pos, look) => { window.__camPin = { pos, look }; }, pos, look);
  await w(1800); await p.screenshot({ path: `${process.env.OUT}_${n}.jpg`, type: 'jpeg', quality: 90 });
  if (process.env.PICK && n === (process.env.PICKSHOT || "near")) console.log(JSON.stringify(await p.evaluate(([x, y]) => { const e = document.elementFromPoint(x, y); return e ? [e.tagName, e.id, e.className, getComputedStyle(e).visibility, e.parentElement && e.parentElement.id] : null; }, process.env.PICK.split(",").map(Number))));
  if (process.env.PICK && n === (process.env.PICKSHOT || "near")) console.log(JSON.stringify(await p.evaluate(([px, py]) => {
    // what covers pixel PX,PY of the near shot (meshes and sprites, by projected box)
    const cam = window.__camera, V = cam.position.constructor, nx = px / 1600 * 2 - 1, ny = -(py / 900 * 2 - 1), out = [];
    window.__scene.traverse(o => {
      if (!(o.isMesh || o.isSprite) || !o.geometry) return;
      let vis = true; for (let q = o; q; q = q.parent) if (!q.visible) vis = false; if (!vis) return;
      const g = o.geometry; if (!g.boundingBox) g.computeBoundingBox();
      const c = new V(); o.getWorldPosition(c); let s = c.clone().project(cam);
      if (o.isInstancedMesh) {          // the nearest instance to the pixel
        const M = o.matrixWorld.clone(), m = M.clone(); let best = 9;
        for (let i = 0; i < o.count; i++) { o.getMatrixAt(i, m); m.premultiply(o.matrixWorld); const w = new V().setFromMatrixPosition(m), q = w.clone().project(cam);
          const dd = Math.hypot(q.x - nx, q.y - ny); if (q.z < 1 && dd < best) { best = dd; s = q; c.copy(w); } }
      }
      if (s.z > 1 || Math.abs(s.x - nx) > 0.12 || Math.abs(s.y - ny) > 0.15) return;
      let chain = [], q = o; while (q && chain.length < 4) { chain.push(q.name || q.type); q = q.parent; }
      out.push({ chain: chain.join(' < '), type: o.type, mat: o.material && o.material.type, name: o.material && o.material.name, tr: o.material && o.material.transparent,
                 map: !!(o.material && o.material.map), col: o.material && o.material.color && o.material.color.getHexString(), d: +c.distanceTo(cam.position).toFixed(1), sc: o.scale.toArray().map(v => +v.toFixed(2)) });
    });
    return out.sort((a, b) => a.d - b.d).slice(0, 15);
  }, process.env.PICK.split(',').map(Number)), null, 0));
}
console.log(JSON.stringify(f));
await b.close();
