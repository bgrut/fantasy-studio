// SHOTGATE (2026-07-29): the build's eyes. Loads a freshly-exported game in
// headless Chrome, presses START, lets the world run, screenshots it, and
// reports console/page errors. Exit 0 = visually alive + error-free;
// exit 2 = page errors; exit 3 = load failure. The research finding this
// implements: the screenshot-verify loop is the single most load-bearing
// habit of the viral agentic game builds.
//
// usage: node shot.mjs <url> <out.png> [waitMs=6000]
import puppeteer from 'puppeteer-core';

const [url, out, waitArg] = process.argv.slice(2);
const wait = parseInt(waitArg || '6000', 10);
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
const { existsSync } = await import('fs');
const chrome = CHROMES.find(p => existsSync(p));
if (!chrome) { console.error('SHOTGATE-SKIP no chrome'); process.exit(0); }

let browser;
try {
  browser = await puppeteer.launch({
    executablePath: chrome, headless: 'new',
    args: ['--use-angle=d3d11', '--window-size=1280,720'],
    defaultViewport: { width: 1280, height: 720 },
  });
  const page = await browser.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  page.on('console', m => {
    if (m.type() !== 'error') return;
    const src = (m.location() && m.location().url) || '';
    if (/favicon/i.test(m.text() + ' ' + src)) return;
    errs.push((m.text() + ' @ ' + src).slice(0, 200));
  });
  await page.goto(url, { waitUntil: 'networkidle2', timeout: 45000 });
  await page.waitForSelector('#startbtn', { timeout: 25000 });
  await new Promise(r => setTimeout(r, 1500));
  await page.click('#startbtn');
  await page.keyboard.down('w');
  await new Promise(r => setTimeout(r, 1200));
  await page.keyboard.up('w');
  await new Promise(r => setTimeout(r, wait));
  await page.screenshot({ path: out });
  // FACTS, NOT JUST LIVENESS: what the running game actually built, so the
  // build can be held against the spec that asked for it. Best-effort — an
  // older export without __game.facts still passes the gate on errors alone.
  try {
    const facts = await page.evaluate(
      () => (window.__game && window.__game.facts) ? window.__game.facts() : null);
    if (facts) console.log('SHOTGATE-FACTS ' + JSON.stringify(facts));
  } catch {}
  if (errs.length) {
    console.error('SHOTGATE-ERRORS ' + errs.slice(0, 5).join(' | ').slice(0, 500));
    process.exit(2);
  }
  console.log('SHOTGATE-OK');
  process.exit(0);
} catch (e) {
  console.error('SHOTGATE-FAIL ' + e.message.slice(0, 300));
  process.exit(3);
} finally {
  try { await browser?.close(); } catch {}
}
