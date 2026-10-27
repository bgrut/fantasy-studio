// Shoot a job from pinned cameras: PINS is a JS expression evaluated in the
// page returning [{pos:[x,y,z], look:[x,y,z]}, ...]. J=job_N OUT=prefix PINS='...' node _cam.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900', '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(3500);
const pins = await p.evaluate(src => eval(src), process.env.PINS);
for (let i = 0; i < pins.length; i++) {
  await p.evaluate(pin => { window.__camPin = pin; }, pins[i]);
  await wait(1800); await p.screenshot({ path: `${process.env.OUT}_${i}.jpg`, type: 'jpeg', quality: 88 });
}
console.log(JSON.stringify(pins), errs.length ? 'ERR ' + errs.join(' | ') : '');
await b.close();
