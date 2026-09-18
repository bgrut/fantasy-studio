// One game. The demo's title card names Crystal Works and quotes the sentence
// that made it, and lists no other builds: the studio's range is shown in the
// studio, not in the demo. A build from the studio shows no list either, and
// its reveal reads the prompt that made it.
//   URL=<demo>   J=<studio job id>   (either may be absent)
import puppeteer from 'puppeteer-core';
const b = await puppeteer.launch({ headless:'new',
  executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--use-angle=d3d11','--enable-unsafe-swiftshader','--window-size=1280,760'] });
const p = await b.newPage();
await p.setViewport({ width:1280, height:760 });
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0,200)));
const wait = ms => new Promise(r => setTimeout(r, ms));
const URL = process.env.URL || null;
const JOB = process.env.J ? 'http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/' : null;

const card = () => p.evaluate(() => {
  const t = document.getElementById('title');
  const picks = [...document.querySelectorAll('#title .worlds a')].length;
  return { up: !!t && t.classList.contains('on'), name: t?.querySelector('b')?.textContent || '', sub: t?.querySelector('small')?.textContent || '',
           picks, row: !!document.querySelector('#title .worlds'), worlds: (window.__factory && window.__factory.SPEC_WORLDS) || null };
});

const checks = {};
if (URL) {
  await p.goto(URL + '?fresh=1', { waitUntil:'domcontentloaded', timeout:90000 });
  await wait(1800);
  await p.screenshot({ path: process.env.OUT || 'worlds.png' });   // the card, up, with nothing beside it
  const home = await card();
  console.log('demo card  :', JSON.stringify(home.name), '|', JSON.stringify(home.sub).slice(0, 70), '| picks', home.picks, '| row', home.row);
  checks.homeUp = home.up && /CRYSTAL WORKS/.test(home.name);
  checks.homeQuoted = /^\u201c.+\u201d$/.test(home.sub);
  checks.homeNoPicks = home.picks === 0 && !home.row;
  // nothing shipped beside the demo: no other build answers under the demo's folder
  const beside = await p.evaluate(async () => { const out = {}; for (const f of ['drift/', 'forest/', 'worlds/moon.json']) { try { out[f] = (await fetch(f, { method: 'HEAD' })).ok; } catch (e) { out[f] = false; } } return out; });
  console.log('beside     :', JSON.stringify(beside));
  checks.nothingBeside = Object.values(beside).every(v => v === false);
}
if (JOB) {
  await p.goto(JOB + '?fresh=1', { waitUntil:'domcontentloaded', timeout:90000 });
  await wait(5000);
  const job = await card();
  console.log('studio card:', JSON.stringify(job.name), '|', JSON.stringify(job.sub).slice(0, 70), '| picks', job.picks);
  checks.jobNoPicks = job.picks === 0;
  checks.jobQuoted = /^\u201c.+\u201d$/.test(job.sub);
}
console.log('checks     :', JSON.stringify(checks));
console.log('errors     :', errs.length ? errs.join(' | ') : 'none');
await b.close();
process.exit(Object.keys(checks).length && Object.values(checks).every(Boolean) && errs.length === 0 ? 0 : 1);
