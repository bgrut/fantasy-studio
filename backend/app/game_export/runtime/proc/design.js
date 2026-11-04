// THE DESIGNER'S SYSTEMS (2026-10-20, with backend/app/game_export/design.py).
// "Different characters, same game": every world played as walk, collect,
// reach. The designer gives each game one mechanic of its own and a moment
// where it turns. Each is small, and felt:
//
//   tracks     prints in the ground lead toward what you seek; they begin a
//              few steps ahead and fade behind you, and there is no marker
//   freshness  what you carry cools from the moment it leaves home; each
//              delivery is judged by its warmth; home fills the basket again
//   lantern    your light is oil; the lamps along the way are dark until you
//              reach them, then they burn on and fill your lantern
//   gusts      the wind comes in shoves you can see in the grass and feel in
//              your step, and you lean into them
//   cold       warmth drains in the open and comes back by a fire, a lit lamp
//              or home; frozen through, you slow and the frame frosts
//
//   moments: storm (rain sweeps in, the light drops), nightfall (the day
//   goes), fog (a bank rolls in), at about half way through the game.
//
// o: { THREE, scene, camera, hAt, LVL, SPEC, sun, hemi, renderer, home:[x,z],
//      pos() -> [x,y,z], next() -> [x,z]|null, progress() -> 0..1,
//      count() -> things done so far, words, seed, night, toast(text, sub) }
// returns { tick(dt, t), push(dt) -> [dx, dz] | null, speed() -> multiplier, state() }

function rng(seed) {
  let a = (seed >>> 0) || 1;
  return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// a small HUD meter in this game's own faces and accent (the maker's, via CSS vars)
function meter(label, icon) {
  const el = document.createElement('div');
  el.className = 'fs-meter';
  el.innerHTML = `<i>${icon}</i><span>${label}</span><b><s></s></b>`;
  if (!document.getElementById('fs-meter-css')) {
    const st = document.createElement('style'); st.id = 'fs-meter-css';
    st.textContent = `.fs-meter{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);display:flex;align-items:center;gap:9px;z-index:25;pointer-events:none;
      font:600 11px var(--f-ui,system-ui);letter-spacing:.14em;text-transform:uppercase;color:var(--art-ink,#eee);text-shadow:0 1px 6px rgba(0,0,0,.7);transition:opacity .6s}
      .fs-meter i{font-style:normal;font-size:15px;filter:drop-shadow(0 1px 4px rgba(0,0,0,.6))}
      .fs-meter b{display:block;width:150px;height:5px;border-radius:3px;background:rgba(0,0,0,.45);overflow:hidden;box-shadow:0 0 0 1px rgba(255,255,255,.12)}
      .fs-meter s{display:block;height:100%;width:100%;background:var(--art-acc,#ffd479);transition:width .25s linear}
      .fs-meter.low s{background:#e8634a} .fs-meter.flash{animation:fsmf .5s ease 2}
      @keyframes fsmf{50%{transform:translateX(-50%) scale(1.08)}}
      .fs-frost{position:fixed;inset:0;pointer-events:none;z-index:4;opacity:0;transition:opacity .8s;
        background:radial-gradient(ellipse at center,transparent 45%,rgba(200,225,245,.25) 75%,rgba(235,245,255,.6) 100%)}`;
    document.head.appendChild(st);
  }
  document.body.appendChild(el);
  return { set(v) { el.querySelector('s').style.width = Math.round(Math.max(0, Math.min(1, v)) * 100) + '%'; el.classList.toggle('low', v < 0.25); },
           flash() { el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); }, el };
}

