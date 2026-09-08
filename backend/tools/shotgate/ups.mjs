import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--window-size=1400,820'] });
const p = await b.newPage(); await p.setViewport({width:1400,height:820});
const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,160)));
p.on('console',m=>{ if(m.type()==='error' && !/favicon/i.test(m.text())) errs.push('c:'+m.text().slice(0,110)); });
await p.goto('http://127.0.0.1:8123/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,1800));
const before = await p.evaluate(()=>({tick:+window.__factory.tick.toFixed(4),
  crystalValue: null, panel: document.querySelectorAll('#ups .up').length}));
// bank enough to buy, then buy one of each
const res = await p.evaluate(()=>{
  const F = window.__factory;
  F.addValue(100000);
  const out = {};
  out.tickBuy  = F.buy('tick');
  out.yieldBuy = F.buy('yield');
  out.smeltBuy = F.buy('smelt');
  out.tickAfter = +F.tick.toFixed(4);
  out.lvls = { tick:F.UPGRADES.tick.lvl, yield:F.UPGRADES.yield.lvl, smelt:F.UPGRADES.smelt.lvl };
  out.costNow = F.costOf(F.UPGRADES.tick);
  // buying should COST: value must have dropped from 100000+
  out.remaining = +document.getElementById('ore').textContent;
  return out;
});
// refusal when broke
const broke = await p.evaluate(()=>{
  const F = window.__factory;
  while (F.buy('tick')) {}                 // spend to the cap or to broke
  return { tickLvl: F.UPGRADES.tick.lvl, cap: F.UPGRADES.tick.cap };
});
await new Promise(r=>setTimeout(r,4000));
const fps = await p.evaluate(()=>new Promise(res=>{let n=0;const t=performance.now();
  const f=()=>{n++; if(performance.now()-t<1500) requestAnimationFrame(f); else res(Math.round(n/((performance.now()-t)/1000)));};
  requestAnimationFrame(f);}));
console.log('panel rows:', before.panel, '| tick', before.tick, '->', res.tickAfter);
console.log('bought:', JSON.stringify(res.lvls), '| next tick cost', res.costNow);
console.log('overclock capped at', broke.tickLvl, 'of', broke.cap, '| fps', fps);
console.log('errors:', errs.length?errs.slice(0,2).join('|'):'none');
await p.screenshot({path:process.env.SP+'/upgrades.jpg',type:'jpeg',quality:92});
await b.close();
