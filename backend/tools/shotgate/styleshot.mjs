import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
for (const [J, nm] of JSON.parse(process.env.JOBS)) {
  const p = await b.newPage(); await p.setViewport({width:1280,height:720});
  const errs=[]; p.on('pageerror',e=>errs.push(e.message.slice(0,120)));
  await p.goto(`http://127.0.0.1:8789/games/job_${J}/dist/`,{waitUntil:'domcontentloaded',timeout:60000});
  await new Promise(r=>setTimeout(r,7000));
  console.log(nm, await p.evaluate(()=>{
    const h1 = document.querySelector('#hud h1');
    return JSON.stringify({
      bodyClass: document.body.className,
      font: getComputedStyle(h1).fontFamily.slice(0,30),
      h1Color: getComputedStyle(h1).color,
      feelPunchProbe: !!window.__game });
  }), '| errors:', errs.length?errs.join('|'):'none');
  await p.click('#startbtn').catch(()=>{});
  await new Promise(r=>setTimeout(r,5000));
  await p.evaluate(()=>window.__game.tp(-40, 5));
  await new Promise(r=>setTimeout(r,3000));
  await p.screenshot({ path: `${process.env.SP}/style_${nm}.jpg`, type:'jpeg', quality:92 });
  await p.close();
}
await b.close();
