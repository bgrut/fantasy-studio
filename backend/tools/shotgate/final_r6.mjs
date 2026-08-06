import puppeteer from 'puppeteer-core';
const SP = process.env.SP;
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
for (const [job, tag] of [['job_17', 'heist'], ['job_16', 'city']]) {
  const p = await b.newPage();
  await p.setViewport({ width: 1600, height: 900 });
  const errs = [];
  p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
  await p.goto(`http://127.0.0.1:8789/games/${job}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
  await new Promise(r => setTimeout(r, 5000));
  await p.click('#startbtn').catch(() => {});
  await new Promise(r => setTimeout(r, 7000));
  console.log(`${tag}: alive=${await p.evaluate(() => typeof window.__game)} errors=${errs.length ? errs.join('|') : 'none'}`);
  console.log('  ', await p.evaluate(() => JSON.stringify({
    peds: (window.__peds || []).length, traffic: (window.__traffic || []).length,
    cars: (window.__cars || []).length, parked: (window.__parkedSpots || []).length,
    npcs: window.__game.npcs().length, jewels: window.__game.objectives().left.length,
    fps: (document.querySelector('#fps') || {}).textContent })));
  if (tag === 'city') {
    // stand right behind a walking pedestrian so their facing can be judged
    await p.evaluate(async () => {
      const pd = window.__peds.find(x => x.obj.visible);
      const a = pd.obj.position;
      window.__game.tp(a.x - Math.sin(pd.obj.rotation.y) * 5, a.z - Math.cos(pd.obj.rotation.y) * 5);
    });
    await new Promise(r => setTimeout(r, 2600));
    await p.screenshot({ path: `${SP}/f_ped.jpg`, type: 'jpeg', quality: 90 });
  }
  await p.evaluate(() => window.__game.tp(12, -26)).catch(() => {});
  await new Promise(r => setTimeout(r, 3000));
  await p.screenshot({ path: `${SP}/f_${tag}.jpg`, type: 'jpeg', quality: 88 });
  await p.close();
}
await b.close();
