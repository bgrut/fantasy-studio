import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,200)));
const sl=ms=>new Promise(r=>setTimeout(r,ms));
await p.goto(`http://127.0.0.1:8789/games/job_7/dist/`,{waitUntil:'networkidle2',timeout:90000});
await sl(6000); await p.click('#startbtn').catch(()=>{}); await sl(8000);
const p0=await p.evaluate(()=>window.__game.pos());
await p.keyboard.down('ShiftLeft'); await p.keyboard.down('KeyW');
await sl(4000);
await p.keyboard.up('KeyW'); await p.keyboard.up('ShiftLeft'); await sl(400);
const p1=await p.evaluate(()=>window.__game.pos());
console.log('RACE (Shift held) moved:', Math.hypot(p1[0]-p0[0],p1[2]-p0[2]).toFixed(2),'m');
console.log('quest:', JSON.stringify(await p.evaluate(()=>window.__game.quest())));
await p.screenshot({path:'./shots_regress/RACE_shift.png'});
console.log('pageerrors:', errs.length?errs:'none');
await b.close();
