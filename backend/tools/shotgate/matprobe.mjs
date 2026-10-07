// The materials a tagged thing actually renders with: colour, emissive,
// maps, metalness. For when a model's colours come out wrong in the game.
//   J=job_N TYPE=<fsTag type> node matprobe.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J, TYPE = process.env.TYPE || 'collectible';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 900, height: 500 });
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 12000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500));
const r = await p.evaluate((TYPE) => {
  const sc = window.__scene || (window.__game && window.__game.scene); if (!sc) return 'no scene handle';
  let hit = null; sc.traverse(o => { if (!hit && o.userData && o.userData.fsTag && o.userData.fsTag.type === TYPE) hit = o; });
  if (!hit) return 'none tagged ' + TYPE;
  const out = [];
  hit.traverse(o => { if (!o.isMesh) return; for (const m of [].concat(o.material)) out.push({ mesh: o.name, type: m.type, color: m.color && m.color.getHexString(), emissive: m.emissive && m.emissive.getHexString(), ei: m.emissiveIntensity, metal: m.metalness, rough: m.roughness, map: !!m.map, vc: m.vertexColors, noAuto: !!m.userData.noAutoTex }); });
  return out;
}, TYPE);
console.log(JSON.stringify(r, null, 1));
await b.close();
