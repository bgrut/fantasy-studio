// Before Start: which meshes in the scene have a material never drawn yet: J=job_N node _undrawn.mjs
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html`, { waitUntil: 'domcontentloaded' });
const w = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 80; i++) { if (await p.evaluate(() => !!(window.__renderer && document.getElementById('startbtn')))) break; await w(250); }
await w(15000);
const look = () => p.evaluate(() => { const R = window.__renderer, out = {}; let total = 0, undrawn = 0, hidden = 0;
  window.__scene.traverse(o => { if (!(o.isMesh || o.isSkinnedMesh || o.isInstancedMesh)) return; total++;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    const nd = mats.some(m => m && !(R.properties.get(m) || {}).currentProgram);
    let vis = true; for (let q = o; q; q = q.parent) if (!q.visible) { vis = false; break; }
    if (nd) { undrawn++; if (!vis) hidden++; const top = (() => { let q = o; while (q.parent && q.parent.type !== 'Scene') q = q.parent; return q.name || q.type; })();
      const k = (vis ? 'shown ' : 'hidden ') + top + ' / ' + (mats[0] && mats[0].name || mats[0] && mats[0].type);
      out[k] = (out[k] || 0) + 1; } });
  return { total, undrawn, hidden, programs: R.info.programs.length, groups: Object.entries(out).sort((a, b) => b[1] - a[1]).slice(0, 25) }; });
console.log('before start', JSON.stringify(await look(), null, 0));
await p.click('#startbtn').catch(() => {}); await w(15000);
const after = await look(); console.log('after start', JSON.stringify({ total: after.total, undrawn: after.undrawn, programs: after.programs }));
await b.close();
