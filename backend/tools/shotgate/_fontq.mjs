// Which faces the makers pick, and do they load: J=job_N [N=12] node _fontq.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const w = ms => new Promise(r => setTimeout(r, ms));
const bad = [];
for (let v = 1; v <= +(process.env.N || 12); v++) {
  const p = await b.newPage(); const fails = [];
  p.on('requestfailed', r => fails.push(r.url())); p.on('response', r => { if (r.status() >= 400 && /fonts\//.test(r.url())) fails.push(r.status() + ' ' + r.url()); });
  await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?vibe=${v}`, { waitUntil: 'domcontentloaded' });
  for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!window.__art)) break; await w(250); }
  await w(1500);
  const r = await p.evaluate(async () => { const a = window.__art; const fam = a.head.replace(/"/g, ''); await document.fonts.ready;
    return { maker: a.maker, head: fam, body: a.body, loaded: document.fonts.check('700 30px "' + fam + '"') }; });
  console.log(v, JSON.stringify(r), fails.length ? 'FAILED ' + fails.join(' ') : '');
  if (!r.loaded || fails.length) bad.push(v);
  await p.close();
}
console.log(bad.length ? 'problems: ' + bad : 'all loaded');
await b.close();
