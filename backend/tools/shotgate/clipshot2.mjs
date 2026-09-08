import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
await p.goto('http://127.0.0.1:8789/games/job_8/dist/clipview.html',{waitUntil:'networkidle2',timeout:90000});
await p.waitForFunction('window.__ready===true',{timeout:60000});
console.log('mesh:', JSON.stringify(await p.evaluate(()=>window.__holes())));
for (const [n,t] of [['idle',1.0],['walk',0.5]]) {
  await p.evaluate((a,b)=>window.__play(a,b), n, t);
  await new Promise(r=>setTimeout(r,400));
  await p.screenshot({path:process.env.SP+'/fix_'+n+'.jpg',type:'jpeg',quality:94});
}
console.log('shots saved'); await b.close();
