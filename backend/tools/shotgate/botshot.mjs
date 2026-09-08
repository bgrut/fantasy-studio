import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/?fresh=1&debug=1',
  { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,6000));
console.log(JSON.stringify(await p.evaluate(async ()=>{
  const F = window.__factory, TY = F.TYPES;
  window.__game.inspect(true);
  const n = F.FACES[1].n;
  F.orbit(0, -1.30, F.HALF * 2.4);
  // a line of machines across the underside, so there is plenty to see
  const out = [];
  for (let k = -3; k <= 3; k++) {
    const i = Math.floor(F.N / 2) + k * 2, j = Math.floor(F.N / 2);
    if (F.cells[1][i][j].t === TY.EMPTY) out.push(F.place(1, i, j, TY.SMELTER, 0));
  }
  await new Promise(r => setTimeout(r, 900));
  const dec = window.__scene.getObjectByName('contact');
  return { placed: out.length, decalCount: dec.count, decalVisible: dec.visible,
           camY: +window.__camera.position.y.toFixed(1), HALF: F.HALF,
           machines: window.__game.facts().machines };
}), null, 1));
await p.screenshot({ path: process.env.OUT });
await b.close();
