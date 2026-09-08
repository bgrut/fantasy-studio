import puppeteer from 'puppeteer-core';
const SP = process.env.SP;
const b = await puppeteer.launch({ headless: 'new',
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1400,860'] });
const p = await b.newPage(); await p.setViewport({ width: 1400, height: 860 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 180)));
await p.goto('http://127.0.0.1:8789/games/job_8/dist/', { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 7000)); await p.click('#startbtn').catch(() => {});
await new Promise(r => setTimeout(r, 8000));
console.log('alive:', await p.evaluate(() => typeof window.__game), '| errors:', errs.length ? errs.join('|') : 'none');
console.log(await p.evaluate(() => {
  const tags = [];
  window.__scene.traverse(o => {
    if (o.userData && o.userData.fsTag && o.userData.fsTag.type === 'placed')
      tags.push(o.userData.fsTag.kind + '@(' + o.position.x.toFixed(0) + ',' + o.position.z.toFixed(0) + ')');
  });
  return 'placed in scene: ' + tags.join(' ');
}));
// stand south of the set looking north across it
await p.evaluate(() => window.__game.tp(8, 55));
await new Promise(r => setTimeout(r, 3500));
await p.screenshot({ path: SP + '/propset_village.jpg', type: 'jpeg', quality: 92 });
await p.evaluate(() => window.__game.tp(2, 41));
await new Promise(r => setTimeout(r, 3000));
await p.screenshot({ path: SP + '/propset_close.jpg', type: 'jpeg', quality: 92 });
await b.close();
