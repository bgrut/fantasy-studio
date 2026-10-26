import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.goto('http://127.0.0.1:8790/?fresh=1', { waitUntil: 'domcontentloaded' });
for (let i = 0; i < 120 && !(await p.evaluate(() => !!(window.__factory && window.__game)).catch(() => false)); i++) await new Promise(r => setTimeout(r, 500));
console.log(JSON.stringify(await p.evaluate(() => { const P = window.__factory.player; return [typeof P, P && Object.keys(P).slice(0, 40), window.__factory.MINERAL_OF_FACE, window.__factory.FACES.map(f => f.name)]; })));
await b.close();
