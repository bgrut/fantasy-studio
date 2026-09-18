// Which WebGL call blocks the main thread across the first sale. Every draw,
// link and texture upload is timed; a call over 20 ms is logged with its
// program and whether that program had drawn before (a first draw that stalls
// is the driver compiling the shader late).
import puppeteer from 'puppeteer-core';
const URL = process.env.URL || 'http://127.0.0.1:8790/';
const q = URL.includes('?') ? '&' : '?';
const b = await puppeteer.launch({ headless: 'new', executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--disable-frame-rate-limit', '--disable-gpu-vsync', '--window-size=1280,760'] });
const p = await b.newPage(); await p.setViewport({ width: 1280, height: 760, deviceScaleFactor: 1 });
await p.evaluateOnNewDocument(() => {
  window.__gl = { slow: [], ids: new WeakMap(), next: 1, drawn: new Set(), current: null, t0: performance.now() };
  const G = window.__gl;
  const P = WebGL2RenderingContext.prototype;
  const wrap = (name, describe) => {
    const orig = P[name];
    P[name] = function (...a) {
      const t = performance.now(); const r = orig.apply(this, a); const ms = performance.now() - t;
      if (ms > 20) G.slow.push({ at: +((t - G.t0) / 1000).toFixed(1), ms: +ms.toFixed(0), call: name, what: describe ? describe.call(this, a) : '' });
      return r;
    };
  };
  const origUse = P.useProgram;
  P.useProgram = function (pr) { if (pr && !G.ids.has(pr)) G.ids.set(pr, G.next++); G.current = pr ? G.ids.get(pr) : null; return origUse.call(this, pr); };
  G.vaos = new WeakMap(); G.vnext = 1; G.firsts = [];
  const drawInfo = function (a) { const id = G.current, first = !G.drawn.has(id); G.drawn.add(id); return 'program ' + id + (first ? ' FIRST DRAW' : '') + ' mode ' + a[0] + ' count ' + a[1]; };
  // every first draw of a (program, vertex array) pair, with its time: a late shader compile follows one of these
  const firstOf = function (a, name) { const v = this.getParameter(this.VERTEX_ARRAY_BINDING); let vid = 0; if (v) { if (!G.vaos.has(v)) G.vaos.set(v, G.vnext++); vid = G.vaos.get(v); }
    const key = G.current + '/' + vid; if (!G.drawn.has(key)) { G.drawn.add(key); G.firsts.push({ at: +((performance.now() - G.t0) / 1000).toFixed(2), program: G.current, vao: vid, call: name, count: a[1], inst: a[3] }); } };
  for (const n of ['drawElements', 'drawArrays', 'drawElementsInstanced', 'drawArraysInstanced']) { const o = P[n]; P[n] = function (...a) { firstOf.call(this, a, n); return o.apply(this, a); }; }
  wrap('drawElements', drawInfo); wrap('drawArrays', drawInfo); wrap('drawElementsInstanced', drawInfo); wrap('drawArraysInstanced', drawInfo);
  wrap('linkProgram', () => 'link'); wrap('compileShader', () => 'compile'); wrap('getProgramParameter', (a) => 'getProgramParameter ' + a[1]); wrap('getShaderParameter', () => 'getShaderParameter');
  wrap('texImage2D', (a) => 'texImage2D ' + (a.length > 6 ? a[3] + 'x' + a[4] : (a[5] && a[5].width) + 'x' + (a[5] && a[5].height))); wrap('texSubImage2D', () => 'texSubImage2D'); wrap('generateMipmap', () => 'mipmap');
  wrap('readPixels', () => 'readPixels'); wrap('getError', () => 'getError'); wrap('finish', () => 'finish'); wrap('flush', () => 'flush'); wrap('clientWaitSync', () => 'clientWaitSync'); wrap('getSyncParameter', () => 'getSyncParameter');
  wrap('bufferData', (a) => 'bufferData ' + (a[1] && a[1].byteLength !== undefined ? a[1].byteLength : a[1])); wrap('bufferSubData', () => 'bufferSubData');
  wrap('bindFramebuffer', () => 'bindFramebuffer'); wrap('framebufferTexture2D', () => 'framebufferTexture2D'); wrap('checkFramebufferStatus', () => 'checkFramebufferStatus'); wrap('getUniformLocation', () => 'getUniformLocation'); wrap('getActiveUniform', () => 'getActiveUniform');
  wrap('texStorage2D', (a) => 'texStorage2D ' + a[3] + 'x' + a[4]); wrap('copyTexImage2D', () => 'copyTexImage2D'); wrap('blitFramebuffer', () => 'blitFramebuffer');
});
await p.goto(URL + q + 'fresh=1&nointro=1', { waitUntil: 'domcontentloaded', timeout: 90000 });
await new Promise(r => setTimeout(r, 4000));
const out = await p.evaluate(async () => {
  const F = window.__factory; F.droneAt(23); const G = window.__gl; const mark = G.slow.length;
  let last = performance.now(); const hits = []; const t0 = performance.now();
  await new Promise(done => { const tick = (t) => { const dt = t - last; last = t; if (dt > 60) hits.push(dt.toFixed(0) + 'ms@' + ((t - G.t0) / 1000).toFixed(1) + 's'); if (t - t0 < 14000) requestAnimationFrame(tick); else done(); }; requestAnimationFrame(tick); });
  return { hits, slow: G.slow.slice(mark), programs: G.next - 1, firstSale: window.__game.facts().firstSale, firsts: G.firsts.filter(f => f.at > (t0 - G.t0) / 1000 - 0.5) };
});
console.log('hitches   :', out.hits.join(' ') || 'none', '| first sale', out.firstSale, '| programs used', out.programs);
for (const s of out.slow) console.log('  slow gl :', s.ms + 'ms@' + s.at + 's', s.call, s.what);
for (const f of out.firsts) console.log('  first   :', f.at + 's', 'program', f.program, 'vao', f.vao, f.call, 'count', f.count, f.inst !== undefined ? 'x' + f.inst : '');
await b.close();
