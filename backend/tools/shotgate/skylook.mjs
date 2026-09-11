// First person, aimed at the sky: AIM=nebula|aurora, Q extra query, OUT
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0,200)));
await p.goto(process.env.URL + '?fresh=1&nointro=1' + (process.env.Q || ''), { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r => setTimeout(r, 3000));
const r = await p.evaluate((aim) => {
  const F = window.__factory, sky = window.__scene.getObjectByName('sky');
  const u = sky.material.uniforms, d = u.uNebDir.value.clone();
  let az = Math.atan2(d.z, d.x);
  if (aim === 'aurora') az += 2.4;
  F.player.fwd.set(Math.cos(az), 0, Math.sin(az)).normalize();
  F.player.pitch = aim === 'aurora' ? 0.28 : 0.55;
  return { amt: u.uNebAmt.value, aurora: u.uAurora.value, time: u.uTime.value };
}, process.env.AIM || 'nebula');
await new Promise(r => setTimeout(r, 700));
await p.screenshot({ path: process.env.OUT || 'skylook.png' });
console.log(JSON.stringify(r), 'errors:', errs.length ? errs.join(' | ') : 'none');
await b.close();
