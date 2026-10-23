// Sample a stalled page's stack several times after Start: J=job_N node _hang2.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const s = await p.createCDPSession(); await s.send('Debugger.enable');
const wait = ms => new Promise(r => setTimeout(r, ms));
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
await wait(12000);
const t0 = Date.now(); p.click('#startbtn').catch(() => {});
for (const at of (process.env.AT || "1500,4000,8000,14000").split(",").map(Number)) {
  await wait(at - (Date.now() - t0));
  const got = new Promise(res => s.once('Debugger.paused', ev => res(ev.callFrames.slice(0, 6).map(f => `${f.functionName || '(anon)'}@${f.location.lineNumber + 1}`).join(' < '))));
  await s.send('Debugger.pause');
  const st = await Promise.race([got, wait(4000).then(() => 'idle')]);
  console.log(at, st); await s.send('Debugger.resume').catch(() => {});
}
await b.close();
