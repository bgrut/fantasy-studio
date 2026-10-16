// stand in front of the first smelter's furnace door. URL= OUT=
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
await p.goto((process.env.URL || 'http://127.0.0.1:8790/') + '?fresh=1&nointro=1', { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 7000));
const r = await p.evaluate(() => {
  const F = window.__factory; let c = null;
  for (let i = 0; i < F.N && !c; i++) for (let j = 0; j < F.N && !c; j++) if (F.cells[0][i][j].t === F.TYPES.SMELTER) c = F.cells[0][i][j];
  if (!c || !c.build) return 'none';
  const lamp = c.build.getObjectByName('lamp'), V = lamp.position.constructor, w = new V(); lamp.getWorldPosition(w);
  const out = new V(1, 0, 0).applyQuaternion(c.build.quaternion);
  F.player.pos.set(w.x + out.x * 2.6, w.y + 0.9, w.z + out.z * 2.6);
  F.player.fwd.set(-out.x, 0, -out.z).normalize(); F.player.pitch = -0.32;
  try { F.tutIdx = 99; } catch (e) {}
  document.getElementById('tutor')?.classList.remove('on');
  c.cook = Math.max(c.cook || 0, 50);
  return { lamp: [w.x, w.y, w.z].map(v => +v.toFixed(1)), glow: c.glow };
});
console.log(JSON.stringify(r));
await new Promise(r => setTimeout(r, 2500));
await p.screenshot({ path: process.env.OUT });
console.log(JSON.stringify(await p.evaluate(() => {
  const cam = window.__camera || window.__factory.camera;
  const out = [];
  for (const [px, py] of [[640, 470], [640, 520]]) {
    const V = cam.position.constructor, ndc = new V(px / 1280 * 2 - 1, -(py / 760 * 2 - 1), 0.5).unproject(cam).sub(cam.position).normalize();
    let best = null;
    window.__scene.traverse(o => { if (!o.isMesh || !o.visible || !o.geometry) return; o.geometry.computeBoundingBox && !o.geometry.boundingBox && o.geometry.computeBoundingBox();
      const bb = o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld); const t = (() => { let tmin = 0, tmax = 1e9; for (const a of ['x','y','z']) { const inv = 1 / ndc[a]; let t0 = (bb.min[a] - cam.position[a]) * inv, t1 = (bb.max[a] - cam.position[a]) * inv; if (inv < 0) [t0, t1] = [t1, t0]; tmin = Math.max(tmin, t0); tmax = Math.min(tmax, t1); } return tmin <= tmax ? tmin : null; })();
      if (t !== null && (!best || t < best.t)) best = { t, name: o.name, parent: o.parent && o.parent.name, geo: o.geometry.type, size: bb.getSize(new V()).toArray().map(v => +v.toFixed(2)), col: o.material && o.material.color && o.material.color.getHexString() }; });
    out.push(best);
  }
  return out;
})));
await b.close();
