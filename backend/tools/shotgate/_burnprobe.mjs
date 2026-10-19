// is there a burning building, and what does it look like from down the street? J=job_N OUT=x.png
import puppeteer from 'puppeteer-core';
import fs from 'fs';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 9000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 4000));
const info = await p.evaluate(() => window.__burning || null);
console.log(JSON.stringify(info));
if (info) {
  const url = await p.evaluate(([x, z, h, gd]) => {
    const T = window.__THREE__ ? null : null; const C = window.__camera; const cam = C.clone();
    const g = window.__spec.world.level.goal; const dx = g[0] - x, dz = g[1] - z, L = Math.hypot(dx, dz) || 1;
    const d = Math.max(45, h * 1.2); cam.position.set(x + dx / L * d, 2.5, z + dz / L * d); cam.lookAt(x, h * 0.5, z); cam.updateMatrixWorld(); cam.updateProjectionMatrix();
    const R = window.__renderer; R.render(window.__scene, cam); return R.domElement.toDataURL('image/png');
  }, [info.at[0], info.at[1], info.h, info.goalDist]);
  fs.writeFileSync(process.env.OUT, Buffer.from(url.split(',')[1], 'base64'));
}
await b.close();
