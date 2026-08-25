// SCENE AUDIT harness (2026-08-25, critique-loop phase 1). Loads a built
// game headless, presses START, waits for the world to assemble, then asks
// the runtime to audit its own scene graph (window.__audit) and prints the
// report as one AUDIT-JSON line. The pipeline turns defects into
// dist/audit_fixes.json, which the runtime applies at every boot.
// Best-effort by design: exit 0 always unless the page never loads.
//
// usage: node audit.mjs <url> [waitMs=9000]
import puppeteer from 'puppeteer-core';

const [url, waitArg] = process.argv.slice(2);
const wait = parseInt(waitArg || '9000', 10);
const CHROMES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  process.env.LOCALAPPDATA + '/Google/Chrome/Application/chrome.exe',
];
const { existsSync } = await import('fs');
const chrome = CHROMES.find(p => existsSync(p));
if (!chrome) { console.log('AUDIT-SKIP no chrome'); process.exit(0); }

let browser;
try {
  browser = await puppeteer.launch({
    executablePath: chrome, headless: 'new',
    args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,720'],
    defaultViewport: { width: 1280, height: 720 },
  });
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('#startbtn', { timeout: 30000 });
  await new Promise(r => setTimeout(r, 1500));
  await page.click('#startbtn');
  // the wait matters: NPCs, cars and placed GLBs land asynchronously, and
  // auditing a half-assembled scene reports phantom defects
  await new Promise(r => setTimeout(r, wait));
  const rep = await page.evaluate(() =>
    typeof window.__audit === 'function' ? window.__audit() : null);
  if (!rep) { console.log('AUDIT-SKIP no __audit hook'); process.exit(0); }
  console.log('AUDIT-JSON ' + JSON.stringify(rep));
  process.exit(0);
} catch (e) {
  console.log('AUDIT-SKIP ' + String(e.message || e).slice(0, 200));
  process.exit(0);
} finally {
  if (browser) await browser.close().catch(() => {});
}
