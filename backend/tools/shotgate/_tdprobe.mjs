// where is the hero, the camera and the goal structure in a defend game? J=job_N
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1600, height: 900 });
await p.goto(`http://127.0.0.1:8789/games/${process.env.J}/dist/index.html?noguide=1`, { waitUntil: 'domcontentloaded' });
await new Promise(r => setTimeout(r, 9000)); await p.click('#startbtn').catch(() => {});
for (const t of [300, 1500, 4000]) { await new Promise(r => setTimeout(r, t));
  console.log(t, JSON.stringify(await p.evaluate(() => {
    const s = window.__scene, c = window.__camera, gm = window.__goalMark; let keep = null;
    s.traverse(o => { if (!keep && o.isGroup && o.children.some(ch => ch.isMesh && ch.geometry && ch.geometry.attributes.position.count > 20000)) keep = o; });
    const r = v => v.toArray().map(x => +x.toFixed(1));
    return { cam: r(c.position), hero: window.__game.pos().map(x => +x.toFixed(1)), goal: gm && gm.position ? r(gm.position) : null, spec_goal: window.__spec.world.level && window.__spec.world.level.goal };
  }))); }
await b.close();
