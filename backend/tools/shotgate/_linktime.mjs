// How long does this machine take to link a trivial shader it has never seen, in an empty page?
// [ANGLE=d3d11|vulkan|gl] [N=12] [ARGS="--flag --flag"] node _linktime.mjs
// Every source carries a random constant, so no driver or ANGLE cache can answer. If this is slow the game is not to blame.
import puppeteer from 'puppeteer-core';
const extra = (process.env.ARGS || '').split(' ').filter(Boolean);
const b = await puppeteer.launch({ headless: process.env.HEADFUL ? false : 'new', executablePath: process.env.EXE || 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: [`--use-angle=${process.env.ANGLE || 'd3d11'}`, ...extra] });
const p = await b.newPage(); await p.goto('about:blank');
const r = await p.evaluate((N) => { const c = document.createElement('canvas'), g = c.getContext('webgl2'), T = [];
  if (!g) return 'no webgl2';
  const dbg = g.getExtension('WEBGL_debug_renderer_info'), who = dbg ? g.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : '';
  for (let i = 0; i < N; i++) { const t = performance.now(), k = Math.random().toFixed(9), vs = g.createShader(g.VERTEX_SHADER), fs = g.createShader(g.FRAGMENT_SHADER);
    g.shaderSource(vs, `#version 300 es\nin vec3 p; uniform mat4 m; void main(){ gl_Position = m * vec4(p, ${k} * 0.001 + 1.0); gl_PointSize = 2.0; }`);
    g.shaderSource(fs, `#version 300 es\nprecision highp float; out vec4 o; uniform vec3 c; void main(){ o = vec4(c * ${k}, 1.0); }`);
    g.compileShader(vs); g.compileShader(fs); const P = g.createProgram(); g.attachShader(P, vs); g.attachShader(P, fs); g.linkProgram(P); g.getProgramParameter(P, g.LINK_STATUS); T.push(Math.round(performance.now() - t)); }
  const s = [...T].sort((a, b) => a - b); return { who: who.slice(0, 70), ms: T, median: s[s.length >> 1], worst: s[s.length - 1], total: T.reduce((a, b) => a + b, 0) }; }, +(process.env.N || 12));
console.log(JSON.stringify(r)); await b.close();
