import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new', executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader'] });
const p = await b.newPage();
p.on('response', r => { if (r.status()===404) console.log('404:', r.url().split('/dist/')[1] || r.url()); });
await p.goto('http://127.0.0.1:8789/games/job_1/dist/',{waitUntil:'networkidle2',timeout:60000});
await new Promise(r=>setTimeout(r,3000)); await b.close();
