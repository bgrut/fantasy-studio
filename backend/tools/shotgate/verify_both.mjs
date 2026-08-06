import puppeteer from 'puppeteer-core';
const SP = process.env.SP;
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
for (const [job, tag, tps] of [
  ['job_10', 'heist', [null]],
  ['job_11', 'city', [null, [20, -34], [-28, 22]]],
]) {
  const p = await b.newPage();
  await p.setViewport({ width: 1600, height: 900 });
  const errs = [];
  p.on('pageerror', e => errs.push(e.message.slice(0, 200)));
  await p.goto(`http://127.0.0.1:8789/games/${job}/dist/`, { waitUntil: 'networkidle2', timeout: 90000 });
  await new Promise(r => setTimeout(r, 5000));
  await p.click('#startbtn').catch(() => {});
  await new Promise(r => setTimeout(r, 6000));
  const alive = await p.evaluate(() => typeof window.__game);
  console.log(`${tag}: alive=${alive} errors=${errs.length ? errs.join(' | ') : 'none'}`);
  console.log('  stats:', JSON.stringify(await p.evaluate(() => ({
    peds: (window.__peds || []).length, traffic: (window.__traffic || []).length,
    cars: (window.__cars || []).length, npcs: (window.__game.npcs ? window.__game.npcs().length : -1),
    obj: window.__game.objectives ? window.__game.objectives() : null }))));
  let i = 0;
  for (const tp of tps) {
    if (tp) await p.evaluate(([x, z]) => window.__game.tp(x, z), tp);
    await new Promise(r => setTimeout(r, 2600));
    await p.screenshot({ path: `${SP}/v_${tag}_${i++}.jpg`, type: 'jpeg', quality: 88 });
  }
  await p.close();
}
await b.close();
