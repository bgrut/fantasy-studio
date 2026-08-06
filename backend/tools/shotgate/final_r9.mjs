import puppeteer from 'puppeteer-core';
const SP = process.env.SP, H = process.env.H;
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
for (const [job, tag] of [[H, 'heist'], ['job_7', 'city']]) {
  const p = await b.newPage();
  await p.setViewport({ width: 1600, height: 900 });
  const errs = [];
  p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
  await p.evaluateOnNewDocument(() => {
    window.addEventListener('unhandledrejection', ev => console.error('UNHANDLED: ' + ev.reason));
  });
  await p.goto(`http://127.0.0.1:8789/games/${job}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
  await new Promise(r => setTimeout(r, 5000));
  await p.click('#startbtn').catch(() => {});
  await new Promise(r => setTimeout(r, 7000));
  console.log(`${tag}: alive=${await p.evaluate(() => typeof window.__game)} errors=${errs.length ? errs.join('|') : 'none'}`);
  console.log('  ', await p.evaluate(() => JSON.stringify({
    peds: (window.__peds || []).length, traffic: (window.__traffic || []).length,
    cars: (window.__cars || []).length, npcs: window.__game.npcs().length,
    jewels: window.__game.objectives().left.length,
    calls: window.__renderer.info.render.calls,
    fps: (document.querySelector('#fps') || {}).textContent })));
  await p.evaluate(() => window.__game.tp(16, -30)).catch(() => {});
  await new Promise(r => setTimeout(r, 3200));
  await p.screenshot({ path: `${SP}/z_${tag}.jpg`, type: 'jpeg', quality: 90 });
  await p.close();
}
await b.close();
