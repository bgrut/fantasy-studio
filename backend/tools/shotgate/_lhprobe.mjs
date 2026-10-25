// The lighthouse climb: in through the door, up the stair, the lamp lit at the top.
// J=job_N OUT=prefix node _lhprobe.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(500); }
await wait(3000); await p.click('#startbtn').catch(() => {}); await wait(3000);
for (let i = 0; i < 120; i++) { if (await p.evaluate(() => { const f = window.__game.facts(); return !f.intro && !f.paused; })) break; await wait(500); }
await wait(1500);
const OUT = process.env.OUT || 'lh';
const state = () => p.evaluate(() => ({ climb: window.__lhClimb && { lit: window.__lhClimb.lit, gate: window.__lhClimb.gate, top: window.__lhClimb.top, steps: window.__lhClimb.steps },
  pos: window.__game.bpos().map(v => +v.toFixed(2)), water: (() => { let v = null; window.__scene.traverse(o => { if (o.isMesh && o.geometry.type === 'PlaneGeometry' && o.material && o.material.userData && o.material.userData.waterKind) v = o.visible; }); return v; })(), quest: ((document.body.innerText.match(/(Reach|Climb|Relight)[^\n]{0,60}/) || [''])[0]) }));
console.log('start ', JSON.stringify(await state()));
// to the door: it teleports us inside
const door = await p.evaluate(() => window.__doors && window.__doors[0] && window.__doors[0].out);
await p.evaluate((d) => window.__game.tp(d[0], d[1]), door); await wait(2500);
console.log('inside', JSON.stringify(await state()));
await p.screenshot({ path: `${OUT}_in.jpg`, type: 'jpeg', quality: 80 });
// walk the stair a while: W held, turning a little left as the stair winds
await p.keyboard.down('KeyW'); for (let k = 0; k < 10; k++) { await p.keyboard.down('KeyA'); await wait(180); await p.keyboard.up('KeyA'); await wait(420); } await p.keyboard.up('KeyW');
await wait(600);
console.log('walked', JSON.stringify(await state()));
await p.screenshot({ path: `${OUT}_stair.jpg`, type: 'jpeg', quality: 80 });
// up on the landing beside the lamp
const L = await p.evaluate(() => window.__lhClimb);
// first onto the landing's far side, the lens still dark ahead
const land = await p.evaluate((L) => { const AN = Math.PI / 2 + 0.5 + (L.steps - 1) * 0.27, a = AN + 0.135 + (Math.PI * 2 - 2.6) * 0.6; return [L.x + Math.cos(a) * 2.25, L.y + 1.0, Math.sin(a) * 2.25]; }, L);
await p.evaluate((q) => window.__game.tp3(q[0], q[1], q[2]), land); await wait(3500);
console.log('landing', JSON.stringify(await state()));
await p.screenshot({ path: `${OUT}_landing.jpg`, type: 'jpeg', quality: 80 });
await p.evaluate((L) => window.__game.tp3(L.x + 1.5, L.y + 1.1, 0.3), L);
await wait(2000);
console.log('top   ', JSON.stringify(await state()));
await p.screenshot({ path: `${OUT}_top.jpg`, type: 'jpeg', quality: 80 });
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'errors none');
await b.close();
