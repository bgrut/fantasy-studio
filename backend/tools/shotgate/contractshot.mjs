// The panel with a live contract and a shard earned. Not a gate.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4500));
await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  F.addValue(60); await new Promise(r => setTimeout(r, 300));
  F.shards = 1;
  const c = F.offerContract(TY.ALLOY);
  for (let k = 0; k < Math.floor(c.need / 2); k++) F.bank(TY.ALLOY);
  F.contractLeft = 47;
  await new Promise(r => setTimeout(r, 600));
});
await p.screenshot({ path: (process.env.OUT || 'contract') + '_hud.png' });
await b.close();
