import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,180)));
await p.goto('http://127.0.0.1:8789/games/job_8/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,1200));
const S=async()=>await p.evaluate(()=>{const c=window.__game.combat(),o=window.__game.objectives(),pp=window.__game.pos();
  const g=(window.__game.npcs()||[]).filter(n=>n.behavior==='guard');
  return {hp:c.hp,got:o.collected,left:o.left.map(l=>[l[0],l[2]]),pos:[+pp[0].toFixed(1),+pp[2].toFixed(1)],
    alert:+(window.__alertPeak||0).toFixed(2),
    near:+Math.min(...g.map(n=>Math.hypot(n.pos[0]-pp[0],n.pos[2]-pp[2]))).toFixed(1),
    chasing:g.filter(n=>n.mode==='chase').length};});
let s=await S(); console.log('spawn:', JSON.stringify(s));
// walk toward each jewel using the game's own teleport-free movement.
// Movement is camera-relative, so drive with all four keys by trial.
await p.keyboard.down('KeyC');
const KEYS=['KeyW','KeyS','KeyA','KeyD'];
for (let j=0;j<4;j++){
  for (let step=0; step<50; step++){
    s=await S(); if(s.hp<=0||!s.left.length) break;
    const t=s.left[0]; const d0=Math.hypot(t[0]-s.pos[0],t[1]-s.pos[1]);
    if (d0<1.6) break;
    // pick the key that most reduces distance (camera-relative safe)
    let best=null,bd=d0;
    for (const k of KEYS){
      await p.keyboard.down(k); await new Promise(r=>setTimeout(r,260)); await p.keyboard.up(k);
      const s2=await S(); const d2=Math.hypot(t[0]-s2.pos[0],t[1]-s2.pos[1]);
      if (d2<bd){bd=d2;best=k;} 
      if (s2.hp<=0) break;
    }
    if (best){ for(let r2=0;r2<3;r2++){ await p.keyboard.down(best); await new Promise(r=>setTimeout(r,420)); await p.keyboard.up(best);} }
  }
  s=await S();
  console.log(`jewel-run ${j+1}: got=${s.got} hp=${s.hp} alert=${s.alert} chasing=${s.chasing} near=${s.near}m pos=${JSON.stringify(s.pos)}`);
  if (s.hp<=0) break;
}
await p.keyboard.up('KeyC');
s=await S(); console.log('FINAL:', JSON.stringify(s));
await p.screenshot({path:'../../heist_play.jpg',type:'jpeg',quality:82,clip:{x:0,y:55,width:1280,height:625}});
console.log('errors:', errs.length?errs.join(' | '):'none');
await b.close();
