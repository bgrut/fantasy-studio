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
        const L = new THREE.PointLight(0xffb15c, 6, 14, 1.7); L.position.y = 2.3; l.G.add(L); l.L = L;
        o.toast(lamps.filter(q => q.lit).length === lamps.length ? 'Every lamp on the way is burning.' : 'The lamp takes. Your lantern is full.', '');
      }
      for (const l of lamps) if (l.L) l.L.intensity = 6 * (0.9 + 0.1 * Math.sin(t * 9 + l.x));
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
