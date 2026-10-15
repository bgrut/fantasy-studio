// The nearest flora boulder close up, lit as played, then with its shadow off. J=job_N OUT=prefix
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(3000);
const info = await p.evaluate(() => {
  const V = window.__scene.position.constructor, pl = window.__game.pos(); let best = null;
  window.__scene.traverse(o => { if (!o.isInstancedMesh || !o.geometry || o.geometry.type !== 'IcosahedronGeometry') return;
    const M4 = o.matrixWorld.constructor;
    for (let i = 0; i < o.count; i++) { const m = new M4(); o.getMatrixAt(i, m); m.premultiply(o.matrixWorld); const c = new V().setFromMatrixPosition(m);
      const d = Math.hypot(c.x - pl[0], c.z - pl[2]); const s = new V().setFromMatrixScale(m); if (!o.geometry.boundingSphere) o.geometry.computeBoundingSphere(); s.multiplyScalar(o.geometry.boundingSphere.radius);
      if (s.x > 1.5 && (!best || d < best.d)) best = { d, c: [c.x, c.y, c.z], s: s.x, mesh: o }; } });
  if (!best) return null;
  window.__rk = best.mesh;
  window.__camPin = { pos: [best.c[0] + best.s * 2.2, best.c[1] + best.s * 1.0, best.c[2] + best.s * 2.2], look: [best.c[0], best.c[1] + best.s * 0.3, best.c[2]] };
  return { d: best.d, s: best.s };
});
console.log(JSON.stringify(info));
await wait(1500); await p.screenshot({ path: process.env.OUT + '_lit.jpg', type: 'jpeg', quality: 90 });
await p.evaluate(() => { if (window.__rk) window.__rk.receiveShadow = false; });
await wait(1200); await p.screenshot({ path: process.env.OUT + '_noshadow.jpg', type: 'jpeg', quality: 90 });
await b.close();
