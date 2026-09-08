import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0,400)));
const t0 = Date.now();
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/?fresh=1',
  { waitUntil:'domcontentloaded', timeout:60000 });
for (let k = 0; k < 40; k++) {
  const ok = await p.evaluate(()=>typeof window.__game === 'object');
  if (ok) { console.log('__game ready after', Date.now() - t0, 'ms'); break; }
  await new Promise(r=>setTimeout(r,250));
}
console.log('final:', await p.evaluate(()=>typeof window.__game));
await b.close();
