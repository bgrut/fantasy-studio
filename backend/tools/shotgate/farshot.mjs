// The other worlds in the flagship's sky: stands on the home face and looks
// at each far world in turn, reporting what they say.   [URL=] OUT=<dir> [Q=creative=1] TAG= node farshot.mjs
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/', OUT = process.env.OUT || '.', Q = process.env.Q || '', TAG = process.env.TAG || 'far';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
await p.goto(URL + (Q ? '?' + Q : ''), { waitUntil: 'domcontentloaded', timeout: 60000 });
await sleep(8000); await p.keyboard.press('Enter').catch(() => {}); await sleep(3500); await p.keyboard.press('g').catch(() => {}); await sleep(800);
const worlds = await p.evaluate(() => {
  const g = window.__scene.getObjectByName('farWorlds');
  return g ? g.children.map(c => ({ pos: c.position.toArray(), open: c.userData.open, k: c.userData.k })) : null;
});
console.log(TAG, 'worlds', JSON.stringify(worlds));
if (worlds) for (let i = 0; i < worlds.length; i++) {
  await p.evaluate((w) => {
    const F = window.__factory, H = F.HALF;
    const from = [0, H + 4, 0], d = [w.pos[0] - from[0], w.pos[1] - from[1], w.pos[2] - from[2]];
    const l = Math.hypot(...d);
    // from the plate, looking out at it, with a little of the worldlet's edge in the frame
    window.__camPin = { pos: from, look: [from[0] + d[0] / l * 50, from[1] + d[1] / l * 50 - 4, from[2] + d[2] / l * 50], up: [0, 1, 0] };
  }, worlds[i]);
  await sleep(900);
  await p.screenshot({ path: `${OUT}/${TAG}_${i}.jpg`, type: 'jpeg', quality: 90 });
}
console.log('errors', JSON.stringify(errs.slice(0, 4)));
await b.close();
