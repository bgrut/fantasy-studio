// Far ore is worth more. A hub on a crystal face has to pay the premium for an
// ember ingot and none for a crystal one; alloys and components carry no
// premium; the label says so; the first premium explains itself.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
p.on('console', m => { const u = (m.location() && m.location().url) || '';
  if (m.type()==='error' && !/favicon/i.test(u)) errs.push('console: '+m.text().slice(0,160)); });
const URL = process.env.URL ||
  ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
const q = URL.includes('?') ? '&' : '?';
const wait = ms => new Promise(r => setTimeout(r, ms));

await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);

const r = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  for (const t of F.TRADED) F.PRICE[t] = 1.0;
  // the top face's own ore, and a face that grows a different one
  const home = F.MINERAL_OF_FACE[0];
  const other = [0, 1, 2, 3, 4, 5].find(f => F.MINERAL_OF_FACE[f] !== home);
  const homeIngot = F.INGOT_OF ? F.INGOT_OF[home] : null;
  const ingotOfMineral = m => Object.keys(F.MINERAL_OF_INGOT).map(Number).find(k => F.MINERAL_OF_INGOT[k] === m);
  const near = ingotOfMineral(home), far = ingotOfMineral(F.MINERAL_OF_FACE[other]);
  const paid = t => { const a = window.__game.facts().value; F.bank(t, 0); return +(window.__game.facts().value - a).toFixed(2); };
  const nearPaid = paid(near);
  const toastBefore = document.getElementById('toast').textContent;
  const farPaid = paid(far);
  await w(200);
  const toastAfter = document.getElementById('toast').textContent;
  const farAgainOnItsOwnFace = (() => { const a = window.__game.facts().value; F.bank(far, other); return +(window.__game.facts().value - a).toFixed(2); })();
  const alloy = (() => { const a = window.__game.facts().value; F.bank(TY.ALLOY, 0); return +(window.__game.facts().value - a).toFixed(2); })();
  const alloyElsewhere = (() => { const a = window.__game.facts().value; F.bank(TY.ALLOY, other); return +(window.__game.facts().value - a).toFixed(2); })();
  // the label on the starter hub
  let hub = null; F.cells[0].forEach((col, i) => col.forEach((c, j) => { if (c.t === TY.HUB && !hub) hub = c; }));
  const label = F.lookLabel ? F.lookLabel(hub) : (document.getElementById('look') ? '' : '');
  return { home, other, near, far, nearPaid, farPaid, premium: F.FAR_PREMIUM, farAgainOnItsOwnFace, alloy, alloyElsewhere,
           toastBefore, toastAfter, label };
});
console.log('faces     : top grows', r.home, '| face', r.other, 'grows', F_name(r.other), '| ingots near', r.near, 'far', r.far);
console.log('paid      : near ingot on the top hub', r.nearPaid, '| far ingot on the top hub', r.farPaid, '(premium ' + r.premium + ')',
            '| far ingot on its own face', r.farAgainOnItsOwnFace, '| alloy here', r.alloy, 'there', r.alloyElsewhere);
console.log('said      :', JSON.stringify(r.toastAfter).slice(0, 110));
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'farore.png' });
await b.close();
function F_name(f) { return 'its own ore'; }

const ok = r.other !== undefined && r.near && r.far
  && Math.abs(r.farPaid - r.nearPaid * r.premium) < 0.05 && Math.abs(r.farAgainOnItsOwnFace - r.nearPaid) < 0.05
  && Math.abs(r.alloy - r.alloyElsewhere) < 0.05
  && /FAR ORE/.test(r.toastAfter) && !/FAR ORE/.test(r.toastBefore)
  && errs.length === 0;
process.exit(ok ? 0 : 1);
