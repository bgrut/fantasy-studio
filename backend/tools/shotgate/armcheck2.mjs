import puppeteer from 'puppeteer-core';
const b=await puppeteer.launch({headless:'new',executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--use-angle=d3d11','--window-size=1280,720']});
const p=await b.newPage(); await p.setViewport({width:1280,height:720});
await p.goto('http://127.0.0.1:8789/games/job_1/dist/clipview.html',{waitUntil:'networkidle2',timeout:90000});
await p.waitForFunction('window.__ready===true',{timeout:60000});
console.log('clips:', JSON.stringify(await p.evaluate(()=>window.__clips)));
for (const [n,t] of [['idle',1.2],['sneak',0.5],['walk',0.4]]) {
  const ok=await p.evaluate((a,b)=>window.__play(a,b),n,t);
  if(!ok){console.log(n,'-> absent');continue;}
  await new Promise(r=>setTimeout(r,300));
  console.log(n.padEnd(6), JSON.stringify(await p.evaluate(()=>window.__arms())));
  await p.screenshot({path:process.env.SP+'/reb_'+n+'.jpg',type:'jpeg',quality:92});
}
await b.close();
