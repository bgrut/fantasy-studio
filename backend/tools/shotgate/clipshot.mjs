import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,140)));
await p.goto('http://127.0.0.1:8789/games/job_8/dist/clipview.html',{waitUntil:'networkidle2',timeout:90000});
await p.waitForFunction('window.__ready===true',{timeout:60000}).catch(()=>{});
console.log('errors:', errs.join('|')||'none');
console.log('clips:', JSON.stringify(await p.evaluate(()=>window.__clips)));
const shots = [['idle',1.0],['walk',0.5],['jump',0.5],['sneak',0.5],['die',1.0]];
for (const [name,t] of shots) {
  const ok = await p.evaluate((n,tt)=>window.__play(n,tt), name, t);
  if(!ok){ console.log(name,'-> NOT FOUND'); continue; }
  await new Promise(r=>setTimeout(r,350));
  const pr = await p.evaluate(()=>window.__probe());
  console.log(name.padEnd(7), JSON.stringify(pr));
  await p.screenshot({path:process.env.SP+'/clip_'+name+'.jpg',type:'jpeg',quality:92});
}
await b.close();
