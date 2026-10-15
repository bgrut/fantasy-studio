import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage();
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 10000)); await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2000));
console.log(JSON.stringify(await p.evaluate(() => {
  const out = [];
  window.__scene.traverse(o => { if (!o.isInstancedMesh || !o.geometry || o.geometry.type !== 'IcosahedronGeometry') return;
    const g = o.geometry, pa = g.attributes.position, nr = g.attributes.normal, map = new Map(); let dup = 0, diff = 0, maxd = 0;
    for (let i = 0; i < pa.count; i++) { const k = Math.round(pa.getX(i) * 1e4) + ',' + Math.round(pa.getY(i) * 1e4) + ',' + Math.round(pa.getZ(i) * 1e4);
      const n = [nr.getX(i), nr.getY(i), nr.getZ(i)];
      if (map.has(k)) { dup++; const m = map.get(k); const d = 1 - (m[0] * n[0] + m[1] * n[1] + m[2] * n[2]); if (d > 0.01) diff++; maxd = Math.max(maxd, d); } else map.set(k, n); }
    out.push({ name: o.name, count: pa.count, indexed: !!g.index, uniq: map.size, dup, diff, maxd: +maxd.toFixed(3), mat: o.material.type, flat: !!o.material.flatShading });
  });
  return out;
})));
await b.close();
