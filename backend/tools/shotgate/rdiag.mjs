import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('pageerror', e => console.log('PAGEERROR:', e.message.slice(0,400)));
p.on('console', m => { if (m.type()==='error') console.log('CONSOLE:', m.text().slice(0,300)); });
await p.setViewport({ width:1280, height:760 });
await p.goto('http://127.0.0.1:8789/games/job_15/dist/', { waitUntil:'domcontentloaded', timeout:60000 });
await new Promise(r=>setTimeout(r,5000));
console.log(JSON.stringify(await p.evaluate(()=>{
  const F = window.__factory, TY = F.TYPES;
  const out = { RIFT: TY.RIFT, hasRiftOpen: typeof F.riftOpen };
  let placed = null;
  for (let i = 5; i < F.N - 5 && !placed; i++)
    for (let j = 5; j < F.N - 5 && !placed; j++)
      if (F.cells[0][i][j].t === TY.EMPTY) placed = [i, j];
  out.spot = placed;
  try { out.ret = F.place(0, placed[0], placed[1], TY.RIFT, 0); }
  catch (e) { out.err = String(e).slice(0, 200); }
  const c = F.cells[0][placed[0]][placed[1]];
  out.cell = { t: c.t, dbt: c.dbt, emit: c.emit, left: c.left, cool: c.cool,
               hasBuild: !!c.build };
  return out;
}), null, 1));
await new Promise(r=>setTimeout(r,1500));
console.log('after 1.5s:', JSON.stringify(await p.evaluate(()=>window.__game.facts().rift)));
await b.close();