export function startDesign(o) {
  const { THREE, scene } = o;
  const D = (o.LVL && o.LVL.design) || {};
  const mech = D.mechanic || 'none', moment = D.moment || 'none';
  if (mech === 'none' && moment === 'none') return null;
  const r = rng((o.seed || 1) * 31 + 977);
  const words = String(o.words || '').toLowerCase();
  const S = { mechanic: mech, moment, layout: D.layout || 'route' };
  let pushFn = null, speedFn = () => 1;
  const ticks = [];
  const near = (a, b, d) => Math.hypot(a[0] - b[0], a[1] - b[1]) < d;

  // ── TRACKS ───────────────────────────────────────────────────────────────
  if (mech === 'tracks') {
    const paw = /\b(fox|cubs?|wolf|wolves|dog|puppy|pups?|cat|kitten|bear|deer|fawn|lynx|tiger|lion|kits?|hare|rabbit)\b/.test(words);
    const cv = document.createElement('canvas'); cv.width = cv.height = 64; const g = cv.getContext('2d');
    g.fillStyle = 'rgba(30,22,14,0.85)';
    if (paw) { g.beginPath(); g.ellipse(32, 40, 12, 10, 0, 0, 7); g.fill(); for (const [x, y] of [[18, 22], [28, 15], [38, 15], [47, 22]]) { g.beginPath(); g.ellipse(x, y, 5, 6, 0, 0, 7); g.fill(); } }
    else { g.beginPath(); g.ellipse(32, 22, 11, 16, 0, 0, 7); g.fill(); g.beginPath(); g.ellipse(32, 50, 9, 9, 0, 0, 7); g.fill(); }
    const tex = new THREE.CanvasTexture(cv);
    const N = 46, geo = new THREE.PlaneGeometry(paw ? 0.16 : 0.2, paw ? 0.16 : 0.32).rotateX(-Math.PI / 2);
    const mat = new THREE.MeshStandardMaterial({ map: tex, transparent: true, depthWrite: false, roughness: 1, polygonOffset: true, polygonOffsetFactor: -4 });
    mat.userData.noAutoTex = true;
    const prints = new THREE.InstancedMesh(geo, mat, N); prints.frustumCulled = false; prints.count = 0; prints.renderOrder = 2; prints.name = 'designTracks';
    scene.add(prints);
    const M4 = new THREE.Matrix4(), Q = new THREE.Quaternion(), V = new THREE.Vector3(), SC = new THREE.Vector3();
    // the trail is laid once per target, wandering from where you stood to
    // what you seek; the grass along it is trodden (main.js.tpl reads
    // window.__trailSegs); the prints show only on the stretch ahead of you
    let trail = null, target = null, clock = 0, remaskMs = 0;
    const boxOf = (segs) => segs.reduce((b, g) => [Math.min(b[0], g[0], g[2]) - 1, Math.min(b[1], g[1], g[3]) - 1, Math.max(b[2], g[0], g[2]) + 1, Math.max(b[3], g[1], g[3]) + 1], [1e9, 1e9, -1e9, -1e9]);
    const layTrail = (p, t) => {
      const dx = t[0] - p[0], dz = t[1] - p[1], L = Math.hypot(dx, dz) || 1, ux = dx / L, uz = dz / L, wx = -uz, wz = ux, ph = r() * 6;
      trail = [];
      for (let s = 0; s <= L; s += 1.2) {
        const env = Math.min(1, s / 6, (L - s) / 6);                        // it starts and ends where it should
        const wob = (Math.sin(s * 0.17 + ph) * 2.2 + Math.sin(s * 0.47 + ph * 2) * 0.7) * env;
        trail.push([p[0] + ux * s + wx * wob, p[1] + uz * s + wz * wob]);
      }
      trail.push([t[0], t[1]]);
      const old = window.__trailSegs;
      window.__trailSegs = trail.slice(1).map((q, i) => [trail[i][0], trail[i][1], q[0], q[1]]);
      // only the strip the old trail and the new one cross is read again
      if (window.__grassRemask) { const b = boxOf(window.__trailSegs), b2 = old ? boxOf(old) : b;
        remaskMs = window.__grassRemask([Math.min(b[0], b2[0]), Math.min(b[1], b2[1]), Math.max(b[2], b2[2]), Math.max(b[3], b2[3])]); }
    };
    const layPrints = (p) => {
      let i0 = 0, bd = Infinity;
      for (let i = 0; i < trail.length; i++) { const d = Math.hypot(trail[i][0] - p[0], trail[i][1] - p[1]); if (d < bd) { bd = d; i0 = i; } }
      const step = paw ? 0.55 : 0.75;
      let k = 0, s = 0, i = i0, cx = trail[i][0], cz = trail[i][1];
      while (i < trail.length - 1 && k < N && s < 34) {
        const a = trail[i], b = trail[i + 1], sl = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, ux = (b[0] - a[0]) / sl, uz = (b[1] - a[1]) / sl;
        if (Math.hypot(cx - a[0], cz - a[1]) + step > sl) { i++; cx = trail[i][0]; cz = trail[i][1]; continue; }
        cx += ux * step; cz += uz * step; s += step;
        if (s < 2.0) continue;                                              // not under your own feet
        const side = (k % 2 ? 1 : -1) * (paw ? 0.08 : 0.13), x = cx - uz * side, z = cz + ux * side;
        const fade = 1 - Math.max(0, (s - 20) / 14);
        V.set(x, o.hAt(x, z) + 0.025, z); Q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.atan2(ux, uz) + (r() - 0.5) * 0.18);
        SC.setScalar(0.45 + 0.55 * fade); M4.compose(V, Q, SC); prints.setMatrixAt(k++, M4);
      }
      prints.count = k; prints.instanceMatrix.needsUpdate = true;
    };
    ticks.push((dt) => {
      if ((clock -= dt) > 0) return; clock = 0.4;
      const p = o.pos(), t = o.next();
      if (!t) { prints.count = 0; if (window.__trailSegs) { const g = window.__trailSegs; window.__trailSegs = null; if (window.__grassRemask) window.__grassRemask(boxOf(g)); }
        trail = null; target = null; return; }
      if (!target || !near(t, target, 0.5)) { target = t.slice(); layTrail([p[0], p[2]], target); }
      layPrints([p[0], p[2]]);
    });
    S.tracks = () => ({ prints: prints.count, trail: trail ? trail.length : 0, remaskMs: +remaskMs.toFixed(1) });
  }

  // ── FRESHNESS ────────────────────────────────────────────────────────────
  if (mech === 'freshness') {
    const noun = (words.match(/\b(bread|loaves|pies?|pizzas?|soup|cocoa|coffee|tea|meals?|buns|pastr(?:y|ies)|cakes?|cookies|medicine|flowers?|bouquets?|milk|eggs|cheese)\b/) || [, 'basket'])[1];
    const m = meter((/bread|loaves|buns|pastr|cakes?|pies?|cookies/.test(noun) ? 'warm from the oven' : /pizza|soup|meals?/.test(noun) ? 'still hot'
      : /cocoa|coffee|tea/.test(noun) ? 'steaming' : /flower|bouquet/.test(noun) ? 'fresh cut' : /milk|eggs|cheese/.test(noun) ? 'fresh from the farm' : 'on time'),
      /flower|bouquet/.test(noun) ? '✿' : '♨');
    const freshLine = /flower|bouquet/.test(noun) ? ['Fresh from the garden.', 'a new armful, still wet'] : /milk|eggs|cheese/.test(noun) ? ['Fresh from the dairy.', 'a full crate again']
      : ['Fresh out of the oven.', 'the basket is full and warm again'];
    // what a delivery is judged as, by what is carried
    const V3 = /flower|bouquet/.test(noun) ? ['Fresh as the morning.', 'A little tired.', 'Wilting.']
      : /cocoa|coffee|tea/.test(noun) ? ['Still steaming.', 'Barely warm.', 'Stone cold.']
      : /pizza|soup|meal/.test(noun) ? ['Still hot.', 'Cooling.', 'Cold.']
      : /milk|eggs|cheese/.test(noun) ? ['Fresh this morning.', 'Getting on.', 'Turned.']
      : /bread|loa|bun|pastr|pie|cake|cookie/.test(noun) ? ['Still warm.', 'A little cool.', 'Gone cold.']
      : ['Right on time.', 'A bit late.', 'Long overdue.'];
    let warm = 1, last = o.count(), home = o.home;
    const COOL = 1 / 95;                                     // cold in a minute and a half
    const verdicts = [];
    S.fresh = () => ({ warm: +warm.toFixed(2), verdicts });
    ticks.push((dt) => {
      const p = o.pos();
      if (near([p[0], p[2]], home, 6.5)) { if (warm < 0.98) { warm = 1; m.flash(); o.toast(freshLine[0], freshLine[1]); } }
      else warm = Math.max(0, warm - dt * COOL);
      m.set(warm);
      const c = o.count();
      if (c > last) {
        last = c;
        const v = warm > 0.66 ? V3[0] : warm > 0.33 ? V3[1] : V3[2];
        verdicts.push(+warm.toFixed(2)); o.toast(v, warm > 0.66 ? 'they will remember that' : 'back home for a fresh batch'); m.flash();
      }
    });
  }

  // ── LANTERN ──────────────────────────────────────────────────────────────
  if (mech === 'lantern') {
    const m = meter('lantern oil', '✹');
    let oil = 1;
    const light = new THREE.PointLight(0xffb866, 0, 16, 1.6); light.castShadow = false; scene.add(light);
    // (2026-11-04) one lamp-light, there from the start, on the nearest lit lamp: a new light at each
    // lamp changed the point-light count in every program's key and froze the game while the world recompiled
    const lampL = new THREE.PointLight(0xffb15c, 0, 14, 1.7); lampL.castShadow = false; scene.add(lampL);
    // lamps along the way, dark until you reach them
    const lamps = [], P = (o.LVL && o.LVL.path) || [];
    const iron = new THREE.MeshStandardMaterial({ color: 0x24221f, roughness: 0.55, metalness: 0.6 });
    const glassOff = new THREE.MeshStandardMaterial({ color: 0x2a2620, roughness: 0.3 });
    for (let i = 1; i < P.length - 1; i++) {
      const [a, b] = [P[i - 1], P[i]], x = (a[0] + b[0]) / 2 + 1.8, z = (a[1] + b[1]) / 2 + 1.2, y = o.hAt(x, z);
      if (o.blocked && o.blocked(x, z)) continue;   // (2026-10-25) never in a sinkhole's pool or through a built site
      const G = new THREE.Group(); G.position.set(x, y, z); scene.add(G);
      const post = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.07, 2.2, 8), iron); post.position.y = 1.1; G.add(post);
      const head = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.12, 0.32, 6), glassOff.clone()); head.position.y = 2.32; G.add(head);
      const cap = new THREE.Mesh(new THREE.ConeGeometry(0.2, 0.18, 6), iron); cap.position.y = 2.56; G.add(cap);
      for (const s of [post, head, cap]) { s.castShadow = true; s.material.userData.noAutoTex = true; }
      lamps.push({ x, z, head, lit: false, G });
    }
    S.lantern = () => ({ oil: +oil.toFixed(2), lit: lamps.filter(l => l.lit).length, lamps: lamps.length });
    ticks.push((dt, t) => {
      const p = o.pos();
      oil = Math.max(0, oil - dt / 150);
      for (const l of lamps) if (!l.lit && near([p[0], p[2]], [l.x, l.z], 2.6)) {
        l.lit = true; oil = 1; m.flash();
        l.head.material.color.setHex(0xffe0a8); l.head.material.emissive = new THREE.Color(0xffa040); l.head.material.emissiveIntensity = 2.4;
        o.toast(lamps.filter(q => q.lit).length === lamps.length ? 'Every lamp on the way is burning.' : 'The lamp takes. Your lantern is full.', '');
      }
      let nl = null, nd = Infinity; for (const l of lamps) if (l.lit) { const d = Math.hypot(p[0] - l.x, p[2] - l.z); if (d < nd) { nd = d; nl = l; } }
      if (nl) { lampL.position.set(nl.x, nl.G.position.y + 2.3, nl.z); lampL.intensity = 6 * (0.9 + 0.1 * Math.sin(t * 9 + nl.x)); }
      light.position.set(p[0] + 0.3, p[1] + 1.5, p[2] + 0.2);
      light.intensity = (o.night ? 5.5 : 2.2) * (0.15 + 0.85 * Math.sqrt(oil)) * (0.94 + 0.06 * Math.sin(t * 11));
      m.set(oil);
    });
  }

  // ── GUSTS ────────────────────────────────────────────────────────────────
  if (mech === 'gusts') {
    const ang = r() * Math.PI * 2, wx = Math.cos(ang), wz = Math.sin(ang);
    let next = 28 + r() * 14, gust = 0, told = false;              // the wind picks up once you are out in it
    S.gusts = () => ({ gust: +gust.toFixed(2) });
    ticks.push((dt) => {
      next -= dt;
      if (next <= 0 && gust <= 0) { gust = 1.8; next = 9 + r() * 9; if (!told) { told = true; o.toast('Lean into it.', 'the gusts come off the water'); } }
      if (gust > 0) gust = Math.max(0, gust - dt);
      window.__gustK = gust > 0 ? Math.sin(Math.min(1, (1.8 - gust) / 0.4) * Math.PI / 2) * Math.min(1, gust / 0.6) : 0;   // the grass can read it
    });
    pushFn = (dt) => { const k = window.__gustK || 0; return k > 0 ? [wx * 2.6 * k * dt, wz * 2.6 * k * dt] : null; };
  }

  // ── COLD ─────────────────────────────────────────────────────────────────
  if (mech === 'cold') {
    const m = meter('warmth', '❄');
    const frost = document.createElement('div'); frost.className = 'fs-frost'; document.body.appendChild(frost);
    let warmth = 1;
    const fires = () => [o.home].concat(window.__places ? window.__places.filter(q => q.kind === 'cottage').map(q => q.at) : [])
      .concat(o.LVL && o.LVL.goal ? [o.LVL.goal] : []);
    S.cold = () => ({ warmth: +warmth.toFixed(2) });
    ticks.push((dt) => {
      const p = o.pos(), byFire = fires().some(f => f && near([p[0], p[2]], f, 7));
      // the higher you climb the harder the cold bites: at twelve metres up, twice as fast
      warmth = byFire ? Math.min(1, warmth + dt / 6) : Math.max(0, warmth - dt / 140 * (1 + Math.max(0, p[1]) / 12));
      m.set(warmth); frost.style.opacity = String(Math.max(0, (0.45 - warmth) / 0.45));
    });
    speedFn = () => 0.62 + 0.38 * Math.min(1, warmth / 0.3);
  }

  // ── BREATH (2026-11-04) ──────────────────────────────────────────────────
  // A climb takes it out of you: every metre gained and every stride run
  // costs breath, and spent you can only trudge. Stone cairns stand at the
  // turns of the way up; stop by one and it comes back. The climb becomes a
  // rhythm, cairn to cairn, and running the whole slope is a choice.
  if (mech === 'breath') {
    const m = meter('breath', '≋');
    let breath = 1, lastY = null, told = 0;
    const cairns = [], P = (o.LVL && o.LVL.path) || [];
    // a cairn every ~22 m of the way, at the turn nearest that mark, the first well clear of home
    let acc = 0, want = 26;
    for (let i = 1; i < P.length - 1; i++) {
      acc += Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]);
      if (acc < want) continue;
      acc = 0; want = 22;
      const a = P[i - 1], b = P[i], L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
      const x = b[0] - (b[1] - a[1]) / L * 2.2, z = b[1] + (b[0] - a[0]) / L * 2.2;   // beside the way, not on it
      if (o.blocked && o.blocked(x, z)) continue;
      cairns.push({ x, z, y: o.hAt(x, z) });
    }
    if (cairns.length) {
      // one mesh for every stone of every cairn: flattened rounded stones stacked smaller upward
      const stone = new THREE.DodecahedronGeometry(1, 1), pa = stone.attributes.position;
      for (let i = 0; i < pa.count; i++) { const n = 0.86 + 0.14 * Math.sin(pa.getX(i) * 7.1 + pa.getZ(i) * 5.3); pa.setXYZ(i, pa.getX(i) * n, pa.getY(i) * n, pa.getZ(i) * n); }
      stone.computeVertexNormals();
      const sm = new THREE.MeshStandardMaterial({ color: 0x8b8578, roughness: 0.93 });
      const per = 6, im = new THREE.InstancedMesh(stone, sm, cairns.length * per); im.name = 'designCairns';
      im.castShadow = im.receiveShadow = true;
      const M4 = new THREE.Matrix4(), Q = new THREE.Quaternion(), V = new THREE.Vector3(), SC = new THREE.Vector3(), C = new THREE.Color();
      let k = 0;
      for (const c of cairns) {
        let y = c.y - 0.05;
        for (let j = 0; j < per; j++) {
          const w = 0.42 * (1 - j * 0.13) * (0.9 + r() * 0.2), h = w * (0.42 + r() * 0.12);
          y += h * (j ? 0.95 : 0.6);
          V.set(c.x + (r() - 0.5) * 0.06 * j, y, c.z + (r() - 0.5) * 0.06 * j);
          Q.setFromEuler(new THREE.Euler((r() - 0.5) * 0.16, r() * 6.28, (r() - 0.5) * 0.16));
          SC.set(w, h, w * (0.85 + r() * 0.2)); M4.compose(V, Q, SC); im.setMatrixAt(k, M4);
          C.setHSL(0.09 + r() * 0.04, 0.06 + r() * 0.06, 0.36 + r() * 0.16); im.setColorAt(k, C);
          k++; y += h * 0.95;
        }
        c.top = y;
      }
      scene.add(im);
    }
    S.breath = () => ({ breath: +breath.toFixed(2), cairns: cairns.length });
    ticks.push((dt) => {
      const p = o.pos(), climb = lastY === null ? 0 : Math.max(0, p[1] - lastY) / Math.max(dt, 1e-3);
      lastY = p[1];
      const atCairn = cairns.some(c => near([p[0], p[2]], [c.x, c.z], 2.8)) || near([p[0], p[2]], o.home, 5);
      const run = (window.__pSpeed || 0) > 4.2;
      if (atCairn && (window.__pSpeed || 0) < 2.5) {
        if (breath < 0.97 && breath + dt / 2.2 >= 0.97 && told < 2 && cairns.length) { told++; o.toast('Breath back.', 'on to the next cairn'); m.flash(); }
        breath = Math.min(1, breath + dt / 2.2);
      } else breath = Math.max(0, breath - dt * (0.004 + Math.min(climb, 3) * 0.022 + (run ? 0.018 : 0)));
      if (breath <= 0.02 && told === 0) { told = 1; o.toast('Winded.', 'rest by a cairn to catch your breath'); }
      m.set(breath);
    });
    // spent, a trudge; the last of it makes your stride heavy before then
    speedFn = () => 0.5 + 0.5 * Math.min(1, breath / 0.25);
  }

  // ── LOAD (2026-11-04) ────────────────────────────────────────────────────
  // What you gather is carried: each one makes the basket heavier and your
  // step slower, and home empties it. Going back is a choice the map asks of
  // you (one more on the way, or lighten the load first).
  if (mech === 'load') {
    const noun = (words.match(/\b(seeds?|eggs?|fossils?|crystals?|mushrooms?|shells?|berries|apples?|flowers?|herbs?|stones?|logs?|firewood|wood|honey|fish|crabs?|fruit|pumpkins?|potatoes|carrots|wool)\b/) || [, 'things'])[1];
    const heavy = /fossil|crystal|stone|log|wood|pumpkin|potato|fish/.test(noun) ? 0.13 : /egg|apple|shell|honey|fruit|carrot|crab/.test(noun) ? 0.09 : 0.06;
    const m = meter('basket', '◒');
    let load = 0, last = o.count(), emptied = 0;
    S.load = () => ({ load, emptied, heavy });
    ticks.push(() => {
      const c = o.count(), p = o.pos();
      if (c > last) {
        load += c - last; last = c; m.flash();
        if (load === 2) o.toast('The basket is getting heavy.', 'home will empty it');
      }
      if (load && near([p[0], p[2]], o.home, 6)) { emptied += load; load = 0; m.flash(); o.toast('Basket emptied.', 'light on your feet again'); }
      m.set(Math.min(1, load * heavy / 0.45));
    });
    speedFn = () => Math.max(0.55, 1 - load * heavy);
  }

  // ── RESONANCE (2026-11-04) ───────────────────────────────────────────────
  // There is no marker: what you are looking for hums, a soft pulse that
  // quickens and rises the nearer you are to it. Warmer, colder, found.
  if (mech === 'resonance') {
    const el = document.createElement('div'); el.className = 'fs-reson';
    el.innerHTML = '<i></i><i></i><span></span>';
    const st = document.createElement('style');
    st.textContent = `.fs-reson{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);width:120px;height:46px;pointer-events:none;z-index:25;
      font:600 11px var(--f-ui,system-ui);letter-spacing:.16em;text-transform:uppercase;color:var(--art-ink,#eee);text-shadow:0 1px 6px rgba(0,0,0,.7)}
      .fs-reson i{position:absolute;left:50%;top:13px;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;border:2px solid var(--art-acc,#ffd479);opacity:0}
      .fs-reson i:first-child{opacity:.9;transform:scale(.45);background:var(--art-acc,#ffd479)}
      .fs-reson.p i:nth-child(2){animation:fsrp .9s ease-out}
      .fs-reson span{position:absolute;left:0;right:0;bottom:0;text-align:center}
      @keyframes fsrp{0%{opacity:.95;transform:scale(.5)}100%{opacity:0;transform:scale(2.6)}}`;
    document.head.appendChild(st); document.body.appendChild(el);
    const ring = el.children[1], word = el.children[2];
    let wait = 1.2, d0 = null, told = false;
    S.resonance = () => ({ d: d0 === null ? null : +d0.toFixed(1) });
    ticks.push((dt) => {
      const p = o.pos(), t = o.next();
      if (!t) { el.style.opacity = '0'; return; }
      el.style.opacity = '1';
      const d = Math.hypot(t[0] - p[0], t[1] - p[2]); d0 = d;
      const k = Math.max(0, Math.min(1, 1 - (d - 3) / 70));                 // 0 far .. 1 at hand
      word.textContent = k > 0.86 ? 'here' : k > 0.62 ? 'warm' : k > 0.35 ? 'cooler' : 'cold';
      if ((wait -= dt) > 0) return;
      wait = 2.6 - 2.25 * k * k;
      el.classList.remove('p'); void el.offsetWidth; el.classList.add('p');
      ring.style.animationDuration = (Math.min(0.9, wait * 0.9)).toFixed(2) + 's';
      if (o.chime) o.chime(330 * Math.pow(2, k * 1.25), 0.025 + 0.045 * k);
      if (!told && k > 0.62) { told = true; o.toast('Warmer.', 'the hum quickens as you near it'); }
    });
  }

  // ── WATCH (2026-11-04) ───────────────────────────────────────────────────
  // An escape had nothing to escape: you walked out. Now the way out is
  // watched. Lights sweep across it (searchlights on masts at a base or a
  // yard, watchmen's lanterns at a castle, cold wisps on a moor or in old
  // ruins); stand in one too long and you are seen, and sent back to the
  // last light you slipped past. Timing, not speed.
  if (mech === 'watch') {
    const P = (o.LVL && o.LVL.path) || [];
    const indoor = !!(o.LVL && o.LVL.interior);
    const kind = indoor ? 'drone' : /\b(castle|keep|fort\w*|citadel|manor|palace|village|monastery|abbey)\b/.test(words) ? 'lantern'
      : /\b(moor\w*|marsh\w*|swamp\w*|bog|temple|ruin\w*|tomb\w*|crypt\w*|forest|woods?|jungle|sunken|haunted|grave\w*)\b/.test(words) ? 'wisp' : 'search';
    const col = kind === 'lantern' ? 0xffb35a : kind === 'wisp' ? 0x8fe8d0 : 0xe8f2ff;
    const L = [], R = 3.0;
    if (P.length > 2) {
      let tot = 0; const cum = [0]; for (let i = 1; i < P.length; i++) cum.push(tot += Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]));
      const n = Math.max(2, Math.min(5, Math.round(tot / 26)));
      const at = (s) => { let i = 1; while (i < P.length - 1 && cum[i] < s) i++; const a = P[i - 1], b = P[i], f = (s - cum[i - 1]) / Math.max(1e-3, cum[i] - cum[i - 1]);
        const l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1; return { x: a[0] + (b[0] - a[0]) * f, z: a[1] + (b[1] - a[1]) * f, ux: (b[0] - a[0]) / l, uz: (b[1] - a[1]) / l, s }; };
      // a soft round pool of light, brightest in the middle
      const cv = document.createElement('canvas'); cv.width = cv.height = 128; const g = cv.getContext('2d');
      const gr = g.createRadialGradient(64, 64, 4, 64, 64, 63); gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.55, 'rgba(255,255,255,.55)'); gr.addColorStop(0.85, 'rgba(255,255,255,.18)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
      const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
      const poolMat = new THREE.MeshBasicMaterial({ map: tex, color: col, transparent: true, opacity: o.night ? 0.85 : 0.6, blending: THREE.AdditiveBlending, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -6 });
      const bc = document.createElement('canvas'); bc.width = 4; bc.height = 64; { const bg = bc.getContext('2d'), gb = bg.createLinearGradient(0, 0, 0, 64); gb.addColorStop(0, '#fff'); gb.addColorStop(0.7, '#555'); gb.addColorStop(1, '#111'); bg.fillStyle = gb; bg.fillRect(0, 0, 4, 64); }
      const beamMat = new THREE.MeshBasicMaterial({ color: col, alphaMap: new THREE.CanvasTexture(bc), transparent: true, opacity: o.night ? 0.05 : 0.025, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
      const iron = new THREE.MeshStandardMaterial({ color: kind === 'lantern' ? 0x3a2c20 : 0x3b4046, roughness: 0.6, metalness: kind === 'search' ? 0.7 : 0.2 });
      const glow = new THREE.MeshBasicMaterial({ color: col });
      for (const m of [poolMat, beamMat, iron, glow]) m.userData.noAutoTex = true;

      for (let k = 0; k < n; k++) {
        const c = at(tot * (0.22 + 0.62 * (n === 1 ? 0.5 : k / (n - 1))));
        const px = -c.uz, pz = c.ux, side = (k % 2 ? 1 : -1);
        const G = new THREE.Group(); scene.add(G);
        const pool = new THREE.Mesh(new THREE.CircleGeometry(R, 40).rotateX(-Math.PI / 2), poolMat); pool.renderOrder = 3; G.add(pool);
        const w = { c, px, pz, pool, sweep: indoor ? 1.8 + r() * 0.8 : 5.5 + r() * 1.5, per: indoor ? 5 + r() * 2 : 9 + r() * 4, ph: r() * 6.28, mast: null, head: null };
        if (kind === 'search') {
          const mx = c.x + px * side * 8.5, mz = c.z + pz * side * 8.5, my = o.hAt(mx, mz), H = 7.5;
          if (!(o.blocked && o.blocked(mx, mz))) {
            const mast = new THREE.Group(); mast.position.set(mx, my, mz); G.add(mast);
            const post = new THREE.Mesh(kind === 'search' ? new THREE.CylinderGeometry(0.12, 0.18, H, 8) : new THREE.CylinderGeometry(0.09, 0.12, H, 6), iron); post.position.y = H / 2; mast.add(post);
            if (kind === 'search') { for (const q of [-1, 1]) { const st2 = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, H * 0.6, 5), iron); st2.position.set(q * 0.55, H * 0.28, 0); st2.rotation.z = q * 0.2; mast.add(st2); }
              const plat = new THREE.Mesh(new THREE.CylinderGeometry(0.75, 0.75, 0.1, 10), iron); plat.position.y = H; mast.add(plat); }
            const head = new THREE.Mesh(kind === 'search' ? new THREE.CylinderGeometry(0.34, 0.26, 0.6, 12) : new THREE.CylinderGeometry(0.18, 0.13, 0.36, 6), iron); head.position.y = H + 0.42; mast.add(head);
            // the searchlight's glass is its +Y end (the head is aimed with lookAt + a quarter turn); a lantern glows all round
            const lens = kind === 'search' ? new THREE.Mesh(new THREE.CircleGeometry(0.3, 16), glow) : new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.11, 0.26, 6), glow);
            if (kind === 'search') { lens.position.y = 0.31; lens.rotation.x = -Math.PI / 2; }
            head.add(lens);
            for (const s of [post, head]) s.castShadow = true;
            w.mast = mast; w.top = new THREE.Vector3(mx, my + H + 0.42, mz); w.head = head;
          }
        } else {
          const orb = new THREE.Mesh(new THREE.SphereGeometry(0.22, 14, 10), glow); G.add(orb); w.orb = orb;
          const halo = new THREE.Mesh(new THREE.SphereGeometry(0.55, 14, 10), beamMat); orb.add(halo);
        }
        if (w.top) { const beam = new THREE.Mesh(new THREE.ConeGeometry(R * 0.82, 1, 24, 1, true), beamMat); beam.renderOrder = 3; G.add(beam); w.beam = beam; }
        L.push(w);
      }
    }
    let seen = 0, grace = 0, passed = -1, caught = 0, told = false;
    const eye = meter(kind === 'wisp' ? 'noticed' : 'seen', '◉'); eye.el.style.opacity = '0';
    const UP = new THREE.Vector3(0, 1, 0), D = new THREE.Vector3(), Q = new THREE.Quaternion();
    S.watch = () => ({ kind, lights: L.length, seen: +seen.toFixed(2), passed, caught });
    ticks.push((dt, t) => {
      const p = o.pos();
      let inside = false;
      for (let i = 0; i < L.length; i++) {
        const w = L[i], sw = Math.sin(t * 6.283 / w.per + w.ph) * w.sweep;
        const x = w.c.x + w.px * sw, z = w.c.z + w.pz * sw, y = o.hAt(x, z);
        w.pool.position.set(x, y + 0.06, z); w.x = x; w.z = z;
        if (w.orb) w.orb.position.set(x, y + 1.6 + Math.sin(t * 2 + i) * 0.25, z);
        if (w.beam) {   // a cone from the lamp to the pool
          D.set(x - w.top.x, y - w.top.y, z - w.top.z); const len = D.length();
          w.beam.scale.set(1, len, 1); Q.setFromUnitVectors(UP, D.clone().normalize().negate()); w.beam.quaternion.copy(Q);
          w.beam.position.set((x + w.top.x) / 2, (y + w.top.y) / 2, (z + w.top.z) / 2);
          if (w.head && kind === 'search') { w.head.lookAt(x, y, z); w.head.rotateX(Math.PI / 2); }
        }
        if (Math.hypot(p[0] - x, p[2] - z) < R * 0.8 && Math.abs(p[1] - y) < 3) inside = true;
        // past a light along the way: it becomes where you are sent back to
        const ahead = (p[0] - w.c.x) * w.c.ux + (p[2] - w.c.z) * w.c.uz;
        if (ahead > 4 && i > passed && Math.hypot(p[0] - w.c.x, p[2] - w.c.z) < 16) passed = i;
      }
      if (grace > 0) { grace -= dt; inside = false; }
      seen = inside ? Math.min(1, seen + dt / 0.85) : Math.max(0, seen - dt / 1.6);
      eye.el.style.opacity = seen > 0.02 ? '1' : '0'; eye.set(seen);
      if (inside && !told) { told = true; o.toast(kind === 'wisp' ? 'Keep out of the lights.' : 'Stay out of the light.', 'wait for it to sweep past'); }
      if (seen >= 1) {
        caught++; seen = 0; grace = 2.2;
        const back = passed >= 0 ? L[passed].c : null;
        const bx = back ? back.x + back.ux * 4.5 : o.home[0], bz = back ? back.z + back.uz * 4.5 : o.home[1];
        if (o.tp) o.tp(bx, bz);
        o.toast(kind === 'wisp' ? 'They found you.' : 'Spotted.', passed >= 0 ? 'back past the last light' : 'back to the start');
      }
    });
  }

  // ── TROUBLE (2026-11-04) ─────────────────────────────────────────────────
  // A patrol is a round where something happens. Now and then smoke goes up
  // somewhere along the way (a fire left burning in the woods, a flare on a
  // marsh or a shore, a lamp-signal in a town) and there is a minute to get
  // there and see to it. Missing one costs nothing but the tally; the round
  // has a rhythm of quiet and hurry.
  if (mech === 'trouble') {
    const P = (o.LVL && o.LVL.path) || [];
    const town = /\b(city|town|street\w*|harbou?r|docks?|port|neon|market|village)\b/.test(words);
    const wet = /\b(marsh\w*|swamp\w*|bog|lake|shore|coast|beach|wetland\w*|estuar\w*|river)\b/.test(words);
    const what = town ? ['A signal lamp is flashing.', 'someone needs you'] : wet ? ['A flare goes up.', 'someone is in trouble out there'] : ['Smoke over the trees.', 'a fire left burning'];
    const cv = document.createElement('canvas'); cv.width = cv.height = 64; const g = cv.getContext('2d');
    const gr = g.createRadialGradient(32, 32, 2, 32, 32, 31); gr.addColorStop(0, 'rgba(255,255,255,.9)'); gr.addColorStop(0.6, 'rgba(255,255,255,.35)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
    const puffT = new THREE.CanvasTexture(cv);
    const G = new THREE.Group(); G.visible = false; G.name = 'designTrouble'; scene.add(G);
    const puffs = [];
    for (let i = 0; i < 14; i++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: puffT, color: town ? 0xffd27a : wet ? 0xff6a4a : 0x8a8580, transparent: true, depthWrite: false, opacity: 0 }));
      sp.material.userData.noAutoTex = true; G.add(sp); puffs.push({ sp, t: i / 14 });
    }
    const ember = new THREE.Mesh(new THREE.SphereGeometry(0.35, 12, 8), new THREE.MeshBasicMaterial({ color: town ? 0xffe9a0 : wet ? 0xff5a3a : 0xff8a3a }));
    ember.material.userData.noAutoTex = true; G.add(ember);
    const m = meter('get there', '!'); m.el.style.opacity = '0';
    let wait = 24 + r() * 10, live = null, seen = 0, missed = 0;
    const ahead = (p) => {   // a point on the way 35-70 m on from the nearest point to you
      if (P.length < 2) return null;
      let bi = 0, bd = 1e9; for (let i = 0; i < P.length; i++) { const d = Math.hypot(P[i][0] - p[0], P[i][1] - p[2]); if (d < bd) { bd = d; bi = i; } }
      let s = 0, want = 35 + r() * 35, i = bi;
      for (let k = 0; k < P.length * 2; k++) { const j = (i + 1) % P.length; const l = Math.hypot(P[j][0] - P[i][0], P[j][1] - P[i][1]);
        if (s + l >= want) { const f = (want - s) / (l || 1); return [P[i][0] + (P[j][0] - P[i][0]) * f + (r() - 0.5) * 8, P[i][1] + (P[j][1] - P[i][1]) * f + (r() - 0.5) * 8]; }
        s += l; i = j; }
      return null;
    };
    S.trouble = () => ({ live: live ? { at: live.at.map(v => +v.toFixed(1)), left: +live.left.toFixed(1) } : null, seen, missed });
    ticks.push((dt, t) => {
      const p = o.pos();
      if (!live) {
        if ((wait -= dt) > 0) return;
        const at = ahead(p);
        if (!at || (o.blocked && o.blocked(at[0], at[1]))) { wait = 5; return; }
        const d = Math.hypot(at[0] - p[0], at[1] - p[2]);
        live = { at, left: Math.max(35, d / 3.2 + 18), full: 0 }; live.full = live.left;
        G.position.set(at[0], o.hAt(at[0], at[1]), at[1]); G.visible = true; m.el.style.opacity = '1';
        o.toast(what[0], what[1]); return;
      }
      live.left -= dt; m.set(live.left / live.full);
      for (const q of puffs) { q.t = (q.t + dt / (town ? 2.2 : 6)) % 1;
        const k = q.t; q.sp.position.set(Math.sin(k * 5 + q.t * 40) * 0.4 * k + k * 1.6, 0.6 + k * (town ? 3 : 11), Math.cos(k * 4) * 0.3 * k);
        q.sp.scale.setScalar(town ? 0.6 + k * 0.6 : 0.8 + k * 4.5); q.sp.material.opacity = (town ? 0.9 * (1 - k) * (Math.sin(t * 8) > 0 ? 1 : 0.2) : 0.5 * Math.min(1, k * 6) * (1 - k)); }
      ember.scale.setScalar(0.8 + 0.3 * Math.sin(t * 13));   // (no light of its own: the point-light count is in every program's key, a new one mid-game recompiles the world)
      if (Math.hypot(live.at[0] - p[0], live.at[1] - p[2]) < 3.6) {
        seen++; o.toast(town ? 'Seen to.' : wet ? 'Help arrives.' : 'Fire out.', seen === 1 ? 'one less thing on the round' : seen + ' seen to this round'); m.flash();
        live = null; G.visible = false; m.el.style.opacity = '0'; wait = 35 + r() * 20;
      } else if (live.left <= 0) {
        missed++; o.toast('Too late for that one.', 'keep to your round'); live = null; G.visible = false; m.el.style.opacity = '0'; wait = 30 + r() * 20;
      }
    });
  }

  // ── THE MOMENT ───────────────────────────────────────────────────────────
  if (moment !== 'none') {
    let at = null;
    const fog = scene.fog, f0 = fog ? { near: fog.near, far: fog.far, d: fog.density, c: fog.color.clone() } : null;
    const sun0 = o.sun ? o.sun.intensity : 0, hemi0 = o.hemi ? o.hemi.intensity : 0, exp0 = o.renderer.toneMappingExposure;
    let rain = null;
    const lines = {
      storm: [['The weather breaks.', 'rain sweeps in across the ground'], ['Here it comes.', 'the sky has turned']],
      nightfall: [['The light is going.', 'the day will not wait'], ['Dusk comes on fast.', 'what is left must be done by lamplight']],
      fog: [['The fog rolls in.', 'keep to what you know'], ['A bank of mist.', 'the far side of the world is gone']],
    }[moment];
    const say = lines[Math.floor(r() * lines.length)];
    S.moment = () => ({ kind: moment, at, k: at === null ? 0 : Math.min(1, (performance.now() / 1000 - at) / 24) });
    ticks.push((dt, t) => {
      if (at === null) { if (o.progress() >= 0.48) { at = t; o.toast(say[0], say[1]); } else return; }
      const k = Math.min(1, (t - at) / 24), e = k * k * (3 - 2 * k);
      if (moment === 'storm' || moment === 'fog') {
        if (fog && f0) {
          if (fog.isFogExp2) fog.density = f0.d * (1 + (moment === 'fog' ? 2.2 : 1.1) * e);
          else { fog.far = f0.far * (1 - (moment === 'fog' ? 0.62 : 0.4) * e); fog.near = f0.near * (1 - 0.6 * e); }
          fog.color.copy(f0.c).lerp(new THREE.Color(moment === 'fog' ? 0xc9cfd2 : 0x4a525a), 0.5 * e);
        }
        if (o.sun) o.sun.intensity = sun0 * (1 - (moment === 'storm' ? 0.55 : 0.3) * e);
        if (moment === 'storm') {
          if (!rain) {
            const N = 1800, pos = new Float32Array(N * 3); for (let i = 0; i < N; i++) { pos[i * 3] = (r() - 0.5) * 44; pos[i * 3 + 1] = r() * 24; pos[i * 3 + 2] = (r() - 0.5) * 44; }
            const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
            rain = new THREE.Points(g, new THREE.PointsMaterial({ color: 0xa8bccf, size: 0.09, transparent: true, opacity: 0, depthWrite: false }));
            rain.frustumCulled = false; scene.add(rain);
          }
          rain.material.opacity = 0.55 * e;
          const p = o.pos(), pa = rain.geometry.attributes.position;
          for (let i = 0; i < pa.count; i++) { let y = pa.getY(i) - dt * 19; if (y < 0) y += 24; pa.setY(i, y); }
          pa.needsUpdate = true; rain.position.set(p[0], p[1] - 2, p[2]);
        }
      } else if (moment === 'nightfall') {
        o.renderer.toneMappingExposure = exp0 * (1 - 0.5 * e);
        if (o.sun) o.sun.intensity = sun0 * (1 - 0.85 * e);
        if (o.hemi) o.hemi.intensity = hemi0 * (1 - 0.55 * e);
        if (fog && f0) fog.color.copy(f0.c).lerp(new THREE.Color(0x141a26), 0.75 * e);
      }
    });
  }

  return {
    tick(dt, t) { for (const f of ticks) f(dt, t); },
    push: (dt) => (pushFn ? pushFn(dt) : null),
    speed: () => speedFn(),
    state: () => Object.fromEntries(Object.entries(S).map(([k, v]) => [k, typeof v === 'function' ? v() : v])),
  };
}
