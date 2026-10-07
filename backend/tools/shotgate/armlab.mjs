// The upper arms of library rigs, measured (see armlab.html). Serve the repo
// root on 8791 first (python -m http.server 8791 from the repo root).
//   F=detective_anim.glb,scientist_anim.glb [C=walk,idle,run] [V=job_N] node armlab.mjs
import puppeteer from 'puppeteer-core';
const F = process.env.F || '', C = process.env.C || 'walk,idle,run', V = process.env.V || 'job_829';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage();
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8791/backend/tools/shotgate/armlab.html?f=${F}&c=${C}&v=${V}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await p.waitForFunction(() => window.__arms, { timeout: 180000 }).catch(() => {});
const r = await p.evaluate(() => window.__arms || null);
for (const [k, v] of Object.entries(r || {})) console.log(k.padEnd(26), JSON.stringify(v));
if (errs.length) console.log('errors', JSON.stringify(errs.slice(0, 3)));
await b.close();
