import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,160)));
await p.goto(process.env.U,{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,7000));
console.log('before:', JSON.stringify(await p.evaluate(()=>({
  dyn: window.__game.facts().dynamic_props,
  npcs: window.__game.npcs().length,
  dead: window.__game.npcs().filter(n=>n.dead).length}))));
// walk into the hostiles and swing until something dies
for (let i=0;i<40;i++){
  await p.evaluate(()=>{
    const ns=window.__game.npcs().filter(n=>!n.dead && n.behavior==='hostile');
    if(ns.length){ const t=ns[0].pos; window.__game.tp(t[0]+1.0, t[2]); }
  });
  await p.evaluate(()=>window.__game.attack && window.__game.attack());
  await new Promise(r=>setTimeout(r,220));
  const d = await p.evaluate(()=>window.__game.npcs().filter(n=>n.dead).length);
  if (d>0) break;
}
await new Promise(r=>setTimeout(r,2500));
console.log('after :', JSON.stringify(await p.evaluate(()=>({
  dyn: window.__game.facts().dynamic_props,
  dead: window.__game.npcs().filter(n=>n.dead).length}))));
console.log('errors:', errs.length?errs.slice(0,2).join('|'):'none');
await p.screenshot({path:process.env.SP+'/ragdoll.jpg',type:'jpeg',quality:92});
await b.close();
