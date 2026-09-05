import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
await p.goto(process.env.U,{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,14000));            // long settle: shaders compiled
const runs=[];
for (let i=0;i<3;i++){
  runs.push(await p.evaluate(()=>new Promise(res=>{let n=0;const t0=performance.now();
    const t=()=>{n++; if(performance.now()-t0<3000) requestAnimationFrame(t); else res(Math.round(n/((performance.now()-t0)/1000)));};
    requestAnimationFrame(t);})));
}
console.log('fps runs:', runs.join(', '),
  '| dpr:', await p.evaluate(()=>window.__renderer ? window.__renderer.getPixelRatio() : 'n/a'),
  '| tris:', (await p.evaluate(()=>window.__game.stats())).tris);
await b.close();
