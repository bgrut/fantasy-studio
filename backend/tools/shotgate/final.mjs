import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,180)));
p.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon'))errs.push('CONSOLE: '+m.text().slice(0,120));});
await p.goto('http://127.0.0.1:8789/games/job_9/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,2000));
await p.screenshot({path:'../../heist_final_entry.jpg',type:'jpeg',quality:85,clip:{x:0,y:55,width:1280,height:625}});
// creep along the wall (sneak) — realistic stealth play
await p.keyboard.down('KeyC');
for(let i=0;i<5;i++){await p.keyboard.down('KeyD');await new Promise(r=>setTimeout(r,500));await p.keyboard.up('KeyD');await new Promise(r=>setTimeout(r,120));}
const s=await p.evaluate(()=>{const c=window.__game.combat(),o=window.__game.objectives(),pp=window.__game.pos();
  const g=(window.__game.npcs()||[]).filter(n=>n.behavior==='guard');
  return {hp:c.hp,got:o.collected,pos:[+pp[0].toFixed(1),+pp[2].toFixed(1)],
    sneaking:!!window.__sneak, alert:+(window.__alertPeak||0).toFixed(2),
    eyeHUD:!!document.getElementById('fsbar'),
    patrolling:g.filter(n=>n.mode==='patrol').length, chasing:g.filter(n=>n.mode==='chase').length};});
await p.screenshot({path:'../../heist_final_sneak.jpg',type:'jpeg',quality:85,clip:{x:0,y:55,width:1280,height:625}});
await p.keyboard.up('KeyC');
console.log('SNEAK STATE:', JSON.stringify(s));
console.log('errors:', errs.length?errs.slice(0,3).join(' | '):'none');
await b.close();
