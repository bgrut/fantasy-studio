import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push('PAGEERROR: '+e.message.slice(0,200)));
p.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon'))errs.push('ERR: '+m.text().slice(0,120));});
await p.goto('http://127.0.0.1:8789/games/job_14/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500));
console.log('controls hint:', await p.evaluate(()=>{const e=[...document.querySelectorAll('div')].map(d=>d.innerHTML).find(h=>h&&h.includes('WASD'));return e?e.replace(/<[^>]+>/g,'').slice(0,90):'(none)';}));
await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,2500));
await p.screenshot({path:'../../h_cam.jpg',type:'jpeg',quality:85,clip:{x:0,y:55,width:1280,height:625}});
// THROW test
const before = await p.evaluate(()=>(window.__game.npcs()||[]).filter(n=>n.behavior==='guard').map(n=>n.pos.slice()));
await p.keyboard.press('KeyQ');
await new Promise(r=>setTimeout(r,1200));
console.log('stone in flight handled:', await p.evaluate(()=>Array.isArray(window.__flights)));
await new Promise(r=>setTimeout(r,4000));
const after = await p.evaluate(()=>(window.__game.npcs()||[]).filter(n=>n.behavior==='guard').map(n=>n.pos));
console.log('guard moves after throw (m):', before.map((q,i)=>Math.hypot(after[i][0]-q[0],after[i][2]-q[2]).toFixed(2)).join(', '));
console.log('throw cooldown set:', await p.evaluate(()=>+(window.__throwCd||0).toFixed(1)));
const st=await p.evaluate(()=>({hp:window.__game.combat().hp, take:window.__take||0, eye:!!document.getElementById('fsbar')}));
console.log('state:', JSON.stringify(st));
await p.screenshot({path:'../../h_throw.jpg',type:'jpeg',quality:85,clip:{x:0,y:55,width:1280,height:625}});
console.log('errors:', errs.length?errs.slice(0,3).join(' | '):'none');
await b.close();
