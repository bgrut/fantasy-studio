// The words. A theme has to change what a player reads everywhere it reads
// — the chips, the tool bar, the goal card, a toast, a contract, the look
// label — singular and plural, in the case of what it replaces, and nothing
// else: no attribute, no id, no seam name. Without a theme nothing changes.
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

const theme = { resource: 'grain/grain', deposit: 'field', ores: ['wheat', 'barley', 'rye'], refined: 'flour/flour', combined: 'dough/dough',
                product: 'loaf/loaves', currency: 'coin', extractor: 'harvester', refiner: 'mill', combiner: 'kneader',
                assembler: 'oven', outlet: 'stall', carrier: 'cart' };
const enc = Buffer.from(JSON.stringify(theme)).toString('base64').replace(/\+/g, '-').replace(/\//g, '_');

// 1. without a theme, the words are the game's own
await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const plain = await p.evaluate(() => ({
  themed: !!window.__game.facts().themed,   // a build that carries its own theme has no plain words to show
  miner: document.querySelector('.tool[data-tool="miner"] b').textContent, chip: document.querySelector('.st[data-ico="miner"] small').textContent,
  goal: document.querySelector('#goal b').textContent, banked: document.querySelector('.hero .big small').textContent }));
console.log('plain     :', JSON.stringify(plain));

// 2. with the bakery: every place a player reads
await p.goto(URL + q + 'fresh=1&nointro=1&theme=' + enc, { waitUntil:'domcontentloaded', timeout:90000 });
await wait(4500);
const themed = await p.evaluate(async () => {
  const F = window.__factory, TY = F.TYPES;
  const w = ms => new Promise(r => setTimeout(r, ms));
  const tool = t => document.querySelector('.tool[data-tool="' + t + '"] b').textContent;
  const chip = t => document.querySelector('.st[data-ico="' + t + '"] small').textContent;
  F.goalIdx = 3; await w(300);                                   // "forge one alloy" becomes the kneader and the dough
  const goal = document.querySelector('#goal b').textContent, tip = document.querySelector('#goal small').textContent;
  F.addValue(60); F.offerContract(TY.INGOT); await w(300);
  const contract = document.querySelector('#contract b').textContent, toast = document.getElementById('toast').textContent;
  // the look label on the starter smelter
  let sm = null; F.cells[0].forEach((col, i) => col.forEach((c, j) => { if (c.t === TY.SMELTER && !sm) sm = { face: 0, i, j }; }));
  const wp = F.tileWorld(0, sm.i, sm.j - 2); F.player.pos.set(wp[0], F.HALF + 1.5, wp[2]); F.player.face = 0;   // from the side, so the crosshair lands on the mill and not the belt before it
  const lp = F.tileWorld(0, sm.i, sm.j); const dx = lp[0] - wp[0], dz = lp[2] - wp[2], d = Math.hypot(dx, dz);
  F.player.fwd.set(dx / d, 0, dz / d); F.player.pitch = -Math.atan2(1.5, d); if (F.setHolo) F.setHolo(null);   // the ray meets the ground on the mill's tile
  await w(500);
  const look = document.getElementById('look').textContent;
  return { miner: tool('miner'), smelter: tool('smelter'), hub: tool('hub'), belt: tool('belt'), forge: tool('forge'),
           chips: [chip('miner'), chip('belt'), chip('smelter'), chip('ingot'), chip('alloy')], banked: document.querySelector('.hero .big small').textContent,
           goal, tip, contract, toast, look, market: [...document.querySelectorAll('#tick .nm')].map(e => e.textContent),
           dataTool: document.querySelector('.tool[data-tool="hub"]') ? 'kept' : 'LOST', seam: F.TYPES.HUB === TY.HUB };
});
console.log('themed    : tools', [themed.miner, themed.belt, themed.smelter, themed.hub, themed.forge].join(' / '), '| chips', themed.chips.join(' / '), '| banked', JSON.stringify(themed.banked));
console.log('            goal', JSON.stringify(themed.goal), '| tip', JSON.stringify(themed.tip).slice(0, 90));
console.log('            contract', JSON.stringify(themed.contract), '| toast', JSON.stringify(themed.toast).slice(0, 100));
console.log('            look', JSON.stringify(themed.look), '| market', themed.market.join('/'), '| attributes', themed.dataTool);
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'theme.png' });
await b.close();

const all = [themed.goal, themed.tip, themed.contract, themed.toast, themed.look, themed.banked, ...themed.chips, themed.miner, themed.smelter, themed.hub, themed.belt].join(' ');
const checks = {
  plain: plain.themed || (plain.miner === 'MINER' && plain.chip === 'rigs' && /CREDITS/i.test(plain.banked)),
  tools: themed.miner === 'HARVESTER' && themed.smelter === 'MILL' && themed.hub === 'STALL' && themed.belt === 'CART' && themed.forge === 'KNEADER',
  chips: themed.chips[0] === 'harvesters' && /flour/.test(themed.chips[3]),
  banked: /COIN/i.test(themed.banked), goal: /KNEADER ONE DOUGH/i.test(themed.goal),
  contract: /wheat flour\b/i.test(themed.contract) && !/flours/i.test(themed.contract), toast: /COIN/i.test(themed.toast),
  look: /MILL/.test(themed.look) && /grain/i.test(themed.look),
  market: themed.market.join('/') === 'wheat/barley/rye/dough/loaf', attributes: themed.dataTool === 'kept',
  leftovers: !/\b(ingot|smelter|credit|alloy|hub)s?\b/i.test(all), errors: errs.length === 0,
};
const failed = Object.keys(checks).filter(k => !checks[k]);
if (failed.length) console.log('failed    :', failed.join(', '), '| contract codes:', [...themed.contract].map(c => c.charCodeAt(0)).join(','));
const ok = failed.length === 0;
process.exit(ok ? 0 : 1);
