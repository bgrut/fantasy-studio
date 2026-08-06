// Re-render dist/game.js from main.js.tpl + the job's already-exported spec.json.
// The exporter does exactly one substitution (__GAME_SPEC__), so this reproduces
// a full export's JS in milliseconds — the iteration loop for runtime-only work.
import fs from 'node:fs';
const job = process.argv[2];
const root = 'C:/Users/bgrut/Desktop/FantasyAI/fantasy-studio/backend';
const dist = `${root}/renders/game_jobs/job_${job}/dist`;
const tpl = fs.readFileSync(`${root}/app/game_export/runtime/main.js.tpl`, 'utf8');
const spec = fs.readFileSync(`${dist}/spec.json`, 'utf8');
// replaceAll + a function replacement: python's str.replace hits BOTH the
// header comment and the real assignment, and a string replacement would let
// `$&` inside the spec JSON expand.
const inj = JSON.stringify(JSON.parse(spec));
fs.writeFileSync(`${dist}/game.js`, tpl.replaceAll('__GAME_SPEC__', () => inj));
console.log('rerendered job_' + job + ' game.js', fs.statSync(`${dist}/game.js`).size, 'bytes');
