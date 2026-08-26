import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1200,700'] });
const p = await b.newPage();
const J = process.env.J;
// seed the CAMPAIGN hero before the game boots: level 3, one heart pick,
// one power pick, $4,200 banked from "level 1"
await p.evaluateOnNewDocument(() => {
  localStorage.setItem('fs_prog_proj_p3',
    JSON.stringify({ lvl: 3, picks: ['heart', 'power'], bank: 4200 }));
});
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/`,{waitUntil:'domcontentloaded',timeout:60000});
await new Promise(r=>setTimeout(r,6000));
await p.click('#startbtn').catch(()=>{});
// popTexts are transient: sample the body promptly and repeatedly
let sawReturn=false, sawHaul=false;
for (let i=0;i<14;i++) {
  const t = await p.evaluate(()=>document.body.innerText);
  if (/Level 3 .* returns/.test(t)) sawReturn=true;
  if (/Career haul: \$4,200/.test(t)) sawHaul=true;
  if (sawReturn && sawHaul) break;
  await new Promise(r=>setTimeout(r,400));
}
const hearts = await p.evaluate(()=>{
  const el=document.getElementById('hearts');
  return el ? el.textContent : null;
});
console.log('returned-hero popup:', sawReturn?'PASS':'FAIL',
  '| career-haul popup:', sawHaul?'PASS':'FAIL',
  '| hearts:', JSON.stringify(hearts));
await b.close();
