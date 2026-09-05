import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,120)));
p.on('console',m=>{ if(m.type()==='error' && !/favicon/i.test(m.text())) errs.push('c:'+m.text().slice(0,90)); });
await p.goto(process.env.U,{waitUntil:'domcontentloaded',timeout:90000});
await new Promise(r=>setTimeout(r,7000)); await p.click('#startbtn').catch(()=>{});
await new Promise(r=>setTimeout(r,8000));
let f={}, st={};
try { f = await p.evaluate(()=>window.__game.facts()); } catch(e) {}
try { st = await p.evaluate(()=>window.__game.stats()); } catch(e) {}
const fps = await p.evaluate(()=>new Promise(res=>{let n=0;const t0=performance.now();
  const t=()=>{n++; if(performance.now()-t0<1500) requestAnimationFrame(t); else res(Math.round(n/((performance.now()-t0)/1000)));};
  requestAnimationFrame(t);}));
await p.screenshot({path:process.env.OUT,type:'jpeg',quality:88});
console.log(JSON.stringify({style:f.style, ground:f.ground_tex, dyn:f.dynamic_props,
  tris:st.tris, calls:st.calls, fps, errors:errs.slice(0,2)}));
await b.close();
