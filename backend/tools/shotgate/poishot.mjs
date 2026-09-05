import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({width:1600,height:900});
await p.goto(process.env.U,{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,9000));
// fly to the nearest point of interest and look at it
const info = await p.evaluate(()=>{
  const L = window.__spec ? null : null;
  const pois = (window.__LVL && window.__LVL.pois) || null;
  return { hasPois: !!pois };
});
await p.evaluate(()=>{ const c=window.__camera, s=window.__game.pos();
  c.position.set(s[0]+22, s[1]+14, s[2]+22); c.lookAt(s[0], s[1]+1, s[2]); });
await new Promise(r=>setTimeout(r,1200));
await p.screenshot({path:process.env.OUT,type:'jpeg',quality:90});
console.log('shot', JSON.stringify(info));
await b.close();
