import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,200)));
const sl=ms=>new Promise(r=>setTimeout(r,ms));
await p.goto(`http://127.0.0.1:8789/games/job_7/dist/`,{waitUntil:'networkidle2',timeout:90000});
await sl(6000); await p.click('#startbtn').catch(()=>{});
for (let i=0;i<14;i++){ await sl(1000);
  const st=await p.evaluate(()=>({t:typeof window.__game, p:window.__game.pos()}));
  if(i%4===0) console.log('t+'+i+'s pos', st.p.map(v=>v.toFixed(1)).join(',')); }
const p0=await p.evaluate(()=>window.__game.pos());
await p.keyboard.down('KeyW'); await sl(4000); await p.keyboard.up('KeyW'); await sl(500);
const p1=await p.evaluate(()=>window.__game.pos());
console.log('RACE moved on W:', Math.hypot(p1[0]-p0[0],p1[2]-p0[2]).toFixed(2),'m');
await p.screenshot({path:'./shots_regress/RACE_final.png'});
console.log('pageerrors:', errs.length?errs:'none');
await b.close();
