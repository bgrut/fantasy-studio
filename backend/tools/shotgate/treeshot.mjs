// The flagship's trees close up: walks the player to stand a few metres from
// a grown tree on the home face, looking at it.   OUT=<dir> [D=6] node treeshot.mjs
import puppeteer from 'puppeteer-core';
const OUT = process.env.OUT || '.', D = +(process.env.D || 6);
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto('http://127.0.0.1:8790/', { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 8000));
await p.keyboard.press('Enter').catch(() => {});
await new Promise(r => setTimeout(r, 4000));
await p.keyboard.press('g').catch(() => {});
await new Promise(r => setTimeout(r, 1500));
for (const [tag, dist] of [['near', D], ['far', D * 3.5]]) {
  const got = await p.evaluate((dist) => {
    const S = window.__scene, F = window.__factory;
    const grp = S.getObjectByName('grove');
    if (!grp) return 'no grove';
    const ims = grp.children.filter(o => o.isInstancedMesh && o.count > 0).sort((a, b) => b.geometry.attributes.position.count - a.geometry.attributes.position.count);
    const im = ims[0];
    if (!im) return 'no trees';
    const M = new (S.matrix.constructor)(); im.getMatrixAt(0, M);
    const V = S.position.constructor, t = new V().setFromMatrixPosition(M);
    const ax = [Math.abs(t.x), Math.abs(t.y), Math.abs(t.z)];
    const f = F.FACES.findIndex(F_ => { const k = ax.indexOf(Math.max(...ax)); return Math.abs(F_.n[k]) === 1 && Math.sign(F_.n[k]) === Math.sign([t.x, t.y, t.z][k]); });
    const n = new V(...F.FACES[f].n), u = new V(...F.FACES[f].u);
    F.player.face = f; F.player.up.copy(n);
    const pl = F.player;
    pl.pos.copy(t).addScaledVector(u, -dist).addScaledVector(n, 1.7);
    pl.fwd.copy(u); pl.pitch = 0.12;
    return [t.x, t.y, t.z].map(v => +v.toFixed(1));
  }, dist);
  await new Promise(r => setTimeout(r, 1200));
  await p.screenshot({ path: `${OUT}/tree_${tag}.jpg`, type: 'jpeg', quality: 88 });
  console.log(tag, JSON.stringify(got));
}
console.log(JSON.stringify(errs.slice(0, 5)));
await b.close();
