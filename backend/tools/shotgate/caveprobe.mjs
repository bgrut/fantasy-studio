// The cave's roof: is it there, where, and what does looking straight up see.
import puppeteer from 'puppeteer-core';
const J = process.env.J, OUT = process.env.OUT || '.';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1200, height: 700 });
const errs = []; p.on('console', m => { if (/cave|error/i.test(m.text())) errs.push(m.text().slice(0, 200)); });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise(r => setTimeout(r, 9000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000)); await p.keyboard.press('g');
const r = await p.evaluate(() => {
  const roof = window.__scene.getObjectByName('caveRoof');
  const pp = window.__game.pos();
  if (!roof) return { roof: null };
  roof.geometry.computeBoundingBox();
  const bb = roof.geometry.boundingBox;
  window.__camPin = { pos: [pp[0], pp[1] + 2, pp[2]], look: [pp[0] + 8, pp[1] + 9, pp[2] + 0.1] };
  return { vis: roof.visible, min: bb.min.y, max: bb.max.y, layers: roof.layers.mask, mat: roof.material.type, side: roof.material.side, inScene: !!roof.parent, fogFar: window.__scene.fog && window.__scene.fog.far };
});
console.log(JSON.stringify(r));
await new Promise(r2 => setTimeout(r2, 1500));
await p.screenshot({ path: `${OUT}/cave_up.jpg`, type: 'jpeg', quality: 85 });
console.log(JSON.stringify(errs));
await b.close();
