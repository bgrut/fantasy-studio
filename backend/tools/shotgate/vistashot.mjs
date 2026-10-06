// Scenery: a high view over the land toward the horizon (the mountains and
// the forest to the edge), a low look through the foliage ahead, and the view
// back toward the start, each pinned, guide hidden.   J=job_N OUT=<dir> TAG= node vistashot.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.', TAG = process.env.TAG || J;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 12000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 3000)); await p.keyboard.press('g');
await new Promise(r => setTimeout(r, 1500));
// hide the HUD for clean scenery frames
await p.addStyleTag({ content: '#hud,#tutor,#guide,#objective,#obj,.fs-guide,#minimap,#fps,#hint,#toast,.kit-toast,#help{display:none!important}' }).catch(() => {});
const views = [
  ['vista', (pp, fx, fz) => ({ pos: [pp[0] - fx * 12, pp[1] + 14, pp[2] - fz * 12], look: [pp[0] + fx * 90, pp[1] + 4, pp[2] + fz * 90] })],
  ['foliage', (pp, fx, fz) => ({ pos: [pp[0] + fz * 6, pp[1] + 1.4, pp[2] - fx * 6], look: [pp[0] + fx * 30 + fz * 6, pp[1] + 2.2, pp[2] + fz * 30 - fx * 6] })],
  ['back', (pp, fx, fz) => ({ pos: [pp[0] + fx * 6, pp[1] + 3.5, pp[2] + fz * 6], look: [pp[0] - fx * 60, pp[1] + 3, pp[2] - fz * 60] })],
];
for (const [name, fn] of views) {
  await p.evaluate((src) => {
    const g = window.__game, pp = g.pos(), yaw = g.heading();
    const fx = -Math.sin(yaw), fz = -Math.cos(yaw);
    window.__camPin = (new Function('return ' + src))()(pp, fx, fz);
  }, fn.toString());
  await new Promise(r => setTimeout(r, 1400));
  await p.screenshot({ path: `${OUT}/${TAG}_${name}.jpg`, type: 'jpeg', quality: 90 });
}
console.log(TAG, JSON.stringify(errs.slice(0, 3)));
await b.close();
