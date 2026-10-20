// leave the factory for three hours (by the clock in its save) and come back. URL=
import puppeteer from 'puppeteer-core';
const U = process.env.URL || 'http://127.0.0.1:8790/';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 720 });
await p.goto(U + '?fresh=1', { waitUntil: 'domcontentloaded' }); await new Promise(r => setTimeout(r, 25000));
const before = await p.evaluate(() => ({ ore: window.__game.facts().value, rate: window.__factory.rateNow }));
await p.goto(U + 'nothing-here', { waitUntil: 'domcontentloaded' });            // unloads the game: it saves
const keyed = await p.evaluate(() => { const k = Object.keys(localStorage).find(k => { try { const d = JSON.parse(localStorage.getItem(k)); return d && d.v && d.m && /^fs-factory-/.test(k); } catch (e) { return false; } }); const d = JSON.parse(localStorage.getItem(k));
  const was = { at: d.at, rm: d.rm, ore: d.ore }; d.at = Date.now() - 3 * 3600 * 1000; if (!(d.rm > 0)) d.rm = 120; localStorage.setItem(k, JSON.stringify(d)); return { k, was, rm: d.rm }; });
await p.goto(U, { waitUntil: 'domcontentloaded' }); await new Promise(r => setTimeout(r, 9000));
const after = await p.evaluate(() => ({ away: window.__away, toast: document.getElementById('toast').textContent }));
console.log(JSON.stringify({ before, keyed, after }));
await p.screenshot({ path: process.env.OUT || 'away.jpg', type: 'jpeg', quality: 80 });
await b.close();
