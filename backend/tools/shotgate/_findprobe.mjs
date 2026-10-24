// The lost are found by reaching them: walk (teleport) to each find spot and see the step count up.
//   J=job_N OUT=prefix node _findprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await p.click('#startbtn').catch(() => {}); await wait(3000);
await p.screenshot({ path: `${process.env.OUT}_spawn.jpg`, type: 'jpeg', quality: 85 });
const spots = await p.evaluate(() => { const out = []; window.__scene.traverse(o => { const t = o.userData && o.userData.fsTag; if (t && t.type === 'objective') out.push([o.position.x, o.position.z, t.name]); }); return out; });
console.log('spots', JSON.stringify(spots.map(s => [+s[0].toFixed(1), +s[1].toFixed(1), s[2]])));
for (let i = 0; i < spots.length; i++) {
  await p.evaluate(a => window.__game.tp(a[0] + 1.2, a[1] + 1.2), spots[i]); await wait(2500);
  if (i === 0) await p.screenshot({ path: `${process.env.OUT}_found.jpg`, type: 'jpeg', quality: 85 });
  console.log('after', i + 1, await p.evaluate(() => document.querySelector('#hud') ? document.querySelector('#hud').innerText.split('\n').slice(0, 4).join(' | ') : ''));
}
await wait(1500); await p.screenshot({ path: `${process.env.OUT}_end.jpg`, type: 'jpeg', quality: 85 });
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'no errors');
await b.close();
