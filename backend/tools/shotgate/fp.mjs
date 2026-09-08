import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1400,820'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:820});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,160)));
p.on('console',m=>{ if(m.type()==='error' && !/favicon/i.test(m.text())) errs.push('c:'+m.text().slice(0,120)); });
await p.goto('http://127.0.0.1:8123/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,2000));
const start = await p.evaluate(()=>({cam:window.__factory.camPos(), ore:window.__factory.ore}));
// walk forward for a second
await p.keyboard.down('KeyW'); await new Promise(r=>setTimeout(r,1100)); await p.keyboard.up('KeyW');
await new Promise(r=>setTimeout(r,400));
const walked = await p.evaluate(()=>window.__factory.camPos());
const moved = Math.hypot(walked[0]-start.cam[0], walked[2]-start.cam[2]);
await new Promise(r=>setTimeout(r,5000));
const s2 = await p.evaluate(()=>({ore:window.__factory.ore, ghost:window.__factory.ghostVisible()}));
const fps = await p.evaluate(()=>new Promise(res=>{let n=0;const t=performance.now();
  const f=()=>{n++; if(performance.now()-t<2000) requestAnimationFrame(f); else res(Math.round(n/((performance.now()-t)/1000)));};
  requestAnimationFrame(f);}));
console.log('errors:', errs.length?errs.slice(0,2).join(' | '):'none');
console.log('eye height:', walked[1].toFixed(2), '| walked:', moved.toFixed(2), 'm');
console.log('ore', start.ore, '->', s2.ore, '| ghost visible:', s2.ghost, '| fps', fps);
await p.screenshot({path:process.env.SP+'/fp.jpg',type:'jpeg',quality:92});
await b.close();
