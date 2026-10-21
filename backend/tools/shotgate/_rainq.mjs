// Is the rain there and drawn: J=job_N node _rainq.mjs [OUT=png]
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__renderer && document.getElementById('startbtn')))) break; await w(250); }
await w(3000); await p.click('#startbtn').catch(() => {}); await w(5000);
console.log(JSON.stringify(await p.evaluate(() => { const r = window.__scene.getObjectByName('rainField');
  return { rain: window.__rain ? { drops: window.__rain.drops, storm: window.__rain.storm } : null, mesh: !!r, visible: r && r.visible, parent: r && r.parent && r.parent.type,
    cam: r && r.material.uniforms.uCam.value.toArray().map(v => +v.toFixed(1)), camPos: window.__game.cam ? null : null, t: r && +r.material.uniforms.uTime.value.toFixed(2), bg: window.__scene.background && window.__scene.background.isColor ? window.__scene.background.getHexString() : 'tex',
    fog: window.__scene.fog && { c: window.__scene.fog.color.getHexString(), near: window.__scene.fog.near, far: window.__scene.fog.far, d: window.__scene.fog.density } }; })));
if (process.env.EXPR) console.log(JSON.stringify(await p.evaluate(process.env.EXPR))); await w(600);
if (process.env.OUT) await p.screenshot({ path: process.env.OUT });
await b.close();
