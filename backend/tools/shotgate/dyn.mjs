import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,200)));
p.on('console',m=>{ if(m.type()==='error') errs.push('c:'+m.text().slice(0,160)); });
await p.goto(process.env.U,{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,8000));
console.log('errors:', errs.length?errs.slice(0,4).join(' | '):'none');
console.log(JSON.stringify(await p.evaluate(()=>{
  const out={};
  try{ const sp=JSON.parse(document.querySelector('script#spec')?.textContent||'null'); }catch(e){}
  out.facts = window.__game.facts();
  let inst=0, instTotal=0;
  window.__scene.traverse(o=>{ if(o.isInstancedMesh){ inst++; instTotal+=o.count; } });
  out.instancedMeshes=inst; out.instances=instTotal;
  return out;
}),null,1));
await b.close();
