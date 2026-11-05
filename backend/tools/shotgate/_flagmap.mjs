// Crystal Works' painted ground maps, saved as images. OUT=prefix [URL=] node _flagmap.mjs
import puppeteer from 'puppeteer-core'; import fs from 'fs';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage();
await p.goto(URL + '?fresh=1&noguide=1&clean=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 12000));
const r = await p.evaluate(() => { const c = window.__scene.getObjectByName('cube'), o = {}; for (const m of c.material) { const k = m.userData.plating; if (o[k] || !m.map || !m.map.image.toDataURL) continue; const s = document.createElement('canvas'); s.width = s.height = 1024; s.getContext('2d').drawImage(m.map.image, 0, 0, 1024, 1024); o[k] = s.toDataURL('image/jpeg', 0.85); } return o; });
for (const k in r) fs.writeFileSync(`${process.env.OUT}_${k}.jpg`, Buffer.from(r[k].split(',')[1], 'base64'));
console.log(Object.keys(r)); await b.close();
