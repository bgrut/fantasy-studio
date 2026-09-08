import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({width:1280,height:720});
await p.goto('http://127.0.0.1:8789/games/job_5/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,4500)); await p.click('#startbtn').catch(()=>{});
for (let s=0;s<9;s++){
  await new Promise(r=>setTimeout(r,1500));
  const d = await p.evaluate(()=>{
    const pp=window.__game.pos(); const c=window.__game.combat();
    const g=(window.__game.npcs()||[]).filter(n=>n.behavior==='guard');
    return {t:+(g[0]?.playT||0).toFixed(1), hp:c.hp,
      guards:g.map(n=>({m:n.mode,a:+(n.alert||0).toFixed(2),
        d:+Math.hypot(n.pos[0]-pp[0],n.pos[2]-pp[2]).toFixed(1)}))};
  });
  console.log(`playT=${d.t}s hp=${d.hp} `, d.guards.map(x=>`${x.m}/a${x.a}/${x.d}m`).join('  '));
  if (d.hp<=0) break;
}
await b.close();
