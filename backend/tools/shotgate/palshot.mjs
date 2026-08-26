import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,720'] });
for (const [J, nm] of [['job_1','synthwave'], ['job_2','sunset']]) {
  const p = await b.newPage(); await p.setViewport({width:1280,height:720});
  await p.goto(`http://127.0.0.1:8789/games/${J}/dist/`,{waitUntil:'domcontentloaded',timeout:60000});
  await new Promise(r=>setTimeout(r,6500)); await p.click('#startbtn').catch(()=>{});
  await new Promise(r=>setTimeout(r,5000));
  console.log(nm, await p.evaluate(()=>JSON.stringify({
    fog: window.__scene.fog ? '#'+window.__scene.fog.color.getHexString() : null,
    accent: window.__accent !== null && window.__accent !== undefined
      ? '#'+window.__accent.toString(16).padStart(6,'0') : null })));
  await p.screenshot({ path: `${process.env.SP}/pal_${nm}.jpg`, type:'jpeg', quality:93 });
  await p.close();
}
await b.close();
