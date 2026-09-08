import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const logs=[]; p.on('console',m=>{const t=m.text(); if(!t.includes('favicon')&&(m.type()==='error'||t.includes('[game]'))) logs.push(t.slice(0,140));});
p.on('pageerror',e=>logs.push('PAGEERROR: '+e.message.slice(0,220)));
await p.goto('http://127.0.0.1:8789/games/job_4/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
const st = async()=>await p.evaluate(()=>window.__game.combat());
await new Promise(r=>setTimeout(r,3000));
console.log('t=3s  ', JSON.stringify(await st()));
await p.screenshot({path:'../../heist_A_spawn.jpg',type:'jpeg',quality:82,clip:{x:0,y:55,width:1280,height:625}});
await new Promise(r=>setTimeout(r,8000));
console.log('t=11s ', JSON.stringify(await st()));
// sneak forward through the house
await p.keyboard.down('KeyC');
for(let i=0;i<5;i++){await p.keyboard.down('KeyW');await new Promise(r=>setTimeout(r,1300));await p.keyboard.up('KeyW');await new Promise(r=>setTimeout(r,350));}
await p.keyboard.up('KeyC');
console.log('after sneak', JSON.stringify(await st()), JSON.stringify(await p.evaluate(()=>window.__game.objectives())));
await p.screenshot({path:'../../heist_B_inside.jpg',type:'jpeg',quality:82,clip:{x:0,y:55,width:1280,height:625}});
console.log('log:', logs.slice(0,5).join(' | ')||'clean');
await b.close();
