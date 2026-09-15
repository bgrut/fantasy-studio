// The kit is shared. A factory build and an adventure build both have to
// link vendor/kit/kit.css, load the studio's faces, set a mood from the
// prompt's words, and set their title in the display face: the factory's
// reveal card and the adventure's start card in the same voice.
//   URL=<factory demo or job dist>  A=<adventure job id>   (either may be absent)
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const wait = ms => new Promise(r => setTimeout(r, ms));
const URL = process.env.URL || (process.env.J ? 'http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/' : null);
const ADV = process.env.A ? 'http://127.0.0.1:8789/games/job_' + process.env.A + '/dist/' : null;

const probe = () => p.evaluate(async () => {
  const link = [...document.querySelectorAll('link[rel="stylesheet"]')].map(l => l.getAttribute('href')).find(h => /vendor\/kit\/kit\.css$/.test(h)) || null;
  await document.fonts.ready;
  // a face nothing on the page uses yet is not loaded; ask for it, as the runtime would
  await Promise.all(['12px "Bricolage Grotesque"', '12px "Instrument Sans"', '12px "DM Mono"'].map(f => document.fonts.load(f).catch(() => null)));
  const faces = { head: document.fonts.check('12px "Bricolage Grotesque"'), ui: document.fonts.check('12px "Instrument Sans"'), mono: document.fonts.check('12px "DM Mono"') };
  const fam = el => el ? getComputedStyle(el).fontFamily : null;
  return { link, faces, mood: document.body.dataset.mood || null,
           startH1: fam(document.querySelector('.fs-start')), title: fam(document.querySelector('#title b')),
           hudH1: fam(document.querySelector('#hud h1')), winH2: fam(document.querySelector('#win h2')) };
});

let fac = null, adv = null;
if (URL) {
  await p.goto(URL + (URL.includes('?') ? '&' : '?') + 'fresh=1', { waitUntil:'domcontentloaded', timeout:90000 });
  await wait(4500);
  fac = await probe();
  console.log('factory   : kit linked', JSON.stringify(fac.link), '| faces', JSON.stringify(fac.faces), '| title in', JSON.stringify(fac.title).slice(0, 40), '| panel in', JSON.stringify(fac.hudH1).slice(0, 40));
}
if (ADV) {
  await p.goto(ADV, { waitUntil:'domcontentloaded', timeout:120000 });
  await wait(9000);
  adv = await probe();
  console.log('adventure : kit linked', JSON.stringify(adv.link), '| faces', JSON.stringify(adv.faces), '| mood', adv.mood, '| start card in', JSON.stringify(adv.startH1).slice(0, 40), '| win card in', JSON.stringify(adv.winH2).slice(0, 40));
  // START plays the kit's reveal: the title, the sentence that made the world
  const btn = await p.$('#startbtn'); if (btn) await btn.click();
  await wait(700);
  adv.reveal = await p.evaluate(() => { const t = document.getElementById('fs-title'); return t && t.classList.contains('on') ? { name: t.querySelector('b').textContent, sub: t.querySelector('small').textContent } : null; });
  await p.screenshot({ path: process.env.OUT || 'kit.png' });
  // and a win closes on the kit's end card
  await p.evaluate(() => { if (window.__game && window.__game.win) window.__game.win('the gate called it'); });   // an older build has no hook: the end card check then fails honestly
  await wait(500);
  adv.end = await p.evaluate(() => { const e = document.getElementById('fs-end'); return e && e.classList.contains('on') ? { title: e.querySelector('h2').textContent, buttons: [...e.querySelectorAll('button')].map(b => b.textContent), font: getComputedStyle(e.querySelector('h2')).fontFamily } : null; });
  console.log('adventure : reveal', JSON.stringify(adv.reveal), '| end card', JSON.stringify(adv.end));
  await p.screenshot({ path: 'kit_end.png' });
}
console.log('errors    :', errs.length ? errs.join(' | ') : 'none');
await b.close();

const okF = !fac || (fac.link && fac.faces.head && fac.faces.ui && fac.faces.mono && /Bricolage/.test(fac.title || '') && /Bricolage/.test(fac.hudH1 || ''));
const okA = !adv || (adv.link && adv.faces.head && adv.faces.ui && adv.faces.mono && !!adv.mood && /Bricolage|DM Mono/.test(adv.startH1 || '') && /Bricolage|DM Mono/.test(adv.winH2 || '')
  && adv.reveal && adv.reveal.name && /^\u201c.+\u201d$/.test(adv.reveal.sub) && adv.end && /win/i.test(adv.end.title) && adv.end.buttons.includes('play again') && /Bricolage|DM Mono/.test(adv.end.font));
process.exit(okF && okA && (fac || adv) && errs.length === 0 ? 0 : 1);
