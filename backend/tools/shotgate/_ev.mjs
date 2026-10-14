import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width:1600, height:900 }); const errs=[]; p.on('pageerror', e=>errs.push(e.message.slice(0,200)));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/?noguide=1`, { waitUntil:'domcontentloaded' });
await new Promise(r=>setTimeout(r,12000)); await p.click('#startbtn').catch(()=>{}); await new Promise(r=>setTimeout(r,3000));
await p.keyboard.down('KeyW'); await new Promise(r=>setTimeout(r,2500)); await p.keyboard.up('KeyW'); await new Promise(r=>setTimeout(r,1200));
await p.screenshot({ path: process.env.OUT + '_pair.jpg', type:'jpeg', quality:85 });
const pts = await p.evaluate(() => { const o = []; window.__scene.traverse(m => { if (m.userData && m.userData.fsTag && m.userData.fsTag.type === 'collectible') o.push([m.position.x, m.position.y, m.position.z]); }); return o; });
for (let i = 0; i < Math.min(2, pts.length); i++) { const [x, y, z] = pts[i];
  await p.evaluate((x, y, z) => { window.__camPin = { pos: [x + 0.9, y + 0.7, z + 0.9], look: [x, y + 0.1, z] }; }, x, y, z);
  await new Promise(r=>setTimeout(r,1200)); await p.screenshot({ path: process.env.OUT + '_ev' + i + '.jpg', type:'jpeg', quality:85 }); }
console.log('evidence', pts.length, errs.join(' | ') || 'ok'); await b.close();
