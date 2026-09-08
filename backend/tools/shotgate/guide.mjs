import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push('PAGEERROR: '+e.message.slice(0,220)));
p.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon'))errs.push('ERR: '+m.text().slice(0,150));});
await p.goto('http://127.0.0.1:8789/games/job_2/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,2000));
console.log('alive:', await p.evaluate(()=>typeof window.__game));
const gpos = await p.evaluate(()=>{const g=(window.__game.npcs()||[]).find(n=>n.behavior==='guide');
  const pp=window.__game.pos(); return g?{d:+Math.hypot(g.pos[0]-pp[0],g.pos[2]-pp[2]).toFixed(1)}:null;});
console.log('guide distance from spawn:', JSON.stringify(gpos));
// walk toward the guide to trigger the greeting
for(let i=0;i<4;i++){await p.keyboard.down('KeyW');await new Promise(r=>setTimeout(r,600));await p.keyboard.up('KeyW');
  const d=await p.evaluate(()=>{const e=document.getElementById('fsdlg');
    return e&&e.style.opacity==='1'?{who:document.getElementById('fsdlgwho').textContent,
      txt:document.getElementById('fsdlgtxt').textContent.slice(0,110)}:null;});
  if(d){console.log('GUIDE SPOKE →', d.who+':', d.txt); break;}}
await p.screenshot({path:'../../guide.jpg',type:'jpeg',quality:86,clip:{x:0,y:55,width:1280,height:625}});
console.log('errors:', errs.length?errs.slice(0,3).join(' | '):'none');
await b.close();
