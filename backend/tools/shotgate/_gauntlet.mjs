// the held gauntlet close: hide the HUD and shoot the frame's lower right. URL= OUT=
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1600,900'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto((process.env.URL || 'http://127.0.0.1:8790/') + '?fresh=1&nointro=1', { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 6000));
await p.evaluate(() => { for (const el of document.querySelectorAll('body > *:not(canvas)')) if (el.tagName !== 'SCRIPT') el.style.visibility = 'hidden'; try { window.__factory.tutIdx = 99; } catch (e) {} });
await new Promise(r => setTimeout(r, 1500));
await p.screenshot({ path: process.env.OUT + '_full.jpg', type: 'jpeg', quality: 92 });
await p.screenshot({ path: process.env.OUT + '_zoom.png', clip: { x: 1050, y: 560, width: 550, height: 340 } });
await b.close();
