// The goal building, looked at: from the approach, from a corner, and from the player's start. J=N OUT=prefix node _goalshot.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--disable-gpu-sandbox', '--window-size=1280,720', '--disable-renderer-backgrounding', '--disable-background-timer-throttling'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/job_${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await w(500); }
await w(4000); await p.click('#startbtn').catch(() => {}); await w(6000);
const g = await p.evaluate(() => { let G = null; window.__scene.traverse(o => { if (!G && o.userData && o.userData.fsTag && o.userData.fsTag.type === 'goal') G = o; });
  if (!G) return null; return { pos: G.position.toArray(), yaw: G.rotation.y, name: G.userData.fsTag.name, station: window.__station || null }; });
console.log('goal', JSON.stringify(g));
if (g) {
  const [x, y, z] = g.pos, s = Math.sin(g.yaw), c = Math.cos(g.yaw);
  const L = (a, h, d) => [x + s * d + c * a, y + h, z + c * d - s * a];   // local (a across, d out the door) to world
  const pins = [{ pos: L(3, 3.2, 17), look: L(0, 2.2, 0) }, { pos: L(-14, 6, 12), look: L(0, 2.5, -1) }, { pos: L(9, 2.0, 9), look: L(-3, 2.2, -2) }];
  for (let k = 0; k < pins.length; k++) { await p.evaluate(pn => { window.__camPin = pn; }, pins[k]); await w(2000); await p.screenshot({ path: `${process.env.OUT}_${k}.jpg`, type: 'jpeg', quality: 88 }); }
}
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'no errors');
await b.close();
