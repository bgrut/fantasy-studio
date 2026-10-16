import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/job_${process.env.MY}/dist/?noguide=1`, { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => !!(window.__game && window.__game.facts))) break; await wait(1000); }
await (await p.$('#startbtn'))?.click(); await wait(2000);
const left = await p.evaluate(() => window.__game.objectives().left);
console.log('left', JSON.stringify(left));
for (const [x, y, z] of left) {
  await p.evaluate((x, z) => window.__game.tp(x, z), x, z);
  for (let t = 0; t < 8; t++) { await wait(400);
    const r = await p.evaluate(() => ({ pos: window.__game.pos().map(v => +v.toFixed(2)), left: window.__game.objectives().left.length, clues: (window.__game.facts().mystery || {}).clues?.length }));
    if (t === 0 || t === 7) console.log([x, y, z].map(v => +v.toFixed(2)), t, JSON.stringify(r)); }
}
await b.close();
