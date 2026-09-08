import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const logs=[]; p.on('console',m=>{const t=m.text(); if(!t.includes('favicon')&&(m.type()==='error'||t.includes('[game]'))) logs.push(m.type()+': '+t.slice(0,150));});
p.on('pageerror',e=>logs.push('PAGEERROR: '+e.message.slice(0,220)));
await p.goto('http://127.0.0.1:8789/games/job_2/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,2500));
const g0=await p.evaluate(()=>(window.__game?.npcs?.()||[]).filter(n=>n.behavior==='guard').map(n=>n.pos));
console.log('guard spawn (x,z):', JSON.stringify(g0.map(q=>[+q[0].toFixed(1),+q[2].toFixed(1)])));
await p.screenshot({path:'../../heist_A_spawn.jpg',type:'jpeg',quality:82,clip:{x:0,y:55,width:1280,height:625}});
await new Promise(r=>setTimeout(r,8000));
const g1=await p.evaluate(()=>(window.__game?.npcs?.()||[]).filter(n=>n.behavior==='guard').map(n=>n.pos));
console.log('patrol moved (m/8s):', g0.map((q,i)=>Math.hypot(g1[i][0]-q[0],g1[i][2]-q[2]).toFixed(2)).join(', '));
console.log('alive after 11s:', await p.evaluate(()=>JSON.stringify(window.__game.combat())));
// sneak deeper in
await p.keyboard.down('KeyC');
for(let i=0;i<4;i++){await p.keyboard.down('KeyW');await new Promise(r=>setTimeout(r,1500));await p.keyboard.up('KeyW');await new Promise(r=>setTimeout(r,400));}
await p.keyboard.up('KeyC');
await p.screenshot({path:'../../heist_B_inside.jpg',type:'jpeg',quality:82,clip:{x:0,y:55,width:1280,height:625}});
console.log('state after sneaking:', await p.evaluate(()=>JSON.stringify(window.__game.combat())));
console.log('log:', logs.slice(0,6).join(' | ')||'clean');
await b.close();
