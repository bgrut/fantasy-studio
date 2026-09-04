import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
await p.goto('http://127.0.0.1:8789/games/job_14/dist/',{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,7000));
const before = await p.evaluate(()=>window.__game.facts().dyn_pos);
console.log('barrel positions before:', JSON.stringify(before));
// stand the player right next to barrel 0 and walk into it
await p.evaluate(t=>{ window.__game.tp(t[0]-1.4, t[2]); }, before[0]);
await new Promise(r=>setTimeout(r,900));
await p.keyboard.down('d');                       // strafe into it
await new Promise(r=>setTimeout(r,300));
await p.keyboard.up('d');
await p.keyboard.down('w');
await new Promise(r=>setTimeout(r,2500));
await p.keyboard.up('w');
await new Promise(r=>setTimeout(r,1200));
const after = await p.evaluate(()=>window.__game.facts().dyn_pos);
console.log('barrel positions after :', JSON.stringify(after));
const d = Math.hypot(after[0][0]-before[0][0], after[0][2]-before[0][2]);
console.log('barrel 0 moved:', d.toFixed(3), 'm');
console.log('settled now:', await p.evaluate(()=>window.__game.facts().dyn_settled));
await p.screenshot({path:process.env.SP+'/push.jpg',type:'jpeg',quality:92});
await b.close();
