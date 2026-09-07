// Drive the factory through the SAME postMessage protocol the studio uses,
// from a real parent page with the game in an iframe — a bridge tested by
// calling its functions directly would not prove the iframe path works.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const GAME = process.env.URL ||
  ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');

// a stand-in for GameStudio.tsx: an iframe plus a message log
await p.setContent(`<!doctype html><style>html,body{margin:0;height:100%}
  iframe{border:0;width:1280px;height:760px;display:block}</style>
  <iframe id="g" src="${GAME}"></iframe>
  <script>
    window.LOG = [];
    addEventListener('message', e => { if (e.data && e.data.type) window.LOG.push(e.data); });
    window.toGame = m => document.getElementById('g').contentWindow.postMessage(m, '*');
  </script>`, { waitUntil:'domcontentloaded' });
await new Promise(r=>setTimeout(r,7000));

let frame = p.frames().find(f => f.url().startsWith(GAME));
if (!frame) { console.log('FAIL: game frame did not load'); await b.close(); process.exit(1); }
// the game autosaves, and a save from an earlier run would seed this one
await frame.evaluate(()=>{ try { localStorage.clear(); } catch (e) {} location.reload(); });
await new Promise(r=>setTimeout(r,7000));
frame = p.frames().find(f => f.url().startsWith(GAME));
if (!frame) { console.log('FAIL: frame gone after reload'); await b.close(); process.exit(1); }

const log = () => p.evaluate(()=>window.LOG.slice());
const clear = () => p.evaluate(()=>{ window.LOG.length = 0; });

// 1. inspect arms
await p.evaluate(()=>window.toGame({ type:'fs-inspect', on:true }));
await new Promise(r=>setTimeout(r,600));
const armed = await frame.evaluate(()=>window.__game.inspecting);
console.log('inspect on     :', armed);

// 2. a click reports what is under it, with a tile and a face
await clear();
await p.evaluate(()=>window.toGame({ type:'fs-dropat', cx:640, cy:400 }));
await new Promise(r=>setTimeout(r,600));
const picks = (await log()).filter(m => m.type === 'fs-pick');
const pick = picks[picks.length - 1];
console.log('pick           :', JSON.stringify(pick && {
  kind: pick.kind, tile: pick.tile, target: pick.target }));

// 3. building is disabled while inspecting: a click must not place anything
const before = await frame.evaluate(()=>window.__game.facts().machines);
await frame.evaluate(()=>{
  const c = document.querySelector('canvas');
  c.dispatchEvent(new PointerEvent('pointerdown', { button:0, clientX:640, clientY:400, bubbles:true }));
});
await new Promise(r=>setTimeout(r,400));
const afterClick = await frame.evaluate(()=>window.__game.facts().machines);
console.log('click builds?  :', afterClick > before ? 'YES (wrong)' : 'no');

// 4. a spawn places a real machine on the picked tile
await clear();
await p.evaluate(()=>window.toGame({ type:'fs-spawn', kind:'smelter' }));
await new Promise(r=>setTimeout(r,600));
const spawned = (await log()).filter(m => m.type === 'fs-spawned').pop();
const afterSpawn = await frame.evaluate(()=>window.__game.facts().machines);
console.log('spawn          :', JSON.stringify(spawned), '| machines',
            before, '->', afterSpawn);

// 5. a kind this genre cannot build is refused with a reason, not silently
await clear();
await p.evaluate(()=>window.toGame({ type:'fs-spawn', kind:'park bench' }));
await new Promise(r=>setTimeout(r,400));
const refused = (await log()).filter(m => m.type === 'fs-spawned').pop();
console.log('bad kind       :', JSON.stringify(refused));

// 6. inspect off restores play
await p.evaluate(()=>window.toGame({ type:'fs-inspect', on:false }));
await new Promise(r=>setTimeout(r,400));
console.log('inspect off    :', !(await frame.evaluate(()=>window.__game.inspecting)));
console.log('errors         :', errs.length ? errs.join(' | ') : 'none');

const ok = armed && pick && pick.kind === 'drop' && pick.tile
  && afterClick === before
  && spawned && spawned.ok && afterSpawn > before
  && refused && refused.ok === false && /machine/i.test(refused.err || '')
  && !(await frame.evaluate(()=>window.__game.inspecting))
  && errs.length === 0;
await p.screenshot({ path: process.env.OUT || 'inspect.png' });
await b.close();
process.exit(ok ? 0 : 1);
