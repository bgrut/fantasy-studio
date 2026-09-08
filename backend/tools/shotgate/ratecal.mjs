// How fast does a factory actually run? The rate tiers have to be reachable.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width:1280, height:760 });
const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const URL = process.env.URL || 'http://127.0.0.1:8790/';
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await new Promise(r=>setTimeout(r,4000));
const r = await p.evaluate(async () => {
  const F = window.__factory, out = {};
  const sample = async (tag, secs) => { const a = window.__game.facts().value; await new Promise(r=>setTimeout(r, secs*1000)); const f = window.__game.facts(); out[tag] = { perMin: +((f.value - a) / secs * 60).toFixed(1), rate_now: f.rate_now, machines: f.machines }; };
  await sample('starter lvl0', 15);
  F.addValue(100000); for (let k=0;k<3;k++) F.buy('tick');
  await sample('starter tick3', 15);
  for (let k=0;k<3;k++) { F.buy('tick'); F.buy('yield'); }
  await sample('starter tick6 yield3', 15);
  out.VALUE = F.VALUE || null; out.TYPES = Object.keys(F.TYPES);
  return out;
});
console.log(JSON.stringify(r, null, 1)); console.log('errors:', errs.join(' | ') || 'none');
await b.close();
