// The desktop build's window hooks (2026-09-29). In its own window (the Steam
// path, flagship-desktop) there is no browser to leave by: F11 goes fullscreen
// and the choice is kept, and the pause menu can quit to the desktop, saving
// first. The native window is faked before the page runs (window.__TAURI__),
// recording what the game asks of it; a plain browser page must show none of it.
//   URL=http://127.0.0.1:8790/ node fnative.mjs      (or J=<job> for a studio build)
import puppeteer from 'puppeteer-core';
const URL = process.env.J ? 'http://127.0.0.1:8789/games/job_' + process.env.J + '/dist/' : (process.env.URL || 'http://127.0.0.1:8790/');
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--enable-unsafe-swiftshader', '--window-size=1280,760'] });
const wait = ms => new Promise(r => setTimeout(r, ms));
const fails = [];
const check = (ok, what) => { console.log((ok ? '  ok   ' : '  FAIL ') + what); if (!ok) fails.push(what); };
async function open(native, keep) {
  const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760 });
  const errs = []; p.on('pageerror', e => errs.push(e.message.slice(0, 160)));
  if (native) await p.evaluateOnNewDocument(() => {
    window.__nativeCalls = [];
    const w = { setFullscreen: v => { window.__nativeCalls.push(['full', v]); return Promise.resolve(); },
                isFullscreen: () => Promise.resolve(false),
                close: () => { window.__nativeCalls.push(['close']); return Promise.resolve(); } };
    window.__TAURI__ = { window: { getCurrentWindow: () => w },
                         core: { invoke: (cmd, args) => {
                           window.__nativeCalls.push(['invoke', cmd, args && (args.id || args.dialog)]);
                           // Steam, as the Steam build answers when Steam is running
                           return Promise.resolve(cmd === 'steam_state'
                             ? { built_in: true, running: true, app_id: 480, player: 'Tester', overlay: true } : undefined);
                         } } };
  });
  await p.goto(URL + '?nointro=1' + (keep ? '' : '&fresh=1'), { waitUntil: 'domcontentloaded', timeout: 90000 });
  for (let i = 0; i < 40; i++) { if (await p.evaluate(() => !!(window.__factory && window.__pad))) break; await wait(500); }
  await wait(1500);
  return { p, errs };
}

// a browser: nothing native
{
  const { p, errs } = await open(false);
  await p.evaluate(() => { try { localStorage.removeItem('fs-factory-settings'); } catch (e) {} });
  await p.evaluate(() => window.__pad.pause(true));
  const has = await p.evaluate(() => ({ q: !!document.getElementById('pz-quit'), f: !!document.getElementById('pz-full') }));
  check(!has.q && !has.f, 'a browser shows no quit button and no fullscreen switch');
  check(errs.length === 0, 'no page errors in the browser' + (errs.length ? ': ' + errs[0] : ''));
  await p.close();
}
// the desktop window
{
  const { p, errs } = await open(true);
  await p.evaluate(() => window.__pad.pause(true));
  const has = await p.evaluate(() => ({ q: !!document.getElementById('pz-quit'), f: !!document.getElementById('pz-full') }));
  check(has.q && has.f, 'the desktop window pauses into a fullscreen switch and a quit button');
  const st = await p.evaluate(() => ({ who: (document.getElementById('pz-steam') || {}).textContent || '', ach: !!document.getElementById('pz-ach') }));
  check(st.who === 'Steam: Tester' && st.ach, `with Steam running the pause menu says who is playing ("${st.who}") and offers the achievements`);
  await p.evaluate(() => { const a = document.getElementById('pz-ach'); if (a) a.click(); });
  await wait(150);
  check(await p.evaluate(() => window.__nativeCalls.some(c => c[0] === 'invoke' && c[1] === 'steam_overlay' && c[2] === 'Achievements')),
        'ACHIEVEMENTS opens the Steam overlay on its achievements page');
  await p.evaluate(() => window.__pad.pause(false));
  await p.keyboard.press('F11'); await wait(200);
  const c1 = await p.evaluate(() => window.__nativeCalls.slice());
  check(c1.some(c => c[0] === 'full' && c[1] === true), 'F11 asks the window for fullscreen');
  await p.keyboard.press('F11'); await wait(200);
  const c2 = await p.evaluate(() => window.__nativeCalls.slice());
  check(c2.filter(c => c[0] === 'full').pop()[1] === false, 'F11 again comes back to a window');
  await p.keyboard.press('F11'); await wait(200);
  await p.evaluate(() => window.__pad.pause(true));
  const cb = await p.evaluate(() => document.getElementById('pz-full').checked);
  check(cb, 'the switch shows the window is fullscreen');
  await p.evaluate(() => { window.__saved = 0; const s0 = localStorage.setItem.bind(localStorage); localStorage.setItem = (k, v) => { if (/^fs-factory-/.test(k) && !/settings|bp|q|motion|muted/.test(k.replace('fs-factory-', ''))) window.__saved++; return s0(k, v); }; });
  await p.evaluate(() => document.getElementById('pz-quit').click());
  await wait(200);
  const q = await p.evaluate(() => ({ calls: window.__nativeCalls.slice(), saved: window.__saved }));
  check(q.calls.some(c => c[0] === 'close') && q.saved > 0, `quit saves (${q.saved} writes) and closes the window`);
  check(errs.length === 0, 'no page errors in the desktop window' + (errs.length ? ': ' + errs[0] : ''));
  await p.close();
  // the choice is kept: the next launch opens fullscreen
  const { p: p2, errs: e2 } = await open(true, true);
  const c3 = await p2.evaluate(() => window.__nativeCalls.slice());
  check(c3.some(c => c[0] === 'full' && c[1] === true), 'the next launch opens fullscreen, as it was left');
  // achievements: the first sale reaches Steam, and what was earned before is sent again at launch
  let sale = false;
  for (let i = 0; i < 40 && !sale; i++) {
    sale = await p2.evaluate(() => window.__nativeCalls.some(c => c[0] === 'invoke' && c[1] === 'steam_achieve' && c[2] === 'CW_FIRST_SALE'));
    if (!sale) await wait(1000);
  }
  const ach = await p2.evaluate(() => window.__game.facts().achievements);
  check(sale && ach.includes('CW_FIRST_SALE'), `the first sale is an achievement, handed to Steam (${ach.join(', ')})`);
  check(e2.length === 0, 'no page errors on the next launch' + (e2.length ? ': ' + e2[0] : ''));
  await p2.close();
  const { p: p3, errs: e3 } = await open(true, true);
  const resent = await p3.evaluate(() => window.__nativeCalls.filter(c => c[0] === 'invoke' && c[1] === 'steam_achieve').map(c => c[2]));
  check(resent.includes('CW_FIRST_SALE'), 'achievements earned before are sent to Steam again at launch');
  check(e3.length === 0, 'no page errors on the third launch' + (e3.length ? ': ' + e3[0] : ''));
  await p3.evaluate(() => { try {
    localStorage.removeItem('fs-factory-ach');
    const s = JSON.parse(localStorage.getItem('fs-factory-settings') || '{}'); delete s.full;
    localStorage.setItem('fs-factory-settings', JSON.stringify(s)); } catch (e) {} });
  await p3.close();
}
await b.close();
console.log(fails.length ? `${fails.length} failed; FAIL` : 'PASS');
process.exit(fails.length ? 1 : 0);
