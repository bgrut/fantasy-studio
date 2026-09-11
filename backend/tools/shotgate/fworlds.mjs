// Three prompts, one system. The demo's title card lists the worlds it ships
// as the sentences that made them; picking one opens that world, under its
// own save, from the same factory.js. A build from the studio shows no list,
// and its reveal reads the prompt that made it.
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
  const picks = [...document.querySelectorAll('#title .worlds a')].map(a => ({
    name: a.querySelector('b')?.textContent, prompt: a.querySelector('span')?.textContent, href: a.getAttribute('href'), here: a.classList.contains('here') }));
  return { up: !!t && t.classList.contains('on'), name: t?.querySelector('b')?.textContent || '', sub: t?.querySelector('small')?.textContent || '',
           picks, saveKey: window.__factory?.SAVE_KEY || null, title: window.__game?.facts?.().title || null };
});

const checks = {};
if (URL) {
  await p.goto(URL + '?fresh=1', { waitUntil:'domcontentloaded', timeout:90000 });
  await wait(1800);
  await p.screenshot({ path: process.env.OUT || 'worlds.png' });   // the card, up, with its picks
  await wait(3200);
  const home = await card();
  console.log('demo card  :', JSON.stringify(home.name), '|', JSON.stringify(home.sub).slice(0, 70), '| picks', home.picks.length, home.picks.map(w => w.name + (w.here ? '*' : '')).join(', '));
  checks.homeQuoted = /^\u201c.+\u201d$/.test(home.sub);
  checks.homePicks = home.picks.length >= 3 && home.picks.every(w => w.name && /^\u201c.+\u201d$/.test(w.prompt)) && home.picks.filter(w => w.here).length === 1;
  const other = home.picks.find(w => !w.here && w.href.startsWith('?spec='));
  checks.otherLinked = !!other;
  if (other) {
    await p.goto(URL + other.href + '&fresh=1', { waitUntil:'domcontentloaded', timeout:90000 });
    await wait(6000);
    const away = await card();
    console.log('picked     :', JSON.stringify(away.name), '|', JSON.stringify(away.sub).slice(0, 70), '| here', away.picks.find(w => w.here)?.name, '| save', away.saveKey);
    checks.otherOpens = away.name !== home.name && away.saveKey && away.saveKey !== home.saveKey;
    checks.otherHere = away.picks.find(w => w.here)?.name === other.name;
    checks.otherQuoted = away.sub === other.prompt;
  }
}
if (JOB) {
  await p.goto(JOB + '?fresh=1', { waitUntil:'domcontentloaded', timeout:90000 });
  await wait(5000);
  const job = await card();
  console.log('studio card:', JSON.stringify(job.name), '|', JSON.stringify(job.sub).slice(0, 70), '| picks', job.picks.length);
  checks.jobNoPicks = job.picks.length === 0;
  checks.jobQuoted = /^\u201c.+\u201d$/.test(job.sub);
}
console.log('checks     :', JSON.stringify(checks));
console.log('errors     :', errs.length ? errs.join(' | ') : 'none');
await b.close();
process.exit(Object.keys(checks).length && Object.values(checks).every(Boolean) && errs.length === 0 ? 0 : 1);
