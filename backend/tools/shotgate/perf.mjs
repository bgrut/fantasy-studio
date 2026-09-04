import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1920,1080'] });
const p = await b.newPage(); await p.setViewport({width:1920,height:1080});
await p.goto(process.env.U,{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,9000));
console.log('stats:', JSON.stringify(await p.evaluate(()=>window.__game.stats())));
const fps = await p.evaluate(()=>new Promise(res=>{let n=0;const t0=performance.now();
  const tick=()=>{n++; if(performance.now()-t0<2000) requestAnimationFrame(tick); else res(Math.round(n/((performance.now()-t0)/1000)));};
  requestAnimationFrame(tick);}));
console.log('fps:', fps);
await p.screenshot({path:process.env.SP+'/terrain.png'});
await b.close();
