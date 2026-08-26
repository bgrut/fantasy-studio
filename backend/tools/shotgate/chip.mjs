import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1400,860'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:860});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,150)));
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:60000});
await new Promise(r=>setTimeout(r,6000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,4500));
console.log('alive:', await p.evaluate(()=>typeof window.__game), '| errors:', errs.length?errs.join('|'):'none');
const info = await p.evaluate(async ()=>{
  let esc=null;
  window.__scene.traverse(o=>{ const t=o.userData&&o.userData.fsTag;
    if(!esc && t && t.type==='npc' && /escort/.test(t.detail||'')) esc=o; });
  if(!esc) return 'no escort';
  const chip = !!esc.userData.fsEscortChip;
  // stand close, walk beside him for a moment, then screenshot with him framed
  window.__game.tp(esc.position.x - 2.5, esc.position.z - 2.5);
  await new Promise(r=>setTimeout(r,2500));
  const rec=(window.__game.npcs()||[]).find(x=>x.behavior==='escort');
  return JSON.stringify({ chip, speed: rec && rec.speed });
});
console.log('escort:', info);
await p.screenshot({ path: process.env.SP + '/escort_chip.jpg', type:'jpeg', quality:93 });
await b.close();
