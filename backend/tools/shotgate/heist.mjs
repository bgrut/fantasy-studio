import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('console',m=>{ if(m.type()==='error') errs.push(m.text().slice(0,160)); });
p.on('pageerror',e=>errs.push('PAGEERROR: '+e.message.slice(0,200)));
await p.goto('http://127.0.0.1:8789/games/job_1/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4000));
await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,5000));
const guards = await p.evaluate(()=> (window.__game?.npcs?.()||[]).filter(n=>n.behavior==='guard'));
console.log('GUARDS:', JSON.stringify(guards.map(g=>g.pos.map(v=>+v.toFixed(1)))));
// record patrol movement over 6s
const before = guards.map(g=>g.pos.slice());
await new Promise(r=>setTimeout(r,6000));
const after = (await p.evaluate(()=> (window.__game?.npcs?.()||[]).filter(n=>n.behavior==='guard'))).map(g=>g.pos);
const moved = before.map((b0,i)=> Math.hypot(after[i][0]-b0[0], after[i][2]-b0[2]).toFixed(2));
console.log('PATROL distance moved in 6s:', moved.join(', '));
// sneak flag
await p.keyboard.down('KeyC'); await p.keyboard.down('KeyW');
await new Promise(r=>setTimeout(r,1500));
console.log('SNEAK flag while holding C:', await p.evaluate(()=>!!window.__sneak));
await p.keyboard.up('KeyC'); await p.keyboard.up('KeyW');
await new Promise(r=>setTimeout(r,600));
console.log('SNEAK flag after release:', await p.evaluate(()=>!!window.__sneak));
console.log('FPS:', await p.evaluate(()=>window.__game?.fps?.()??'n/a'));
await p.screenshot({path:'C:/Users/bgrut/Desktop/FantasyAI/fantasy-studio/backend/heist_shot.jpg',type:'jpeg',quality:80,clip:{x:0,y:60,width:1280,height:620}});
console.log('ERRORS:', errs.length? errs.slice(0,5).join(' | ') : 'none');
await b.close();
