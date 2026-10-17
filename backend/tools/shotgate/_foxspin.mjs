// The hero turning: frames and numbers while A is held, then while W+A. J=job_N OUT=prefix
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11', '--window-size=1280,720'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(9000); await p.click('#startbtn').catch(() => {}); await wait(3000);
await p.evaluate(() => { for (const el of document.querySelectorAll('.fs-card, #fsdlg, #toast')) el.style.display = 'none'; });
const probe = () => p.evaluate(() => { let pl = null; window.__scene.traverse(o => { if (!pl && o.userData && o.userData.fsTag && o.userData.fsTag.type === 'player') pl = o; });
  const V = pl.position.constructor, w = new V(); pl.getWorldPosition(w); let rig = null; pl.traverse(o => { if (!rig && o.isSkinnedMesh) rig = o; });
  const rw = new V(); if (rig) { const bb = new (window.__scene.position.constructor === V ? Object : Object)(); }
  const box = new (pl.position.constructor)(); // placeholder
  // the body's own centre in the world, from the skinned mesh's bounding sphere
  let c = null; if (rig) { rig.geometry.computeBoundingSphere(); c = rig.geometry.boundingSphere.center.clone().applyMatrix4(rig.matrixWorld); }
  const g = window.__game; return { pos: g.pos().map(v => +v.toFixed(2)), holder: [w.x, w.z].map(v => +v.toFixed(2)), rotY: +pl.rotation.y.toFixed(2),
    kids: pl.children.map(k => [k.type, +k.rotation.y.toFixed(2), +k.position.x.toFixed(2), +k.position.z.toFixed(2)]), body: c ? [c.x, c.z].map(v => +v.toFixed(2)) : null,
    gait: (g.facts().gait || {}).top }; });
const log = async (tag, n, dt) => { for (let i = 0; i < n; i++) { await wait(dt); const r = await probe(); console.log(tag, i, JSON.stringify(r));
  if (i % 2 === 0) await p.screenshot({ path: `${process.env.OUT}_${tag}${i}.jpg`, type: 'jpeg', quality: 80 }); } };
await p.keyboard.down('KeyA'); await log('A', 6, 250); await p.keyboard.up('KeyA'); await wait(800);
await p.keyboard.down('KeyW'); await wait(600); await p.keyboard.down('KeyD'); await log('WD', 6, 250); await p.keyboard.up('KeyD'); await p.keyboard.up('KeyW');
await b.close();
