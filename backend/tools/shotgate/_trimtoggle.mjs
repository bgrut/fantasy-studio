import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(3500);
await p.screenshot({ path: process.env.OUT + '_on.jpg', type: 'jpeg', quality: 90 });
const M = await p.evaluate(() => { const L = []; window.__scene.traverse(o => { if (o.isInstancedMesh && o.geometry.type === 'BoxGeometry' && o.count > 3 && o.geometry.parameters.width === 1) L.push(o); });
  window.__trims = L; const M4 = L[0].matrixWorld.constructor, V = window.__scene.position.constructor;
  return L.map(o => { const m = new M4(); o.getMatrixAt(0, m); return +new V().setFromMatrixPosition(m).y.toFixed(2); }); });
console.log(JSON.stringify(M));
for (let k = 0; k < M.length; k++) { await p.evaluate(k => window.__trims.forEach((o, i) => o.visible = i !== k), k); await wait(900); await p.screenshot({ path: process.env.OUT + '_hide' + k + '.jpg', type: 'jpeg', quality: 90 }); }
await wait(1200); await p.screenshot({ path: process.env.OUT + '_off.jpg', type: 'jpeg', quality: 90 });
await b.close();
