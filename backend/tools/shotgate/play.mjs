import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,180)));
await p.goto('http://127.0.0.1:8789/games/job_6/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,1200));
const S=async()=>await p.evaluate(()=>{const c=window.__game.combat(),o=window.__game.objectives(),pp=window.__game.pos();
  const g=(window.__game.npcs()||[]).filter(n=>n.behavior==='guard');
  return {hp:c.hp,got:o.collected,left:o.left,pos:[+pp[0].toFixed(1),+pp[2].toFixed(1)],
    near:+Math.min(...g.map(n=>Math.hypot(n.pos[0]-pp[0],n.pos[2]-pp[2]))).toFixed(1),
    chasing:g.filter(n=>n.mode==='chase').length};});
let s=await S(); console.log('spawn:', JSON.stringify(s));
await p.screenshot({path:'../../heist_1_entry.jpg',type:'jpeg',quality:82,clip:{x:0,y:55,width:1280,height:625}});
// SNEAK to each jewel in turn, crouched
await p.keyboard.down('KeyC');
for (let j=0;j<4 && s.hp>0;j++){
  for (let step=0; step<26 && s.hp>0; step++){
    s=await S(); if(!s.left.length) break;
    const tgt=s.left[0];
    const ang=Math.atan2(tgt[0]-s.pos[0], tgt[2]-s.pos[1]);
    await p.evaluate(a=>{window.__game.face&&window.__game.face(a);},ang);
    // steer with the mouse-less approach: use tp-free WASD toward target
    const dx=tgt[0]-s.pos[0], dz=tgt[2]-s.pos[1];
    if (Math.hypot(dx,dz)<1.6) break;
    const k = Math.abs(dx)>Math.abs(dz) ? (dx>0?'KeyD':'KeyA') : (dz>0?'KeyS':'KeyW');
    await p.keyboard.down(k); await new Promise(r=>setTimeout(r,320)); await p.keyboard.up(k);
  }
  s=await S(); console.log(`jewel ${j+1} attempt →`, JSON.stringify(s));
  if (s.got>j) console.log('   ✔ collected');
}
await p.keyboard.up('KeyC');
s=await S(); console.log('FINAL:', JSON.stringify(s));
await p.screenshot({path:'../../heist_2_deep.jpg',type:'jpeg',quality:82,clip:{x:0,y:55,width:1280,height:625}});
console.log('errors:', errs.length?errs.join(' | '):'none');
await b.close();
