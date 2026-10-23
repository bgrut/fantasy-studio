// Where is a hung page stuck? Pause it in the debugger and print the stack: J=job_N [START=1] node _hang.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
const s = await p.createCDPSession(); await s.send('Debugger.enable');
const wait = ms => new Promise(r => setTimeout(r, ms));
p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' }).catch(() => {});
await wait(9000);
if (process.env.START) { p.click('#startbtn').catch(() => {}); await wait(6000); }
s.on('Debugger.paused', ev => { console.log(ev.callFrames.slice(0, 8).map(f => `${f.functionName || '(anon)'} @ line ${f.location.lineNumber + 1}`).join('\n')); process.exit(0); });
await s.send('Debugger.pause');
await wait(8000); console.log('not paused (page idle)'); process.exit(0);
