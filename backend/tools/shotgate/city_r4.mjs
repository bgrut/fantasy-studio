import puppeteer from 'puppeteer-core';
const SP = process.env.SP;
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1600,900'] });
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 900 });
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0, 220)));
await p.goto('http://127.0.0.1:8789/games/job_12/dist/', { waitUntil: 'networkidle2', timeout: 90000 });
await new Promise(r => setTimeout(r, 5000));
await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 6000));
console.log('alive:', await p.evaluate(() => typeof window.__game));
console.log('stats:', JSON.stringify(await p.evaluate(() => ({
  peds: (window.__peds || []).length,
  traffic: (window.__traffic || []).length,
  cars: (window.__cars || []).length,
  built: (window.__builtFootprints || []).length,
}))));
const shots = [
  ['a_spawn', null],
  ['b_street', [18, -40]],
  ['c_block', [-30, 25]],
  ['d_far', [60, 60]],
];
for (const [name, tp] of shots) {
  if (tp) await p.evaluate(([x, z]) => window.__game.tp(x, z), tp);
  await new Promise(r => setTimeout(r, 2600));
  await p.screenshot({ path: `${SP}/r4_${name}.jpg`, type: 'jpeg', quality: 88 });
}
console.log('render:', JSON.stringify(await p.evaluate(() => {
  const r = window.__renderer || null;
  return r ? { calls: r.info.render.calls, tris: r.info.render.triangles,
               programs: r.info.programs.length } : 'no __renderer';
})));
await b.close();
