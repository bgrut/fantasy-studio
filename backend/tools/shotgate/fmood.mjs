// World zero reads the prompt. A build whose spec names red or rust must come
// out warm; one that names nothing must come out the default void — and the
// check is on the SCENE's sky, not on a label, so a mood that is chosen but
// never applied is caught.
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const URL = process.env.URL ||
  ('http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/');
await p.goto(URL + '?fresh=1&nointro=1', { waitUntil:'domcontentloaded', timeout:90000 });
for (let k = 0; k < 60; k++) {
  if (await p.evaluate(()=>typeof window.__game === 'object')) break;
  await new Promise(r=>setTimeout(r,200));
}
await new Promise(r=>setTimeout(r,1200));
const r = await p.evaluate(()=>{
  const S = window.__SPEC, f = window.__game.facts();
  const sky = window.__scene.background;
  const text = [S.title, S.world && S.world.name, S.world && S.world.description].filter(Boolean).join(' ');
  const cube = window.__scene.children.find(o => o.isMesh && o.geometry.type === 'BoxGeometry'
                                            && o.geometry.parameters.width === window.__factory.N * window.__factory.T);
  return { title: S.title, palette: S.world && S.world.palette, mood: f.mood, text,
           sky: [sky.r, sky.g, sky.b].map(v => +v.toFixed(3)),
           ground: '#' + cube.material.color.getHexString(),
           overlay: (window.__factory.WORLDS[0].plate || {}).overlay || null };
});
const warmWords = /\b(red|rust|ember|cinder|lava|ash|crimson|copper|desert)/i.test(r.text);
const coldWords = /\b(ice|frost|frozen|snow|glacier|arctic|winter)/i.test(r.text);
console.log('spec      :', JSON.stringify(r.title), '| palette from extractor:', r.palette ? 'yes' : 'none');
console.log('mood      :', r.mood, '| sky rgb', JSON.stringify(r.sky), '| ground', r.ground, '| plating', r.overlay);
let ok = ['void','warm','cold','green'].includes(r.mood) && errs.length === 0;
if (warmWords)      ok = ok && r.mood === 'warm' && r.sky[0] > r.sky[2] && r.overlay === 'soot';
else if (coldWords) ok = ok && r.mood === 'cold' && r.sky[2] > r.sky[0] && r.overlay === 'frost';
else                ok = ok && (r.palette ? true : r.mood === 'void');
// A COMMITTED PALETTE WINS ONLY WHEN IT AGREES. The extractor handed a red
// moon a violet night sky one build in four; the rule is asked directly
// because a given build may or may not carry a palette at all.
const rule = await p.evaluate(() => {
  const F = window.__factory;
  return { mood: F.MOOD, red: F.agreesWithMood('#3a0c08'), violet: F.agreesWithMood('#0d0a24'),
           ice: F.agreesWithMood('#0a1420'), green: F.agreesWithMood('#08170f'), none: F.agreesWithMood(null),
           sky: '#' + F.SKY_COL.toString(16).padStart(6, '0') };
});
const expect = { warm: { red: true, violet: false, ice: false }, cold: { red: false, ice: true, violet: true },
                 green: { green: true, red: false }, void: { red: true, violet: true, ice: true, green: true } }[rule.mood] || {};
const ruleOk = !rule.none && Object.keys(expect).every(k => rule[k] === expect[k]);
console.log('palette   : mood', rule.mood, '| red', rule.red, '| violet', rule.violet, '| ice', rule.ice,
            '| green', rule.green, '| none', rule.none, '| sky in use', rule.sky, '|', ruleOk ? 'rule holds' : 'RULE BROKEN');
ok = ok && ruleOk;
console.log('verdict   :', ok ? 'the world matches its prompt' : 'MISMATCH');
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await p.screenshot({ path: process.env.OUT || 'mood.png' });
await b.close();
process.exit(ok ? 0 : 1);
