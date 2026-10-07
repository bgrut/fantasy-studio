// How many characters a build actually spawned, by name, and the console
// warnings from spawning: a guard against an NPC loader that fails quietly.
//   J=job_N node npcprobe.mjs
import puppeteer from 'puppeteer-core';
const J = process.env.J;
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--use-angle=d3d11'] });
const p = await b.newPage(); await p.setViewport({ width: 1000, height: 600 });
const warns = []; p.on('console', m => { if (['warning', 'error'].includes(m.type())) warns.push(m.text().slice(0, 160)); });
p.on('pageerror', e => warns.push('PAGEERROR ' + e.message));
await p.goto(`http://127.0.0.1:8789/games/${J}/dist/index.html`, { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 12000));
await p.click('#startbtn').catch(() => {}); await new Promise(r => setTimeout(r, 2500));
const n = await p.evaluate(() => { const ns = window.__game && window.__game.npcRefs ? window.__game.npcRefs() : [];
  const by = {}; for (const x of ns) by[x.name] = (by[x.name] || 0) + 1; return { total: ns.length, by, vessels: ns.filter(x => x.vessel).length }; });
console.log(J, JSON.stringify(n), JSON.stringify(warns.filter(w => !/404/.test(w)).slice(0, 6)));
await b.close();
