// Crystal Works: the cranes round a green worldlet, shot from beside and behind a skein as it flies
// (the camera re-pinned each frame off the lead bird's instance matrix).   OUT=prefix [URL=] node _flagcranes.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
await p.goto(URL + '?fresh=1&noguide=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
const w = ms => new Promise(r => setTimeout(r, ms));
await w(9000); await p.keyboard.press('Enter').catch(() => {}); await p.click('#startbtn').catch(() => {}); await w(5000);
await p.addStyleTag({ content: 'body > *:not(canvas){visibility:hidden !important}' });
const views = JSON.parse(process.env.VIEWS || '[[1.6,0.5,-2.2,0],[3.5,1.4,4,8],[-0.6,-1.2,-0.8,4]]');   // [right, up, back] in wingspans, then which bird to look at
for (let i = 0; i < views.length; i++) {
  console.log(JSON.stringify(await p.evaluate(v => {
    let g = null; window.__scene.traverse(o => { if (o.name === 'worldIslets') g = o; });
    if (!g || !g.userData.flock) return 'no flock';
    cancelAnimationFrame(window.__fcLoop || 0);
    const F = g.userData.flock, m = new (g.matrix.constructor)(), e = m.elements;
    const step = () => {
      g.userData.batch.getMatrixAt(F.birds[0].id, m);
      const s = Math.hypot(e[0], e[1], e[2]), o = [e[12], e[13], e[14]];
      const ax = [e[0] / s, e[1] / s, e[2] / s], ay = [e[4] / s, e[5] / s, e[6] / s], az = [e[8] / s, e[9] / s, e[10] / s];
      const at = (r, u, bk) => [0, 1, 2].map(k => o[k] + (ax[k] * r + ay[k] * u - az[k] * bk) * s);
      const tb = F.birds[Math.min(v[3], F.birds.length - 1)]; const m2 = new (g.matrix.constructor)(); g.userData.batch.getMatrixAt(tb.id, m2);
      window.__camPin = { pos: at(v[0], v[1], v[2]), look: [m2.elements[12], m2.elements[13], m2.elements[14]] };
      window.__fcLoop = requestAnimationFrame(step);
    };
    step(); return { visible: g.visible, birds: F.birds.length };
  }, views[i])));
  await w(1800); await p.screenshot({ path: `${process.env.OUT}_${i}.jpg`, type: 'jpeg', quality: 88 });
}
console.log(errs.length ? 'ERR ' + errs[0] : 'no errors');
await b.close();
