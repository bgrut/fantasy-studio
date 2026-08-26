import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1400,860'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:860});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,180)));
p.on('console',m=>{ if(/\[events\]/.test(m.text())) console.log('LOG:',m.text()); });
await p.goto('http://127.0.0.1:8789/games/' + process.env.J + '/dist/',{waitUntil:'domcontentloaded',timeout:60000});
await new Promise(r=>setTimeout(r,6000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,6000));
console.log('alive:', await p.evaluate(()=>typeof window.__game), '| errors:', errs.length?errs.join('|'):'none');
console.log('events:', await p.evaluate(()=>JSON.stringify(window.__game.events())));
const before = await p.evaluate(()=>window.__game.npcs().length);
console.log('npcs before:', before);
console.log('trigger:', await p.evaluate(()=>window.__game.trigger(0)));
await new Promise(r=>setTimeout(r,1500));
const after = await p.evaluate(()=>({
  npcs: window.__game.npcs().length,
  timer: window.__evTimerEl ? window.__evTimerEl.textContent : null,
  chasing: window.__game.npcs().filter(n=>n.mode==='chase').length }));
console.log('after trigger:', JSON.stringify(after));
await new Promise(r=>setTimeout(r,2600));
console.log('timer ticking:', await p.evaluate(()=>window.__evTimerEl && window.__evTimerEl.textContent));
await p.screenshot({ path: process.env.SP + '/events_fired.jpg', type:'jpeg', quality:92 });
console.log('final errors:', errs.length?errs.join('|'):'none');
await b.close();
