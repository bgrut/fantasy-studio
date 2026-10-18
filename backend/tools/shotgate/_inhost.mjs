// indoor hostiles: where are they against the rooms, at load and later? J=job_N
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 9000));
const snap = () => p.evaluate(() => {
  const R = window.__spec.world.level.interior.rooms, hs = window.__game.npcs().filter(n => n.behavior === "hostile");
  const inR = (x, z) => R.findIndex(([cx, cz, w, d]) => Math.abs(x - cx) <= w / 2 && Math.abs(z - cz) <= d / 2);
  return hs.map(h => { const [x, , z] = h.pos; return [+x.toFixed(1), +z.toFixed(1), inR(x, z), h.dormant ? "d" : ""]; });
});
console.log('load ', JSON.stringify(await snap()));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 12000));
console.log('12s  ', JSON.stringify(await snap()));
await b.close();
