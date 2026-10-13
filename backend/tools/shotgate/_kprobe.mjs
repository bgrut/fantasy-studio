import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
await p.goto(`http://127.0.0.1:8789/games/job_${process.env.J}/dist/index.html${process.env.Q ? '?' + process.env.Q : ''}`, { waitUntil:'domcontentloaded' });
await new Promise(r=>setTimeout(r,9000)); await p.click('#startbtn').catch(()=>{}); await new Promise(r=>setTimeout(r,4000));
await p.keyboard.down('KeyW'); await new Promise(r=>setTimeout(r,2500));
const out = [];
for (let i = 0; i < 4; i++) { out.push(await p.evaluate(() => { const f = window.__game.facts ? window.__game.facts() : {}; const m = window.__mm ? window.__mm() : null;
  return { mm: m && { on: m.on, take: m.take, speed: m.speed }, gait: f.gait_engine && { armed: f.gait_engine.armed, armedLong: f.gait_engine.armedLong, trunk: f.gait_engine.trunk_deg, cad: f.gait_engine.cadence_spm }, lean: f.lean }; })); await new Promise(r=>setTimeout(r,400)); }
console.log(JSON.stringify(out));
await b.close();
