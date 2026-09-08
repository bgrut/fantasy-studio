import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,180)));
await p.goto('http://127.0.0.1:8789/games/job_7/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,1200));
const S=async()=>await p.evaluate(()=>{const c=window.__game.combat(),o=window.__game.objectives(),pp=window.__game.pos();
  const g=(window.__game.npcs()||[]).filter(n=>n.behavior==='guard');
  return {hp:c.hp,got:o.collected,left:o.left.map(l=>[l[0],l[2]]),pos:[+pp[0].toFixed(1),+pp[2].toFixed(1)],
    alert:+(window.__alertPeak||0).toFixed(2),
    near:+Math.min(...g.map(n=>Math.hypot(n.pos[0]-pp[0],n.pos[2]-pp[2]))).toFixed(1),
    chasing:g.filter(n=>n.mode==='chase').length};});
let s=await S(); console.log('spawn:', JSON.stringify(s));
// teleport-free honest play: crouch and walk to each jewel using long holds
await p.keyboard.down('KeyC');
for (let j=0;j<4;j++){
  for (let step=0; step<40; step++){
    s=await S(); if(s.hp<=0||!s.left.length) break;
    const t=s.left[0], dx=t[0]-s.pos[0], dz=t[1]-s.pos[1];
    if (Math.hypot(dx,dz)<1.5) break;
    const k = Math.abs(dx)>Math.abs(dz) ? (dx>0?'KeyD':'KeyA') : (dz>0?'KeyS':'KeyW');
    await p.keyboard.down(k); await new Promise(r=>setTimeout(r,600)); await p.keyboard.up(k);
    await new Promise(r=>setTimeout(r,60));
  }
  s=await S();
  console.log(`after jewel-run ${j+1}: got=${s.got} hp=${s.hp} alert=${s.alert} chasing=${s.chasing} nearest=${s.near}m`);
  if (s.hp<=0) break;
}
await p.keyboard.up('KeyC');
s=await S(); console.log('FINAL:', JSON.stringify(s));
await p.screenshot({path:'../../heist_play.jpg',type:'jpeg',quality:82,clip:{x:0,y:55,width:1280,height:625}});
console.log('errors:', errs.length?errs.join(' | '):'none');
await b.close();
