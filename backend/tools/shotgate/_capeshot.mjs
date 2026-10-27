// The hero's cloth, moving: stand, walk, run, turn, stop, each shot from a camera that rides with the hero.
// J=job_N OUT=prefix [SIDE=1] node _capeshot.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,800', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 800 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
p.on('console', m => { if (/cape|cloth/i.test(m.text())) errs.push('console: ' + m.text().slice(0, 200)); });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.waitForFunction(() => window.__game && document.querySelector('#startbtn'), { timeout: 90000 }).catch(() => {});
await wait(4000); await p.click('#startbtn').catch(() => {});
await p.waitForFunction(() => window.__game && !(window.__game.facts && window.__game.facts().intro), { timeout: 30000 }).catch(() => {});
await wait(2500);
// a camera behind and to the side of the hero, looking at the shoulders
await p.evaluate((side) => {
  window.__camPin = () => { const a0 = window.__game.pos(), q = { x: a0[0], y: a0[1], z: a0[2] }, y = window.__heroYaw || 0;
    const fx = Math.sin(y), fz = Math.cos(y), a = side ? 1.9 : 0.55, d = 3.4;
    const cx = q.x - (fx * Math.cos(a) - fz * Math.sin(a)) * d, cz = q.z - (fz * Math.cos(a) + fx * Math.sin(a)) * d;
    return { pos: [cx, q.y + 1.9, cz], look: [q.x, q.y + 1.0, q.z] }; };
}, !!process.env.SIDE);
const shot = async (n) => { await p.screenshot({ path: `${process.env.OUT}_${n}.jpg`, type: 'jpeg', quality: 86 }); };
const facts = async () => p.evaluate(() => ({ cape: window.__cape ? window.__cape() : null, fps: window.__game.facts ? window.__game.facts().fps : null }));
await shot('stand');
await p.keyboard.down('KeyW'); await wait(1600); await shot('walk');
await p.keyboard.down('ShiftLeft'); await wait(1800); await shot('run');
await p.keyboard.down('KeyA'); await wait(700); await shot('turn'); await p.keyboard.up('KeyA');
await wait(600); await p.keyboard.up('ShiftLeft'); await p.keyboard.up('KeyW'); await wait(350); await shot('stop');
await wait(2500); await shot('settle');
console.log(JSON.stringify(await facts()), errs.length ? 'ERR ' + errs.join(' | ') : '');
await b.close();
