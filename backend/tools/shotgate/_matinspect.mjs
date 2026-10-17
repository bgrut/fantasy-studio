import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 9000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500));
console.log(JSON.stringify(await p.evaluate(n => { const o = window.__scene.getObjectByName(n); if (!o) return 'none'; const m = o.material;
  return { type: m.type, map: !!m.map, normal: !!m.normalMap, nImg: m.normalMap && m.normalMap.image ? [m.normalMap.image.width, m.normalMap.image.height] : null, rep: m.normalMap && m.normalMap.repeat.toArray(), obc: String(m.onBeforeCompile).slice(0, 80), key: m.customProgramCacheKey && m.customProgramCacheKey() }; }, process.env.N || 'pitch')));
await b.close();
