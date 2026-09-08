import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const sl=ms=>new Promise(r=>setTimeout(r,ms));
await p.goto(`http://127.0.0.1:8789/games/job_${process.argv[2]}/dist/`,{waitUntil:'networkidle2',timeout:90000});
await sl(6000);
console.log('startbtn present:', await p.evaluate(()=>!!document.getElementById('startbtn')));
console.log('startbtn visible:', await p.evaluate(()=>{const e=document.getElementById('startbtn'); if(!e) return 'none'; const r=e.getBoundingClientRect(); return r.width+'x'+r.height;}));
await p.click('#startbtn').catch(e=>console.log('CLICK FAIL', e.message.slice(0,90)));
await sl(9000);
// countdown element text
console.log('overlay:', await p.evaluate(()=>{
  const el=document.getElementById('countdown')||document.querySelector('#cd,.countdown');
  return el?{txt:el.textContent, disp:getComputedStyle(el).display}:'no countdown el';
}));
console.log('start overlay display:', await p.evaluate(()=>{
  const s=document.getElementById('start'); return s?getComputedStyle(s).display:'no #start';
}));
await p.evaluate(()=>{ window.__game.keys.KeyW = true; });
await sl(3500);
console.log('pos after synthetic keys.KeyW:', await p.evaluate(()=>window.__game.pos().map(v=>+v.toFixed(2))));
await p.evaluate(()=>{ window.__game.keys.KeyW = false; });
await b.close();
