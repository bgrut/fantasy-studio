import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('console',m=>{ if(m.type()==='error'&&!m.text().includes('favicon')) errs.push(m.text().slice(0,160)); });
p.on('pageerror',e=>errs.push('PAGEERROR: '+e.message.slice(0,200)));
await p.goto('http://127.0.0.1:8789/games/job_1/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500));
await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,5000));
const g0 = await p.evaluate(()=> (window.__game?.npcs?.()||[]).filter(n=>n.behavior==='guard').map(n=>n.pos));
console.log('guards spawned:', g0.length, JSON.stringify(g0.map(q=>[+q[0].toFixed(1),+q[2].toFixed(1)])));
await p.screenshot({path:'../../heist_spawn.jpg',type:'jpeg',quality:82,clip:{x:0,y:55,width:1280,height:625}});
await new Promise(r=>setTimeout(r,7000));
const g1 = await p.evaluate(()=> (window.__game?.npcs?.()||[]).filter(n=>n.behavior==='guard').map(n=>n.pos));
console.log('patrol moved (m/7s):', g0.map((q,i)=>Math.hypot(g1[i][0]-q[0],g1[i][2]-q[2]).toFixed(2)).join(', '));
// walk forward into the house to look for guards / rooms
for (let i=0;i<3;i++){ await p.keyboard.down('KeyW'); await new Promise(r=>setTimeout(r,1400)); await p.keyboard.up('KeyW'); await new Promise(r=>setTimeout(r,300)); }
await p.screenshot({path:'../../heist_inside.jpg',type:'jpeg',quality:82,clip:{x:0,y:55,width:1280,height:625}});
console.log('errors:', errs.length? errs.slice(0,4).join(' | '):'none');
await b.close();
