import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1400,820'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:820});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,170)));
p.on('console',m=>{ if(m.type()==='error' && !/favicon/i.test(m.text())) errs.push('c:'+m.text().slice(0,130)); });
await p.goto('http://127.0.0.1:8123/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,2000));
const read = () => p.evaluate(()=>({
  value:+document.getElementById('ore').textContent,
  ingots:+document.getElementById('ingot').textContent,
  smelters:+document.getElementById('nsmelt').textContent,
  belts:+document.getElementById('nbelt').textContent,
  onbelt:+document.getElementById('nitem').textContent,
}));
console.log('t=2s ', JSON.stringify(await read()));
await new Promise(r=>setTimeout(r,12000));
console.log('t=14s', JSON.stringify(await read()));
const fps = await p.evaluate(()=>new Promise(res=>{let n=0;const t=performance.now();
  const f=()=>{n++; if(performance.now()-t<2000) requestAnimationFrame(f); else res(Math.round(n/((performance.now()-t)/1000)));};
  requestAnimationFrame(f);}));
console.log('errors:', errs.length?errs.slice(0,2).join(' | '):'none', '| fps', fps);
await p.evaluate(()=>{ window.__factory.overheadOn && window.__factory.overheadOn(); });
await p.keyboard.press('Tab');
await new Promise(r=>setTimeout(r,900));
await p.screenshot({path:process.env.SP+'/smelter.jpg',type:'jpeg',quality:92});
await b.close();
