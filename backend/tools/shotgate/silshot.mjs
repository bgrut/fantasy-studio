import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
for (const J of process.env.JOBS.split(',')) {
  const p = await b.newPage(); await p.setViewport({width:1280,height:720});
  const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,120)));
  await p.goto(`http://127.0.0.1:8789/games/job_${J}/dist/`,{waitUntil:'domcontentloaded',timeout:60000});
  await new Promise(r=>setTimeout(r,6500)); await p.click('#startbtn').catch(()=>{});
  await new Promise(r=>setTimeout(r,5000));
  // stand east of the west forest, looking across it at the mountains
  await p.evaluate(()=>window.__game.tp(-30, 0));
  await new Promise(r=>setTimeout(r,3200));
  console.log(`job_${J} alive:`, await p.evaluate(()=>typeof window.__game),
    '| errors:', errs.length?errs.join('|'):'none',
    '| trees:', await p.evaluate(()=>{
      let n=0; window.__scene.traverse(o=>{ if(o.isInstancedMesh && o.count>50) n=Math.max(n,o.count); });
      return n; }));
  await p.screenshot({ path: `${process.env.SP}/sil_${J}.jpg`, type:'jpeg', quality:92 });
  await p.close();
}
await b.close();
