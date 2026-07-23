// Fantasy Studio game runtime (Phase 26). Deterministic template — the
// exporter injects __GAME_SPEC__ and never edits logic. three.js r170 (MIT) +
// Rapier 0.14 (Apache-2.0), all vendored locally: works fully offline.
import * as THREE from 'three';
import { GLTFLoader } from './vendor/jsm/loaders/GLTFLoader.js';
import { clone as skClone } from './vendor/jsm/utils/SkeletonUtils.js';
import { mergeGeometries } from './vendor/jsm/utils/BufferGeometryUtils.js';
import { Sky } from './vendor/jsm/objects/Sky.js';
import { EffectComposer } from './vendor/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from './vendor/jsm/postprocessing/RenderPass.js';
import { ShaderPass } from './vendor/jsm/postprocessing/ShaderPass.js';
import { UnrealBloomPass } from './vendor/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from './vendor/jsm/postprocessing/OutputPass.js';
import RAPIER from './vendor/rapier.es.js';

const SPEC = __GAME_SPEC__;

const errBox = document.getElementById('err');
function fail(msg) {
  errBox.style.display = 'block';
  errBox.textContent += msg + '\n';
  console.error('[game] ' + msg);
}
window.addEventListener('error', e => fail('uncaught: ' + e.message));

// seeded RNG so scatter placement is reproducible (spec.seed)
function mulberry32(a) {
  return function () {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

// exp = per-environment tone-mapping exposure (Phase 65): bright grounds
// (snow, sand) under the old flat 0.75 read as a washed-out white void.
const SKY = {
  day:      { sky: 0x87b5e0, fog: 0xa8c4dd, sun: 3.2, amb: 0.55, sunPos: [40, 80, 30], exp: 0.66 },
  sunset:   { sky: 0xe8996a, fog: 0xd9a07a, sun: 2.2, amb: 0.40, sunPos: [80, 25, 10], exp: 0.72 },
  // night done RIGHT (pass 2): full moonlit-blue treatment — strong cool sun,
  // generous ambient, fog clearly brighter than the sky. Unmistakably night,
  // but every shape reads on a laptop screen at recording brightness.
  night:    { sky: 0x121c30, fog: 0x263a5e, sun: 0.95, amb: 0.5,
              sunCol: 0xa8c2ff, sunPos: [30, 60, -40], exp: 0.8 },
  overcast: { sky: 0x9aa4ad, fog: 0x9aa4ad, sun: 1.2, amb: 0.65, sunPos: [20, 90, 20], exp: 0.62 },
  // alien worlds: mars = butterscotch haze over rust; space = airless black,
  // hard sun; dusk = deep violet-blue with a low warm sun
  mars:     { sky: 0xd99a66, fog: 0xc98a5a, sun: 2.6, amb: 0.45, sunPos: [60, 55, 20], exp: 0.7 },
  space:    { sky: 0x05070d, fog: 0x0a0f1c, sun: 3.8, amb: 0.20, sunPos: [50, 70, -30], exp: 0.8 },
  dusk:     { sky: 0x3b3a5e, fog: 0x4a4a72, sun: 1.2, amb: 0.42,
              sunCol: 0xffd9b0, sunPos: [70, 18, 15], exp: 0.75 },
};

async function main() {
  await RAPIER.init();
  const pal = SKY[SPEC.world.sky] || SKY.day;

  // ── SOUND (game-feel pass) — synthesized in WebAudio: zero asset files,
  // zero network, works in every export. Each player action gets an answer:
  // pickup chime, attack whoosh, hit thud, hurt sting, countdown beeps,
  // win fanfare, lose fall. First activated by the START click (a user
  // gesture, so autoplay policy is satisfied by design).
  let actx = null;
  let sfxMuted = false;
  // ── AMBIENT BED (Phase 69): looping filtered-noise wind + night crickets,
  // fully procedural (zero asset files). Started once by the same START-click
  // gesture that unlocks sfx; volume follows weather/wind and the sky preset.
  let ambientOn = false;
  function startAmbient() {
    if (ambientOn || sfxMuted || !actx) return;
    ambientOn = true;
    try {
      const sky = SPEC.world.sky || 'day';
      // wind: 4s of white noise -> looped buffer -> lowpass -> slow gain LFO
      const n = actx.sampleRate * 4;
      const buf = actx.createBuffer(1, n, actx.sampleRate);
      const ch = buf.getChannelData(0);
      let last = 0;
      for (let i = 0; i < n; i++) {   // brown-ish noise reads as wind, not hiss
        last = (last + (Math.random() * 2 - 1) * 0.04) * 0.985;
        ch[i] = last * 6;
      }
      const src = actx.createBufferSource();
      src.buffer = buf; src.loop = true;
      const lp = actx.createBiquadFilter();
      lp.type = 'lowpass';
      lp.frequency.value = SPEC.world.weather === 'snow' ? 320 : 480;
      const g = actx.createGain();
      const wind = Math.max(0.15, Math.min(SPEC.world.wind ?? 0.5, 1));
      g.gain.value = 0.05 + wind * 0.075;
      const lfo = actx.createOscillator(), lg = actx.createGain();
      lfo.frequency.value = 0.09; lg.gain.value = g.gain.value * 0.45;
      lfo.connect(lg); lg.connect(g.gain); lfo.start();
      src.connect(lp); lp.connect(g); g.connect(actx.destination);
      src.start();
      // night crickets: sparse randomized chirps (skip horror = dead silence sells it)
      if ((sky === 'night' || sky === 'dusk') && SPEC.style !== 'horror') {
        const chirp = () => {
          if (!ambientOn || sfxMuted) return;
          try {
            const t0 = actx.currentTime;
            for (let k = 0; k < 3; k++) {
              const o = actx.createOscillator(), cg = actx.createGain();
              o.type = 'sine'; o.frequency.value = 4200 + Math.random() * 500;
              cg.gain.setValueAtTime(0, t0 + k * 0.07);
              cg.gain.linearRampToValueAtTime(0.012, t0 + k * 0.07 + 0.015);
              cg.gain.linearRampToValueAtTime(0, t0 + k * 0.07 + 0.05);
              o.connect(cg); cg.connect(actx.destination);
              o.start(t0 + k * 0.07); o.stop(t0 + k * 0.07 + 0.06);
            }
          } catch (e) {}
          setTimeout(chirp, 1400 + Math.random() * 3200);
        };
        setTimeout(chirp, 1200);
      }
    } catch (e) { /* ambience is garnish — never break the game over it */ }
  }
  function sfx(kind) {
    try {
      if (sfxMuted) return;
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      if (!actx) actx = new AC();
      if (actx.state === 'suspended') actx.resume();
      const t0 = actx.currentTime;
      const tone = (type, f0, f1, dur, vol, at) => {
        const o = actx.createOscillator(), g = actx.createGain();
        o.type = type;
        o.frequency.setValueAtTime(f0, t0 + at);
        if (f1 !== f0) o.frequency.exponentialRampToValueAtTime(Math.max(f1, 1), t0 + at + dur);
        g.gain.setValueAtTime(vol, t0 + at);
        g.gain.exponentialRampToValueAtTime(0.0008, t0 + at + dur);
        o.connect(g); g.connect(actx.destination);
        o.start(t0 + at); o.stop(t0 + at + dur + 0.02);
      };
      if (kind === 'pickup')  { tone('sine', 880, 880, 0.09, 0.16, 0); tone('sine', 1318.5, 1318.5, 0.22, 0.14, 0.07); }
      else if (kind === 'attack') { tone('sawtooth', 320, 70, 0.16, 0.10, 0); }
      else if (kind === 'hit')  { tone('square', 150, 55, 0.13, 0.16, 0); }
      else if (kind === 'hurt') { tone('sawtooth', 220, 90, 0.22, 0.15, 0); tone('sine', 110, 60, 0.25, 0.12, 0); }
      else if (kind === 'beep') { tone('sine', 660, 660, 0.12, 0.14, 0); }
      else if (kind === 'go')   { tone('sine', 990, 990, 0.30, 0.16, 0); }
      else if (kind === 'step') { tone('sine', 523.25, 523.25, 0.1, 0.12, 0); tone('sine', 784, 784, 0.22, 0.12, 0.09); }
      else if (kind === 'win')  { [523.25, 659.25, 784, 1046.5].forEach((f, i) => tone('triangle', f, f, 0.3, 0.14, i * 0.12)); }
      else if (kind === 'lose') { [392, 311, 233].forEach((f, i) => tone('triangle', f, f, 0.34, 0.14, i * 0.16)); }
    } catch (e) { /* audio is garnish — never let it break the game */ }
  }

  // ── renderer / scene / camera ────────────────────────────────────────────
  // RESILIENT CONTEXT CREATION (2026-07-08): Chrome refuses new WebGL contexts
  // when its global limit is hit (many tabs) or hardware accel is off/blocked
  // — the "Error creating WebGL context" the shared link hit. Ask for a
  // software fallback (failIfMajorPerformanceCaveat:false), drop antialias on
  // retry, and if it STILL fails, show a helpful message instead of a dead end.
  let renderer = null;
  for (const opts of [
    { antialias: true, powerPreference: 'high-performance', failIfMajorPerformanceCaveat: false },
    { antialias: false, powerPreference: 'default', failIfMajorPerformanceCaveat: false },
    { antialias: false, powerPreference: 'low-power', failIfMajorPerformanceCaveat: false },
  ]) {
    try {
      renderer = new THREE.WebGLRenderer(opts);
      if (renderer.getContext()) break;      // got a live context — done
      renderer = null;
    } catch (e) { renderer = null; }
  }
  if (!renderer) {
    const box = document.createElement('div');
    box.style.cssText = 'position:fixed;inset:0;display:flex;flex-direction:column;'
      + 'align-items:center;justify-content:center;gap:14px;background:#0d0b16;'
      + 'color:#eceaf6;z-index:99;font:600 15px system-ui;text-align:center;padding:24px;';
    box.innerHTML = "<div style='font-size:19px'>This browser blocked 3D graphics</div>"
      + "<div style='font-weight:400;color:#a8a4c4;max-width:420px;line-height:1.5'>"
      + "Chrome ran out of graphics slots or has hardware acceleration off. "
      + "Try closing a few other tabs, or enable "
      + "<b>Settings → System → Use hardware acceleration</b>, then retry. "
      + "It also works in Firefox and on mobile.</div>";
    const b = document.createElement('button');
    b.textContent = '↻ Retry';
    b.style.cssText = 'padding:9px 28px;border-radius:10px;border:0;cursor:pointer;'
      + 'background:#5cffc9;color:#0a0a12;font:700 14px system-ui;';
    b.onclick = () => location.reload();
    box.appendChild(b);
    document.body.appendChild(box);
    throw new Error('WebGL unavailable in this browser');
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(innerWidth, innerHeight, false);   // false: don't set inline px style — CSS fills
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;   // filmic response for the Sky
  // Phase 65: per-environment exposure; snow is high-albedo — damp it further
  // so arctic scenes read as LIT SNOW instead of a white void.
  renderer.toneMappingExposure = ((SKY[SPEC.world.sky] || SKY.day).exp || 0.75)
    * (SPEC.world.weather === 'snow' ? 0.86 : 1.0)
    // high-albedo grounds (desert sand, beach) wash out like snow does —
    // same damp, keyed on the actual ground color instead of a name list
    * ((0.299 * SPEC.world.ground_color[0] + 0.587 * SPEC.world.ground_color[1]
        + 0.114 * SPEC.world.ground_color[2]) > 0.62 ? 0.88 : 1.0);
  renderer.domElement.style.cssText = 'display:block;width:100%;height:100%';  // fill the frame
  document.getElementById('app').appendChild(renderer.domElement);

  // WEBGL CONTEXT-LOSS RECOVERY: WebView2/browsers cap live GL contexts; an
  // exhausted context renders a silent white canvas while the HTML UI keeps
  // working (looks like a broken build — it isn't). Detect and self-reload.
  renderer.domElement.addEventListener('webglcontextlost', (e) => {
    e.preventDefault();
    const d = document.createElement('div');
    d.style.cssText = 'position:fixed;inset:0;display:flex;align-items:center;'
      + 'justify-content:center;background:#0d0b16;color:#cfcbe6;z-index:99;'
      + 'font:600 16px system-ui;';
    d.textContent = 'Graphics context recovered — reloading…';
    document.body.appendChild(d);
    setTimeout(() => location.reload(), 600);
  });

  const scene = new THREE.Scene();
  const WIND_U = { value: 0 };                   // shared wind clock (Phase 81)
  scene.background = new THREE.Color(pal.sky);
  if (SPEC.world.fog) {
    // fog_density 0..1: 0.5 = default atmosphere, higher pulls the fog wall
    // in close ("mistier", "thick fog"), lower pushes it out ("clear air")
    const fd = SPEC.world.fog_density != null ? SPEC.world.fog_density : 0.5;
    // 2026-07-15 haze fix: the old envelope (near at 0.24 of world for the
    // DEFAULT) milked out everything past ~22 m — battle royale foxes at 40 m
    // were 60% fog. Default air is now CRISP (near 0.55 of world, full fog
    // well past the far edge); prompted "thick fog" still closes right in.
    const near = SPEC.world.size_m * (0.80 - fd * 0.72);   // 0.80..0.08 of world
    const far  = SPEC.world.size_m * (2.20 - fd * 1.55);   // 2.20..0.65 of world
    scene.fog = new THREE.Fog(pal.fog, Math.max(near, 2), Math.max(far, near + 20));
  }

  // QUALITY PACK — real atmospheric sky (day/sunset/overcast) or a starfield
  // dome (night): kills the flat-color backdrop everywhere at once.
  if (SPEC.world.sky !== 'night') {
    const sky = new Sky();
    sky.scale.setScalar(4000);
    scene.add(sky);
    const su = sky.material.uniforms;
    const cfg = {
      day:      { turbidity: 6,  rayleigh: 1.2, elev: 35 },
      sunset:   { turbidity: 8,  rayleigh: 2.6, elev: 6 },
      overcast: { turbidity: 20, rayleigh: 0.6, elev: 25 },
    }[SPEC.world.sky] || { turbidity: 6, rayleigh: 1.2, elev: 35 };
    su.turbidity.value = cfg.turbidity;
    su.rayleigh.value = cfg.rayleigh;
    su.mieCoefficient.value = 0.004;
    su.mieDirectionalG.value = 0.85;
    const phi = THREE.MathUtils.degToRad(90 - cfg.elev);
    const theta = THREE.MathUtils.degToRad(38);
    su.sunPosition.value.setFromSphericalCoords(1, phi, theta);
    scene.background = null;              // the sky IS the background now
    try {
      // ENVIRONMENT REFLECTIONS baked from this same sky: glossy materials
      // (car paint, windows) pick up real reflections instead of reading
      // flat and blotchy under pure direct light.
      const pmrem = new THREE.PMREMGenerator(renderer);
      const envScene = new THREE.Scene();
      const sky2 = new Sky();
      sky2.scale.setScalar(1000);
      for (const k in su) sky2.material.uniforms[k].value = su[k].value;
      envScene.add(sky2);
      scene.environment = pmrem.fromScene(envScene, 0.02).texture;
      pmrem.dispose();
    } catch (e) { console.warn('[game] env reflections skipped: ' + e.message); }
    // CLOUDS (Phase 74): soft drifting billboards — an empty blue dome reads
    // as a render, a sky with weather reads as a place. Sprite count/opacity
    // tuned per mood; they drift slowly downwind and always face the camera.
    {
      const cN = SPEC.world.sky === 'overcast' ? 26 : 14;
      const ccnv = document.createElement('canvas'); ccnv.width = 256; ccnv.height = 128;
      const cctx = ccnv.getContext('2d');
      const rngCl = mulberry32(SPEC.seed + 313);
      for (let i = 0; i < 26; i++) {                 // one puffy texture, many sprites
        const x = 40 + rngCl() * 176, y = 34 + rngCl() * 56, r = 14 + rngCl() * 30;
        const g2 = cctx.createRadialGradient(x, y, 0, x, y, r);
        g2.addColorStop(0, 'rgba(255,255,255,0.16)');
        g2.addColorStop(1, 'rgba(255,255,255,0)');
        cctx.fillStyle = g2; cctx.beginPath(); cctx.arc(x, y, r, 0, 7); cctx.fill();
      }
      const ctex = new THREE.CanvasTexture(ccnv);
      const cmat = new THREE.SpriteMaterial({
        map: ctex, transparent: true, depthWrite: false, fog: false,
        opacity: SPEC.world.sky === 'overcast' ? 0.9 : 0.75,
        color: SPEC.world.sky === 'sunset' ? 0xffd9c4 : 0xffffff });
      window.__clouds = [];
      for (let i = 0; i < cN; i++) {
        const sp = new THREE.Sprite(cmat);
        const a = rngCl() * Math.PI * 2, d = 180 + rngCl() * 900;
        sp.position.set(Math.cos(a) * d, 130 + rngCl() * 160, Math.sin(a) * d);
        const s = 220 + rngCl() * 300;
        sp.scale.set(s, s * 0.42, 1);
        scene.add(sp);
        window.__clouds.push(sp);
      }
    }
    // MOUNTAIN SKYLINE (Phase 93): open worlds ended at a fog wall — a ring
    // of displaced low-poly ridges past the playfield gives every level a
    // horizon. Fog tints them into the distance automatically; snow weather
    // and cold skies get white caps via vertex color.
    if (!(((SPEC.world || {}).level || {}).osm) && !(((SPEC.world || {}).level || {}).interior)) {
      const gsizeM = SPEC.world.size_m;
      const rngM = mulberry32(SPEC.seed + 777);
      const snowy = SPEC.world.weather === 'snow';
      const rock = new THREE.Color(snowy ? 0x9aa4ad : 0x6b6f66)
        .lerp(new THREE.Color(pal.sky), 0.22);
      const capC = new THREE.Color(0xf4f7fa);
      const mmat = new THREE.MeshStandardMaterial({ roughness: 1.0, vertexColors: true });
      const ring = new THREE.Group();
      const NPK = 11;
      for (let i = 0; i < NPK; i++) {
        const a = (i / NPK) * Math.PI * 2 + rngM() * 0.35;
        const dist = gsizeM * (0.78 + rngM() * 0.28);
        const hgt = gsizeM * (0.10 + rngM() * 0.14);
        const rad = hgt * (1.5 + rngM() * 0.9);
        const geo = new THREE.ConeGeometry(rad, hgt, 7 + Math.floor(rngM() * 4), 3);
        const posA = geo.attributes.position;
        const col = new Float32Array(posA.count * 3);
        for (let v = 0; v < posA.count; v++) {
          const vx = posA.getX(v), vy = posA.getY(v), vz = posA.getZ(v);
          const n = Math.sin(vx * 0.9 + i * 7) * Math.cos(vz * 1.1 + i * 3);
          posA.setX(v, vx * (1 + n * 0.22));
          posA.setZ(v, vz * (1 + n * 0.22));
          const t = (vy / hgt + 0.5);
          const c = (snowy || t < 0.72) && !(snowy && t > 0.4)
            ? rock.clone().offsetHSL(0, 0, (t - 0.4) * 0.12)
            : capC;
          col[v * 3] = c.r; col[v * 3 + 1] = c.g; col[v * 3 + 2] = c.b;
        }
        geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
        geo.computeVertexNormals();
        const m = new THREE.Mesh(geo, mmat);
        m.position.set(Math.cos(a) * dist, hgt * 0.42, Math.sin(a) * dist);
        m.rotation.y = rngM() * Math.PI;
        ring.add(m);
      }
      scene.add(ring);
    }
  } else {
    const sN = 1400, sPos = new Float32Array(sN * 3);
    const sRng = mulberry32(SPEC.seed + 5);
    for (let i = 0; i < sN; i++) {
      const a = sRng() * Math.PI * 2, e = Math.asin(sRng() * 0.95 + 0.05), r = 900;
      sPos[i * 3] = r * Math.cos(e) * Math.cos(a);
      sPos[i * 3 + 1] = r * Math.sin(e);
      sPos[i * 3 + 2] = r * Math.cos(e) * Math.sin(a);
    }
    const sg = new THREE.BufferGeometry();
    sg.setAttribute('position', new THREE.BufferAttribute(sPos, 3));
    const stars = new THREE.Points(sg, new THREE.PointsMaterial({
      color: 0xcdd6ff, size: 1.6, sizeAttenuation: false, fog: false,
      transparent: true, opacity: 0.9 }));
    stars.frustumCulled = false;
    scene.add(stars);
  }

  // VIEW PRESET (Phase 45): 3d = perspective third-person; topdown/side use
  // an ORTHOGRAPHIC camera — the honest "2D game" feel on the same 3D world
  const VIEW = SPEC.view || '3d';
  let camera;
  if (VIEW === '3d') {
    camera = new THREE.PerspectiveCamera(SPEC.camera.fov_deg, innerWidth / innerHeight, 0.1, 1000);
  } else {
    const oa = innerWidth / innerHeight;
    const os = VIEW === 'side' ? 9 : 16;      // world units of half-height on screen
    camera = new THREE.OrthographicCamera(-os * oa, os * oa, os, -os, 0.1, 1000);
  }

  const hemi = new THREE.HemisphereLight(pal.sky, 0x3a3f35, pal.amb);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(pal.sunCol || 0xffffff, pal.sun);
  sun.position.set(...pal.sunPos);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  const sc = SPEC.world.size_m * 0.5;
  Object.assign(sun.shadow.camera, { left: -sc, right: sc, top: sc, bottom: -sc, far: 400 });
  scene.add(sun);

  // ── physics world ────────────────────────────────────────────────────────
  const world = new RAPIER.World({ x: 0, y: -9.81, z: 0 });

  // ── ground (QUALITY PACK 2: hand-painted-style ground — soft tonal
  // blotches, bare-dirt patches, fine speckle, a WORN TRAIL painted along the
  // level path, and real asphalt roads when the level carries OSM data) ─────
  const gsize = SPEC.world.size_m;
  const LVL = SPEC.world.level || null;
  // SIDE-SCROLLER projection: gameplay lives on the z=0 plane — pull the
  // mission targets onto it so everything is actually reachable
  if (VIEW === 'side' && LVL) {
    if (LVL.goal) LVL.goal[1] = 0;
    for (const key of ['collect_points', 'path']) {
      if (LVL[key]) for (const p of LVL[key]) p[1] = 0;
    }
    if (LVL.landmarks) for (const p of LVL.landmarks) p[1] = 0;
  }
  const OSM = (LVL && LVL.osm) || null;
  const INTERIOR = (LVL && LVL.interior) || null;   // Phase 95: room levels
  const gcol = new THREE.Color(...SPEC.world.ground_color);
  {
    // SATURATION FLOOR (Phase 76): LLM ground colors trend pastel — real
    // grass/soil is richer. Only colored grounds are lifted (snow/sand with
    // near-zero saturation stay untouched).
    const _h = {}; gcol.getHSL(_h);
    if (_h.s > 0.08 && _h.s < 0.3) gcol.setHSL(_h.h, 0.34, Math.min(_h.l, 0.42));
  }
  const TEXN = LVL ? 1024 : 256;        // level ground is painted 1:1 (no tiling)
  const cnv = document.createElement('canvas'); cnv.width = cnv.height = TEXN;
  const ctx = cnv.getContext('2d');
  const rngTex = mulberry32(SPEC.seed + 1);
  ctx.fillStyle = '#' + gcol.getHexString(); ctx.fillRect(0, 0, TEXN, TEXN);
  // large soft blotches: patchy meadow / mottled concrete, not one flat tone
  for (let i = 0; i < TEXN / 12; i++) {
    const r = TEXN * (0.04 + rngTex() * 0.14), x = rngTex() * TEXN, y = rngTex() * TEXN;
    const c2 = gcol.clone().offsetHSL((rngTex() - 0.5) * 0.02, (rngTex() - 0.5) * 0.10, (rngTex() - 0.5) * 0.09);
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, '#' + c2.getHexString() + '99'); g.addColorStop(1, '#' + c2.getHexString() + '00');
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
  }
  // bare-dirt patches showing through
  const dirt = gcol.clone().lerp(new THREE.Color(0x6b5334), 0.65);
  for (let i = 0; i < TEXN / 36; i++) {
    const r = TEXN * (0.012 + rngTex() * 0.045), x = rngTex() * TEXN, y = rngTex() * TEXN;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, '#' + dirt.getHexString() + '66'); g.addColorStop(1, '#' + dirt.getHexString() + '00');
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
  }
  // fine speckle (pebbles / grass tufts)
  for (let i = 0; i < TEXN * 26; i++) {
    const sh = (rngTex() - 0.5) * 0.22;
    const c2 = gcol.clone().offsetHSL(0, (rngTex() - 0.5) * 0.06, sh * 0.5);
    ctx.fillStyle = '#' + c2.getHexString();
    ctx.fillRect(rngTex() * TEXN, rngTex() * TEXN, 1 + rngTex() * 2, 1 + rngTex() * 2);
  }
  const W2T = v => (v / gsize + 0.5) * TEXN;         // world (x,z) -> texel
  function drawTrail(pts, widthM, col, alpha) {
    ctx.strokeStyle = col; ctx.globalAlpha = alpha;
    ctx.lineCap = ctx.lineJoin = 'round';
    ctx.lineWidth = Math.max(2, widthM / gsize * TEXN);
    ctx.beginPath();
    pts.forEach(([x, z], i) => i ? ctx.lineTo(W2T(x), W2T(z)) : ctx.moveTo(W2T(x), W2T(z)));
    ctx.stroke(); ctx.globalAlpha = 1;
  }
  if (OSM) {                                   // real streets: asphalt + wear
    for (const r of OSM.roads) drawTrail(r.pts, (r.w || 7) + 2, '#26262b', 0.92);
    for (const r of OSM.roads) drawTrail(r.pts, (r.w || 7) * 0.55, '#3a3a41', 0.85);
  } else if (LVL && LVL.path) {                // worn trail along the mission route
    const c = LVL.corridor_m || 5.5;
    drawTrail(LVL.path, c * 1.15, '#' + dirt.getHexString(), 0.5);
    drawTrail(LVL.path, c * 0.60, '#7a6140', 0.65);
    drawTrail(LVL.path, c * 0.22, '#8a7048', 0.75);
  }
  const gtex = new THREE.CanvasTexture(cnv);
  gtex.wrapS = gtex.wrapT = THREE.RepeatWrapping;
  gtex.repeat.set(LVL ? 1 : gsize / 8, LVL ? 1 : gsize / 8);
  gtex.anisotropy = 8;
  gtex.colorSpace = THREE.SRGBColorSpace;
  // Phase 32 LEVEL: terrain heightfield (hills, flattened path corridor) when
  // the LevelPlan is present; flat plane otherwise. hAt(x,z) is THE ground
  // sampler — scatter, objectives, NPCs and landmarks all sit on it.
  let hAt = () => 0;
  // Phase 65: micro-detail bump — a small tiled noise canvas breaks the flat
  // "void" read at grazing angles (snow drifts, dirt clods) for ~zero cost.
  const bcnv = document.createElement('canvas');
  bcnv.width = bcnv.height = 256;
  {
    const bctx = bcnv.getContext('2d');
    const bimg = bctx.createImageData(256, 256);
    const rngB = mulberry32(SPEC.seed + 77);
    const base = new Float32Array(34 * 34);
    for (let i = 0; i < base.length; i++) base[i] = rngB();
    for (let y = 0; y < 256; y++) for (let x = 0; x < 256; x++) {
      // two octaves of bilinear value noise (tileable via modulo lattice)
      let v = 0;
      for (const [fq, w] of [[8, 0.65], [32, 0.35]]) {
        const gx = (x / 256) * fq, gy = (y / 256) * fq;
        const x0 = Math.floor(gx) % fq, y0 = Math.floor(gy) % fq;
        const x1 = (x0 + 1) % fq, y1 = (y0 + 1) % fq;
        const tx = gx - Math.floor(gx), ty = gy - Math.floor(gy);
        const s = (ix, iy) => base[(iy * 31 + ix * 7) % base.length];
        v += w * (s(x0, y0) * (1 - tx) * (1 - ty) + s(x1, y0) * tx * (1 - ty)
                + s(x0, y1) * (1 - tx) * ty + s(x1, y1) * tx * ty);
      }
      const g = Math.floor(110 + v * 90);
      const k = (y * 256 + x) * 4;
      bimg.data[k] = bimg.data[k + 1] = bimg.data[k + 2] = g;
      bimg.data[k + 3] = 255;
    }
    bctx.putImageData(bimg, 0, 0);
  }
  const btex = new THREE.CanvasTexture(bcnv);
  btex.wrapS = btex.wrapT = THREE.RepeatWrapping;
  btex.repeat.set(gsize / 3, gsize / 3);
  const gmat = new THREE.MeshStandardMaterial({ map: gtex, roughness: 0.96,
                                                bumpMap: btex, bumpScale: 0.35 });
  // MACRO VARIATION (Phase 74): the tiled detail map repeats every 8 m, so
  // from any distance the ground reads as one flat tone. A second LOW-FREQ
  // canvas is sampled in WORLD coordinates (1:1 across the map, no tiling)
  // and multiplied over the albedo — big soft meadow/soil drifts like real
  // terrain, for one extra texture fetch.
  {
    const MN = 128;
    const mcnv = document.createElement('canvas'); mcnv.width = mcnv.height = MN;
    const mctx = mcnv.getContext('2d');
    const mimg = mctx.createImageData(MN, MN);
    const rngM = mulberry32(SPEC.seed + 555);
    const lat = new Float32Array(18 * 18);
    for (let i = 0; i < lat.length; i++) lat[i] = rngM();
    for (let y = 0; y < MN; y++) for (let x = 0; x < MN; x++) {
      let v = 0;
      for (const [fq, w] of [[5, 0.7], [11, 0.3]]) {
        const gx = (x / MN) * fq, gy = (y / MN) * fq;
        const x0 = Math.floor(gx) % fq, y0 = Math.floor(gy) % fq;
        const x1 = (x0 + 1) % fq, y1 = (y0 + 1) % fq;
        const tx = gx - Math.floor(gx), ty = gy - Math.floor(gy);
        const s = (ix, iy) => lat[(iy * 17 + ix * 5) % lat.length];
        v += w * (s(x0, y0) * (1 - tx) * (1 - ty) + s(x1, y0) * tx * (1 - ty)
                + s(x0, y1) * (1 - tx) * ty + s(x1, y1) * tx * ty);
      }
      const k = (y * MN + x) * 4;
      // centered at 128 = neutral; warm/dark drift on one side, cool/light on the other
      mimg.data[k]     = Math.floor(118 + v * 26);
      mimg.data[k + 1] = Math.floor(122 + v * 16);
      mimg.data[k + 2] = Math.floor(116 + v * 14);
      mimg.data[k + 3] = 255;
    }
    mctx.putImageData(mimg, 0, 0);
    const macroTex = new THREE.CanvasTexture(mcnv);
    macroTex.wrapS = macroTex.wrapT = THREE.ClampToEdgeWrapping;
    gmat.onBeforeCompile = sh => {
      sh.uniforms.macroMap = { value: macroTex };
      sh.uniforms.macroSize = { value: gsize };
      sh.vertexShader = sh.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vMacroW;')
        .replace('#include <worldpos_vertex>',
                 '#include <worldpos_vertex>\nvMacroW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
      sh.fragmentShader = sh.fragmentShader
        .replace('#include <common>',
                 '#include <common>\nuniform sampler2D macroMap; uniform float macroSize; varying vec3 vMacroW;')
        .replace('#include <map_fragment>',
                 `#include <map_fragment>
                  { vec3 m = texture2D(macroMap, clamp(vMacroW.xz / macroSize + 0.5, 0.0, 1.0)).rgb;
                    diffuseColor.rgb *= mix(vec3(1.0), m * 2.0, 0.5); }`);
    };
  }
  if (LVL && LVL.heights && LVL.heights.length === LVL.grid_n * LVL.grid_n) {
    const n = LVL.grid_n, hs = LVL.heights;
    hAt = (x, z) => {
      const fx = (x / gsize + 0.5) * (n - 1), fz = (z / gsize + 0.5) * (n - 1);
      const j0 = Math.max(0, Math.min(n - 2, Math.floor(fx)));
      const i0 = Math.max(0, Math.min(n - 2, Math.floor(fz)));
      const tx = Math.max(0, Math.min(1, fx - j0)), tz = Math.max(0, Math.min(1, fz - i0));
      return hs[i0 * n + j0] * (1 - tx) * (1 - tz) + hs[i0 * n + j0 + 1] * tx * (1 - tz)
           + hs[(i0 + 1) * n + j0] * (1 - tx) * tz + hs[(i0 + 1) * n + j0 + 1] * tx * tz;
    };
    // world-space grid mesh + EXACT-match trimesh collider (same vertices)
    const verts = new Float32Array(n * n * 3);
    const uvs = new Float32Array(n * n * 2);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      const k = i * n + j;
      verts[k * 3] = (j / (n - 1) - 0.5) * gsize;
      verts[k * 3 + 1] = hs[k];
      verts[k * 3 + 2] = (i / (n - 1) - 0.5) * gsize;
      // 1:1 painted map; v inverted (canvas y is top-down, texture v is not)
      uvs[k * 2] = j / (n - 1); uvs[k * 2 + 1] = 1 - i / (n - 1);
    }
    const idx = new Uint32Array((n - 1) * (n - 1) * 6);
    let p = 0;
    for (let i = 0; i < n - 1; i++) for (let j = 0; j < n - 1; j++) {
      const a = i * n + j, b = a + 1, c = a + n, d = c + 1;
      idx[p++] = a; idx[p++] = c; idx[p++] = b;
      idx[p++] = b; idx[p++] = c; idx[p++] = d;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(verts, 3));
    geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
    geo.setIndex(new THREE.BufferAttribute(idx, 1));
    geo.computeVertexNormals();
    const terrain = new THREE.Mesh(geo, gmat);
    terrain.receiveShadow = true;
    scene.add(terrain);
    world.createCollider(RAPIER.ColliderDesc.trimesh(verts, idx));
  } else {
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(gsize, gsize), gmat);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
    world.createCollider(RAPIER.ColliderDesc.cuboid(gsize / 2, 0.05, gsize / 2)
      .setTranslation(0, -0.05, 0));
  }

  // WATER (ocean/lake worlds): translucent plane at world.water_level with a
  // gentle tide bob; the camera dipping below it switches to underwater fog
  const WATER = (SPEC.world.water_level ?? null);
  let waterMesh = null, underwater = false;
  const origFog = scene.fog;
  if (WATER !== null) {
    waterMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(gsize * 1.3, gsize * 1.3),
      new THREE.MeshStandardMaterial({ color: 0x1d5d8e, transparent: true, opacity: 0.7,
                                       roughness: 0.12, metalness: 0.1, side: THREE.DoubleSide,
                                       depthWrite: false }));
    waterMesh.rotation.x = -Math.PI / 2;
    // LAKE LEVEL FIX (Phase 88): a fixed height FLOATS above rolling terrain
    // (the penguin's frozen lake hovered over the ground). Water fills the
    // LOW BASINS: clamp to just above the terrain's 12th-percentile height.
    {
      const hs = [];
      for (let i = -8; i <= 8; i++) {
        for (let j = -8; j <= 8; j++) hs.push(hAt(i * gsize / 16, j * gsize / 16));
      }
      hs.sort((a, b) => a - b);
      waterMesh.position.y = Math.min(WATER, hs[Math.floor(hs.length * 0.12)] + 0.05);
    }
    scene.add(waterMesh);
  }

  // THE GOAL IS A PLACE, NOT A LIGHT (Phase 47): when the reach objective
  // names a structure ("reach the cat shelter", "reach the cabin"), a real
  // WALK-IN building stands at the goal — door open, windows warm, hearth
  // lit. You win by stepping inside. Abstract goals keep the classic beacon.
  let goalPos = null, goalMesh = null;
  const _reachOb = (SPEC.objectives || []).find(o => o.kind === 'reach');
  const _structHit = _reachOb && (_reachOb.label || '').toLowerCase().match(
    /\b(shelter|cabin|house|home|hut|shrine|castle|tower|barn|cottage|inn|temple|church|fort|lodge|den|village|camp|outpost|lighthouse|station)\b/);
  if (LVL && LVL.goal) {
    goalPos = new THREE.Vector3(LVL.goal[0], hAt(LVL.goal[0], LVL.goal[1]), LVL.goal[1]);
    if (_structHit) {
      // door faces the approach: back along the mission path, else the spawn
      const _pp = (LVL.path && LVL.path.length > 1) ? LVL.path[LVL.path.length - 2] : [0, 0];
      const doorYaw = Math.atan2(_pp[0] - goalPos.x, _pp[1] - goalPos.z);
      const S = new THREE.Group();
      S.position.copy(goalPos);
      S.rotation.y = doorYaw;
      // structure FLAVOR by noun (Phase 48): castles are stone keeps with
      // corner towers, lighthouses carry a light column — not every goal
      // is a cottage
      const _kindWord = _structHit[1];
      const isCastle = ['castle', 'fort', 'tower'].includes(_kindWord);
      const isLighthouse = ['lighthouse', 'station'].includes(_kindWord);
      const wallMat = new THREE.MeshStandardMaterial({
        color: isCastle ? 0x7d818c : isLighthouse ? 0xe8e4da : 0x9a8f7e,
        roughness: 0.9 });
      const roofMat = new THREE.MeshStandardMaterial({
        color: isCastle ? 0x5a5e6a : 0x6a4438, roughness: 0.85 });
      const warmMat = new THREE.MeshStandardMaterial({
        color: 0xffd88a, emissive: 0xffc86a, emissiveIntensity: 1.6 });
      const addBox = (w, h, d, x, y, z, mat) => {
        const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat || wallMat);
        m.position.set(x, y, z);
        m.castShadow = true;
        S.add(m);
        return m;
      };
      addBox(6.4, 0.16, 5.4, 0, 0.08, 0, roofMat);            // floor slab
      addBox(6.4, 3.1, 0.28, 0, 1.63, -2.55);                 // back wall
      addBox(0.28, 3.1, 5.4, -3.06, 1.63, 0);                 // side walls
      addBox(0.28, 3.1, 5.4, 3.06, 1.63, 0);
      addBox(2.3, 3.1, 0.28, -2.05, 1.63, 2.55);              // front, door gap
      addBox(2.3, 3.1, 0.28, 2.05, 1.63, 2.55);
      addBox(1.8, 0.9, 0.28, 0, 2.73, 2.55);                  // lintel
      if (isCastle) {
        // corner towers with cone caps — reads "keep" from any distance
        for (const [tx, tz] of [[-3.06, -2.55], [3.06, -2.55], [-3.06, 2.55], [3.06, 2.55]]) {
          const tw = new THREE.Mesh(new THREE.CylinderGeometry(0.72, 0.82, 4.6, 10), wallMat);
          tw.position.set(tx, 2.3, tz);
          tw.castShadow = true;
          S.add(tw);
          const cap = new THREE.Mesh(new THREE.ConeGeometry(0.95, 1.2, 10), roofMat);
          cap.position.set(tx, 5.2, tz);
          S.add(cap);
        }
        const parapet = new THREE.Mesh(new THREE.BoxGeometry(6.6, 0.5, 5.6), roofMat);
        parapet.position.y = 3.4;
        S.add(parapet);
      } else {
        const roof = new THREE.Mesh(new THREE.ConeGeometry(4.9, 2.2, 4), roofMat);
        roof.rotation.y = Math.PI / 4;
        roof.position.y = 4.28;
        roof.castShadow = true;
        S.add(roof);
      }
      if (isLighthouse) {
        // the light column: striped tower + a bright lamp visible for miles
        const col = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.3, 6.5, 14), wallMat);
        col.position.y = 6.5;
        S.add(col);
        for (const sy of [4.6, 6.5, 8.4]) {
          const stripe = new THREE.Mesh(new THREE.CylinderGeometry(1.12, 1.12, 0.55, 14),
            new THREE.MeshStandardMaterial({ color: 0xc23b3b, roughness: 0.8 }));
          stripe.position.y = sy;
          S.add(stripe);
        }
        const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.8, 14, 10),
          new THREE.MeshStandardMaterial({ color: 0xfff2c0, emissive: 0xffe9a0,
                                           emissiveIntensity: 3.2 }));
        lamp.position.y = 10.2;
        S.add(lamp);
        const beam = new THREE.PointLight(0xffe9a0, 2.4, 40);
        beam.position.y = 10.2;
        S.add(beam);
      }
      for (const wx of [-2.05, 2.05]) {                       // warm windows
        const w = new THREE.Mesh(new THREE.BoxGeometry(0.85, 0.85, 0.1), warmMat);
        w.position.set(wx, 1.8, 2.62);
        S.add(w);
      }
      const hearth = new THREE.PointLight(0xffc27a, 1.6, 9);  // lit inside
      hearth.position.set(0, 1.6, -0.5);
      S.add(hearth);
      const halo = makeGoalHalo();                            // findable from afar
      halo.position.y = 6.2;
      S.add(halo);
      const mat2 = new THREE.Mesh(                            // welcome mat = win spot
        new THREE.CircleGeometry(0.9, 24),
        new THREE.MeshStandardMaterial({ color: 0xb9a0ff, emissive: 0x7c5cff,
                                         emissiveIntensity: 1.2 }));
      mat2.rotation.x = -Math.PI / 2;
      mat2.position.set(0, 0.18, 0.4);
      S.add(mat2);
      scene.add(S);
      S.updateMatrixWorld(true);
      // colliders per wall segment — the DOORWAY stays open, you walk in
      const _v = new THREE.Vector3();
      const wallCols = [[6.4, 3.1, 0.28, 0, 1.63, -2.55], [0.28, 3.1, 5.4, -3.06, 1.63, 0],
                        [0.28, 3.1, 5.4, 3.06, 1.63, 0], [2.3, 3.1, 0.28, -2.05, 1.63, 2.55],
                        [2.3, 3.1, 0.28, 2.05, 1.63, 2.55]];
      for (const [w, h, d, x, y, z] of wallCols) {
        _v.set(x, y, z).applyMatrix4(S.matrixWorld);
        world.createCollider(
          RAPIER.ColliderDesc.cuboid(w / 2, h / 2, d / 2)
            .setTranslation(_v.x, _v.y, _v.z)
            .setRotation({ x: 0, y: Math.sin(doorYaw / 2), z: 0, w: Math.cos(doorYaw / 2) }));
      }
      S.userData.fsTag = { type: 'goal', name: _structHit[1],
                           detail: 'step inside to finish the journey' };
      goalMesh = mat2;
    } else {
      const pil = new THREE.Mesh(
        new THREE.CylinderGeometry(0.9, 0.9, 22, 20, 1, true),
        new THREE.MeshBasicMaterial({ color: 0x9f7bff, transparent: true, opacity: 0.16,
                                      side: THREE.DoubleSide, depthWrite: false }));
      pil.position.set(goalPos.x, goalPos.y + 11, goalPos.z);
      scene.add(pil);
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(1.5, 0.09, 10, 40),
        new THREE.MeshStandardMaterial({ color: 0xb9a0ff, emissive: 0x7c5cff, emissiveIntensity: 2.2 }));
      ring.rotation.x = Math.PI / 2;
      ring.position.set(goalPos.x, goalPos.y + 0.25, goalPos.z);
      scene.add(ring);
      goalMesh = ring;
    }
  }
  function makeGoalHalo() {
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const g2 = c.getContext('2d');
    const grad = g2.createRadialGradient(32, 32, 2, 32, 32, 30);
    grad.addColorStop(0, 'rgba(255,216,138,0.95)');
    grad.addColorStop(1, 'rgba(255,216,138,0)');
    g2.fillStyle = grad;
    g2.fillRect(0, 0, 64, 64);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(c), transparent: true, depthTest: false }));
    sp.scale.setScalar(3.2);
    return sp;
  }
  // ── SKY LIFE (Phase 48): drifting clouds + a distant bird flock — the sky
  // stops being an empty gradient. Day-family palettes only.
  const clouds = [], birds = [];
  if (['day', 'sunset', 'overcast', 'dusk'].includes(SPEC.world.sky)
      && (SPEC.style || 'default') !== 'horror') {
    const cc = document.createElement('canvas');
    cc.width = 128; cc.height = 64;
    const cg = cc.getContext('2d');
    for (const [bx, by, br] of [[36, 40, 22], [64, 32, 26], [92, 42, 20], [58, 46, 24]]) {
      const grad = cg.createRadialGradient(bx, by, 2, bx, by, br);
      grad.addColorStop(0, 'rgba(255,255,255,0.85)');
      grad.addColorStop(1, 'rgba(255,255,255,0)');
      cg.fillStyle = grad;
      cg.fillRect(0, 0, 128, 64);
    }
    const ctex = new THREE.CanvasTexture(cc);
    const rngS = mulberry32(SPEC.seed + 77);
    for (let i = 0; i < 7; i++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({
        map: ctex, transparent: true, opacity: 0.45 + rngS() * 0.25, depthWrite: false }));
      sp.scale.set(26 + rngS() * 22, 9 + rngS() * 6, 1);
      sp.position.set((rngS() - 0.5) * gsize * 1.4, 38 + rngS() * 18,
                      (rngS() - 0.5) * gsize * 1.4);
      scene.add(sp);
      clouds.push({ sp, v: 0.5 + rngS() * 0.7 });
    }
    // birds: dark chevrons wheeling high — tiny, but the sky feels inhabited
    const bc = document.createElement('canvas');
    bc.width = bc.height = 32;
    const bg2 = bc.getContext('2d');
    bg2.strokeStyle = 'rgba(30,30,40,0.9)';
    bg2.lineWidth = 3;
    bg2.lineCap = 'round';
    bg2.beginPath();
    bg2.moveTo(4, 20);
    bg2.quadraticCurveTo(16, 8, 16, 16);
    bg2.quadraticCurveTo(16, 8, 28, 20);
    bg2.stroke();
    const btex = new THREE.CanvasTexture(bc);
    for (let i = 0; i < 5; i++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({
        map: btex, transparent: true, depthWrite: false }));
      sp.scale.setScalar(1.6);
      birds.push({ sp, a: rngS() * Math.PI * 2, r: 20 + rngS() * 26,
                   h: 26 + rngS() * 12, w: 0.05 + rngS() * 0.04,
                   cx: (rngS() - 0.5) * gsize * 0.4, cz: (rngS() - 0.5) * gsize * 0.4 });
      scene.add(sp);
    }
  }

  // invisible boundary walls — the park has edges; you can't run off the world
  const wh = 4, ext = gsize / 2;
  for (const [wx, wz, hx, hz] of [[ext, 0, 0.5, ext], [-ext, 0, 0.5, ext],
                                  [0, ext, ext, 0.5], [0, -ext, ext, 0.5]]) {
    world.createCollider(RAPIER.ColliderDesc.cuboid(hx, wh, hz).setTranslation(wx, wh, wz));
  }

  // ── asset loading ────────────────────────────────────────────────────────
  const loader = new GLTFLoader();
  const loadGLB = url => new Promise((res, rej) =>
    loader.load(url, res, undefined, () => rej(new Error('failed to load ' + url))));

  // belt-and-suspenders vs "string" strips: any alpha-aware material gets a
  // hard alphaTest so low-alpha fringe fragments DISCARD in three.js too
  function hardenAlpha(root) {
    root.traverse(o => {
      if (!o.isMesh) return;
      const ms = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of ms) {
        if (m && (m.transparent || m.alphaTest > 0) && m.map) {
          m.alphaTest = Math.max(m.alphaTest || 0, 0.55);
          m.transparent = false;      // MASK semantics: opaque + discard
          m.depthWrite = true;
          m.needsUpdate = true;
        }
      }
    });
  }
  function prepModel(gltf, targetH, byMaxDim) {
    const root = gltf.scene;
    hardenAlpha(root);
    root.traverse(o => {
      if (o.isMesh) {
        o.castShadow = true;
        o.frustumCulled = false;
        // generated meshes are OPEN shells — single-sided rendering shows
        // holes through heads/ears at grazing angles ("half cut-off face",
        // 2026-07-08). Render both sides until GPU-day watertight meshes.
        for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
          if (m) m.side = THREE.DoubleSide;
        }
      }
    });
    const box = new THREE.Box3().setFromObject(root);
    // flyers/swimmers normalize by their LONGEST dimension (wingspan / body
    // length) — height normalization blew a wings-out dragon up to kaiju size
    const h = byMaxDim
      ? Math.max(box.max.x - box.min.x, box.max.y - box.min.y, box.max.z - box.min.z, 1e-3)
      : Math.max(box.max.y - box.min.y, 1e-3);
    const s = targetH / h;
    root.scale.setScalar(s);
    const box2 = new THREE.Box3().setFromObject(root);
    if (byMaxDim) {
      // fly/swim: pivot at BODY CENTER so pitch/roll rotate the creature
      // about itself (a whale pitching around its tail reads broken)
      root.position.y -= (box2.min.y + box2.max.y) / 2;
    } else {
      root.position.y -= box2.min.y;           // feet on y=0
    }
    const holder = new THREE.Group();
    holder.add(root);
    return { holder, root, radius: Math.max((box2.max.x - box2.min.x), (box2.max.z - box2.min.z)) * 0.5 };
  }
  // rotate a model so its LONG horizontal axis points down +Z (the runtime's
  // travel direction) — cars/boats read sideways without this
  function alignLongAxis(root, enabled) {
    if (!enabled) return false;
    const bb = new THREE.Box3().setFromObject(root);
    if ((bb.max.x - bb.min.x) > (bb.max.z - bb.min.z) * 1.15) {
      // VERIFIED against Blender renders (2026-07-05): generator vehicles that
      // lie along X carry the NOSE at +X, so -90° puts the nose on +Z.
      // (+90° drives them backwards — do not "fix" this again without
      // re-rendering the asset. Per-asset flips: spec yaw_offset_deg = 180.)
      root.rotation.y -= Math.PI / 2;
      return true;
    }
    return false;
  }
  // generated-car paint reads flat/blotchy until the GPU texture tier lands —
  // a glossier material response under the Sky light hides most of it
  const _despeckled = new Set();
  function despeckleTexture(m) {
    // DE-SPECKLE (Phase 87): generated vehicle textures carry white noise
    // dots ('blotchy paint'). One-time on load: pixels far brighter than
    // their 5x5 neighborhood average get pulled back to it. Cached per map.
    const img = m.map && m.map.image;
    if (!img || !img.width || _despeckled.has(m.map.uuid)) return;
    _despeckled.add(m.map.uuid);
    try {
      const W = Math.min(img.width, 2048), H = Math.min(img.height, 2048);
      const c = document.createElement('canvas'); c.width = W; c.height = H;
      const g = c.getContext('2d', { willReadFrequently: true });
      g.drawImage(img, 0, 0, W, H);
      const d = g.getImageData(0, 0, W, H), px = d.data;
      const lum = new Float32Array(W * H);
      for (let i = 0; i < W * H; i++) lum[i] = 0.299 * px[i * 4] + 0.587 * px[i * 4 + 1] + 0.114 * px[i * 4 + 2];
      const out = g.createImageData(W, H); out.data.set(px);
      for (let y = 2; y < H - 2; y += 1) {
        for (let x = 2; x < W - 2; x += 1) {
          const i = y * W + x;
          let nb = 0, cnt = 0;
          for (let dy = -2; dy <= 2; dy += 2) for (let dx = -2; dx <= 2; dx += 2) {
            if (!dx && !dy) continue;
            nb += lum[i + dy * W + dx]; cnt++;
          }
          nb /= cnt;
          const dev = lum[i] - nb;
          if (dev > 52 || dev < -60) {               // bright speckle OR dark blotch
            const k = nb / Math.max(lum[i], 1);
            out.data[i * 4] = px[i * 4] * k;
            out.data[i * 4 + 1] = px[i * 4 + 1] * k;
            out.data[i * 4 + 2] = px[i * 4 + 2] * k;
          }
        }
      }
      g.putImageData(out, 0, 0);
      const t = new THREE.CanvasTexture(c);
      t.colorSpace = m.map.colorSpace; t.flipY = m.map.flipY;
      t.wrapS = m.map.wrapS; t.wrapT = m.map.wrapT;
      t.anisotropy = renderer.capabilities.getMaxAnisotropy();
      m.map = t; m.needsUpdate = true;
    } catch (e) { /* tainted/compressed texture: keep the original */ }
  }
  function polishVehiclePaint(root, enabled) {
    if (!enabled) return;
    root.traverse(o => {
      if (!o.isMesh) return;
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        if (m && m.isMeshStandardMaterial) {
          m.roughness = 0.38; m.metalness = 0.28;
          despeckleTexture(m);
          m.needsUpdate = true;
        }
      }
    });
  }

  // ── scatter props (shared world-dressing manifest — video side reuses it) ─
  // Path-aware: props keep clear of the level's walking corridor and sit ON
  // the terrain. Landmarks = oversized instances of the first prop at the
  // LevelPlan's scenic points.
  const PATH = (LVL && LVL.path) || null;
  const CORR = (LVL && LVL.corridor_m || 5.5) + 1.5;
  function pathDist(x, z) {
    if (!PATH) return Infinity;
    let best = Infinity;
    for (let k = 0; k < PATH.length - 1; k++) {
      const [ax, az] = PATH[k], [bx, bz] = PATH[k + 1];
      const dx = bx - ax, dz = bz - az, L2 = dx * dx + dz * dz;
      const t = L2 < 1e-9 ? 0 : Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / L2));
      best = Math.min(best, Math.hypot(x - (ax + t * dx), z - (az + t * dz)));
    }
    return best;
  }

  // ── REAL-CITY BLOCKS (OSM footprints — © OpenStreetMap contributors) ─────
  // The video pipeline's city system, now shared: every named-city prompt gets
  // the actual street grid. Footprints extrude into one merged mesh (single
  // draw call) with per-building tint; each gets a box collider. Buildings
  // that would sit on the mission path / spawn / goal are skipped.
  const bldBoxes = [];                  // [minx, minz, maxx, maxz] per building
  function inBldg(x, z, pad = 1.5) {
    for (const b of bldBoxes) {
      if (x > b[0] - pad && x < b[2] + pad && z > b[1] - pad && z < b[3] + pad) return true;
    }
    return false;
  }
  if (OSM && OSM.buildings && OSM.buildings.length) {
    const wallGeos = [], capGeos = [];
    const tintA = new THREE.Color(0x8d8a84), tintB = new THREE.Color(0x5f6b78);
    const rngB = mulberry32(SPEC.seed + 77);
    // ExtrudeGeometry groups: materialIndex 0 = caps (roof/underside after the
    // rotate), 1 = side walls. Split so walls get the facade texture and roofs
    // stay plain — window grids on rooftops read as a bug from the follow-cam.
    function splitGroups(geo) {
      for (const g of geo.groups) {
        const sub = new THREE.BufferGeometry();
        for (const name of ['position', 'normal', 'uv', 'color']) {
          const a = geo.attributes[name];
          sub.setAttribute(name, new THREE.BufferAttribute(
            a.array.slice(g.start * a.itemSize, (g.start + g.count) * a.itemSize), a.itemSize));
        }
        (g.materialIndex === 0 ? capGeos : wallGeos).push(sub);
      }
    }
    for (const b of OSM.buildings) {
      let mnx = 1e9, mnz = 1e9, mxx = -1e9, mxz = -1e9;
      for (const [px, pz] of b.pts) {
        mnx = Math.min(mnx, px); mxx = Math.max(mxx, px);
        mnz = Math.min(mnz, pz); mxz = Math.max(mxz, pz);
      }
      const cx = (mnx + mxx) / 2, cz = (mnz + mxz) / 2;
      if (Math.hypot(cx, cz) < 9) continue;                       // spawn stays open
      if (goalPos && Math.hypot(cx - goalPos.x, cz - goalPos.z) < 8) continue;
      if (pathDist(cx, cz) < CORR + Math.max(mxx - mnx, mxz - mnz) / 2) continue;
      try {
        const shape = new THREE.Shape();
        b.pts.forEach(([px, pz], i) => i ? shape.lineTo(px, -pz) : shape.moveTo(px, -pz));
        const h = Math.max(b.h || 9, 4);
        const geo = new THREE.ExtrudeGeometry(shape, { depth: h, bevelEnabled: false });
        geo.rotateX(-Math.PI / 2);                                // extrude up
        const gy = hAt(cx, cz);
        geo.translate(0, gy, 0);
        const tint = tintA.clone().lerp(tintB, rngB()).offsetHSL(0, 0, (rngB() - 0.5) * 0.12);
        const nv = geo.attributes.position.count, cols = new Float32Array(nv * 3);
        for (let i = 0; i < nv; i++) { cols[i * 3] = tint.r; cols[i * 3 + 1] = tint.g; cols[i * 3 + 2] = tint.b; }
        geo.setAttribute('color', new THREE.BufferAttribute(cols, 3));
        splitGroups(geo);
        bldBoxes.push([mnx, mnz, mxx, mxz]);
        world.createCollider(RAPIER.ColliderDesc
          .cuboid((mxx - mnx) / 2, h / 2, (mxz - mnz) / 2)
          .setTranslation(cx, gy + h / 2, cz));
      } catch (e) { /* one bad footprint never kills the city */ }
    }
    if (wallGeos.length) {
      // procedural FACADE: window grid tiled in metres over the extrude UVs
      // (one 6m x 6m tile: 4 windows across, 2 floors) + a matching emissive
      // map so a fraction of windows glow — detail on EVERY building, no
      // assets, any city.
      const fc = document.createElement('canvas'); fc.width = fc.height = 256;
      const fx = fc.getContext('2d');
      const ec = document.createElement('canvas'); ec.width = ec.height = 256;
      const ex = ec.getContext('2d');
      fx.fillStyle = '#969490'; fx.fillRect(0, 0, 256, 256);   // multiplied by tint
      ex.fillStyle = '#000000'; ex.fillRect(0, 0, 256, 256);
      const rngW = mulberry32(SPEC.seed + 5);
      for (let wy = 0; wy < 2; wy++) for (let wx = 0; wx < 4; wx++) {
        const x = 10 + wx * 64, y = 16 + wy * 128, lit = rngW() < 0.28;
        fx.fillStyle = lit ? '#e8d9a8' : (rngW() < 0.5 ? '#2c3138' : '#3d4550');
        fx.fillRect(x, y, 40, 76);
        fx.strokeStyle = '#5b5b60'; fx.lineWidth = 3; fx.strokeRect(x, y, 40, 76);
        fx.fillStyle = '#77767c'; fx.fillRect(x - 4, y + 76, 48, 6);   // sill
        if (lit) { ex.fillStyle = '#cfa96a'; ex.fillRect(x, y, 40, 76); }
      }
      const facadeTex = new THREE.CanvasTexture(fc);
      const litTex = new THREE.CanvasTexture(ec);
      for (const t of [facadeTex, litTex]) {
        t.wrapS = t.wrapT = THREE.RepeatWrapping;
        t.repeat.set(1 / 6, 1 / 6);                    // extrude UVs are metres
        t.anisotropy = 4;
      }
      facadeTex.colorSpace = THREE.SRGBColorSpace;
      const walls = new THREE.Mesh(mergeGeometries(wallGeos, false),
        new THREE.MeshStandardMaterial({ vertexColors: true, map: facadeTex,
          emissive: 0xffc873, emissiveMap: litTex, emissiveIntensity: 0.4,
          roughness: 0.85, metalness: 0.08 }));
      const roofs = new THREE.Mesh(mergeGeometries(capGeos, false),
        new THREE.MeshStandardMaterial({ vertexColors: true, color: 0x77746e,
          roughness: 0.96, metalness: 0.02 }));
      for (const m of [walls, roofs]) {
        m.castShadow = true; m.receiveShadow = true;
        scene.add(m);
      }
      console.log('[game] OSM city "' + (OSM.place || '?') + '": ' + bldBoxes.length +
                  ' buildings (textured facades), ' + (OSM.roads || []).length + ' roads');
    }
  }
  const rng = mulberry32(SPEC.seed);
  let landmarkAsset = null;
  const swayProps = [];             // Phase 33: wind-swayed prop roots
  function placeProp(inst, x, z, scale, collide) {
    inst.scale.multiplyScalar(scale);
    inst.rotation.y = rng() * Math.PI * 2;
    const bb = new THREE.Box3().setFromObject(inst);
    const gy = hAt(x, z);
    inst.position.set(x, gy - bb.min.y, z);
    scene.add(inst);
    if ((bb.max.y - bb.min.y) > 1.2) swayProps.push({ o: inst, ph: rng() * Math.PI * 2 });
    if (collide) {
      const r = Math.max(bb.max.x - bb.min.x, bb.max.z - bb.min.z) * 0.25;
      world.createCollider(RAPIER.ColliderDesc.cylinder((bb.max.y - bb.min.y) / 2, Math.max(r, 0.1))
        .setTranslation(x, gy + (bb.max.y - bb.min.y) / 2, z));
    }
  }
  // QUALITY PACK: props render as INSTANCED sub-meshes — hundreds of trees at
  // 60fps instead of a sparse dozen of cloned groups.
  for (const sct of SPEC.world.scatter || []) {
    try {
      const gltf = await loadGLB(sct.asset);
      if (!landmarkAsset) landmarkAsset = gltf;
      gltf.scene.updateMatrixWorld(true);
      // ART-DIRECTION COHERENCE (prop half): nudge every prop's albedo toward
      // the sky palette so low-poly trees and photoreal heroes share a mood
      const propTint = new THREE.Color(pal.sky).lerp(new THREE.Color(0xffffff), 0.45);
      gltf.scene.traverse(o => {
        if (!o.isMesh) return;
        for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
          if (m && m.color) m.color.lerp(propTint, 0.08);
        }
      });
      const parts = [];
      gltf.scene.traverse(o => {
        if (o.isMesh) parts.push({ geo: o.geometry, mat: o.material, local: o.matrixWorld.clone() });
      });
      const N = sct.count;
      const places = [];
      // Phase 65 CLUSTERING: real vegetation grows in patches, not an even
      // sprinkle. A low-frequency seeded value noise gates placement — dense
      // groves + open clearings from the same instance budget.
      const cRng = mulberry32(SPEC.seed + 131);
      const cLat = new Float32Array(144);
      for (let i = 0; i < 144; i++) cLat[i] = cRng();
      const clusterN = (x, z) => {
        const f = 12 / gsize;                       // ~one cell per 8-12 m
        const gx = (x + gsize) * f, gz = (z + gsize) * f;
        const x0 = Math.floor(gx), z0 = Math.floor(gz);
        const s = (ix, iz) => cLat[((iz * 13 + ix * 7) % 144 + 144) % 144];
        const tx = gx - x0, tz = gz - z0;
        return s(x0, z0) * (1 - tx) * (1 - tz) + s(x0 + 1, z0) * tx * (1 - tz)
             + s(x0, z0 + 1) * (1 - tx) * tz + s(x0 + 1, z0 + 1) * tx * tz;
      };
      for (let i = 0; i < N; i++) {
        let x, z, tries = 0;
        do {
          x = (rng() - 0.5) * gsize * 0.9; z = (rng() - 0.5) * gsize * 0.9; tries++;
        } while ((Math.hypot(x, z) < sct.min_dist_m || pathDist(x, z) < CORR
                  || inBldg(x, z)
                  || (clusterN(x, z) < 0.45 && tries < 22)) && tries < 30);
        places.push({ x, z, s: 1 + (rng() - 0.5) * 2 * sct.scale_jitter, rot: rng() * Math.PI * 2 });
      }
      const M = new THREE.Matrix4(), T = new THREE.Matrix4(), SV = new THREE.Vector3();
      const jitC = new THREE.Color();
      for (const p of parts) {
        const im = new THREE.InstancedMesh(p.geo, p.mat, N);
        im.castShadow = true;
        im.frustumCulled = false;
        for (let i = 0; i < N; i++) {
          const pl = places[i];
          T.makeRotationY(pl.rot).scale(SV.set(pl.s, pl.s, pl.s));
          T.setPosition(pl.x, hAt(pl.x, pl.z), pl.z);
          M.multiplyMatrices(T, p.local);
          im.setMatrixAt(i, M);
          // per-instance color variation — a forest of identical flat trees
          // reads as plastic; ±8% tone + a hue whisper makes it ALIVE
          const jr = mulberry32(SPEC.seed + i * 131 + 7)();
          const jg = mulberry32(SPEC.seed + i * 131 + 8)();
          jitC.setRGB(0.92 + jr * 0.16, 0.92 + jg * 0.16, 0.92 + jr * 0.12);
          im.setColorAt(i, jitC);
        }
        im.instanceMatrix.needsUpdate = true;
        if (im.instanceColor) im.instanceColor.needsUpdate = true;
        scene.add(im);
      }
      if (sct.collide) {
        for (let i = 0; i < Math.min(N, 260); i++) {
          const pl = places[i];
          world.createCollider(RAPIER.ColliderDesc.cylinder(1.6 * pl.s, 0.22 * pl.s)
            .setTranslation(pl.x, hAt(pl.x, pl.z) + 1.6 * pl.s, pl.z));
        }
      }
    } catch (e) { fail(e.message); }
  }

  // ── INTERIOR (Phase 95): rooms, walls with colliders, floor/ceiling,
  // pooled torch lights, furniture. 'Inside a castle/house/dungeon' is a
  // real level type — combat/collect/reach verbs all work within walls.
  if (INTERIOR) {
    const IK = INTERIOR.kind || 'castle';
    const WH = INTERIOR.wall_h || 4.0, WT = INTERIOR.wall_t || 0.5;
    const texL = new THREE.TextureLoader();
    const itex = (n, rx, ry) => {
      const t = texL.load('textures/' + n + '.jpg');
      t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rx, ry);
      t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = renderer.capabilities.getMaxAnisotropy();
      return t;
    };
    const wallFile = IK === 'house' ? 'plaster' : 'stone';
    const floorFile = IK === 'dungeon' ? 'stone' : 'planks';
    const bx = INTERIOR.bounds[0], bz = INTERIOR.bounds[1];
    const fmat = new THREE.MeshStandardMaterial({
      map: itex(floorFile, bx / 4, bz / 4), roughness: 0.9 });
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(bx, bz), fmat);
    floor.rotation.x = -Math.PI / 2; floor.position.y = 0.02;
    floor.receiveShadow = true;
    scene.add(floor);
    const cmatI = new THREE.MeshStandardMaterial({
      map: itex(wallFile, bx / 6, bz / 6), roughness: 1.0,
      color: 0x9a948c });
    const ceil = new THREE.Mesh(new THREE.PlaneGeometry(bx, bz), cmatI);
    ceil.rotation.x = Math.PI / 2; ceil.position.y = WH;
    scene.add(ceil);
    const wmat = new THREE.MeshStandardMaterial({
      map: itex(wallFile, 3, 1.2), roughness: 0.95 });
    const DOOR_W = 2.4, DOOR_H = Math.min(3.0, WH - 0.6);
    function seg(cx, cz, ln, rot, y0, hgt, thick) {
      const m = new THREE.Mesh(new THREE.BoxGeometry(ln, hgt, thick), wmat);
      m.position.set(cx, y0 + hgt / 2, cz);
      m.rotation.y = rot ? Math.PI / 2 : 0;
      m.castShadow = m.receiveShadow = true;
      scene.add(m);
      const rr = rot ? [thick / 2, hgt / 2, ln / 2] : [ln / 2, hgt / 2, thick / 2];
      world.createCollider(RAPIER.ColliderDesc.cuboid(...rr)
        .setTranslation(cx, y0 + hgt / 2, cz));
    }
    for (const [cx, cz, ln, rot, door] of INTERIOR.walls) {
      if (door < 0) { seg(cx, cz, ln, rot, 0, WH, WT); continue; }
      // doorway: two flanking segments + a lintel above the gap
      const dCenter = -ln / 2 + door * ln;
      const l1 = Math.max(0.1, dCenter - DOOR_W / 2 + ln / 2);
      const l2 = Math.max(0.1, ln / 2 - dCenter - DOOR_W / 2);
      const off1 = -ln / 2 + l1 / 2, off2 = ln / 2 - l2 / 2;
      const o1x = rot ? cx : cx + off1, o1z = rot ? cz + off1 : cz;
      const o2x = rot ? cx : cx + off2, o2z = rot ? cz + off2 : cz;
      seg(o1x, o1z, l1, rot, 0, WH, WT);
      seg(o2x, o2z, l2, rot, 0, WH, WT);
      const lx = rot ? cx : cx + dCenter, lz = rot ? cz + dCenter : cz;
      seg(lx, lz, DOOR_W, rot, DOOR_H, WH - DOOR_H, WT);
    }
    // pillars: castle/temple great-hall columns (square, stone, collidable)
    for (const [px2, pz2] of INTERIOR.pillars || []) {
      const pm = new THREE.Mesh(new THREE.BoxGeometry(0.9, WH, 0.9), wmat);
      pm.position.set(px2, WH / 2, pz2);
      pm.castShadow = pm.receiveShadow = true;
      scene.add(pm);
      world.createCollider(RAPIER.ColliderDesc.cuboid(0.45, WH / 2, 0.45)
        .setTranslation(px2, WH / 2, pz2));
    }
    // torches: pooled flame lights (count FIXED at load — no shader recompiles)
    const flameG = new THREE.SphereGeometry(0.09, 6, 5);
    const flameM = new THREE.MeshBasicMaterial({ color: 0xffb347 });
    window.__torches = [];
    for (const [tx, tz] of (INTERIOR.torches || []).slice(0, 10)) {
      const pl = new THREE.PointLight(0xff9a3d, 14, 13, 1.8);
      pl.position.set(tx, WH * 0.62, tz);
      scene.add(pl);
      const fm = new THREE.Mesh(flameG, flameM);
      fm.position.copy(pl.position);
      scene.add(fm);
      window.__torches.push(pl);
    }
    // furniture from the shared props (collider = simple box)
    (async () => {
      const cache = {};
      for (const [name, fx, fz, fyaw] of INTERIOR.furniture || []) {
        try {
          if (!cache[name]) cache[name] = await loadGLB('props/' + name + '.glb');
          const inst = cache[name].scene.clone(true);
          inst.position.set(fx, 0, fz);
          inst.rotation.y = fyaw;
          inst.traverse(o => { if (o.isMesh) { o.castShadow = true; } });
          scene.add(inst);
          const bb = new THREE.Box3().setFromObject(inst);
          const sz = bb.getSize(new THREE.Vector3());
          world.createCollider(RAPIER.ColliderDesc.cuboid(
            Math.max(sz.x, 0.2) / 2, Math.max(sz.y, 0.2) / 2, Math.max(sz.z, 0.2) / 2)
            .setTranslation(fx, sz.y / 2, fz));
        } catch (e) { /* missing prop file: skip */ }
      }
    })();
    // indoor mood: dim the sun, warm the ambience, pull fog off, close camera
    sun.intensity *= 0.35;
    hemi.intensity *= 0.55;
    if (scene.fog) { scene.fog.near = 60; scene.fog.far = 160; }
    scene.background = new THREE.Color(0x0d0c0a);
    SPEC.camera.distance_m = Math.min(SPEC.camera.distance_m || 6, 4.6);
  }

  // GRASS: instanced cross-blades on the terrain, thinned along the walking
  // path — the "flat green plane" is gone. (Gated off for cities/snow.)
  if ((SPEC.world.scatter || []).length && SPEC.world.grass !== false) {
    // undergrowth stays PLANT-colored: pull toward green so brown forest
    // floors get living tufts, not floating tan cards
    const gcolA = new THREE.Color(...SPEC.world.ground_color)
      .lerp(new THREE.Color(0x4d7a33), 0.55).offsetHSL(0, 0.08, 0.13);   // lighter vs photo ground
    const gcolB = gcolA.clone().offsetHSL(0.02, 0.05, -0.07);
    // REAL blade shape: tapered to a tip, bowed forward, shaded dark at the
    // root — reads as grass, not floating rectangles
    const blade = new THREE.PlaneGeometry(0.10, 0.34, 1, 3);
    blade.translate(0, 0.17, 0);
    {
      const bp = blade.attributes.position;
      const bcol = new Float32Array(bp.count * 3);
      for (let i = 0; i < bp.count; i++) {
        const t = bp.getY(i) / 0.34;               // 0 root -> 1 tip
        bp.setX(i, bp.getX(i) * (1 - 0.85 * t));   // taper to a point
        bp.setZ(i, t * t * 0.07);                  // bow
        const sh = 0.66 + 0.34 * t;                // root shadow (was 0.5 — read as black spikes)
        bcol[i * 3] = sh; bcol[i * 3 + 1] = sh; bcol[i * 3 + 2] = sh;
      }
      blade.setAttribute('color', new THREE.BufferAttribute(bcol, 3));
      blade.computeVertexNormals();
    }
    const bmat = new THREE.MeshStandardMaterial({ side: THREE.DoubleSide, roughness: 1.0,
                                                  vertexColors: true });
    // WIND (Phase 81): blades sway from the tip, phase-shifted by world
    // position so gusts ripple across the meadow instead of ticking in sync
    bmat.onBeforeCompile = sh => {
      sh.uniforms.uWind = WIND_U;
      sh.vertexShader = 'uniform float uWind;\n' + sh.vertexShader.replace(
        '#include <begin_vertex>',
        ['#include <begin_vertex>',
         'vec4 wpW = instanceMatrix * vec4(position, 1.0);',
         'float wA = smoothstep(0.03, 0.34, position.y);',
         'transformed.x += sin(uWind * 1.7 + wpW.x * 0.5 + wpW.z * 0.35) * 0.055 * wA;',
         'transformed.z += cos(uWind * 1.35 + wpW.x * 0.33 + wpW.z * 0.5) * 0.045 * wA;'
        ].join('\n'));
    };
    const GR = Math.min(gsize * 0.48, 70);
    const GN = Math.min(13000, Math.floor(GR * GR * 2.2));
    const rngG = mulberry32(SPEC.seed + 21);
    for (const baseRot of [0, Math.PI / 2]) {
      const im = new THREE.InstancedMesh(blade, bmat, GN);
      im.frustumCulled = false;
      const M = new THREE.Matrix4(), RX = new THREE.Matrix4();
      const SV = new THREE.Vector3(), C = new THREE.Color();
      let placed = 0;
      for (let i = 0; i < GN * 2 && placed < GN; i++) {
        const x = (rngG() - 0.5) * 2 * GR, z = (rngG() - 0.5) * 2 * GR;
        if (pathDist(x, z) < CORR * 0.5 && rngG() < 0.7) continue;   // trodden path
        if (inBldg(x, z, 0.5)) continue;                             // not through floors
        const s = 0.7 + rngG() * 0.8;
        M.makeRotationY(baseRot + rngG() * 0.9)
          .multiply(RX.makeRotationX((rngG() - 0.5) * 0.5))          // random lean
          .scale(SV.set(s, s * (0.8 + rngG() * 0.5), s));
        M.setPosition(x, hAt(x, z), z);
        im.setMatrixAt(placed, M);
        im.setColorAt(placed, C.lerpColors(gcolA, gcolB, rngG()));
        placed++;
      }
      im.count = placed;
      im.instanceMatrix.needsUpdate = true;
      if (im.instanceColor) im.instanceColor.needsUpdate = true;
      scene.add(im);
    }
  }
  if (LVL && LVL.landmarks && landmarkAsset) {
    for (const [lx, lz, ls] of LVL.landmarks) {
      const inst = landmarkAsset.scene.clone(true);
      inst.traverse(o => { if (o.isMesh) o.castShadow = true; });
      placeProp(inst, lx, lz, ls, true);
    }
  }

  // RACE COURSE FURNITURE (scalable: derived entirely from the level path, so
  // ANY race in ANY world gets it): glowing gates mark the route, a checkered
  // banner marks the finish — players can SEE where the race goes.
  if ((SPEC.objectives || []).some(o => o.kind === 'race') && PATH && PATH.length > 2 && goalPos) {
    const gateMat = new THREE.MeshStandardMaterial({
      color: 0xffa227, emissive: 0xff7a00, emissiveIntensity: 1.6, roughness: 0.5 });
    const poleMat = new THREE.MeshStandardMaterial({ color: 0x222228, roughness: 0.6 });
    const step = Math.max(2, Math.floor(PATH.length / 6));
    for (let k = step; k < PATH.length - 1; k += step) {
      const [x, z] = PATH[k];
      const hd = Math.atan2(PATH[k + 1][0] - PATH[k][0], PATH[k + 1][1] - PATH[k][1]);
      const gate = new THREE.Group();
      const ring = new THREE.Mesh(new THREE.TorusGeometry(3.4, 0.15, 8, 28), gateMat);
      ring.position.y = 3.7;
      gate.add(ring);
      const arrow = new THREE.Mesh(new THREE.ConeGeometry(0.45, 1.0, 4), gateMat);
      arrow.rotation.x = Math.PI / 2;                 // cone points down-route
      arrow.position.y = 3.7;
      gate.add(arrow);
      gate.position.set(x, hAt(x, z), z);
      gate.rotation.y = hd;
      scene.add(gate);
    }
    const fin = new THREE.Group();                    // checkered finish banner
    const chk = document.createElement('canvas'); chk.width = 64; chk.height = 16;
    const cx2 = chk.getContext('2d');
    for (let i = 0; i < 8; i++) for (let j = 0; j < 2; j++) {
      cx2.fillStyle = (i + j) % 2 ? '#101014' : '#f2f2ee';
      cx2.fillRect(i * 8, j * 8, 8, 8);
    }
    const banner = new THREE.Mesh(new THREE.PlaneGeometry(9.5, 1.5),
      new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(chk), side: THREE.DoubleSide }));
    banner.position.y = 4.7;
    fin.add(banner);
    for (const sx of [-4.75, 4.75]) {
      const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 5.3, 8), poleMat);
      pole.position.set(sx, 2.65, 0);
      fin.add(pole);
    }
    fin.position.set(goalPos.x, goalPos.y, goalPos.z);
    fin.rotation.y = Math.atan2(goalPos.x - PATH[PATH.length - 2][0],
                                goalPos.z - PATH[PATH.length - 2][1]);
    scene.add(fin);
  }

  // ── Phase 33 dynamics: precipitation + wind ──────────────────────────────
  const WEATHER = SPEC.world.weather || 'none';
  const WIND = SPEC.world.wind ?? 0.5;
  let precip = null, precipVel = 0, precipBox = 46;
  if (WEATHER === 'rain' || WEATHER === 'snow') {
    const N = WEATHER === 'rain' ? 2200 : 1400;
    precipVel = WEATHER === 'rain' ? 20 : 1.6;
    const pos = new Float32Array(N * 3);
    const rngW = mulberry32(SPEC.seed + 913);
    for (let i = 0; i < N; i++) {
      pos[i * 3] = (rngW() - 0.5) * precipBox;
      pos[i * 3 + 1] = rngW() * 26;
      pos[i * 3 + 2] = (rngW() - 0.5) * precipBox;
    }
    const pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const pm = new THREE.PointsMaterial({
      color: WEATHER === 'rain' ? 0x9db8d8 : 0xffffff,
      size: WEATHER === 'rain' ? 0.055 : 0.12,
      transparent: true, opacity: WEATHER === 'rain' ? 0.55 : 0.85,
      sizeAttenuation: true, depthWrite: false });
    precip = new THREE.Points(pg, pm);
    precip.frustumCulled = false;
    scene.add(precip);
  }
  function stepDynamics(dt, playerPos, t) {
    if (precip) {
      const a = precip.geometry.attributes.position, arr = a.array, N = arr.length / 3;
      const drift = WIND * (WEATHER === 'snow' ? 1.6 : 0.7);
      for (let i = 0; i < N; i++) {
        arr[i * 3 + 1] -= precipVel * dt * (0.8 + (i % 5) * 0.1);
        arr[i * 3] += Math.sin(t * 1.3 + i) * drift * dt;
        if (arr[i * 3 + 1] < 0) {
          arr[i * 3 + 1] = 24 + (i % 7);
          arr[i * 3] = playerPos.x + (Math.random() - 0.5) * precipBox;
          arr[i * 3 + 2] = playerPos.z + (Math.random() - 0.5) * precipBox;
        }
      }
      a.needsUpdate = true;
    }
    if (WIND > 0.05) {
      for (const s of swayProps) {
        s.o.rotation.z = Math.sin(t * 1.1 + s.ph) * 0.018 * WIND
                       + Math.sin(t * 2.7 + s.ph * 2) * 0.008 * WIND;
      }
    }
  }

  // ── NPC entities: wander / follow template AI ────────────────────────────
  // START OVERLAY (game-design pass, 2026-07-06): every game opens like a
  // real game — title, mission, controls, a START button. The world idles as
  // a living backdrop; nothing moves until the player says go. Races then
  // count down 3…2…1…GO! before the grid (player included) can launch.
  const IS_RACE = (SPEC.objectives || []).some(o => o.kind === 'race');
  let raceGo = !IS_RACE;
  let gameStarted = false;
  let runT0 = 0;                          // run clock starts at START
  const bestKey = 'fs_best_' + (SPEC.title || 'game');
  const fmtT = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

  function startCountdown() {
    const cd = document.createElement('div');
    cd.style.cssText = 'position:fixed;top:36%;left:50%;transform:translate(-50%,-50%);'
      + 'font:800 96px system-ui;color:#ffd166;text-shadow:0 4px 26px rgba(0,0,0,.6);'
      + 'z-index:30;pointer-events:none;';
    document.body.appendChild(cd);
    let n = 3;
    cd.textContent = n;
    sfx('beep');
    const iv = setInterval(() => {
      n--;
      if (n > 0) { cd.textContent = n; sfx('beep'); }
      else if (n === 0) { cd.textContent = 'GO!'; raceGo = true; sfx('go'); }
      else { cd.remove(); clearInterval(iv); }
    }, 900);
  }

  {
    const objLines = (SPEC.objectives || []).map(o => {
      if (o.kind === 'race') return `Beat ${o.count} rivals to the finish`;
      if (o.kind === 'collect') return `Collect ${o.count} ${o.label}`;
      if (o.kind === 'defeat') return `Defeat ${o.count} ${o.label}`;
      if (o.kind === 'survive') return `Survive ${o.count} seconds of ${o.label || 'the onslaught'}`;
      return `Reach the ${o.label || 'beacon'}`;
    });
    if (!objLines.length) objLines.push('Reach the glowing beacon');
    const mode = SPEC.player.mode || 'walk';
    const controls = mode === 'drive'
      ? 'W throttle · S brake/reverse · A/D steer · Shift boost'
      : mode === 'fly'
        ? 'WASD glide · Space rise · C dive · Shift boost'
        : mode === 'swim'
          ? 'WASD swim · Space surface · C dive · Shift burst'
          : 'WASD / arrows move · Space jump · Shift run · F attack';
    const ov = document.createElement('div');
    ov.style.cssText = 'position:fixed;inset:0;display:flex;align-items:center;'
      + 'justify-content:center;background:rgba(8,7,14,.62);z-index:40;backdrop-filter:blur(3px);';
    // narrative layer: the LLM-written quest intro turns "collect 6 fireflies"
    // into a game with a WORLD — content, not code, so it can't break a build
    const introHtml = SPEC.intro
      ? `<div style="font:italic 400 15px Georgia,serif;color:#b9b4d8;margin-bottom:14px;max-width:44ch;margin-left:auto;margin-right:auto;line-height:1.5;">${SPEC.intro}</div>`
      : '';
    ov.innerHTML = '<div style="text-align:center;max-width:520px;padding:36px;">'
      + `<h1 style="font:800 40px system-ui;color:#fff;margin:0 0 10px;">${SPEC.title || 'Your World'}</h1>`
      + introHtml
      + `<div style="font:500 16px system-ui;color:#cfcbe6;margin-bottom:6px;">`
      + objLines.map(l => '• ' + l).join('<br>') + '</div>'
      + `<div style="font:400 13px system-ui;color:#8d89a6;margin-bottom:24px;">${controls} · drag to look</div>`
      + '<button id="startbtn" style="font:700 20px system-ui;color:#0d0b16;background:#5cffc9;'
      + 'border:none;border-radius:14px;padding:14px 46px;cursor:pointer;">START</button>'
      + '<div style="font:600 11px system-ui;color:#5cffc9;opacity:.65;margin-top:20px;letter-spacing:.6px;">'
      + '⚡ MADE WITH FANTASY STUDIO — one sentence → a playable world</div></div>';
    document.body.appendChild(ov);
    // personal best on the start screen — "one more run" fuel
    try {
      const pb = parseFloat(localStorage.getItem(bestKey));
      if (pb > 0) {
        const el = document.createElement('div');
        el.style.cssText = 'font:600 13px system-ui;color:#5cffc9;margin-top:10px;';
        el.textContent = `your best: ${fmtT(pb)}`;
        document.getElementById('startbtn').parentNode.insertBefore(
          el, document.getElementById('startbtn'));
      }
    } catch (e) {}
    document.getElementById('startbtn').addEventListener('click', () => {
      ov.remove();
      gameStarted = true;
      runT0 = performance.now();
      sfx('step');                        // gesture unlocks WebAudio + confirms start
      startAmbient();                     // Phase 69: wind bed (+ night crickets)
      if (IS_RACE) startCountdown();
    });
  }

  const npcs = [];
  const rngN = mulberry32(SPEC.seed + 31);
  let vehIdx = 0;                       // starting-grid slot for vehicle rivals
  // WAVE POOL (survive verb): extra hostiles are pre-built DORMANT at load
  // time — waking one costs nothing, so waves never cause loading hitches
  // (same no-mid-game-spikes philosophy as the collectible glow sprites)
  const surviveSecs = (SPEC.objectives || []).filter(o => o.kind === 'survive')
    .reduce((a, o) => a + (o.count || 0), 0);
  let wavePoolLeft = surviveSecs > 0
    ? Math.min(10, Math.ceil(surviveSecs / 20) * 2 + 1) : 0;
  for (const ent of SPEC.entities || []) {
    try {
      const gltf = await loadGLB(ent.asset);
      const hostile = ent.behavior === 'hostile';
      const hasAnims = !!(gltf.animations && gltf.animations.length);
      const baseN = ent.count || 1;
      let extraN = 0;
      if (hostile && wavePoolLeft > 0) { extraN = wavePoolLeft; wavePoolLeft = 0; }
      for (let i = 0; i < baseN + extraN; i++) {
        const dormant = i >= baseN;      // wave-pool member: hidden until woken
        // SkeletonUtils.clone — plain clone() breaks skinned meshes (gliding)
        const inst = skClone(gltf.scene);
        hardenAlpha(inst);
        const mats = [];
        inst.traverse(o => {
          if (o.isMesh) {
            o.castShadow = true; o.frustumCulled = false;
            // own materials so tint/flash is per-instance; ALL NPCs get the
            // night self-lift (their own texture as a faint emissive) — the
            // old flat red hostile glow rendered wolves as pink ghosts at
            // night. Menace now comes from a subtle warm shift + hit flash.
            const dark = pal.sun < 1.0;
            const ms = Array.isArray(o.material) ? o.material : [o.material];
            for (let mi = 0; mi < ms.length; mi++) {
              const m = ms[mi].clone();
              if (Array.isArray(o.material)) o.material[mi] = m; else o.material = m;
              m.side = THREE.DoubleSide;    // no hollow heads on NPCs either
              if (m.map) despeckleTexture(m);
              if (m.emissive !== undefined) {
                if (dark && m.map) m.emissiveMap = m.map;
                if (hostile) m.emissive.setRGB(dark ? 0.30 : 0.10, dark ? 0.16 : 0.02, dark ? 0.16 : 0.02);
                else if (dark) m.emissive.setScalar(0.24);
                m.needsUpdate = true;
              }
              if (hostile) mats.push(m);
            }
          }
        });
        const box = new THREE.Box3().setFromObject(inst);
        const h = Math.max(box.max.y - box.min.y, 1e-3);
        inst.scale.multiplyScalar((ent.height_m || 1.0) / h);
        alignLongAxis(inst, ent.behavior === 'vehicle');   // rivals drive nose-first too
        polishVehiclePaint(inst, ent.behavior === 'vehicle');
        const b2 = new THREE.Box3().setFromObject(inst);
        const holder = new THREE.Group();
        inst.position.y = -b2.min.y;
        holder.add(inst);
        let startYaw = rngN() * Math.PI * 2;
        if (ent.behavior === 'vehicle' && PATH && PATH.length > 1) {
          // STARTING GRID: rivals line up beside the player at the route start,
          // facing down the street — no more cars materializing inside blocks
          const hd = Math.atan2(PATH[1][0] - PATH[0][0], PATH[1][1] - PATH[0][1]);
          const rx = Math.cos(hd), rz = -Math.sin(hd);         // lateral (right)
          const lane = (vehIdx % 2 ? 1 : -1) * (2.4 + Math.floor(vehIdx / 2) * 0.001);
          const back = 5 + Math.floor(vehIdx / 2) * 5.5;
          holder.position.set(
            PATH[0][0] + rx * lane - Math.sin(hd) * back, 0,
            PATH[0][1] + rz * lane - Math.cos(hd) * back);
          startYaw = hd;
          vehIdx++;
        } else {
          // hostiles spawn FAR (out along the path, guarding the objectives)
          const spread = hostile ? 0.6 : 0.3;
          holder.position.set((rngN() - 0.5) * gsize * spread, 0, (rngN() - 0.5) * gsize * spread);
          if (hostile && Math.hypot(holder.position.x, holder.position.z) < 14) {
            holder.position.x += Math.sign(holder.position.x || 1) * 16;
          }
        }
        scene.add(holder);
        // per-instance animation: idle/walk/run clips crossfade with movement
        let anim = null;
        if (hasAnims) {
          const mixer = new THREE.AnimationMixer(inst);
          const acts = {};
          for (const c of gltf.animations) acts[c.name] = mixer.clipAction(c);
          const pick = w => acts[w] || acts[Object.keys(acts)[0]];
          anim = { mixer, idle: pick('idle'), walk: pick('walk'), run: pick('run'), cur: null };
          anim.cur = anim.idle; anim.cur.play();
        }
        if (dormant) holder.visible = false;
        holder.userData.fsTag = {            // Inspector hover-audit identity
          type: 'npc', name: ent.name || 'creature',
          detail: `${ent.behavior || 'wander'} · speed ${ent.speed || 1.5}`
                  + (hostile ? ` · hp ${ent.hp || 3}` : '') };
        npcs.push({ obj: holder, speed: ent.speed || 1.5, behavior: ent.behavior || 'wander',
                    target: null, yaw: startYaw, phase: rngN() * Math.PI * 2,
                    h: ent.height_m || 1.0,
                    hp: ent.hp || 3, cd: 0, dead: false, dieT: 0, mats, anim, dormant });
      }
    } catch (e) { fail(e.message); }
  }
  function wakeWave(px, pz, k) {
    // survive verb: wake k dormant hostiles in a ring around the player
    let woke = 0;
    for (const n of npcs) {
      if (!n.dormant || n.dead) continue;
      const a = rngN() * Math.PI * 2, d = 17 + rngN() * 6;
      n.obj.position.set(px + Math.cos(a) * d, 0, pz + Math.sin(a) * d);
      n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z);
      n.obj.visible = true; n.dormant = false;
      if (++woke >= k) break;
    }
    return woke;
  }
  function stepNPCs(dt, playerPos, t) {
    for (const n of npcs) {
      if (n.dormant) continue;           // wave-pool members sleep until woken
      // death animation: keel over + sink, then remove
      if (n.dead) {
        n.dieT += dt;
        n.obj.rotation.x = Math.min(n.dieT * 4, Math.PI / 2);
        if (n.dieT > 1.4) { scene.remove(n.obj); n.gone = true; }
        continue;
      }
      let tx = null, tz = null;
      if (n.behavior === 'hostile' && !won && !lost) {
        const d = Math.hypot(playerPos.x - n.obj.position.x, playerPos.z - n.obj.position.z);
        // BATTLE ROYALE (Phase 70): rivals fight EACH OTHER, not just the
        // player — each hostile hunts its nearest living rival when that
        // rival is closer than the player. Kills by rivals still count
        // toward last-one-standing (win = no rivals left, whoever fell them).
        if (HAS_BR) {
          let rv = null, rd = 1e9;
          for (const o2 of npcs) {
            if (o2 === n || o2.behavior !== 'hostile' || o2.dead || o2.dormant) continue;
            const dd = Math.hypot(o2.obj.position.x - n.obj.position.x,
                                  o2.obj.position.z - n.obj.position.z);
            if (dd < rd) { rd = dd; rv = o2; }
          }
          if (rv && rd < d && rd < 18) {
            // strike range must exceed the mutual-chase orbit radius (~3.2 m
            // measured) or rivals circle forever without landing a blow
            if (rd > 3.4) { tx = rv.obj.position.x; tz = rv.obj.position.z; }
            else {
              n.cd -= dt;
              if (n.cd <= 0) {
                n.cd = 1.3;
                rv.hp -= 1;
                for (const m of rv.mats || []) { if (m.emissive) m.emissive.setHex(0xff4444); }
                if (rv.hp <= 0 && !rv.dead) {
                  rv.dead = true;
                  burst(rv.obj.position.clone().add(new THREE.Vector3(0, 0.8, 0)), 0xff8a5c);
                  popText(`${n.name || 'rival'} eliminated ${rv.name || 'a rival'}`, '#ffb28a');
                }
              }
            }
            const moving = tx !== null;
            if (moving) {
              const dx = tx - n.obj.position.x, dz = tz - n.obj.position.z;
              n.yaw = THREE.MathUtils.damp(n.yaw, Math.atan2(dx, dz), 6, dt);
              n.obj.rotation.y = n.yaw;
              const sp = n.speed * dt;
              n.obj.position.x += Math.sin(n.yaw) * sp;
              n.obj.position.z += Math.cos(n.yaw) * sp;
              n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z);
            }
            if (n.anim) {
              const want = moving ? n.anim.run : n.anim.idle;
              if (want && want !== n.anim.cur) {
                want.reset(); want.crossFadeFrom(n.anim.cur, 0.2, true); want.play();
                n.anim.cur = want;
              }
              n.anim.mixer.update(dt);
            }
            continue;   // this rival is busy brawling — skip player logic
          }
        }
        const pSafe = inSafeZone(playerPos.x, playerPos.z);
        const nSafe = inSafeZone(n.obj.position.x, n.obj.position.z);
        if (pSafe && (d < 14 || nSafe)) {
          // the firelight holds them: back off to the edge of the glow
          const ang = Math.atan2(n.obj.position.x - pSafe.x,
                                 n.obj.position.z - pSafe.z);
          tx = pSafe.x + Math.sin(ang) * (pSafe.r + 3.0);
          tz = pSafe.z + Math.cos(ang) * (pSafe.r + 3.0);
        }
        else if (d < 14 && d > 1.7) { tx = playerPos.x; tz = playerPos.z; }   // chase
        else if (d <= 1.7) {                                                  // attack
          n.cd -= dt;
          if (n.cd <= 0) { n.cd = 1.2; playerHit(1); }
        } else if (!n.target || Math.hypot(n.target[0] - n.obj.position.x, n.target[1] - n.obj.position.z) < 0.6) {
          n.target = [(rngN() - 0.5) * gsize * 0.6, (rngN() - 0.5) * gsize * 0.6];
          tx = n.target[0]; tz = n.target[1];
        } else { tx = n.target[0]; tz = n.target[1]; }
      } else if (n.behavior === 'vehicle') {
        // RACE AI: drive the level path toward the goal, record finish order.
        // The grid holds until the countdown says GO.
        if (!raceGo) { /* engines revving */ }
        else if (!n.finished) {
          if (n.wp === undefined) { n.wp = 1; n.vjit = 0.85 + rngN() * 0.35; }
          const P2 = PATH || [[0, 0], [goalPos ? goalPos.x : 40, goalPos ? goalPos.z : 40]];
          const wpt = P2[Math.min(n.wp, P2.length - 1)];
          const dW = Math.hypot(wpt[0] - n.obj.position.x, wpt[1] - n.obj.position.z);
          if (dW < 3 && n.wp < P2.length - 1) n.wp++;
          else if (goalPos && Math.hypot(goalPos.x - n.obj.position.x, goalPos.z - n.obj.position.z) < 2.5) {
            n.finished = true; raceFinishers++;
          }
          tx = wpt[0]; tz = wpt[1];
        }
      } else if (n.behavior === 'flee') {
        // HUNTING PREY (Phase 66): grazes until it DETECTS the player, then
        // bolts away. Detection radius scales with how loud the player is —
        // standing 4 m, walking 9 m, RUNNING 22 m — so a hunt means slow,
        // patient approaches. Spooked prey calms after 6 s out of range.
        const d = Math.hypot(playerPos.x - n.obj.position.x, playerPos.z - n.obj.position.z);
        const loud = window.__pSpeed || 0;
        const hear = loud > 4 ? 22 : (loud > 0.4 ? 9 : 4);
        n.spook = Math.max(0, (n.spook || 0) - dt);
        if (d < hear) n.spook = 6;
        if (n.spook > 0 && d < 40) {
          const away = Math.atan2(n.obj.position.x - playerPos.x, n.obj.position.z - playerPos.z);
          tx = n.obj.position.x + Math.sin(away) * 18;
          tz = n.obj.position.z + Math.cos(away) * 18;
          n._fleeing = true;
        } else {
          n._fleeing = false;
          if (!n.target || Math.hypot(n.target[0] - n.obj.position.x, n.target[1] - n.obj.position.z) < 0.8) {
            n.target = [(rngN() - 0.5) * gsize * 0.6, (rngN() - 0.5) * gsize * 0.6];
          }
          tx = n.target[0]; tz = n.target[1];
        }
      } else if (n.behavior === 'follow') {
        const d = Math.hypot(playerPos.x - n.obj.position.x, playerPos.z - n.obj.position.z);
        if (d > 2.6) { tx = playerPos.x; tz = playerPos.z; }
      } else if (n.behavior === 'wander') {
        if (!n.target || Math.hypot(n.target[0] - n.obj.position.x, n.target[1] - n.obj.position.z) < 0.6) {
          n.target = [(rngN() - 0.5) * gsize * 0.6, (rngN() - 0.5) * gsize * 0.6];
        }
        tx = n.target[0]; tz = n.target[1];
      }
      const moving = tx !== null;
      if (moving) {
        const dx = tx - n.obj.position.x, dz = tz - n.obj.position.z;
        const want = Math.atan2(dx, dz);
        // vehicles steer smoothly (no pivot-in-place), creatures turn quicker
        n.yaw = THREE.MathUtils.damp(n.yaw, want, n.behavior === 'vehicle' ? 2.2 : 6, dt);
        n.obj.rotation.y = n.yaw;
        const sp = n.speed * (n.vjit || 1) * (n._fleeing ? 1.9 : 1) * dt;  // prey bolts
        n.obj.position.x += Math.sin(n.yaw) * sp;
        n.obj.position.z += Math.cos(n.yaw) * sp;
        n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z)
                         + (n.anim ? 0 : Math.abs(Math.sin(t * 7 + n.phase)) * 0.045);
      } else {
        n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z)
                         + (n.anim ? 0 : Math.sin(t * 2 + n.phase) * 0.01 + 0.01);
      }
      // side-scroller: creatures drift onto the gameplay lane too
      if (VIEW === 'side') {
        n.obj.position.z += (0 - n.obj.position.z) * Math.min(2.5 * dt, 1);
      }
      // blocks_enemies rule: placed solids are solid for NPCs too — a fence
      // line actually FENCES (push out radially from each segment)
      for (const b of npcBlockers) {
        const bx = n.obj.position.x - b.x, bz = n.obj.position.z - b.z;
        const bd = Math.hypot(bx, bz);
        if (bd < b.r) {
          const k2 = (b.r + 0.02) / Math.max(bd, 1e-4);
          n.obj.position.x = b.x + bx * k2;
          n.obj.position.z = b.z + bz * k2;
          n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z);
        }
      }
      // real gait: crossfade idle/walk/run with movement state (no more gliding)
      if (n.anim) {
        const want = moving ? ((n.behavior === 'hostile' && n.speed > 2.2) || n._fleeing
                               ? n.anim.run : n.anim.walk)
                            : n.anim.idle;
        if (want && want !== n.anim.cur) {
          want.reset(); want.crossFadeFrom(n.anim.cur, 0.2, true); want.play();
          n.anim.cur = want;
        }
        // Phase 66 anti-ice-skate: stride rate follows the NPC's ACTUAL speed
        // (clips are authored at ~2.5 m/s walk / ~5 m/s run cadence)
        if (moving && n.anim.cur) {
          const base = n.anim.cur === n.anim.run ? 5.0 : 2.5;
          n.anim.cur.timeScale = Math.min(Math.max(n.speed / base, 0.55), 1.7);
        }
        n.anim.mixer.update(dt);
      }
      // stay inside the walls
      const lim = gsize * 0.47;
      n.obj.position.x = THREE.MathUtils.clamp(n.obj.position.x, -lim, lim);
      n.obj.position.z = THREE.MathUtils.clamp(n.obj.position.z, -lim, lim);
    }
  }

  // ── MISSIONS: ordered objective steps (collect / defeat / reach) with a
  // quest-log HUD. Genres compose from these verbs (Phase 36).
  const objEl = document.getElementById('obj');
  const questEl = document.getElementById('quest');
  let steps = (SPEC.objectives || []).map(o => ({ ...o }));
  if (!steps.length && goalPos) steps = [{ kind: 'reach', label: 'the beacon', count: 1 }];
  else if (goalPos && steps.length && steps[steps.length - 1].kind !== 'reach')
    steps.push({ kind: 'reach', label: 'the beacon', count: 1 });
  let stepIdx = -1, kills = 0, won = false, lost = false, raceFinishers = 0;
  const collectibles = [];
  const rngC = mulberry32(SPEC.seed + 77);
  const cgeo = new THREE.SphereGeometry(0.11, 12, 10);
  let cpUsed = 0;                        // LVL.collect_points consumed so far
  // glow SPRITE, not a PointLight: per-collectible lights caused a full
  // shader recompile on every pickup (removing a light changes the lighting
  // program of EVERY material → the ~1s freeze players reported). A shared
  // additive sprite is visually identical and costs nothing to remove.
  const glowTex = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const g = c.getContext('2d');
    const grad = g.createRadialGradient(32, 32, 2, 32, 32, 30);
    grad.addColorStop(0, 'rgba(255,225,140,0.95)');
    grad.addColorStop(0.4, 'rgba(255,195,90,0.35)');
    grad.addColorStop(1, 'rgba(255,195,90,0)');
    g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  })();
  function makeGlow(scale) {
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: glowTex, transparent: true, blending: THREE.AdditiveBlending,
      depthWrite: false }));
    sp.scale.setScalar(scale);
    return sp;
  }

  // ── R-A JUICE: every action answers visually too ─────────────────────────
  // particle burst (pickups, kills), floating "+1" text, screen shake on hurt
  const bursts = [];
  const burstGeo = new THREE.SphereGeometry(0.05, 6, 5);
  function burst(pos, color) {
    const g = new THREE.Group();
    for (let i = 0; i < 10; i++) {
      const p = new THREE.Mesh(burstGeo,
        new THREE.MeshBasicMaterial({ color, transparent: true }));
      p.position.copy(pos);
      p.userData.v = new THREE.Vector3((Math.random() - 0.5) * 6,
                                       Math.random() * 5 + 2,
                                       (Math.random() - 0.5) * 6);
      g.add(p);
    }
    scene.add(g);
    bursts.push({ g, t: 0 });
  }
  function stepBursts(dt) {
    for (let i = bursts.length - 1; i >= 0; i--) {
      const b = bursts[i]; b.t += dt;
      for (const p of b.g.children) {
        p.position.addScaledVector(p.userData.v, dt);
        p.userData.v.y -= 12 * dt;
        p.material.opacity = Math.max(0, 1 - b.t / 0.6);
      }
      if (b.t > 0.6) {
        for (const p of b.g.children) p.material.dispose();
        scene.remove(b.g); bursts.splice(i, 1);
      }
    }
  }
  function popText(txt, color) {
    const d = document.createElement('div');
    d.textContent = txt;
    d.style.cssText = 'position:fixed;left:50%;top:42%;transform:translateX(-50%);'
      + `font:800 26px system-ui;color:${color};text-shadow:0 2px 10px rgba(0,0,0,.5);`
      + 'z-index:25;pointer-events:none;transition:all .7s ease-out;opacity:1;';
    document.body.appendChild(d);
    requestAnimationFrame(() => { d.style.top = '34%'; d.style.opacity = '0'; });
    setTimeout(() => d.remove(), 750);
  }
  let shakeT = 0;                        // seconds of screen shake remaining
  // collectibles that LOOK like what the prompt promised: preload the
  // generated mesh for any collect step that shipped one ("fire flames",
  // "pearls", "moon rocks") — orbs are only the fallback
  const collectTpl = {};
  for (let ci = 0; ci < steps.length; ci++) {
    const st = steps[ci];
    if (st.kind !== 'collect' || !st.asset) continue;
    try {
      const g = await loadGLB(st.asset);
      prepModel(g, 0.55, true);
      g.scene.traverse(o => {
        if (!o.isMesh) return;
        for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
          if (m && m.emissive !== undefined) {     // pickups glow, even at night
            if (m.map) m.emissiveMap = m.map;
            m.emissive.setScalar(0.6);
            m.needsUpdate = true;
          }
        }
      });
      collectTpl[ci] = g.scene;
    } catch (e) {
      console.warn('[game] collect asset fell back to orb:', e.message);
    }
  }
  function spawnCollectibles(step) {
    const pts = LVL && LVL.collect_points;
    const tpl = collectTpl[steps.indexOf(step)];   // generated mesh, if the spec baked one
    for (let i = 0; i < step.count; i++) {
      let s;
      if (tpl) {
        s = tpl.clone(true);
      } else {
        const m = new THREE.MeshStandardMaterial({
          color: 0xfff2b0, emissive: 0xffd54a, emissiveIntensity: 2.6, roughness: 0.4 });
        s = new THREE.Mesh(cgeo, m);
      }
      let cx, cz;
      if (pts && cpUsed < pts.length) { cx = pts[cpUsed][0]; cz = pts[cpUsed][1]; cpUsed++; }
      else {
        const ang = rngC() * Math.PI * 2;
        const d = 5 + rngC() * gsize * 0.32;
        cx = Math.cos(ang) * d; cz = Math.sin(ang) * d;
      }
      if (VIEW === 'side') cz = 0;        // side-scroller: pickups on the lane
      const baseY = hAt(cx, cz) + 1.0 + rngC() * 0.6;
      s.position.set(cx, baseY, cz);
      s.userData.fsTag = { type: 'collectible', name: step.label || 'item',
                           detail: 'collect it' };
      s.add(makeGlow(1.7));
      scene.add(s);
      collectibles.push({ mesh: s, baseY, phase: rngC() * Math.PI * 2 });
    }
  }
  // ── HEALTH PACKS: heart pickups on the ground — restore 1 HP on touch,
  // politely wait if you're already at full health (pro-game behavior)
  const healthPacks = [];
  {
    const n = SPEC.world.health_packs || 0;
    const rngH = mulberry32(SPEC.seed + 913);
    for (let i = 0; i < n; i++) {
      const geo = new THREE.OctahedronGeometry(0.16, 0);
      const m = new THREE.MeshStandardMaterial({
        color: 0xff5c6a, emissive: 0xff2438, emissiveIntensity: 1.6, roughness: 0.35 });
      const s = new THREE.Mesh(geo, m);
      const ang = rngH() * Math.PI * 2;
      const d = 8 + rngH() * (SPEC.world.size_m * 0.35 - 8);
      const hx = Math.cos(ang) * d, hz = VIEW === 'side' ? 0 : Math.sin(ang) * d;
      const hy = hAt(hx, hz) + 0.55;
      s.position.set(hx, hy, hz);
      s.userData.fsTag = { type: 'pickup', name: 'health pack', detail: '+1 ♥ on touch' };
      s.add(makeGlow(1.1));
      scene.add(s);
      healthPacks.push({ mesh: s, baseY: hy, phase: rngH() * Math.PI * 2 });
    }
  }
  // ── POINTS OF INTEREST (moon plan 2.1): templated micro-locations off the
  // path — ruined tower, campsite, shrine, stone circle, lumber camp. Each
  // is a prop cluster + a heart reward. Open worlds read as DESIGNED.
  if (!INTERIOR && LVL && LVL.pois && LVL.pois.length) {
    const stoneT = new THREE.TextureLoader().load('textures/stone.jpg');
    stoneT.wrapS = stoneT.wrapT = THREE.RepeatWrapping;
    stoneT.colorSpace = THREE.SRGBColorSpace;
    const stoneM = new THREE.MeshStandardMaterial({ map: stoneT, roughness: 0.95 });
    const rngP = mulberry32(SPEC.seed + 551);
    const addStone = (x, z, w, h, d2, ry) => {
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d2), stoneM);
      m.position.set(x, hAt(x, z) + h / 2 - 0.05, z);
      m.rotation.y = ry || 0;
      m.castShadow = m.receiveShadow = true;
      scene.add(m);
      if (h > 1.2) world.createCollider(RAPIER.ColliderDesc.cuboid(w / 2, h / 2, d2 / 2)
        .setTranslation(m.position.x, m.position.y, m.position.z));
    };
    const reward = (x, z) => {
      const geo = new THREE.OctahedronGeometry(0.16, 0);
      const mm = new THREE.MeshStandardMaterial({
        color: 0xff5c6a, emissive: 0xff2438, emissiveIntensity: 1.6, roughness: 0.35 });
      const sm = new THREE.Mesh(geo, mm);
      const hy2 = hAt(x, z) + 0.55;
      sm.position.set(x, hy2, z);
      scene.add(sm);
      healthPacks.push({ mesh: sm, baseY: hy2, phase: rngP() * 6.28 });
    };
    let fires = 0;
    const propC = {};
    const addProp = async (name, x, z, ry, sc2) => {
      try {
        if (!propC[name]) propC[name] = await loadGLB('props/' + name + '.glb');
        const inst = propC[name].scene.clone(true);
        inst.position.set(x, hAt(x, z), z);
        inst.rotation.y = ry || 0;
        if (sc2) inst.scale.multiplyScalar(sc2);
        inst.traverse(o => { if (o.isMesh) o.castShadow = true; });
        scene.add(inst);
      } catch (e) { /* prop not shipped: stones still make the POI */ }
    };
    for (const poi of LVL.pois) {
      const { kind, x, z, rot } = poi;
      if (kind === 'ruin') {
        // broken tower: partial ring of shattered wall stubs
        for (let k = 0; k < 6; k++) {
          const a = rot + k / 8 * Math.PI * 2;
          addStone(x + Math.cos(a) * 2.6, z + Math.sin(a) * 2.6,
                   1.3, 0.8 + rngP() * 2.6, 0.7, -a);
        }
        addProp('crate', x, z, rot);
      } else if (kind === 'camp') {
        addProp('log', x + 1.4, z, rot, 1);
        addProp('log', x - 1.2, z + 0.8, rot + 1.2, 1);
        addProp('barrel', x - 0.6, z - 1.5, 0);
        addStone(x, z, 0.9, 0.35, 0.9, rot);        // fire ring base
        if (fires < 2) {                             // light budget: max 2 fires
          fires++;
          const fl = new THREE.PointLight(0xff9a3d, 9, 11, 1.9);
          fl.position.set(x, hAt(x, z) + 0.8, z);
          scene.add(fl);
          window.__torches = window.__torches || [];
          window.__torches.push(fl);                 // reuse the flicker loop
        }
      } else if (kind === 'shrine') {
        addStone(x, z, 2.6, 0.4, 2.6, rot);
        addStone(x, z, 1.6, 0.35, 1.6, rot);
        addStone(x, z, 0.5, 2.2, 0.5, rot);
      } else if (kind === 'circle') {
        for (let k = 0; k < 6; k++) {
          const a = rot + k / 6 * Math.PI * 2;
          addStone(x + Math.cos(a) * 3.2, z + Math.sin(a) * 3.2,
                   0.7, 1.6 + rngP() * 1.0, 0.5, -a);
        }
      } else {                                       // lumber camp
        addProp('stump', x + 1.2, z + 0.6, 0);
        addProp('stump', x - 1.0, z - 0.8, 0);
        addProp('log', x, z + 1.6, rot, 1);
        addProp('crate', x - 1.6, z + 0.4, rot);
      }
      reward(x, z);
    }
  }
  function stepHealthPacks(dt, nt) {
    if (!healthPacks.length) return;
    const t = performance.now() / 1000;
    for (const p of healthPacks) {
      if (!p.mesh.parent) continue;
      p.mesh.position.y = p.baseY + Math.sin(t * 2 + p.phase) * 0.12;
      p.mesh.rotation.y += dt * 1.6;
      if (php < (P.hp || 5)
          && Math.hypot(p.mesh.position.x - nt.x, p.mesh.position.z - nt.z)
             < Math.max(1.4, (P.height_m || 1) * 0.9)) {
        scene.remove(p.mesh);
        php = Math.min(php + 1, P.hp || 5);
        renderHearts();
        sfx('pickup');
        burst(p.mesh.position, 0xff5c6a);
        popText('+1 ♥', '#ff8fa0');
      }
    }
  }

  // ── PLACED ITEMS (Phase 42 Inspector): objects at EXPLICIT coordinates —
  // click-to-place from the studio. Procedural props draw instantly (no
  // generation wait); any library noun arrives as a GLB like an entity.
  // Items with `interact` text are READABLE: walk up, press E.
  let inspectOn = false;                 // studio inspect mode (picking bridge)
  const placedItems = [];
  const interactables = [];
  function procProp(kind) {
    const g = new THREE.Group();
    const std = (c, e, ei) => new THREE.MeshStandardMaterial({
      color: c, emissive: e || 0x000000, emissiveIntensity: ei || 1, roughness: 0.7 });
    const add = (geo, mat, x, y, z, rx, ry, rz) => {
      const m = new THREE.Mesh(geo, mat);
      m.position.set(x || 0, y || 0, z || 0);
      if (rx) m.rotation.x = rx; if (ry) m.rotation.y = ry; if (rz) m.rotation.z = rz;
      g.add(m); return m;
    };
    if (kind === 'book') {
      add(new THREE.CylinderGeometry(0.30, 0.36, 0.5, 8), std(0x6f6a78), 0, 0.25);
      add(new THREE.BoxGeometry(0.36, 0.05, 0.5), std(0x7a2e2e), -0.16, 0.55, 0, 0, 0, 0.28);
      add(new THREE.BoxGeometry(0.36, 0.05, 0.5), std(0x7a2e2e), 0.16, 0.55, 0, 0, 0, -0.28);
      add(new THREE.BoxGeometry(0.30, 0.03, 0.44), std(0xf4ecd8, 0xf4ecd8, 0.35), -0.14, 0.58, 0, 0, 0, 0.28);
      add(new THREE.BoxGeometry(0.30, 0.03, 0.44), std(0xf4ecd8, 0xf4ecd8, 0.35), 0.14, 0.58, 0, 0, 0, -0.28);
      return { g, h: 0.75 };
    }
    if (kind === 'sign') {
      add(new THREE.CylinderGeometry(0.05, 0.07, 1.15, 8), std(0x6b4a2f), 0, 0.575);
      add(new THREE.BoxGeometry(0.95, 0.55, 0.07), std(0xa8845c, 0x604020, 0.25), 0, 1.25);
      return { g, h: 1.55 };
    }
    if (kind === 'chest') {
      add(new THREE.BoxGeometry(0.85, 0.45, 0.55), std(0x6b4a2f), 0, 0.225);
      add(new THREE.BoxGeometry(0.85, 0.2, 0.55), std(0x7d5636), 0, 0.5, -0.14, -0.6);
      add(new THREE.BoxGeometry(0.87, 0.09, 0.57), std(0xd9a441, 0xa87418, 0.5), 0, 0.32);
      return { g, h: 0.72 };
    }
    if (kind === 'building') {
      add(new THREE.BoxGeometry(4.4, 3.3, 3.7), std(0x9a8f7e), 0, 1.65);
      const roof = add(new THREE.ConeGeometry(3.35, 1.9, 4), std(0x6a4438), 0, 4.25, 0, 0, Math.PI / 4);
      roof.castShadow = true;
      add(new THREE.BoxGeometry(0.95, 1.7, 0.1), std(0x4c3423), 0, 0.85, 1.86);
      for (const wx of [-1.35, 1.35]) {
        add(new THREE.BoxGeometry(0.7, 0.7, 0.06), std(0xffd88a, 0xffc86a, 1.4), wx, 1.9, 1.87);
      }
      return { g, h: 5.2 };
    }
    if (kind === 'rock') {
      const geo = new THREE.DodecahedronGeometry(0.7, 0);
      const pos = geo.attributes.position;
      const rj = mulberry32(1234);
      for (let i = 0; i < pos.count; i++) {
        const s = 0.8 + rj() * 0.45;
        pos.setXYZ(i, pos.getX(i) * s, pos.getY(i) * (0.55 + rj() * 0.3), pos.getZ(i) * s);
      }
      geo.computeVertexNormals();
      const m = add(geo, new THREE.MeshStandardMaterial({
        color: 0x8b8d92, roughness: 0.95, flatShading: true }), 0, 0.45);
      m.castShadow = true;
      return { g, h: 1.0 };
    }
    if (kind === 'fence') {
      // one 2m segment — the studio's line tool tiles these A→B
      for (const px of [-0.95, 0.95]) {
        add(new THREE.BoxGeometry(0.13, 1.05, 0.13), std(0x6b4a2f), px, 0.525);
      }
      add(new THREE.BoxGeometry(2.05, 0.11, 0.09), std(0x7d5636), 0, 0.86);
      add(new THREE.BoxGeometry(2.05, 0.11, 0.09), std(0x7d5636), 0, 0.46);
      return { g, h: 1.1 };
    }
    if (kind === 'campfire') {
      for (const a of [0, 1.05, 2.1]) {
        add(new THREE.CylinderGeometry(0.07, 0.07, 0.95, 6), std(0x5b3d26),
            0, 0.09, 0, Math.PI / 2, a);
      }
      add(new THREE.ConeGeometry(0.26, 0.6, 8), std(0xff7a2a, 0xff5a10, 2.6), 0, 0.42);
      add(new THREE.ConeGeometry(0.13, 0.38, 8), std(0xffd23a, 0xffb810, 3.0), 0, 0.55);
      return { g, h: 0.85 };
    }
    // default / beacon: a glowing waypoint pillar
    add(new THREE.CylinderGeometry(0.34, 0.42, 0.3, 10), std(0x3a3550), 0, 0.15);
    add(new THREE.CylinderGeometry(0.12, 0.19, 2.2, 10), std(0xb9a0ff, 0x7c5cff, 2.2), 0, 1.35);
    return { g, h: 2.5 };
  }
  for (const [pIdx, it] of (SPEC.world.placed_items || []).entries()) {
    try {
      let obj, hgt = it.height_m || 0, pAnim = null;
      if (it.asset) {
        const gltf = await loadGLB(it.asset);
        obj = prepModel(gltf, hgt || 1.0, false).holder;
        // LIVING PLACEMENTS (Phase 48): placed creatures breathe — play the
        // idle clip instead of freezing in bind pose (shelter cats look home)
        if (gltf.animations && gltf.animations.length) {
          pAnim = new THREE.AnimationMixer(obj);
          const clip = gltf.animations.find(c => c.name === 'idle') || gltf.animations[0];
          pAnim.clipAction(clip).play();
        }
      } else {
        const pp = procProp((it.kind || 'beacon').toLowerCase());
        obj = pp.g;
        if (hgt > 0) obj.scale.multiplyScalar(hgt / pp.h); else hgt = pp.h;
      }
      const gy = hAt(it.x, it.z);
      obj.position.set(it.x, gy, it.z);
      obj.rotation.y = (it.yaw_deg || 0) * Math.PI / 180;
      obj.traverse(o => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
      obj.userData.fsTag = { type: 'placed', name: it.name || it.kind,
                             idx: pIdx, kind: it.kind, rules: it.rules || [],
                             detail: it.interact ? 'readable · walk up + press E' : it.kind };
      scene.add(obj);
      const bb = new THREE.Box3().setFromObject(obj);
      if (it.collide !== false && (bb.max.y - bb.min.y) > 0.5) {
        world.createCollider(RAPIER.ColliderDesc.cuboid(
          Math.max((bb.max.x - bb.min.x) / 2 * 0.8, 0.1), (bb.max.y - bb.min.y) / 2,
          Math.max((bb.max.z - bb.min.z) / 2 * 0.8, 0.1))
          .setTranslation(it.x, gy + (bb.max.y - bb.min.y) / 2, it.z));
      }
      if (it.interact) {
        const gl = makeGlow(1.5);
        gl.position.y = Math.min(hgt * 0.6, 1.2);
        obj.add(gl);
        interactables.push({ x: it.x, z: it.z, label: it.name || it.kind,
                             text: it.interact,
                             r: Math.max(2.1, (bb.max.x - bb.min.x)) });
      }
      placedItems.push({ obj, it, anim: pAnim,
                         r: Math.max((bb.max.x - bb.min.x), (bb.max.z - bb.min.z)) / 2 });
    } catch (e) { console.warn('[game] placed item failed:', e.message); }
  }
  // PLACED PROPS TELL THE TRUTH (Phase 44: rules come from the spec's rule
  // chips, all HONORED): safe_zone repels hostiles, blocks_enemies stops NPC
  // movement, hurts_touch damages the player standing in it.
  const _hasRule = (p, r) => (p.it.rules || []).includes(r)
    || (r === 'safe_zone' && ['campfire', 'beacon'].includes((p.it.kind || '').toLowerCase())
        && !(p.it.rules || []).length);
  const safeZones = placedItems.filter(p => _hasRule(p, 'safe_zone'))
    .map(p => ({ x: p.it.x, z: p.it.z, r: 6.0 }));
  const npcBlockers = placedItems.filter(p => _hasRule(p, 'blocks_enemies'))
    .map(p => ({ x: p.it.x, z: p.it.z, r: Math.max(p.r + 0.35, 0.8) }));
  const hurtZones = placedItems.filter(p => _hasRule(p, 'hurts_touch'))
    .map(p => ({ x: p.it.x, z: p.it.z, r: Math.max(p.r + 0.5, 1.2) }));
  function inSafeZone(x, z) {
    for (const s of safeZones) {
      if (Math.hypot(x - s.x, z - s.z) < s.r) return s;
    }
    return null;
  }
  let hurtCd = 0;
  function stepHurtZones(dt, nt) {
    hurtCd = Math.max(0, hurtCd - dt);
    if (hurtCd > 0) return;
    for (const h of hurtZones) {
      if (Math.hypot(nt.x - h.x, nt.z - h.z) < h.r) {
        hurtCd = 1.0;
        playerHit(1);
        return;
      }
    }
  }

  // ── BATTLE ROYALE storm zone (Phase 61, 'eliminate' objective) ───────────
  // A shrinking safe circle: outside it the player takes 1 HP/s. Rivals are
  // regular hostiles (the eliminate step counts kills), so the zone is the
  // genre pressure that forces engagement instead of camping.
  const HAS_BR = (SPEC.objectives || []).some(o => o.kind === 'eliminate');
  let storm = null;
  if (HAS_BR) {
    const R0 = gsize * 0.48, R1 = Math.max(9, gsize * 0.06), ZONE_T = 150;
    const wallMat = new THREE.MeshBasicMaterial({
      color: 0x7c5cff, transparent: true, opacity: 0.16,
      side: THREE.DoubleSide, depthWrite: false });
    const wall = new THREE.Mesh(
      new THREE.CylinderGeometry(1, 1, 26, 64, 1, true), wallMat);
    wall.position.y = 13;
    scene.add(wall);
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.985, 1.0, 96),
      new THREE.MeshBasicMaterial({ color: 0xa88bff, transparent: true,
        opacity: 0.85, side: THREE.DoubleSide, depthWrite: false }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.12;
    scene.add(ring);
    storm = { R0, R1, ZONE_T, t0: null, r: R0, wall, ring, hurtCd: 0 };
    // LOOT (Phase 70): supply crates — grab one for DOUBLE DAMAGE + a heart.
    // Seeded positions inside the first zone ring; glow so they read at range.
    const rngL = mulberry32(SPEC.seed + 404);
    storm.crates = [];
    for (let i = 0; i < 4; i++) {
      const a = rngL() * Math.PI * 2, r = 10 + rngL() * (R0 * 0.7);
      const x = Math.sin(a) * r, z = Math.cos(a) * r;
      const crate = new THREE.Mesh(
        new THREE.BoxGeometry(0.8, 0.8, 0.8),
        new THREE.MeshStandardMaterial({ color: 0x9a6b2f, roughness: 0.6,
          emissive: 0xffb347, emissiveIntensity: 0.35 }));
      crate.position.set(x, hAt(x, z) + 0.4, z);
      crate.rotation.y = rngL() * Math.PI;
      scene.add(crate);
      storm.crates.push(crate);
    }
  }
  function stepStorm(dt, nt) {
    if (!storm || won || lost) return;
    // LAST ONE STANDING (Phase 70): the win is standing alone — rivals felled
    // by OTHER rivals count too, not only the player's own kills.
    {
      const st = steps[stepIdx];
      if (st && st.kind === 'eliminate'
          && !npcs.some(n => n.behavior === 'hostile' && !n.dead && !n.dormant)) {
        advanceStep();
        return;
      }
    }
    if (storm.t0 === null) storm.t0 = performance.now();
    const u = Math.min((performance.now() - storm.t0) / 1000 / storm.ZONE_T, 1);
    storm.r = storm.R0 + (storm.R1 - storm.R0) * u;      // linear close
    storm.wall.scale.set(storm.r, 1, storm.r);
    storm.ring.scale.set(storm.r, storm.r, 1);
    storm.wall.material.opacity = 0.16 + 0.10 * Math.sin(performance.now() / 300);
    for (let i = storm.crates.length - 1; i >= 0; i--) {
      const c = storm.crates[i];
      c.rotation.y += dt * 0.9;
      if (Math.hypot(c.position.x - nt.x, c.position.z - nt.z) < 1.5) {
        scene.remove(c);
        storm.crates.splice(i, 1);
        atkDmg = 2;
        php = Math.min(php + 1, P.hp);
        renderHearts();
        sfx('pickup');
        burst(c.position.clone(), 0xffb347);
        popText('SUPPLY CRATE — double damage!', '#ffd9a8');
      }
    }
    storm.hurtCd -= dt;
    if (Math.hypot(nt.x, nt.z) > storm.r && storm.hurtCd <= 0) {
      storm.hurtCd = 1.0;
      playerHit(1);
      popText('storm!', '#b9a4ff');
    }
  }

  // ── SPORTS ball + goal (Phase 61, 'score' objective) ─────────────────────
  // Arcade ball physics (velocity + gravity + ground bounce + drag); walk
  // into the ball to kick it toward where you face. Goal mouth at the level
  // goal position; N goals wins. Ball resets to centre after each goal.
  const SCORE_OB = (SPEC.objectives || []).find(o => o.kind === 'score');
  let ball = null;
  if (SCORE_OB) {
    const bm = new THREE.Mesh(
      new THREE.SphereGeometry(0.42, 24, 18),
      new THREE.MeshStandardMaterial({ color: 0xf2f0e8, roughness: 0.5 }));
    // classic panel look: darker second hemisphere material would need UVs —
    // a simple dark band texture via vertex colors is overkill; keep clean.
    bm.castShadow = true;
    scene.add(bm);
    // goal mouth: two posts + crossbar at the goal position, facing spawn
    const gp = goalPos ? { x: goalPos.x, z: goalPos.z } : { x: 0, z: gsize * 0.3 };
    const yaw = Math.atan2(-gp.x, -gp.z);               // mouth faces origin
    const postMat = new THREE.MeshStandardMaterial({ color: 0xf5f5f5, roughness: 0.35 });
    const W = 6.4, H = 2.6;
    const goalGrp = new THREE.Group();
    for (const sx of [-1, 1]) {
      const post = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, H, 10), postMat);
      post.position.set(sx * W / 2, H / 2, 0);
      goalGrp.add(post);
    }
    const bar = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, W, 10), postMat);
    bar.rotation.z = Math.PI / 2;
    bar.position.y = H;
    goalGrp.add(bar);
    goalGrp.position.set(gp.x, 0, gp.z);
    goalGrp.rotation.y = yaw;
    scene.add(goalGrp);
    ball = { m: bm, v: new THREE.Vector3(), gp, yaw, W, H,
             reset() {
               this.m.position.set(0, 0.42 + hAt(0, 0), 0);
               this.v.set(0, 0, 0);
             } };
    ball.reset();
  }
  function stepBall(dt, nt) {
    if (!ball || won || lost) return;
    const p = ball.m.position, v = ball.v;
    // kick: player contact sends the ball where the PLAYER faces
    const pd = Math.hypot(p.x - nt.x, p.z - nt.z);
    if (pd < 1.35) {
      const dir = new THREE.Vector3(Math.sin(modelYaw), 0, Math.cos(modelYaw));
      const power = 9 + (keys['ShiftLeft'] || keys['ShiftRight'] ? 5 : 0);
      v.set(dir.x * power, 3.2, dir.z * power);
      sfx('hit');
    }
    v.y -= 22 * dt;                                     // gravity (arcadey)
    p.addScaledVector(v, dt);
    const gy = hAt(p.x, p.z) + 0.42;
    if (p.y < gy) { p.y = gy; v.y = Math.abs(v.y) * 0.45; v.x *= 0.985; v.z *= 0.985; }
    v.x *= (1 - 0.4 * dt); v.z *= (1 - 0.4 * dt);       // rolling drag
    const half = gsize / 2 - 1;
    if (Math.abs(p.x) > half) { p.x = Math.sign(p.x) * half; v.x *= -0.6; }
    if (Math.abs(p.z) > half) { p.z = Math.sign(p.z) * half; v.z *= -0.6; }
    ball.m.rotation.x += v.z * dt * 2; ball.m.rotation.z -= v.x * dt * 2;
    // goal test in the goal's local frame: |x| < W/2, y < H, crossing z=0 band
    const lx = Math.cos(-ball.yaw) * (p.x - ball.gp.x) - Math.sin(-ball.yaw) * (p.z - ball.gp.z);
    const lz = Math.sin(-ball.yaw) * (p.x - ball.gp.x) + Math.cos(-ball.yaw) * (p.z - ball.gp.z);
    if (Math.abs(lx) < ball.W / 2 && p.y < ball.H && Math.abs(lz) < 0.55) {
      const st = steps[stepIdx];
      if (st && st.kind === 'score') {
        st._goals = (st._goals || 0) + 1;
        sfx('win');
        burst(p.clone(), 0xffe27a);
        popText('GOAL!', '#ffe27a');
        renderQuest();
        ball.reset();
        if (st._goals >= st.count) advanceStep();
      } else {
        ball.reset();
      }
    }
  }

  // interact UI: proximity prompt + reading panel (books, signs, hints)
  let readable = null, reading = false;
  const intEl = document.createElement('div');
  intEl.style.cssText = 'position:fixed;left:50%;bottom:96px;transform:translateX(-50%);'
    + 'font:600 14px system-ui;color:#eceaf6;background:rgba(10,9,18,.74);'
    + 'border:1px solid rgba(255,255,255,.16);border-radius:10px;padding:8px 14px;'
    + 'z-index:24;display:none;pointer-events:none;';
  document.body.appendChild(intEl);
  const readEl = document.createElement('div');
  readEl.style.cssText = 'position:fixed;inset:0;display:none;align-items:center;'
    + 'justify-content:center;background:rgba(8,7,14,.55);z-index:44;backdrop-filter:blur(2px);';
  readEl.innerHTML = '<div style="max-width:460px;margin:20px;background:#141021;'
    + 'border:1px solid rgba(255,255,255,.14);border-radius:16px;padding:26px 30px;">'
    + '<div id="fs_read_t" style="font:800 18px system-ui;color:#ffd88a;margin-bottom:10px;"></div>'
    + '<div id="fs_read_b" style="font:400 15px/1.55 Georgia,serif;color:#eceaf6;white-space:pre-wrap;"></div>'
    + '<div style="margin-top:16px;font:600 11px system-ui;color:#807d99;">E or Esc to close</div></div>';
  document.body.appendChild(readEl);
  function setReading(r, item) {
    reading = r;
    readEl.style.display = r ? 'flex' : 'none';
    if (r && item) {
      document.getElementById('fs_read_t').textContent = (item.label || 'note').toUpperCase();
      document.getElementById('fs_read_b').textContent = item.text;
      sfx('beep');
    }
  }
  readEl.addEventListener('click', () => setReading(false));
  addEventListener('keydown', e => {
    if (e.code === 'KeyE') {
      if (reading) { setReading(false); return; }
      if (readable && gameStarted) setReading(true, readable);
    }
  });
  addEventListener('keydown', e => {      // Esc closes the page, not the game
    if (e.code === 'Escape' && reading) { setReading(false); e.stopImmediatePropagation(); }
  }, true);
  function stepInteract(nt) {
    if (!interactables.length) return;
    let best = null, bd = 1e9;
    for (const t of interactables) {
      const d = Math.hypot(t.x - nt.x, t.z - nt.z);
      if (d < t.r + 0.8 && d < bd) { bd = d; best = t; }
    }
    if (best !== readable) {
      readable = best;
      intEl.style.display = best ? 'block' : 'none';
      if (best) intEl.textContent = `E — read the ${best.label}`;
    }
  }
  if (interactables.length) {
    const hint = document.querySelector('#hud .hint');
    if (hint) hint.textContent += ' · E to read';
  }

  // CAPTURE verb (Phase 72): glowing ground rings — stand inside to raise the
  // capture meter; a living hostile inside CONTESTS the zone (meter pauses,
  // ring flashes red). One zone active at a time.
  const CAP_R = 4.0, CAP_HOLD = 8.0;
  function spawnCaptureZones(st) {
    const rngC = mulberry32(SPEC.seed + 909);
    st._zones = [];
    for (let i = 0; i < st.count; i++) {
      const a = rngC() * Math.PI * 2, d = 16 + rngC() * gsize * 0.24;
      const x = Math.cos(a) * d, z = Math.sin(a) * d;
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(CAP_R - 0.5, CAP_R, 40),
        new THREE.MeshBasicMaterial({ color: 0x5cffc9, transparent: true,
                                      opacity: 0.55, side: THREE.DoubleSide }));
      ring.rotation.x = -Math.PI / 2;
      ring.position.set(x, hAt(x, z) + 0.06, z);
      const glow = new THREE.PointLight(0x5cffc9, 1.4, 12);
      glow.position.set(x, hAt(x, z) + 1.4, z);
      ring.visible = glow.visible = (i === 0);
      scene.add(ring); scene.add(glow);
      st._zones.push({ x, z, ring, glow });
    }
  }
  function stepCapture(st, px, pz, dt) {
    const zn = st._zones && st._zones[st._zi];
    if (!zn) return;
    const inside = Math.hypot(px - zn.x, pz - zn.z) < CAP_R;
    const contested = inside && npcs.some(n => n.behavior === 'hostile' && !n.dead && !n.dormant
      && Math.hypot(n.obj.position.x - zn.x, n.obj.position.z - zn.z) < CAP_R);
    zn.ring.material.color.setHex(contested ? 0xff5c6a : (inside ? 0xaefff0 : 0x5cffc9));
    zn.ring.material.opacity = inside ? 0.85 : 0.55;
    if (inside && !contested) {
      st._hold += dt;
      if (st._hold >= CAP_HOLD) {
        zn.ring.visible = zn.glow.visible = false;
        st._zi++; st._hold = 0;
        popText(`Zone ${st._zi}/${st.count} captured!`, '#5cffc9');
        sfx('pickup');
        const nx = st._zones[st._zi];
        if (nx) { nx.ring.visible = nx.glow.visible = true; }
        else { advanceStep(); return; }
      }
      renderQuest();
    } else if (st._hold > 0 && !inside) {
      st._hold = Math.max(0, st._hold - dt * 0.5);   // meter decays when you leave
      renderQuest();
    }
  }
  function stepLabel(st) {
    if (st.kind === 'collect') return `Collect ${st.count} ${st.label || 'items'}`;
    if (st.kind === 'defeat') return `Defeat ${st.count} ${st.label || 'enemies'}`;
    if (st.kind === 'race') return `Win the race (${st.count} ${st.label || 'rivals'})`;
    if (st.kind === 'survive') return `Survive ${st.label || 'the onslaught'}`;
    if (st.kind === 'eliminate') return `Last one standing — eliminate ${st.count} ${st.label || 'rivals'}`;
    if (st.kind === 'hunt') return `Hunt ${st.count} ${st.label || 'prey'} (approach quietly)`;
    if (st.kind === 'score') return `Score ${st.count} ${st.label || 'goals'}`;
    if (st.kind === 'capture') return `Capture ${st.count} zone${st.count > 1 ? 's' : ''} (hold 8s each)`;
    return `Reach ${st.label || 'the beacon'}`;
  }
  function stepProgress(st) {
    if (st.kind === 'collect') return `${st._got || 0}/${st.count}`;
    if (st.kind === 'defeat' || st.kind === 'eliminate' || st.kind === 'hunt')
      return `${Math.min(kills - (st._k0 || 0), st.count)}/${st.count}`;
    if (st.kind === 'score') return `${st._goals || 0}/${st.count}`;
    if (st.kind === 'capture') {
      const pct = st._hold ? ` · ${Math.min(99, Math.round(st._hold / 8 * 100))}%` : '';
      return `${st._zi || 0}/${st.count}${pct}`;
    }
    if (st.kind === 'survive') {
      const left = st._t0 === undefined ? st.count
        : Math.max(0, Math.ceil(st.count - (performance.now() - st._t0) / 1000));
      return `${left}s`;
    }
    return '';
  }
  function renderQuest() {
    if (!steps.length) return;
    questEl.style.display = 'block';
    questEl.innerHTML = steps.map((st, i) => {
      const cls = i < stepIdx ? 'qs done' : (i === stepIdx ? 'qs active' : 'qs');
      const mark = i < stepIdx ? '✓' : (i === stepIdx ? '▸' : '·');
      const prog = i === stepIdx ? ' ' + stepProgress(st) : '';
      return `<div class="${cls}">${mark} ${stepLabel(st)}${prog}</div>`;
    }).join('');
    const st = steps[stepIdx];
    if (st) {
      objEl.style.display = 'block';
      const p = stepProgress(st);
      objEl.textContent = stepLabel(st) + (p ? ` — ${p}` : '');
    }
  }
  function advanceStep() {
    stepIdx++;
    const st = steps[stepIdx];
    if (!st) {
      // reward beats narrative beats generic — most specific line wins
      doWin(SPEC.reward ? `You won the ${SPEC.reward}!`
            : (SPEC.win_text || 'Mission complete!'));
      return;
    }
    if (st.kind === 'collect') { st._got = 0; spawnCollectibles(st); }
    if (st.kind === 'defeat' || st.kind === 'eliminate' || st.kind === 'hunt') { st._k0 = kills; }
    if (st.kind === 'score') { st._goals = 0; }
    if (st.kind === 'capture') { st._zi = 0; st._hold = 0; spawnCaptureZones(st); }
    renderQuest();
  }
  let won_ = false;   // guard alias kept for clarity in doWin
  function doWin(text) {
    if (won || lost) return;
    won = true; won_ = true;
    sfx('win');
    // run time + personal best (localStorage) — every win answers "how well?"
    try {
      const secs = (performance.now() - runT0) / 1000;
      const prev = parseFloat(localStorage.getItem(bestKey));
      const isPB = !(prev > 0) || secs < prev;
      if (isPB) localStorage.setItem(bestKey, String(secs));
      // MEDALS: par derives from the actual level geometry — the distance a
      // player must cover (spawn → collect points → goal) at cruise speed,
      // with slack for looking around. Same formula for every game class.
      let travel = Math.hypot(goalPos.x, goalPos.z);
      const cps = (LVL && LVL.collect_points) || [];
      let px = 0, pz = 0;
      for (const p of cps) { travel += Math.hypot(p[0] - px, p[1] - pz); px = p[0]; pz = p[1]; }
      const par = Math.max(20, travel / Math.max(P.walk_speed, 1) * 1.5);
      const medal = secs <= par ? '🥇 GOLD' : secs <= par * 1.6 ? '🥈 SILVER'
                  : secs <= par * 2.6 ? '🥉 BRONZE' : '';
      document.getElementById('wintime').textContent =
        (medal ? medal + ' · ' : '') + `time ${fmtT(secs)}`
        + (isPB ? ' — new personal best!' : ` · best ${fmtT(prev)}`);
    } catch (e) {}
    document.getElementById('wintext').textContent = text;
    document.getElementById('win').style.display = 'flex';
    // Game Projects: hub passes ?next=<url> for level progression
    const nxt = new URLSearchParams(location.search).get('next');
    if (nxt && /^[\w./?=-]+$/.test(nxt)) {
      const a = document.getElementById('nextlvl');
      a.href = nxt; a.style.display = 'inline-block';
    }
    if (location.pathname.includes('/levels/')) {
      const b = document.getElementById('backhub');
      b.href = '../../../'; b.style.display = 'inline-block';
    }
    console.log('[game] WIN — ' + text);
  }

  // ── COMBAT: player health + hearts, damage vignette, lose state ──────────
  let php = SPEC.player.hp || 5;
  const maxHp = php;
  const heartsEl = document.getElementById('hearts');
  const hostilesExist = (SPEC.entities || []).some(e => e.behavior === 'hostile');
  function renderHearts() {
    if (!hostilesExist) return;
    heartsEl.style.display = 'block';
    heartsEl.textContent = '♥'.repeat(php) + '♡'.repeat(Math.max(0, maxHp - php));
    heartsEl.style.color = php <= 1 ? '#ff5c6a' : '#ff8fa0';
  }
  renderHearts();
  function doLose(text) {
    if (won || lost) return;
    lost = true;
    sfx('lose');
    document.getElementById('losetext').textContent = text;
    document.getElementById('lose').style.display = 'flex';
    console.log('[game] LOSE — ' + text);
  }
  const dmgEl = document.getElementById('dmg');
  function playerHit(dmg) {
    if (won || lost) return;
    php = Math.max(0, php - dmg);
    sfx('hurt');
    shakeT = 0.3;                        // impact you can FEEL
    renderHearts();
    dmgEl.style.opacity = '1';
    setTimeout(() => { dmgEl.style.opacity = '0'; }, 160);
    if (php <= 0) doLose('Overwhelmed by enemies.');
  }

  // ── player: animated GLB + kinematic capsule ─────────────────────────────
  let mixer = null, actions = {}, current = null;
  const P = SPEC.player;
  const pg = await loadGLB(P.asset);            // hard fail = visible error
  const { holder, root: pRoot, radius } =
    prepModel(pg, P.height_m, ['fly', 'swim'].includes(P.mode || 'walk'));
  // ORIENTATION (2026-07-06 rewrite — heuristics OUT, baked truth IN):
  // generated assets now leave the bake with render-VERIFIED orientation
  // (silhouette-matched against their reference), so the runtime stops
  // guessing. Only two facts survive here, both render-verified:
  //   drive/swim travel along their long axis → align long axis to +Z
  //   (car nose is +X per the 2026-07-05 axis renders; whale body likewise).
  //   Flyers keep their wingspan lateral — no rotation at all.
  alignLongAxis(pRoot, ['drive', 'swim'].includes(P.mode || 'walk'));
  polishVehiclePaint(pRoot, (P.mode || 'walk') === 'drive');
  holder.rotation.y = THREE.MathUtils.degToRad(P.yaw_offset_deg || 0);

  // PROCEDURAL MOTION (Phase 20 lite): no rig required — the mesh itself
  // deforms in the vertex shader, keyed off geometry, so it works for ANY
  // generated creature. Swimmers get a traveling nose→tail body wave (the
  // whale finally *swims*); flyers get a wing flap that grows toward the
  // wingtips. Amplitude follows speed: gentle at idle, full when moving.
  // HERO DE-BLOTCH (Phase 95): the speckle/blotch filter only ran on
  // vehicles — characters kept raw generated textures. Every material with
  // a texture on the player now gets the same one-time clean.
  pRoot.traverse(o => {
    if (!o.isMesh) return;
    for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
      if (m && m.map) despeckleTexture(m);
    }
  });
  const procShaders = [];
  if (P.mode === 'fly' || P.mode === 'swim') {
    pRoot.traverse(o => {
      if (!o.isMesh || o.isSkinnedMesh) return;
      o.geometry.computeBoundingBox();
      const bb = o.geometry.boundingBox;
      const sx = Math.max(bb.max.x - bb.min.x, 1e-3);
      const sz = Math.max(bb.max.z - bb.min.z, 1e-3);
      const chunk = P.mode === 'swim'
        ? `float tf = clamp((${bb.max.z.toFixed(4)} - position.z) / ${sz.toFixed(4)}, 0.0, 1.0);
           float wv = sin(uTime * 3.2 - position.z * ${(5.0 / sz).toFixed(4)}) * uAmp * tf * tf;
           transformed.y += wv * ${(sz * 0.055).toFixed(4)};
           transformed.x += wv * ${(sz * 0.02).toFixed(4)};`
        : `float wf = smoothstep(${(0.10 * sx).toFixed(4)}, ${(0.50 * sx).toFixed(4)}, abs(position.x));
           float fl = sin(uTime * 5.2) * uAmp * wf;
           transformed.y += abs(position.x) * fl * 0.5;
           transformed.z -= abs(position.x) * abs(fl) * 0.06;`;
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        if (!m) continue;
        m.onBeforeCompile = sh => {
          sh.uniforms.uTime = { value: 0 };
          sh.uniforms.uAmp = { value: 0.35 };
          sh.vertexShader = 'uniform float uTime;\nuniform float uAmp;\n'
            + sh.vertexShader.replace('#include <begin_vertex>',
                                      '#include <begin_vertex>\n' + chunk);
          procShaders.push(sh);
        };
        m.needsUpdate = true;
      }
    });
  }
  const playerObj = new THREE.Group();
  playerObj.add(holder);
  scene.add(playerObj);

  // NIGHT READABILITY: dark palettes get a soft moonlit fill parented to the
  // CAMERA — it always lights the side of the hero the player is looking at,
  // for any orbit angle. The atmosphere stays; the character never vanishes.
  if (pal.sun < 1.0) {
    scene.add(camera);                       // camera needs to be in the graph
    const fill = new THREE.PointLight(0xc3d6ff, pal.sun < 0.7 ? 120 : 40, 30, 1.9);
    fill.position.set(0, 0.6, 0.4);          // just above/behind the lens
    camera.add(fill);
    hemi.intensity = Math.max(hemi.intensity, 0.34);
    // "moonlit hero" grade: the player's own texture doubles as a faint
    // emissive map, so a dark-furred/dark-armored hero still reads at night
    holder.traverse(o => {
      if (!o.isMesh) return;
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        if (m && m.emissive !== undefined && m.map) {
          m.emissiveMap = m.map; m.emissive.setScalar(0.34); m.needsUpdate = true;
        } else if (m && m.emissive) {
          m.emissive.setScalar(0.12);
        }
      }
    });
  }

  if (pg.animations && pg.animations.length) {
    mixer = new THREE.AnimationMixer(pg.scene);
    for (const clip of pg.animations) actions[clip.name] = mixer.clipAction(clip);
    const pick = want => actions[P.anims[want]] || actions[want] ||
                         actions[Object.keys(actions)[0]];
    actions.__idle = pick('idle'); actions.__walk = pick('walk'); actions.__run = pick('run');
    actions.__attack = actions['attack'] || null;    // one-shot swing overlay
    if (actions.__attack) {
      actions.__attack.setLoop(THREE.LoopOnce, 1);
      actions.__attack.clampWhenFinished = false;
    }
    current = actions.__idle; current.play();
  } else {
    console.warn('[game] player GLB has no animations — static fallback');
  }
  let attackUntil = 0;                 // swing overlay suppresses the locomotion FSM
  function setAnim(next) {
    if (!mixer || !next || next === current) return;
    if (performance.now() < attackUntil) return;
    next.reset(); next.crossFadeFrom(current, 0.22, true); next.play();
    current = next;
  }
  function playAttackAnim() {
    if (!mixer || !actions.__attack) return 0;
    const a = actions.__attack;
    // SNAPPY SWING (2026-07-19 'attack always lags'): the baked clip has a
    // windup — skip its first 10% and play fast enough that the whole swing
    // lands in ~0.45 s. Input-to-impact now reads instant.
    const clip = a.getClip();
    a.timeScale = Math.max(1, clip.duration / 0.45);
    const dur = Math.min(clip.duration / a.timeScale, 0.5);
    a.reset(); a.setEffectiveWeight(1);
    a.time = clip.duration * 0.10;
    a.crossFadeFrom(current, 0.05, true); a.play();
    current = a;
    attackUntil = performance.now() + dur * 1000;
    setTimeout(() => {                 // return to locomotion after the swing
      attackUntil = 0;
      const back = actions.__idle;
      if (back) { back.reset(); back.crossFadeFrom(a, 0.15, true); back.play(); current = back; }
    }, dur * 1000);
    return dur;
  }

  // WEAPON IN HAND (bipeds): a real katana / bow parented to the hand bone —
  // it moves with the swing. Procedural, so every melee/ranged prompt gets one.
  (() => {
    const atkMode = (SPEC.player.attack && SPEC.player.attack !== 'none')
      ? SPEC.player.attack
      : ((SPEC.entities || []).some(e => e.behavior === 'hostile') ? 'melee' : 'none');
    if (atkMode === 'none') return;
    let handBone = null;
    pg.scene.traverse(o => { if (!handBone && o.isBone && /hand_R/i.test(o.name)) handBone = o; });
    if (!handBone) return;
    const w = new THREE.Group();
    if (atkMode === 'ranged') {
      const bow = new THREE.Mesh(
        new THREE.TorusGeometry(0.30, 0.013, 8, 24, Math.PI),
        new THREE.MeshStandardMaterial({ color: 0x6b4a2a, roughness: 0.8 }));
      bow.rotation.z = -Math.PI / 2;
      const str = new THREE.Mesh(
        new THREE.CylinderGeometry(0.003, 0.003, 0.60, 4),
        new THREE.MeshBasicMaterial({ color: 0xded8c4 }));
      w.add(bow, str);
    } else {
      const blade = new THREE.Mesh(
        new THREE.BoxGeometry(0.028, 0.62, 0.009),
        new THREE.MeshStandardMaterial({ color: 0xd9dfe8, metalness: 0.95, roughness: 0.22 }));
      blade.position.y = 0.37;
      const guard = new THREE.Mesh(
        new THREE.BoxGeometry(0.095, 0.018, 0.034),
        new THREE.MeshStandardMaterial({ color: 0x7a6428, metalness: 0.7, roughness: 0.45 }));
      guard.position.y = 0.055;
      const grip = new THREE.Mesh(
        new THREE.CylinderGeometry(0.015, 0.015, 0.17, 8),
        new THREE.MeshStandardMaterial({ color: 0x241d2b, roughness: 0.9 }));
      grip.position.y = -0.04;
      w.add(blade, guard, grip);
    }
    w.traverse(o => { if (o.isMesh) o.castShadow = true; });
    w.rotation.x = Math.PI / 2;          // lie along the hand's forward
    handBone.add(w);
  })();

  const capR = Math.min(Math.max(radius * 0.6, 0.22), 0.6);
  const capHalf = Math.max(P.height_m / 2 - capR, 0.1);
  // spawn ON the terrain, never at flat-world height: on hilly or seabed
  // worlds a flat spawn embeds the capsule in the ground and the character
  // controller blocks EVERY move (whale glued to the seabed, dragon molded
  // into the hillside — the "keys turn but nothing moves" bug)
  function spawnHeight(x, z) {
    const g = hAt(x, z) + P.height_m / 2 + 0.15;
    if (SPEC.player.mode === 'fly') return g + 6;              // airborne start
    if (SPEC.player.mode === 'swim' && SPEC.world.water_level != null)
      return Math.max(g + 0.4,                                  // clear of seabed,
        Math.min((hAt(x, z) + SPEC.world.water_level) / 2,      // mid-water,
                 SPEC.world.water_level - P.height_m / 2 - 0.2)); // under surface
    return g;
  }
  const body = world.createRigidBody(
    RAPIER.RigidBodyDesc.kinematicPositionBased().setTranslation(0, spawnHeight(0, 0), 0));
  const collider = world.createCollider(RAPIER.ColliderDesc.capsule(capHalf, capR), body);
  const kcc = world.createCharacterController(0.02);
  kcc.setApplyImpulsesToDynamicBodies(false);
  kcc.enableAutostep(0.3, 0.15, true);
  kcc.enableSnapToGround(0.3);
  let vy = 0;

  // ── input: keyboard + gamepad + touch stick ──────────────────────────────
  const keys = {};
  addEventListener('keydown', e => { keys[e.code] = true; });
  addEventListener('keyup', e => { keys[e.code] = false; });
  const FLY = SPEC.player.mode === 'fly';   // dragons/birds/aircraft — flight loop below
  const SWIM = SPEC.player.mode === 'swim'; // whales/sharks/subs — swim loop below
  let yaw = 0, pitch = 0.35, dragging = false, px = 0, py = 0;
  let camZoom = 1, freeLookT = 0;   // wheel zoom · seconds of free-look after a drag
  addEventListener('wheel', e => {
    camZoom = THREE.MathUtils.clamp(camZoom * (1 + Math.sign(e.deltaY) * 0.09), 0.45, 2.6);
  }, { passive: true });
  renderer.domElement.addEventListener('pointerdown', e => {
    if (e.target.closest('#stick')) return;
    // inspect mode keeps camera DRAG-look; a still click (no movement) picks
    dragging = true; px = e.clientX; py = e.clientY;
  });
  addEventListener('pointerup', () => dragging = false);
  addEventListener('pointermove', e => {
    if (!dragging) return;
    if (SPEC.view && SPEC.view !== '3d') return;   // 2D views: fixed camera axis
    yaw -= (e.clientX - px) * 0.005; pitch = THREE.MathUtils.clamp(pitch + (e.clientY - py) * 0.004, 0.05, 1.2);
    px = e.clientX; py = e.clientY;
    freeLookT = 3;
  });
  // touch joystick
  const stick = document.getElementById('stick'), nub = document.getElementById('nub');
  let stickVec = { x: 0, y: 0 };
  if (stick) {
    stick.addEventListener('pointerdown', e => stick.setPointerCapture(e.pointerId));
    stick.addEventListener('pointermove', e => {
      if (e.buttons === 0) return;
      const r = stick.getBoundingClientRect();
      let dx = (e.clientX - r.left - 52) / 52, dy = (e.clientY - r.top - 52) / 52;
      const m = Math.hypot(dx, dy); if (m > 1) { dx /= m; dy /= m; }
      stickVec = { x: dx, y: dy };
      nub.style.left = 32 + dx * 30 + 'px'; nub.style.top = 32 + dy * 30 + 'px';
    });
    const reset = () => { stickVec = { x: 0, y: 0 }; nub.style.left = '32px'; nub.style.top = '32px'; };
    stick.addEventListener('pointerup', reset); stick.addEventListener('pointercancel', reset);
  }
  function readMove() {
    let x = 0, z = 0, run = false;
    if (keys.KeyW || keys.ArrowUp) z -= 1;
    if (keys.KeyS || keys.ArrowDown) z += 1;
    if (keys.KeyA || keys.ArrowLeft) x -= 1;
    if (keys.KeyD || keys.ArrowRight) x += 1;
    run = !!(keys.ShiftLeft || keys.ShiftRight);
    const gps = navigator.getGamepads ? navigator.getGamepads() : [];
    for (const gp of gps) {
      if (!gp) continue;
      if (Math.abs(gp.axes[0]) > 0.15) x += gp.axes[0];
      if (Math.abs(gp.axes[1]) > 0.15) z += gp.axes[1];
      if (Math.abs(gp.axes[2] || 0) > 0.2) yaw -= gp.axes[2] * 0.03;
      run = run || (gp.buttons[10] && gp.buttons[10].pressed);
    }
    x += stickVec.x; z += stickVec.y;
    const m = Math.hypot(x, z);
    if (m > 1) { x /= m; z /= m; }
    return { x, z, run, mag: Math.min(m, 1) };
  }

  // ── player ATTACK: melee arc (sword and claws) or ranged projectiles ──────
  const ATTACK = SPEC.player.attack && SPEC.player.attack !== 'none'
    ? SPEC.player.attack : (hostilesExist ? 'melee' : 'none');
  if (ATTACK !== 'none') {
    const hint = document.querySelector('#hud .hint');
    if (hint) hint.textContent += ` · F to ${ATTACK === 'ranged' ? 'shoot' : 'attack'}`;
  }
  const projectiles = [];
  // LIGHT + PROJECTILE POOL (2026-07-19 'attack still lags'): adding a NEW
  // PointLight mid-game changes the scene's light count, which forces THREE
  // to recompile EVERY shader — a visible freeze on each swing. Both attack
  // lights now exist from load (count never changes) and projectile meshes
  // are pooled; nothing is created or removed during combat.
  const atkFlash = new THREE.PointLight(0xffffff, 0, 5);
  scene.add(atkFlash);
  const projLight = new THREE.PointLight(0x9fe8ff, 0, 4);
  scene.add(projLight);
  const projPool = [];
  for (let i = 0; i < 6; i++) {
    const m = new THREE.Mesh(
      new THREE.SphereGeometry(0.09, 8, 6),
      new THREE.MeshBasicMaterial({ color: 0xaef4ff }));
    m.visible = false;
    scene.add(m);
    projPool.push(m);
  }
  let atkCd = 0;
  // TARGET MARKER + reach helper: a red diamond floats over the nearest
  // hostile you can hit — no more guessing whether the swing will land
  // ("hard to aim without a prop", 2026-07-08)
  const MELEE_REACH = 3.2;
  let atkDmg = 1;               // Phase 70: loot crates upgrade to 2
  const RANGED_RANGE = 26;   // Phase 68: rifle/bow aim + marker range
  function nearestHostile(maxD) {
    let best = null, bd = maxD;
    for (const n of npcs) {
      // Phase 66: prey ('flee') is a legitimate attack target — hunting games
      if (!(n.behavior === 'hostile' || n.behavior === 'flee') || n.dead || n.dormant) continue;
      const d = Math.hypot(n.obj.position.x - playerObj.position.x,
                           n.obj.position.z - playerObj.position.z);
      if (d < bd) { bd = d; best = n; }
    }
    return best;
  }
  let tgtMark = null;
  if (ATTACK !== 'none') {
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const g2 = c.getContext('2d');
    g2.translate(32, 32); g2.rotate(Math.PI / 4);
    g2.fillStyle = 'rgba(255,80,90,0.95)';
    g2.fillRect(-10, -10, 20, 20);
    g2.strokeStyle = 'rgba(255,255,255,0.9)'; g2.lineWidth = 3;
    g2.strokeRect(-10, -10, 20, 20);
    tgtMark = new THREE.Sprite(new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(c), transparent: true, depthTest: false }));
    tgtMark.scale.setScalar(0.45);
    tgtMark.visible = false;
    scene.add(tgtMark);
  }
  // footstep dust — pooled soft puffs at the feet while moving on ground
  const _dustPool = [];
  let _dustT = 0;
  {
    const dc = document.createElement('canvas'); dc.width = dc.height = 64;
    const dg = dc.getContext('2d');
    const grad = dg.createRadialGradient(32, 32, 2, 32, 32, 30);
    grad.addColorStop(0, 'rgba(255,255,255,0.55)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    dg.fillStyle = grad; dg.beginPath(); dg.arc(32, 32, 30, 0, 7); dg.fill();
    const dtex = new THREE.CanvasTexture(dc);
    const gc2 = new THREE.Color(...SPEC.world.ground_color).lerp(new THREE.Color(0xffffff), 0.5);
    for (let i = 0; i < 10; i++) {
      const m = new THREE.Sprite(new THREE.SpriteMaterial({
        map: dtex, transparent: true, depthWrite: false, color: gc2 }));
      m.visible = false; scene.add(m);
      _dustPool.push({ m, live: 0 });
    }
  }
  function puffDust(x, y, z) {
    const d = _dustPool.find(q => !q.live) || _dustPool[0];
    d.m.position.set(x + (Math.random() - 0.5) * 0.2, y + 0.12, z + (Math.random() - 0.5) * 0.2);
    d.m.scale.set(0.3, 0.3, 1);
    d.m.material.opacity = 0.5; d.m.visible = true; d.live = 0.5;
  }
  function stepDust(dt) {
    for (const d of _dustPool) {
      if (!d.live) continue;
      d.live = Math.max(0, d.live - dt);
      d.m.scale.multiplyScalar(1 + dt * 2.4);
      d.m.position.y += dt * 0.4;
      d.m.material.opacity = d.live;
      if (!d.live) d.m.visible = false;
    }
  }
  // pooled 3D damage numbers — no allocations during combat
  const _dmgPool = [];
  function dmgNumber(pos, dmg) {
    let sp = _dmgPool.find(d => !d.live);
    if (!sp) {
      if (_dmgPool.length >= 8) sp = _dmgPool[0];
      else {
        const cn = document.createElement('canvas'); cn.width = 128; cn.height = 64;
        const sm = new THREE.SpriteMaterial({ transparent: true, depthTest: false });
        const spr = new THREE.Sprite(sm);
        spr.scale.set(0.9, 0.45, 1); spr.visible = false;
        scene.add(spr);
        sp = { spr, cn, live: 0 };
        _dmgPool.push(sp);
      }
    }
    const g2 = sp.cn.getContext('2d');
    g2.clearRect(0, 0, 128, 64);
    g2.font = '700 44px system-ui'; g2.textAlign = 'center';
    g2.fillStyle = dmg > 1 ? '#ffd257' : '#ffffff';
    g2.strokeStyle = 'rgba(0,0,0,0.8)'; g2.lineWidth = 6;
    g2.strokeText('-' + dmg, 64, 46); g2.fillText('-' + dmg, 64, 46);
    if (sp.spr.material.map) sp.spr.material.map.dispose();
    sp.spr.material.map = new THREE.CanvasTexture(sp.cn);
    sp.spr.position.copy(pos).add(new THREE.Vector3(0, 1.3, 0));
    sp.spr.visible = true; sp.spr.material.opacity = 1;
    sp.live = 0.7;
  }
  function stepDmgNumbers(dt) {
    for (const d of _dmgPool) {
      if (!d.live) continue;
      d.live = Math.max(0, d.live - dt);
      d.spr.position.y += dt * 1.2;
      d.spr.material.opacity = Math.min(1, d.live * 2.5);
      if (!d.live) d.spr.visible = false;
    }
  }
  function rumble(ms, mag) {
    try {
      for (const gp of navigator.getGamepads() || []) {
        if (gp && gp.vibrationActuator) {
          gp.vibrationActuator.playEffect('dual-rumble',
            { duration: ms, strongMagnitude: mag, weakMagnitude: mag * 0.6 });
        }
      }
    } catch (e) { /* no haptics */ }
  }
  function dmgEnemy(n, dmg) {
    if (n.dead || n.dormant) return;
    n.hp -= dmg;
    window.__hitStop = 0.08;                       // weight: the world flinches
    dmgNumber(n.obj.position, dmg);
    rumble(80, 0.7);
    for (const m of n.mats) { if (m.emissive) m.emissive.setHex(0xff4444); }
    setTimeout(() => { for (const m of n.mats) {
      if (m.emissive) m.emissive.setRGB(0.30, 0.16, 0.16); } }, 120);
    if (n.hp <= 0) {
      n.dead = true; kills++; sfx('hit');
      const _st2 = steps[stepIdx];
      if (_st2 && ['defeat', 'eliminate', 'hunt'].includes(_st2.kind)
          && kills - (_st2._k0 || 0) >= _st2.count) {
        window.__slowMo = 0.7;                     // savor the last one
        rumble(220, 1.0);
      }
      burst(n.obj.position.clone().add(new THREE.Vector3(0, 0.8, 0)), 0xff5c6a);
      const st = steps[stepIdx];
      if (st && (st.kind === 'defeat' || st.kind === 'eliminate' || st.kind === 'hunt')) {
        renderQuest();
        if (kills - (st._k0 || 0) >= st.count) advanceStep();
      }
    }
  }
  function doAttack() {
    if (ATTACK === 'none' || atkCd > 0 || won || lost) return;
    atkCd = ATTACK === 'ranged' ? 0.35 : 0.55;
    sfx('attack');
    // AIM ASSIST: swings snap toward the marked target — you committed to
    // the attack, the game commits to the hit (reach was 2.3m and the angle
    // check punished honest inputs; now 3.2m + auto-face)
    if (ATTACK === 'melee') {
      const tn = nearestHostile(MELEE_REACH);
      if (tn) {
        modelYaw = Math.atan2(tn.obj.position.x - playerObj.position.x,
                              tn.obj.position.z - playerObj.position.z);
      }
    } else if (ATTACK === 'ranged') {
      // Phase 68 AIM: shots snap toward the marked target out to rifle range —
      // hunters line up on the prey the marker shows, not pixel-perfect yaw
      const tn = nearestHostile(RANGED_RANGE);
      if (tn) {
        modelYaw = Math.atan2(tn.obj.position.x - playerObj.position.x,
                              tn.obj.position.z - playerObj.position.z);
      }
    }
    playAttackAnim();                          // the actual katana/claw motion
    const dir = new THREE.Vector3(Math.sin(modelYaw), 0, Math.cos(modelYaw));
    if (ATTACK === 'ranged') {
      const m = projPool.find(pm => !pm.visible)
        || projPool[0];                        // spam beyond 6: reuse the oldest
      m.visible = true;
      m.position.copy(playerObj.position).add(new THREE.Vector3(0, P.height_m * 0.6, 0))
        .add(dir.clone().multiplyScalar(0.5));
      projLight.intensity = 1.6;               // one shared glow tracks the newest shot
      projectiles.push({ mesh: m, vel: dir.clone().multiplyScalar(24), life: 2 });
    } else {
      // melee: damage lands MID-SWING (180ms in) so the hit matches the motion
      setTimeout(() => {
        if (won || lost) return;
        atkFlash.position.copy(playerObj.position).add(dir.clone().multiplyScalar(1.2))
          .add(new THREE.Vector3(0, P.height_m * 0.5, 0));
        atkFlash.intensity = 3.5;
        setTimeout(() => { atkFlash.intensity = 0; }, 110);
        for (const n of npcs) {
          // Phase 68: prey ('flee') dies to claws too — a wolf hunts with its bite
          if (!(n.behavior === 'hostile' || n.behavior === 'flee') || n.dead) continue;
          const dx = n.obj.position.x - playerObj.position.x;
          const dz = n.obj.position.z - playerObj.position.z;
          const d = Math.hypot(dx, dz);
          if (d > MELEE_REACH) continue;
          let a = Math.atan2(dx, dz) - modelYaw;
          while (a > Math.PI) a -= 2 * Math.PI;
          while (a < -Math.PI) a += 2 * Math.PI;
          if (Math.abs(a) < 1.35) dmgEnemy(n, atkDmg);
        }
      }, 120);
    }
  }
  // controls per device: keyboard F/Space · touch ATTACK button · gamepad A/X or RT
  addEventListener('keydown', e => {
    // GRAMMAR: Space = JUMP on foot (fly/swim use it to ascend) — attack
    // lives on F, matching every modern game's muscle memory
    if (e.code === 'KeyF') { e.preventDefault(); doAttack(); }
  });
  const atkBtn = document.getElementById('atkbtn');
  if (atkBtn && ATTACK !== 'none') {
    atkBtn.style.display = matchMedia('(pointer:coarse)').matches ? 'flex' : 'none';
    atkBtn.textContent = ATTACK === 'ranged' ? 'SHOOT' : 'ATTACK';
    atkBtn.addEventListener('pointerdown', e => { e.preventDefault(); doAttack(); });
  }
  let gpAtkHeld = false;
  function pollGamepadAttack() {
    const gps = navigator.getGamepads ? navigator.getGamepads() : [];
    for (const gp of gps) {
      if (!gp) continue;
      const pressed = (gp.buttons[0] && gp.buttons[0].pressed) ||   // A / Cross
                      (gp.buttons[7] && gp.buttons[7].pressed);     // RT / R2
      if (pressed && !gpAtkHeld) doAttack();
      gpAtkHeld = pressed;
    }
  }

  // exposed for the verify harness (synthetic input, position probes, dev teleport)
  window.__game = {
    pos: () => playerObj.position.toArray(), keys, ready: true,
    tp: (x, z) => body.setTranslation({ x, y: spawnHeight(x, z), z }, true),
    attack: doAttack,
    combat: () => ({ hp: php, kills, mode: ATTACK, lost,
                     hostiles: npcs.filter(n => n.behavior === 'hostile' && !n.dead).length }),
    quest: () => ({ step: stepIdx, total: steps.length,
                    active: steps[stepIdx] ? stepLabel(steps[stepIdx]) : null, won }),
    objectives: () => ({ collected: steps.filter(s => s.kind === 'collect').reduce((a, s) => a + (s._got || 0), 0),
                         left: collectibles.filter(c => c.mesh.parent).map(c => c.mesh.position.toArray()) }),
    npcs: () => npcs.filter(n => !n.gone).map(n => ({ behavior: n.behavior, dead: !!n.dead, pos: n.obj.position.toArray() })),
    placed: () => placedItems.map(p => ({ kind: p.it.kind, x: p.it.x, z: p.it.z,
                                          interact: !!p.it.interact, alive: !!p.anim })),
    reading: () => ({ readable: readable ? readable.label : null, open: reading }),
    inspect: on => setInspectOn(on),
    view: VIEW,
  };

  // Inspect = SOFT FREEZE: while editing, enemies stop, damage stops, and
  // the run/survive clocks hold — dying mid-edit is not a feature. Exiting
  // inspect shifts the clocks by the frozen duration (same math as pause).
  let inspT0 = 0, inspF = null;        // free-cam focus point while inspecting
  function setInspectOn(on) {
    on = !!on;
    if (on === inspectOn) return;
    inspectOn = on;
    renderer.domElement.style.cursor = on ? 'crosshair' : '';
    if (on) {
      inspT0 = performance.now();
      inspF = { x: playerObj.position.x, z: playerObj.position.z };
    }
    else {
      const d = performance.now() - inspT0;
      runT0 += d;
      const st = steps[stepIdx];
      if (st && st._t0 !== undefined) st._t0 += d;
    }
  }

  // ── INSPECTOR PICKING BRIDGE (Phase 42): the studio turns on inspect mode
  // via postMessage; hover/click raycasts report what's under the cursor and
  // WHERE — so "place a building here" carries real coordinates. Standalone
  // (itch.io, shared zip) the bridge is inert: no parent listens.
  playerObj.userData.fsTag = { type: 'player', name: SPEC.player.name || 'player',
                               detail: SPEC.player.mode || 'walk' };
  {
    const rc = new THREE.Raycaster();
    const nv = new THREE.Vector2();
    addEventListener('message', e => {
      if (e.data && e.data.type === 'fs-inspect') setInspectOn(e.data.on);
    });
    const pickAt = (cx, cy, kindEv) => {
      nv.set((cx / innerWidth) * 2 - 1, -(cy / innerHeight) * 2 + 1);
      rc.setFromCamera(nv, camera);
      for (const h of rc.intersectObjects(scene.children, true)) {
        if (h.object.isSprite) continue;         // glow halos aren't things
        let o = h.object, tag = null;
        while (o) {
          if (o.userData && o.userData.fsTag) { tag = o.userData.fsTag; break; }
          o = o.parent;
        }
        window.parent.postMessage({
          type: 'fs-pick', kind: kindEv,
          x: +h.point.x.toFixed(2), z: +h.point.z.toFixed(2), y: +h.point.y.toFixed(2),
          target: tag || { type: 'ground', name: 'ground',
                           detail: `terrain (${h.point.x.toFixed(1)}, ${h.point.z.toFixed(1)})` },
        }, '*');
        return;
      }
    };
    window.__game.pick = (cx, cy) => pickAt(cx, cy, 'click');   // test harness
    // pick on pointerUP with no movement — dragging stays camera-look, so
    // Inspect mode never steals the ability to orbit and reposition the view
    let pkX = 0, pkY = 0;
    renderer.domElement.addEventListener('pointerdown', e => {
      pkX = e.clientX; pkY = e.clientY;
    });
    renderer.domElement.addEventListener('pointerup', e => {
      if (!inspectOn) return;
      if (Math.hypot(e.clientX - pkX, e.clientY - pkY) < 6) {
        pickAt(e.clientX, e.clientY, 'click');
      }
    });
    let hovT = 0;
    renderer.domElement.addEventListener('pointermove', e => {
      if (!inspectOn) return;
      const now = performance.now();
      if (now - hovT < 130) return;              // ~8 Hz is plenty for a chip
      hovT = now;
      pickAt(e.clientX, e.clientY, 'hover');
    });
  }

  // ── FOOTSTEP DUST (Phase 81) — bird flock already ships via Phase 48 ─────
  const dusts = [];
  {
    const dc = document.createElement('canvas'); dc.width = dc.height = 32;
    const dg2 = dc.getContext('2d');
    const grad = dg2.createRadialGradient(16, 16, 2, 16, 16, 15);
    grad.addColorStop(0, 'rgba(255,255,255,0.55)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    dg2.fillStyle = grad; dg2.fillRect(0, 0, 32, 32);
    const dtex = new THREE.CanvasTexture(dc);
    const dustCol = new THREE.Color(...SPEC.world.ground_color).lerp(new THREE.Color(1, 1, 1), 0.35);
    for (let i = 0; i < 10; i++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: dtex, color: dustCol,
        transparent: true, opacity: 0, depthWrite: false }));
      sp.scale.set(0.5, 0.5, 1); scene.add(sp);
      dusts.push({ sp, t: 1 });
    }
  }
  let dustT = 0, dustIdx = 0;

  // ── MATERIAL ENRICHMENT (Phase 76): the SCALABLE realism pass ─────────────
  // Every flat-colored material in the scene — trees, castles, buildings,
  // rocks, fences, ANY prop in ANY game — gains a procedural detail texture
  // classified from its material name/color: bark striations, mottled stone,
  // shingles, leaf speckle. One traverse, cached per class+color, no
  // per-asset artwork ever. Meshes that already carry real textures (GPU
  // characters, terrain) are untouched.
  {
    // PHOTOREAL TIER (Phase 77): SDXL-generated seamless photo textures
    // (shipped in dist/textures/) replace the procedural canvases for the
    // big surface classes. Missing files fall back to canvases silently.
    // hyper-real is the DEFAULT look; only deliberate style packs
    // (cartoon/anime/pixel/horror/lowpoly) keep the painted canvases
    const PHOTO = !SPEC.style || SPEC.style === 'photoreal' || SPEC.style === 'default';
    const _texLoader = new THREE.TextureLoader();
    const _pbrCache = {};
    function pbr(name, rep, srgb) {
      const key = name + rep;
      if (_pbrCache[key]) return _pbrCache[key];
      const t = _texLoader.load('textures/' + name + '.jpg');
      t.anisotropy = renderer.capabilities.getMaxAnisotropy();  // crisp at grazing angles
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.repeat.set(rep, rep);
      if (srgb) t.colorSpace = THREE.SRGBColorSpace;
      _pbrCache[key] = t;
      return t;
    }
    const PBR_FILE = { bark: 'bark', stone: 'stone', roof: 'roof', brick: 'brick',
                       foliage: 'leaves', needles: 'needles' };
    const _detailCache = {};
    function detailTex(cls, baseHex) {
      const key = cls + baseHex;
      if (_detailCache[key]) return _detailCache[key];
      const N = 256, c = document.createElement('canvas');
      c.width = c.height = N;
      const g = c.getContext('2d');
      const base = new THREE.Color(baseHex);
      g.fillStyle = '#' + base.getHexString(); g.fillRect(0, 0, N, N);
      const rngD = mulberry32(9137 + cls.length);
      const shade = (k) => '#' + base.clone().offsetHSL(0, 0, k).getHexString();
      if (cls === 'bark') {
        for (let i = 0; i < 90; i++) {                       // vertical striations
          g.strokeStyle = shade((rngD() - 0.6) * 0.10); g.lineWidth = 1 + rngD() * 3;
          const x = rngD() * N; g.beginPath(); g.moveTo(x, 0);
          g.bezierCurveTo(x + rngD() * 8 - 4, N / 3, x + rngD() * 8 - 4, 2 * N / 3, x + rngD() * 10 - 5, N);
          g.stroke();
        }
      } else if (cls === 'stone') {
        for (let i = 0; i < 70; i++) {                       // mottled blocks + cracks
          g.fillStyle = shade((rngD() - 0.5) * 0.09);
          g.fillRect(rngD() * N, rngD() * N, 14 + rngD() * 44, 10 + rngD() * 26);
        }
        g.strokeStyle = shade(-0.13); g.lineWidth = 1.5;
        for (let y = 16; y < N; y += 26 + Math.floor(rngD() * 8)) {
          g.beginPath(); g.moveTo(0, y); g.lineTo(N, y + rngD() * 6 - 3); g.stroke();
        }
      } else if (cls === 'roof') {
        for (let y = 0; y < N; y += 16) {                    // shingle rows
          g.fillStyle = shade((rngD() - 0.5) * 0.08); g.fillRect(0, y, N, 15);
          g.strokeStyle = shade(-0.12); g.beginPath(); g.moveTo(0, y); g.lineTo(N, y); g.stroke();
        }
      } else if (cls === 'foliage' || cls === 'needles') {
        for (let i = 0; i < 900; i++) {                      // leaf speckle
          g.fillStyle = shade((rngD() - 0.42) * 0.16);
          const s = 2 + rngD() * 5;
          g.fillRect(rngD() * N, rngD() * N, s, s * 0.6);
        }
      } else {                                               // generic grain
        for (let i = 0; i < 500; i++) {
          g.fillStyle = shade((rngD() - 0.5) * 0.06);
          g.fillRect(rngD() * N, rngD() * N, 2 + rngD() * 6, 2 + rngD() * 6);
        }
      }
      const t = new THREE.CanvasTexture(c);
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.colorSpace = THREE.SRGBColorSpace;
      _detailCache[key] = t;
      return t;
    }
    function classify(m) {
      const n = (m.name || '').toLowerCase();
      if (/bark|trunk|wood|fence|branch/.test(n)) return 'bark';
      if (/wall|brick|facade/.test(n)) return 'brick';
      if (/stone|rock|castle|slit/.test(n)) return 'stone';
      if (/roof|shingle/.test(n)) return 'roof';
      if (/needle/.test(n)) return 'needles';
      if (/leaf|leaves|bush|foliage|lit|dark|mid/.test(n)) return 'foliage';
      const hsl = {}; m.color.getHSL(hsl);
      if (hsl.s > 0.2 && hsl.h > 0.16 && hsl.h < 0.45) return 'foliage';
      if (hsl.s < 0.12) return 'stone';
      if (hsl.h < 0.12) return 'bark';
      return 'grain';
    }
    const _seen = new Set();
    scene.traverse(o => {
      if (!o.isMesh || !o.material) return;
      if (o.isSkinnedMesh) return;                           // characters keep real textures
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        if (!m) continue;
      if (m.map && m.map.anisotropy < 4) {           // crisp at grazing angles
        m.map.anisotropy = renderer.capabilities.getMaxAnisotropy();
        m.map.needsUpdate = true;
      }
      if (!m.isMeshStandardMaterial || m.map || _seen.has(m.uuid)) continue;
        _seen.add(m.uuid);
        if (!o.geometry.attributes.uv) continue;             // needs UVs to texture
        const cls = classify(m);
        if (cls === 'foliage' || cls === 'needles') {
          // canopies breathe in the wind — subtle, phase-shifted per tree
          m.onBeforeCompile = sh => {
            sh.uniforms.uWind = WIND_U;
            sh.vertexShader = 'uniform float uWind;\n' + sh.vertexShader.replace(
              '#include <begin_vertex>',
              ['#include <begin_vertex>',
               '#ifdef USE_INSTANCING',
               'vec4 wpF = instanceMatrix * vec4(position, 1.0);',
               '#else',
               'vec4 wpF = vec4(position, 1.0);',
               '#endif',
               'transformed.x += sin(uWind * 0.9 + wpF.x * 0.11 + wpF.z * 0.07) * 0.05;',
               'transformed.z += cos(uWind * 0.75 + wpF.z * 0.1 + wpF.x * 0.08) * 0.04;'
              ].join('\n'));
          };
        }
        if (PHOTO && PBR_FILE[cls]) {
          m.map = pbr(PBR_FILE[cls], 2, true);
          m.normalMap = pbr(PBR_FILE[cls] + '_n', 2, false);
          m.normalScale = new THREE.Vector2(0.9, 0.9);
          m.color.setRGB(1, 1, 1);
        } else {
          const tex = detailTex(cls, '#' + m.color.getHexString());
          m.map = tex;
          m.color.setRGB(1, 1, 1);
          m.bumpMap = tex; m.bumpScale = 0.06;
        }
        m.roughness = Math.min(1, (m.roughness || 0.9) + 0.03);
        m.needsUpdate = true;
      }
    });
    // GROUND surface relief: the painted albedo (trails, roads) stays the
    // color map; a matching photo NORMAL map adds real micro-relief
    if (PHOTO) {
      const wn = (SPEC.world.name || '').toLowerCase();
      const gname = (SPEC.world.weather === 'snow') ? 'snow'
        : /desert|beach|dune/.test(wn) ? 'sand'
        : /forest|wood|jungle/.test(wn) ? 'forest'
        : /city|street|town|road/.test(wn) ? 'asphalt' : 'grass';
      gmat.normalMap = pbr(gname + '_n', Math.max(10, Math.round(gsize / 6)), false);
      gmat.normalScale = new THREE.Vector2(0.65, 0.65);
      gmat.needsUpdate = true;
      // ALBEDO BLEND: overlay the photo surface into the painted world canvas
      // (soft-light keeps trails/roads/tints; photo brings blade/grain detail)
      const gimg = new Image();
      gimg.onload = () => {
        const c2 = gtex.image, g2 = c2.getContext('2d');
        g2.globalAlpha = 0.5;
        g2.globalCompositeOperation = 'overlay';
        const tile = Math.max(48, Math.round(c2.width / (gsize / 9)));
        for (let ty = 0; ty < c2.height; ty += tile)
          for (let tx2 = 0; tx2 < c2.width; tx2 += tile)
            g2.drawImage(gimg, tx2, ty, tile, tile);
        g2.globalAlpha = 1; g2.globalCompositeOperation = 'source-over';
        gtex.needsUpdate = true;
      };
      gimg.src = 'textures/' + gname + '.jpg';
    }
  }
  // re-open scope: enrichment block ends above
  {
  // sun shadow softening + ground-bounce tied to the actual terrain color —
  // hard black-edged shadows are the #2 "this is CG" tell after fog
  sun.shadow.radius = 3;
  sun.shadow.bias = -0.0004;
  hemi.groundColor.copy(gcol.clone().multiplyScalar(0.55));
  }

  // QUALITY PACK — cinematic post chain: SSAO + subtle bloom + vignette + filmic out
  // SSAO (Phase 73 v2): a dedicated DEPTH PREPASS (RGBA-packed, half-res —
  // the same approach three's own AO passes use) feeds a compact 8-tap AO
  // shader. v1 shared one depth texture with the composer's ping-pong
  // targets, which blanked the whole frame — never bind a texture that a
  // later pass in the same chain may write to.
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const _dMat = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking });
  const _dRT = new THREE.WebGLRenderTarget(innerWidth >> 1, innerHeight >> 1);
  const ssao = new ShaderPass({
    uniforms: { tDiffuse: { value: null }, tDepth: { value: _dRT.texture },
                camNear: { value: camera.near }, camFar: { value: camera.far },
                res: { value: new THREE.Vector2(innerWidth, innerHeight) } },
    vertexShader: `varying vec2 vUv;
      void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `#include <packing>
      uniform sampler2D tDiffuse; uniform sampler2D tDepth;
      uniform float camNear; uniform float camFar; uniform vec2 res;
      varying vec2 vUv;
      float viewZ(vec2 uv){
        float d = unpackRGBAToDepth(texture2D(tDepth, uv));    // gl_FragCoord.z
        return perspectiveDepthToViewZ(d, camNear, camFar);    // negative view Z
      }
      void main(){
        vec4 c = texture2D(tDiffuse, vUv);
        float z0 = viewZ(vUv);
        if (z0 < -220.0) { gl_FragColor = c; return; }         // sky/far: skip
        float px = 1.0 / res.y;
        // screen radius shrinks with distance so AO stays world-scaled
        float rad = clamp(26.0 / max(-z0, 1.0), 2.0, 14.0) * px;
        float occ = 0.0;
        for (int i = 0; i < 8; i++) {
          float a = 0.7853982 * float(i) + (z0 * 13.7);        // per-depth spin
          vec2 off = vec2(cos(a), sin(a)) * rad * (0.4 + 0.6 * fract(float(i) * 0.618));
          float dz = viewZ(vUv + off) - z0;                     // >0 means closer
          occ += clamp(dz / 0.55, 0.0, 1.0) * step(dz, 2.6);    // range-checked
        }
        float ao = 1.0 - 0.38 * (occ / 8.0);
        gl_FragColor = vec4(c.rgb * ao, c.a);
      }`,
  });
  composer.addPass(ssao);
  // MeshDepthMaterial as the scene override: skinned/instanced meshes pack
  // correct depth (it carries USE_SKINNING variants); the AO shader
  // linearizes with perspectiveDepthToViewZ.
  function renderDepthPrepass() {
    scene.overrideMaterial = _dMat;
    const fogSave = scene.fog; scene.fog = null;
    renderer.setRenderTarget(_dRT);
    renderer.clear();
    renderer.render(scene, camera);
    renderer.setRenderTarget(null);
    scene.overrideMaterial = null; scene.fog = fogSave;
  }
  const bloom = new UnrealBloomPass(
    new THREE.Vector2(innerWidth, innerHeight), 0.25, 0.65, 0.85);
  composer.addPass(bloom);
  const vignette = new ShaderPass({
    uniforms: { tDiffuse: { value: null }, strength: { value: 0.42 } },
    vertexShader: `varying vec2 vUv;
      void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform sampler2D tDiffuse; uniform float strength; varying vec2 vUv;
      void main(){
        vec4 c = texture2D(tDiffuse, vUv);
        float d = distance(vUv, vec2(0.5));
        c.rgb *= smoothstep(0.92, 0.35, d * strength * 2.0) * 0.25 + 0.75;
        gl_FragColor = c;
      }`,
  });
  composer.addPass(vignette);
  // ART-DIRECTION COHERENCE: one gentle color grade pulls every element —
  // photoreal heroes, low-poly props, painted terrain — toward the sky
  // palette's mood. Consistency is the cheapest "looks expensive" trick in
  // games; this is the whole-frame half of it (props get tinted at load).
  const gradeTint = new THREE.Color(pal.sky).lerp(new THREE.Color(0xffffff), 0.55);
  {
    // luminance-normalize the tint: dark palettes (night/space) shift HUE
    // without multiplying the whole frame darker — mood without murk
    const l = 0.299 * gradeTint.r + 0.587 * gradeTint.g + 0.114 * gradeTint.b;
    gradeTint.multiplyScalar(THREE.MathUtils.clamp(0.9 / Math.max(l, 0.2), 1.0, 2.4));
  }
  const grade = new ShaderPass({
    uniforms: { tDiffuse: { value: null },
                tint: { value: new THREE.Vector3(gradeTint.r, gradeTint.g, gradeTint.b) } },
    vertexShader: `varying vec2 vUv;
      void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform sampler2D tDiffuse; uniform vec3 tint; varying vec2 vUv;
      void main(){
        vec4 c = texture2D(tDiffuse, vUv);
        float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
        c.rgb = mix(c.rgb, c.rgb * tint, 0.22);          // mood tint
        c.rgb = mix(vec3(l), c.rgb, 1.06);               // slight saturation lift
        gl_FragColor = c;
      }`,
  });
  composer.addPass(grade);
  // 2D views: the ortho camera stands 40+m off the subject, which would put
  // the WHOLE world inside the fog band — push fog out by the standoff
  if (VIEW !== '3d' && scene.fog) {
    const standoff = VIEW === 'side' ? 42 : 46;
    scene.fog.near += standoff;
    scene.fog.far += standoff;
  }
  // ── STYLE PACKS (Phase 44): the user picked this in the studio — one
  // GLOBAL render treatment applied coherently to the whole frame. Never
  // guessed by an LLM, so it's never wrong.
  const STYLE = SPEC.style || 'default';
  const STYLE_CFG = {
    cartoon: { bands: 5, sat: 1.35, exposure: 1.05, grain: 0, edge: 2.4, gamma: 1.0 },
    anime:   { bands: 8, sat: 1.18, exposure: 1.08, grain: 0, edge: 1.1, gamma: 1.0 },
    horror:  { bands: 0, sat: 0.32, exposure: 0.7, grain: 0.13, edge: 0, gamma: 1.7 },
    pixel:   { bands: 6, sat: 1.12, exposure: 1.0, grain: 0, edge: 0, gamma: 1.0 },
    lowpoly: { bands: 7, sat: 1.15, exposure: 1.02, grain: 0, edge: 0, gamma: 1.0 },
  }[STYLE];
  let stylePass = null;
  if (STYLE_CFG) {
    stylePass = new ShaderPass({
      uniforms: { tDiffuse: { value: null },
                  bands: { value: STYLE_CFG.bands },
                  sat: { value: STYLE_CFG.sat },
                  exposure: { value: STYLE_CFG.exposure },
                  grain: { value: STYLE_CFG.grain },
                  edge: { value: STYLE_CFG.edge },
                  gamma: { value: STYLE_CFG.gamma },
                  time: { value: 0 },
                  res: { value: new THREE.Vector2(innerWidth, innerHeight) } },
      vertexShader: `varying vec2 vUv;
        void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: `uniform sampler2D tDiffuse;
        uniform float bands; uniform float sat; uniform float exposure;
        uniform float grain; uniform float edge; uniform float time;
        uniform float gamma; uniform vec2 res; varying vec2 vUv;
        float lum(vec2 uv){ return dot(texture2D(tDiffuse, uv).rgb, vec3(.299,.587,.114)); }
        void main(){
          vec4 c = texture2D(tDiffuse, vUv);
          c.rgb *= exposure;
          if (gamma != 1.0) {                     // midtone crush (horror dark)
            c.rgb = pow(max(c.rgb, vec3(0.0)), vec3(gamma));
          }
          if (edge > 0.0) {                       // ink outlines (sobel)
            vec2 px = 1.0 / res;
            float gx = lum(vUv + vec2(px.x, 0.)) - lum(vUv - vec2(px.x, 0.));
            float gy = lum(vUv + vec2(0., px.y)) - lum(vUv - vec2(0., px.y));
            float e = clamp(length(vec2(gx, gy)) * edge * 6.0, 0.0, 1.0);
            c.rgb *= (1.0 - e * 0.8);
          }
          if (bands > 0.5) {                      // cel / posterize
            c.rgb = floor(c.rgb * bands + 0.5) / bands;
          }
          float l = dot(c.rgb, vec3(.299,.587,.114));
          c.rgb = mix(vec3(l), c.rgb, sat);       // saturation (or drain)
          if (grain > 0.0) {                      // film grain (horror)
            float g = fract(sin(dot(vUv * res + time, vec2(12.9898, 78.233))) * 43758.5453);
            c.rgb += (g - 0.5) * grain;
          }
          gl_FragColor = c;
        }`,
    });
    composer.addPass(stylePass);
  }
  // per-style scene setup beyond the post pass
  const STYLE_PR = STYLE === 'pixel' ? 0.22 : null;   // chunky retro pixels
  if (STYLE_PR) {
    renderer.setPixelRatio(STYLE_PR);
    composer.setPixelRatio && composer.setPixelRatio(STYLE_PR);
    renderer.domElement.style.imageRendering = 'pixelated';
  }
  if (STYLE === 'horror') {
    // horror must be DARK regardless of the world's sky: crush the sky and
    // fog toward black, dim the lights, let the vignette close in
    if (scene.fog) {
      scene.fog.near *= 0.45;
      scene.fog.far *= 0.55;
      scene.fog.color.multiplyScalar(0.4);
    }
    if (scene.background && scene.background.isColor) scene.background.multiplyScalar(0.3);
    scene.traverse(o => { if (o.isLight) o.intensity *= 0.5; });
    bloom.strength = 0.12;
    vignette.uniforms.strength.value = 0.9;
  }
  if (STYLE === 'anime') bloom.strength = 0.45;   // dreamy glow
  if (STYLE === 'lowpoly') {
    scene.traverse(o => {
      if (o.isMesh) {
        for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
          if (m && 'flatShading' in m) { m.flatShading = true; m.needsUpdate = true; }
        }
      }
    });
  }
  composer.addPass(new OutputPass());

  advanceStep();                          // mission begins: activate step 1

  // ── PAUSE / SETTINGS (Esc) — a real game shell: resume, sound, restart.
  // Pausing also freezes the run clock and survive timers (no unfair time).
  let paused = false, pauseT0 = 0;
  const pauseBtnCss = 'font:600 15px system-ui;color:#eceaf6;background:rgba(255,255,255,.07);'
    + 'border:1px solid rgba(255,255,255,.14);border-radius:10px;padding:10px 34px;cursor:pointer;';
  const pv = document.createElement('div');
  pv.style.cssText = 'position:fixed;inset:0;display:none;align-items:center;'
    + 'justify-content:center;background:rgba(8,7,14,.6);z-index:45;backdrop-filter:blur(3px);';
  pv.innerHTML = '<div style="text-align:center;padding:32px;">'
    + '<h2 style="font:800 26px system-ui;color:#fff;margin:0 0 18px;">Paused</h2>'
    + '<div style="display:flex;flex-direction:column;gap:10px;">'
    + `<button id="pv_resume" style="${pauseBtnCss}">Resume</button>`
    + `<button id="pv_sound" style="${pauseBtnCss}">Sound: ON</button>`
    + `<button id="pv_restart" style="${pauseBtnCss}">Restart level</button>`
    + '</div></div>';
  document.body.appendChild(pv);
  function setPaused(p) {
    if (p === paused) return;
    paused = p;
    pv.style.display = p ? 'flex' : 'none';
    if (p) pauseT0 = performance.now();
    else {
      const dtp = performance.now() - pauseT0;
      runT0 += dtp;
      const st = steps[stepIdx];
      if (st && st._t0 !== undefined) st._t0 += dtp;
    }
  }
  document.getElementById('pv_resume').addEventListener('click', () => setPaused(false));
  document.getElementById('pv_restart').addEventListener('click', () => location.reload());
  document.getElementById('pv_sound').addEventListener('click', () => {
    sfxMuted = !sfxMuted;
    document.getElementById('pv_sound').textContent = `Sound: ${sfxMuted ? 'OFF' : 'ON'}`;
  });
  addEventListener('keydown', e => {
    if (e.code === 'Escape' && gameStarted && !won && !lost) setPaused(!paused);
  });

  // ── main loop ────────────────────────────────────────────────────────────
  const clock = new THREE.Clock();
  const fpsEl = document.getElementById('fps');
  // spawn facing AWAY from the camera (camera sits at +yaw behind the player,
  // so "away" is yaw+π) — otherwise the first W press whips the hero 180° and
  // the controls read as inverted for the whole first turn
  let fCount = 0, fTime = 0, modelYaw = Math.PI, lowT = 0, qTier = 0;
  // angle-aware damping: always turn the SHORT way (raw damp on angles walks
  // 270° around when the target crosses the ±π seam)
  function dampAngle(cur, target, lambda, dt) {
    const d = Math.atan2(Math.sin(target - cur), Math.cos(target - cur));
    return cur + d * (1 - Math.exp(-lambda * dt));
  }
  const DRIVE = SPEC.player.mode === 'drive';    // arcade car physics
  if (DRIVE && PATH && PATH.length > 1) {        // face down the street at spawn
    modelYaw = Math.atan2(PATH[1][0] - PATH[0][0], PATH[1][1] - PATH[0][1]);
  }
  if (DRIVE) {                                   // driving instructions in the HUD
    const hint = document.querySelector('#hud .hint');
    if (hint) {
      hint.textContent = 'W throttle · S brake/reverse · A/D steer · Shift boost'
        + ((SPEC.objectives || []).some(o => o.kind === 'race')
           ? ' — follow the orange gates to the checkered finish' : '');
    }
  }
  // SPINNING WHEELS (Phase 85 v3): find the BAKED wheels from the mesh
  // itself — the lowest vertex band clusters along the length axis at the
  // axles. Overlay wheels sit exactly ON the baked ones (slightly larger,
  // so they visually replace them) and turn with the holder. Scalable:
  // pure geometry, zero per-car data.
  const wheels = [];
  function addWheels(node) {
    node.updateWorldMatrix(true, true);
    const inv = new THREE.Matrix4().copy(node.matrixWorld).invert();
    const pts = [];
    node.traverse(o => {
      if (!o.isMesh || !o.geometry || !o.geometry.attributes.position) return;
      const pos = o.geometry.attributes.position;
      const m = new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld);
      const step = Math.max(1, Math.floor(pos.count / 5000));
      const v = new THREE.Vector3();
      for (let i = 0; i < pos.count; i += step) {
        v.fromBufferAttribute(pos, i).applyMatrix4(m);
        pts.push([v.x, v.y, v.z]);
      }
    });
    if (pts.length < 100) return;
    let minY = 1e9, maxY = -1e9, minZ = 1e9, maxZ = -1e9;
    for (const q of pts) {
      if (q[1] < minY) minY = q[1]; if (q[1] > maxY) maxY = q[1];
      if (q[2] < minZ) minZ = q[2]; if (q[2] > maxZ) maxZ = q[2];
    }
    const h = maxY - minY, len = maxZ - minZ;
    const low = pts.filter(q => q[1] < minY + h * 0.28);
    const BINS = 24, hist = new Array(BINS).fill(0);
    const bz = i => minZ + (i + 0.5) / BINS * len;
    for (const q of low) hist[Math.min(BINS - 1, Math.floor((q[2] - minZ) / len * BINS))]++;
    let fi = Math.floor(BINS * 0.6), ri = 0;
    for (let i = Math.floor(BINS * 0.55); i < BINS; i++) if (hist[i] > hist[fi]) fi = i;
    for (let i = 0; i < Math.floor(BINS * 0.45); i++) if (hist[i] > hist[ri]) ri = i;
    const zones = [];                          // collected wheel volumes to EXCISE
    for (const [bin, front] of [[fi, true], [ri, false]]) {
      const zc = bz(bin), tol = len / BINS * 1.6;
      const cl = low.filter(q => Math.abs(q[2] - zc) < tol);
      if (cl.length < 8) continue;
      let top = 0, xs = 0;
      for (const q of cl) { if (q[1] - minY > top) top = q[1] - minY; xs += Math.abs(q[0]); }
      const wr = THREE.MathUtils.clamp(top * 0.62, 0.14, 0.55);
      let xlo = 1e9, xhi = -1e9;
      for (const q of cl) { if (q[0] < xlo) xlo = q[0]; if (q[0] > xhi) xhi = q[0]; }
      const xc = (xlo + xhi) / 2;                     // meshes are NOT centered on x=0
      const xoff = Math.max((xhi - xlo) / 2 * 0.88, wr * 0.9);
      zones.push({ zc, xc, tol: tol * 1.45, topY: minY + top * 1.25, xmin: xoff * 0.35 });
      const tireGeo = new THREE.CylinderGeometry(wr, wr, wr * 0.8, 18);
      tireGeo.rotateZ(Math.PI / 2);
      const tireMat = new THREE.MeshStandardMaterial({ color: 0x181818, roughness: 0.92 });
      const hubGeo = new THREE.CylinderGeometry(wr * 0.42, wr * 0.42, wr * 0.53, 12);
      hubGeo.rotateZ(Math.PI / 2);
      const hubMat = new THREE.MeshStandardMaterial({ color: 0x8f8f8f, roughness: 0.4, metalness: 0.6 });
      for (const sx of [-1, 1]) {
        const g = new THREE.Group();
        const tire = new THREE.Mesh(tireGeo, tireMat);
        tire.add(new THREE.Mesh(hubGeo, hubMat));
        g.add(tire);
        g.position.set(xc + sx * xoff, minY + wr, zc);
        node.add(g);
        wheels.push({ g, tire, front, wr });
      }
    }
    // EXCISE the baked wheels (Phase 86): drop every triangle fully inside a
    // detected wheel volume so the fused-in tires stop showing through the
    // animated overlays. Geometry is cloned first (rival cars share it) and
    // the cut ABORTS if it would take >25% of the mesh (mis-detection guard).
    if (zones.length) {
      node.traverse(o => {
        if (!o.isMesh || !o.geometry || !o.geometry.index) return;
        const m = new THREE.Matrix4().multiplyMatrices(inv, o.matrixWorld);
        const geo = o.geometry.clone();
        const pos = geo.attributes.position, idx = geo.index;
        const va = new THREE.Vector3(), vb = new THREE.Vector3(), vc = new THREE.Vector3();
        const keep = [];
        const inZone = v => zones.some(zn => v.y < zn.topY
          && Math.abs(v.z - zn.zc) < zn.tol && Math.abs(v.x - (zn.xc || 0)) > zn.xmin);
        for (let i = 0; i < idx.count; i += 3) {
          va.fromBufferAttribute(pos, idx.getX(i)).applyMatrix4(m);
          vb.fromBufferAttribute(pos, idx.getX(i + 1)).applyMatrix4(m);
          vc.fromBufferAttribute(pos, idx.getX(i + 2)).applyMatrix4(m);
          const nIn = (inZone(va) ? 1 : 0) + (inZone(vb) ? 1 : 0) + (inZone(vc) ? 1 : 0);
          if (nIn < 2) {
            keep.push(idx.getX(i), idx.getX(i + 1), idx.getX(i + 2));
          }
        }
        if (keep.length < idx.count * 0.6) return;    // suspicious cut — abort
        if (keep.length === idx.count) return;        // nothing to cut
        geo.setIndex(keep);
        o.geometry = geo;
      });
    }
  }
  if (DRIVE && playerObj.children.length) addWheels(playerObj.children[0]);
  if (FLY) {                                     // flight instructions in the HUD
    const hint = document.querySelector('#hud .hint');
    if (hint) hint.textContent = 'WASD glide · Space rise · C dive · Shift boost · drag to look';
  }
  if (SWIM) {                                    // swim instructions in the HUD
    const hint = document.querySelector('#hud .hint');
    if (hint) hint.textContent = 'WASD swim · Space surface · C dive · Shift burst · drag to look';
  }
  if (VIEW === 'side') {                         // side-scroller controls
    const hint = document.querySelector('#hud .hint');
    if (hint) hint.textContent = 'A/D or ←/→ to run · Space to jump · Shift to sprint'
      + (ATTACK !== 'none' ? ' · F to attack' : '');
  }
  if (VIEW === 'topdown') {                      // top-down controls
    const hint = document.querySelector('#hud .hint');
    if (hint) hint.textContent = 'WASD / arrows to move · Shift to run · wheel to zoom'
      + (ATTACK !== 'none' ? ' · F to attack' : '');
  }
  let vSpeed = 0, hudTick = 0, prevV = 0, leanP = 0, leanR = 0;
  const camTarget = new THREE.Vector3();
  const _camWant = new THREE.Vector3();

  renderer.setAnimationLoop(() => {
    let dt = Math.min(clock.getDelta(), 0.05);
    // JUICE (moon plan 1.2): hit-stop freezes 80ms on melee connect; the
    // final kill of a quest step lands in brief slow motion
    if (window.__hitStop > 0) { window.__hitStop -= dt; dt *= 0.08; }
    else if (window.__slowMo > 0) { window.__slowMo -= dt; dt *= 0.35; }
    WIND_U.value = performance.now() / 1000;   // wind clock (Phase 81)
    for (const w of wheels) {                  // roll with speed, steer in front
      w.tire.rotation.x += ((window.__pSpeed || 0) / w.wr) * dt;
      if (w.front) w.g.rotation.y = THREE.MathUtils.damp(w.g.rotation.y,
        (keys['KeyA'] || keys['ArrowLeft'] ? 0.42 : 0) +
        (keys['KeyD'] || keys['ArrowRight'] ? -0.42 : 0), 8, dt);
    }
    dustT -= dt;
    if ((window.__pSpeed || 0) > 3 && dustT <= 0 && typeof playerObj !== 'undefined') {
      dustT = 0.22;                            // one puff per running stride-ish
      const d0 = dusts[dustIdx++ % dusts.length];
      d0.t = 0;
      d0.sp.position.set(playerObj.position.x,
        hAt(playerObj.position.x, playerObj.position.z) + 0.12, playerObj.position.z);
    }
    for (const d of dusts) {
      if (d.t < 1) {
        d.t += dt * 2.2;
        d.sp.material.opacity = 0.5 * (1 - d.t);
        d.sp.position.y += dt * 0.5;
        const dsc = 0.4 + d.t * 0.8; d.sp.scale.set(dsc, dsc, 1);
      } else if (d.sp.material.opacity !== 0) d.sp.material.opacity = 0;
    }
    // pre-START or paused: inputs are dead, world idles as the backdrop
    const mvRaw = (gameStarted && !paused) ? readMove() : { x: 0, z: 0, run: false, mag: 0 };
    // Inspect FREE-FLY: while editing, WASD/arrows pan the EDITOR CAMERA
    // across the world (hero stays put) — scout anywhere, click, place.
    const mv = inspectOn ? { x: 0, z: 0, run: false, mag: 0 } : mvRaw;
    if (inspectOn && inspF) {
      const pf = (16 + gsize * 0.05) * dt * (mvRaw.run ? 2.2 : 1);
      const fw = -mvRaw.z, st2 = mvRaw.x;
      inspF.x += (-Math.sin(yaw) * fw + Math.cos(yaw) * st2) * pf;
      inspF.z += (-Math.cos(yaw) * fw - Math.sin(yaw) * st2) * pf;
      const ext2 = gsize / 2 - 2;
      inspF.x = THREE.MathUtils.clamp(inspF.x, -ext2, ext2);
      inspF.z = THREE.MathUtils.clamp(inspF.z, -ext2, ext2);
    }
    let speed;
    const dir = new THREE.Vector3();
    if (DRIVE) {
      // CAR PHYSICS: throttle/brake + speed-scaled steering — no crab-walking
      const throttle = raceGo ? -mv.z : 0;          // W/up = forward (after GO)
      const steer = raceGo ? mv.x : 0;
      const maxV = mv.run ? P.run_speed : P.walk_speed;
      if (throttle > 0.05) vSpeed += 11 * throttle * dt;
      else if (throttle < -0.05) vSpeed -= 14 * -throttle * dt;   // brake/reverse
      else vSpeed *= Math.max(0, 1 - 1.6 * dt);                   // coast friction
      vSpeed = THREE.MathUtils.clamp(vSpeed, -maxV * 0.35, maxV);
      const grip = Math.min(Math.abs(vSpeed) / 5, 1);
      modelYaw -= steer * 1.9 * grip * Math.sign(vSpeed || 1) * dt;
      dir.set(Math.sin(modelYaw), 0, Math.cos(modelYaw));
      speed = Math.abs(vSpeed);
      vy = Math.max(vy - 9.81 * dt, -25);
      var desired = { x: dir.x * vSpeed * dt, y: vy * dt, z: dir.z * vSpeed * dt };
    } else if (FLY) {
      // FLIGHT: camera-relative glide, Space to rise, C to dive. The kinematic
      // body still collides with terrain/buildings, so landing just works.
      speed = (mv.run ? P.run_speed : P.walk_speed);
      dir.set(mv.x, 0, mv.z);
      let horiz = 0;
      if (dir.lengthSq() > 1e-4) {
        dir.normalize().applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
        modelYaw = dampAngle(modelYaw, Math.atan2(dir.x, dir.z), P.turn_speed, dt);
        horiz = speed * mv.mag;
      }
      let vv = 0;
      if (keys.Space) vv = speed * 0.75;
      else if (keys.KeyC || keys.ControlLeft) vv = -speed * 0.75;
      // auto-liftoff: a flyer moving along the ground catches air — no more
      // dragging the dragon's belly through the dirt
      if (kcc.computedGrounded() && horiz > 0.1 && vv <= 0) vv = speed * 0.55;
      const bob = Math.sin(performance.now() / 480) * 0.3;   // hover breathing
      vy = 0;                                                // no gravity aloft
      var desired = { x: dir.x * horiz * dt, y: (vv + bob) * dt, z: dir.z * horiz * dt };
      // glide feel: pitch into climbs/dives, bank into turns
      leanP = THREE.MathUtils.damp(leanP, THREE.MathUtils.clamp(-vv * 0.045, -0.4, 0.4), 4, dt);
      leanR = THREE.MathUtils.damp(leanR, THREE.MathUtils.clamp(-mv.x * 0.32, -0.45, 0.45), 4, dt);
      holder.rotation.x = leanP; holder.rotation.z = leanR;
    } else if (SWIM) {
      // SWIMMING: like flight but capped at the water surface, with a slower
      // drift and a gentle roll — whales breach, they don't hover
      speed = (mv.run ? P.run_speed : P.walk_speed);
      dir.set(mv.x, 0, mv.z);
      let horiz = 0;
      if (dir.lengthSq() > 1e-4) {
        dir.normalize().applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
        modelYaw = dampAngle(modelYaw, Math.atan2(dir.x, dir.z), P.turn_speed * 0.6, dt);
        horiz = speed * mv.mag;
      }
      let vv = 0;
      if (keys.Space) vv = speed * 0.6;
      else if (keys.KeyC || keys.ControlLeft) vv = -speed * 0.6;
      const bob = Math.sin(performance.now() / 640) * 0.18;
      vy = 0;                                              // buoyant — no gravity
      var desired = { x: dir.x * horiz * dt, y: (vv + bob) * dt, z: dir.z * horiz * dt };
      leanP = THREE.MathUtils.damp(leanP, THREE.MathUtils.clamp(-vv * 0.05, -0.35, 0.35), 3, dt);
      leanR = THREE.MathUtils.damp(leanR, THREE.MathUtils.clamp(-mv.x * 0.25, -0.35, 0.35), 3, dt);
      holder.rotation.x = leanP; holder.rotation.z = leanR;
    } else {
      if (VIEW === 'side') {
        // side-scroller: A/D (or ←→) run the lane, Space jumps — W/S unused
        speed = (mv.run ? P.run_speed : P.walk_speed) * Math.min(Math.abs(mv.x), 1);
        dir.set(Math.sign(mv.x || 0), 0, 0);
      } else {
        speed = (mv.run ? P.run_speed : P.walk_speed) * mv.mag;
        dir.set(mv.x, 0, mv.z);
      }
      if (dir.lengthSq() > 1e-4) {
        dir.normalize().applyAxisAngle(new THREE.Vector3(0, 1, 0), VIEW === '3d' ? yaw : 0);
        modelYaw = dampAngle(modelYaw, Math.atan2(dir.x, dir.z), P.turn_speed, dt);
      }
      // GRAMMAR: jump — grounded Space gives a real ballistic arc through the
      // same collider (platformers unlock from this one verb)
      if (gameStarted && keys.Space && kcc.computedGrounded()) { vy = 7.2; sfx('step'); }
      vy = Math.max(vy - 9.81 * dt, -25);
      // airborne body language: tilt back on the rise, forward into the fall —
      // the cheap half of jump articulation until the jump clip lands
      const airTilt = kcc.computedGrounded() ? 0
        : THREE.MathUtils.clamp(-vy * 0.035, -0.22, 0.3);
      leanP = THREE.MathUtils.damp(leanP, airTilt, 7, dt);
      holder.rotation.x = leanP;
      var desired = { x: dir.x * speed * dt, y: vy * dt, z: dir.z * speed * dt };
      if (VIEW === 'side') {              // hold the hero on the gameplay lane
        desired.z = (0 - body.translation().z) * Math.min(6 * dt, 1);
      }
    }
    kcc.computeColliderMovement(collider, desired);
    const cm = kcc.computedMovement();
    if (kcc.computedGrounded()) vy = 0;
    const t = body.translation();
    body.setNextKinematicTranslation({ x: t.x + cm.x, y: t.y + cm.y, z: t.z + cm.z });
    world.step();

    let nt = body.translation();
    if (FLY && nt.y > 60) {   // flight ceiling — the world stays in view
      body.setNextKinematicTranslation({ x: nt.x, y: 60, z: nt.z });
      nt = { x: nt.x, y: 60, z: nt.z };
    }
    if (SWIM && WATER !== null && nt.y > WATER - 0.15) {   // swimmers stay wet
      body.setNextKinematicTranslation({ x: nt.x, y: WATER - 0.15, z: nt.z });
      nt = { x: nt.x, y: WATER - 0.15, z: nt.z };
    }
    if (WATER !== null) {     // tide bob + underwater fog when the camera dips
      waterMesh.position.y = WATER + Math.sin(performance.now() / 1400) * 0.12;
      const under = camera.position.y < waterMesh.position.y;
      if (under !== underwater) {
        underwater = under;
        scene.fog = under ? new THREE.FogExp2(0x0e4a66, 0.028) : origFog;
        hemi.intensity = under ? Math.max(hemi.intensity, 0.5) : hemi.intensity;
      }
    }
    if (nt.y < -10) {   // fall-recovery safety net: respawn at origin
      const ry = spawnHeight(0, 0);
      body.setNextKinematicTranslation({ x: 0, y: ry, z: 0 });
      vy = 0; nt = { x: 0, y: ry, z: 0 };
      console.warn('[game] fell out of world — respawned');
    }
    playerObj.position.set(nt.x, nt.y - (capHalf + capR), nt.z);
    holder.rotation.y = modelYaw + THREE.MathUtils.degToRad(P.yaw_offset_deg || 0);
    if (DRIVE) {
      // suspension feel: pitch under accel/brake, roll into turns
      const accel = (vSpeed - prevV) / Math.max(dt, 1e-3); prevV = vSpeed;
      leanP = THREE.MathUtils.damp(leanP,
        THREE.MathUtils.clamp(-accel * 0.012, -0.06, 0.06), 6, dt);
      leanR = THREE.MathUtils.damp(leanR,
        THREE.MathUtils.clamp(mv.x * Math.min(Math.abs(vSpeed) / 8, 1) * 0.07, -0.08, 0.08), 6, dt);
      holder.rotation.x = leanP; holder.rotation.z = leanR;
    } else if (!FLY && !SWIM) {
      // FOOT-PLANT LITE (Phase 74): align the body to the terrain slope so
      // feet track the ground on hills instead of the front hovering and the
      // back sinking. Sampled fore/aft of the facing, softened + damped.
      const ahead = Math.max(0.45 * (P.height_m || 1), 0.3);
      const hF = hAt(nt.x + Math.sin(modelYaw) * ahead, nt.z + Math.cos(modelYaw) * ahead);
      const hB = hAt(nt.x - Math.sin(modelYaw) * ahead, nt.z - Math.cos(modelYaw) * ahead);
      const slopeP = Math.atan2(hB - hF, 2 * ahead) * 0.7;
      leanP = THREE.MathUtils.damp(leanP,
        THREE.MathUtils.clamp(slopeP, -0.35, 0.35), 5, dt);
      holder.rotation.x = leanP;
    }

    // animation state machine
    window.__pSpeed = speed;   // Phase 66: prey hearing keys off player loudness
    _dustT -= dt;
    if (speed > 3.2 && grounded && _dustT <= 0) {   // running on the ground
      puffDust(nt.x, hAt(nt.x, nt.z), nt.z);
      _dustT = 0.22;
    }
    if (mixer) {
      setAnim(speed < 0.1 ? actions.__idle : (mv.run && mv.mag > 0.3 ? actions.__run : actions.__walk));
      if (current && current.getClip()) {
        const base = current === actions.__run ? P.run_speed : P.walk_speed;
        current.timeScale = speed > 0.1 ? Math.max(speed / base, 0.5) : 1.0;
      }
      mixer.update(dt);
    }

    // Inspect mode is a SOFT FREEZE: NPCs, damage and timers hold still so
    // you can edit in peace, but the camera, player and rendering stay live
    if (gameStarted && !paused && !inspectOn) stepNPCs(dt, nt, performance.now() / 1000);
    if (tgtMark) {
      const tn = (!won && !lost && !inspectOn)
        ? nearestHostile(ATTACK === 'ranged' ? RANGED_RANGE : MELEE_REACH) : null;
      tgtMark.visible = !!tn;
      if (tn) {
        tgtMark.position.set(tn.obj.position.x,
                             tn.obj.position.y + tn.h + 0.35
                               + Math.sin(performance.now() / 240) * 0.06,
                             tn.obj.position.z);
      }
    }
    stepDynamics(dt, nt, performance.now() / 1000);

    // SURVIVE verb: hold out while escalating waves close in
    {
      const st = steps[stepIdx];
      if (st && st.kind === 'survive' && gameStarted && !paused && !won && !lost) {
        if (st._t0 === undefined) { st._t0 = performance.now(); st._wave = 0; st._sec = -1; }
        const elapsed = (performance.now() - st._t0) / 1000;
        if (elapsed > (st._wave + 1) * 20) {          // a bigger wave every 20s
          st._wave++;
          const woke = wakeWave(nt.x, nt.z, 1 + Math.min(st._wave, 3));
          if (woke) { popText(`Wave ${st._wave + 1}!`, '#ff8fa0'); sfx('beep'); }
        }
        const sec = Math.ceil(elapsed);
        if (sec !== st._sec) { st._sec = sec; renderQuest(); }   // once a second
        if (elapsed >= st.count) advanceStep();
      }
    }

    // goal beacon: pulse; completes REACH steps, decides RACE steps
    if (goalPos && !won && !lost) {
      if (goalMesh) goalMesh.rotation.z += dt * 0.8;
      const st = steps[stepIdx];
      const gd = Math.hypot(goalPos.x - nt.x, goalPos.z - nt.z);
      if (st && st.kind === 'reach' && gd < 2.2) advanceStep();
      else if (st && st.kind === 'race') {
        // live standings: position = cars already finished + cars closer to goal
        hudTick += dt;
        const rivals = npcs.filter(n => n.behavior === 'vehicle');
        if (hudTick > 0.25) {
          hudTick = 0;
          const ahead = raceFinishers + rivals.filter(n => !n.finished &&
            Math.hypot(goalPos.x - n.obj.position.x, goalPos.z - n.obj.position.z) < gd).length;
          objEl.style.display = 'block';
          objEl.textContent = `Race to the beacon — position ${ahead + 1} / ${rivals.length + 1}`;
        }
        if (gd < 2.6) {
          const rank = raceFinishers + 1;
          if (rank === 1) advanceStep();
          else doLose(`Finished #${rank} — the ${st.label || 'cars'} beat you. Try again!`);
        }
      }
    }
    // capture zones tick independently of the beacon — a capture game may
    // have no reach objective at all (goalPos null)
    {
      const stc = steps[stepIdx];
      if (stc && stc.kind === 'capture' && !won && !lost) stepCapture(stc, nt.x, nt.z, dt);
    }
    stepDmgNumbers(dt);
    stepDust(dt);
    if (window.__torches) {
      const tt = performance.now() / 1000;
      for (let i = 0; i < window.__torches.length; i++) {
        window.__torches[i].intensity = 12.5 + Math.sin(tt * 9 + i * 2.1) * 1.6
          + Math.sin(tt * 23 + i * 5.7) * 0.9;
      }
    }
    if (window.__clouds) {                          // slow downwind drift
      for (const sp of window.__clouds) {
        sp.position.x += dt * 1.6;
        if (sp.position.x > 1100) sp.position.x = -1100;
      }
    }

    // combat: attack cooldown + projectiles + gamepad attack edge
    pollGamepadAttack();
    if (atkCd > 0) atkCd -= dt;
    for (let i = projectiles.length - 1; i >= 0; i--) {
      const pr = projectiles[i];
      pr.mesh.position.addScaledVector(pr.vel, dt);
      pr.life -= dt;
      let hit = false;
      for (const n of npcs) {
        // Phase 68: prey ('flee') is shootable — hunting needs a kill
        if (!(n.behavior === 'hostile' || n.behavior === 'flee') || n.dead) continue;
        const dd = pr.mesh.position.distanceTo(n.obj.position.clone().add(new THREE.Vector3(0, 0.5, 0)));
        if (dd < 0.9) { dmgEnemy(n, atkDmg); hit = true; break; }
      }
      if (hit || pr.life <= 0 || pr.mesh.position.y < hAt(pr.mesh.position.x, pr.mesh.position.z) - 0.2) {
        pr.mesh.visible = false;               // back to the pool
        projectiles.splice(i, 1);
      }
    }
    if (projectiles.length) {
      projLight.position.copy(projectiles[projectiles.length - 1].mesh.position);
    } else if (projLight.intensity > 0) {
      projLight.intensity = 0;
    }

    // collectibles: bob + spin + proximity pickup
    if (collectibles.length) {
      const t = performance.now() / 1000;
      for (const c of collectibles) {
        if (!c.mesh.parent) continue;
        c.mesh.position.y = c.baseY + Math.sin(t * 2.2 + c.phase) * 0.22;
        c.mesh.rotation.y += dt * 2;
        const dx = c.mesh.position.x - nt.x, dz = c.mesh.position.z - nt.z;
        const pickR = Math.max(1.4, (P.height_m || 1) * 0.9);  // big heroes reach further
        if (dx * dx + dz * dz < pickR * pickR) {
          scene.remove(c.mesh);
          const st = steps[stepIdx];
          if (st && st.kind === 'collect') {
            st._got = (st._got || 0) + 1;
            sfx('pickup');
            burst(c.mesh.position, 0xffd54a);
            popText(`+1 ${st.label || ''}  ·  ${st._got}/${st.count}`, '#ffd54a');
            renderQuest();
            if (st._got >= st.count) advanceStep();
          }
        }
      }
    }

    // third-person follow camera — auto-recenters behind the player while
    // moving so turns stay visible; pauses 3 s after a manual drag-look
    freeLookT = Math.max(0, freeLookT - dt);
    if (!dragging && freeLookT <= 0 && mv.mag > 0.15) {
      let dyaw = (modelYaw + Math.PI) - yaw;
      dyaw = Math.atan2(Math.sin(dyaw), Math.cos(dyaw));
      yaw += dyaw * Math.min(1, (DRIVE ? 3.0 : 1.8) * dt);
    }
    // inspect free-cam looks at the roaming focus point, slightly pulled back
    const fX = (inspectOn && inspF) ? inspF.x : nt.x;
    const fZ = (inspectOn && inspF) ? inspF.z : nt.z;
    const fY = (inspectOn && inspF) ? hAt(fX, fZ) + 1.4 : nt.y;
    if (VIEW === 'topdown') {
      // 2D-Zelda camera: straight down, orthographic, wheel zooms the map
      camera.position.lerp(new THREE.Vector3(fX, fY + 46, fZ + 0.01), 1 - Math.exp(-8 * dt));
      camera.lookAt(fX, fY, fZ);
      camera.zoom = THREE.MathUtils.damp(camera.zoom || 1, 1.15 / camZoom, 6, dt);
      camera.updateProjectionMatrix();
    } else if (VIEW === 'side') {
      // side-scroller camera: fixed on the z axis, tracks the runner
      camera.position.lerp(new THREE.Vector3(fX, fY + 2.4, 42), 1 - Math.exp(-8 * dt));
      camera.lookAt(fX, fY + 1.1, 0);
      camera.zoom = THREE.MathUtils.damp(camera.zoom || 1, 1.0 / camZoom, 6, dt);
      camera.updateProjectionMatrix();
    } else {
      // Phase 69 look-ahead: the camera peeks ~0.9 m into the travel direction
      // at speed, so fast movement reads as intent instead of chase-cam lag
      const lookAhead = Math.min((window.__pSpeed || 0) / Math.max(P.run_speed, 1), 1) * 0.9;
      // STICKY-CAM FIX (2026-07-20): lookAt() is instant, so a raw look-ahead
      // point SNAPS sideways on every turn — damp the target like the
      // position, and the pan is glass again
      _camWant.set(fX + Math.sin(modelYaw) * lookAhead,
                   fY + SPEC.camera.height_m * 0.5,
                   fZ + Math.cos(modelYaw) * lookAhead);
      if (camTarget.lengthSq() === 0) camTarget.copy(_camWant);
      camTarget.lerp(_camWant, 1 - Math.exp(-7 * dt));
      const cd = SPEC.camera.distance_m * camZoom * (inspectOn ? 1.5 : 1);
      let cx = fX + Math.sin(yaw) * Math.cos(pitch) * cd;     // camera BEHIND
      let cz = fZ + Math.cos(yaw) * Math.cos(pitch) * cd;     // (W walks away)
      let cy = fY + Math.sin(pitch) * cd + SPEC.camera.height_m * 0.4;
      // INTERIOR (2026-07-23): never rise above the ceiling — the camera
      // outside the roof showed a void where the player should be
      if (INTERIOR) cy = Math.min(cy, (INTERIOR.wall_h || 4.0) - 0.35);
      // CAMERA COLLISION (moon plan 1.1): spherecast pull-in — a ray from the
      // player's head toward the desired camera spot; any wall in between
      // pulls the camera in front of it instead of letting it clip through
      {
        const hx = fX, hy = fY + SPEC.camera.height_m * 0.55, hz = fZ;
        let ddx = cx - hx, ddy = cy - hy, ddz = cz - hz;
        const dl = Math.hypot(ddx, ddy, ddz) || 1;
        ddx /= dl; ddy /= dl; ddz /= dl;
        const ray = new RAPIER.Ray({ x: hx, y: hy, z: hz }, { x: ddx, y: ddy, z: ddz });
        const hit = world.castRay(ray, dl, true, undefined, undefined, collider, body);
        if (hit && hit.timeOfImpact > 0.01) {
          const t = Math.max(hit.timeOfImpact - 0.3, 0.4);
          cx = hx + ddx * t; cy = hy + ddy * t; cz = hz + ddz * t;
        }
      }
      camera.position.lerp(new THREE.Vector3(cx, cy, cz), 1 - Math.exp(-8 * dt));
      camera.lookAt(camTarget);
    }
    if (shakeT > 0) {                    // decaying screen shake on damage
      shakeT = Math.max(0, shakeT - dt);
      camera.position.x += (Math.random() - 0.5) * 0.5 * shakeT;
      camera.position.y += (Math.random() - 0.5) * 0.4 * shakeT;
    }
    stepBursts(dt);
    if (gameStarted && !paused) {
      stepHealthPacks(dt, nt);
      stepInteract(nt);
      if (!inspectOn) stepHurtZones(dt, nt);
      if (!inspectOn) stepStorm(dt, nt);   // battle-royale zone (Phase 61)
      if (!inspectOn) stepBall(dt, nt);    // sports ball + goal (Phase 61)
    }
    // placed creatures idle-breathe even while paused/inspecting — life sells
    for (const p of placedItems) {
      if (p.anim) p.anim.update(dt);
    }
    // sky life drifts
    for (const c of clouds) {
      c.sp.position.x += c.v * dt;
      if (c.sp.position.x > gsize * 0.75) c.sp.position.x = -gsize * 0.75;
    }
    for (const b of birds) {
      b.a += b.w * dt * 8;
      b.sp.position.set(b.cx + Math.cos(b.a) * b.r,
                        b.h + Math.sin(b.a * 2) * 1.5,
                        b.cz + Math.sin(b.a) * b.r);
    }

    // procedural swim/flap motion: time + speed-scaled amplitude
    if (procShaders.length) {
      const a = 0.35 + 0.65 * Math.min(speed / Math.max(P.walk_speed, 0.1), 1) * mv.mag
        + (keys.Space || keys.KeyC ? 0.25 : 0);
      const tNow = performance.now() / 1000;
      for (const sh of procShaders) {
        sh.uniforms.uTime.value = tNow;
        sh.uniforms.uAmp.value += (Math.min(a, 1) - sh.uniforms.uAmp.value) * Math.min(4 * dt, 1);
      }
    }
    if (stylePass) stylePass.uniforms.time.value = performance.now() / 1000;
    renderDepthPrepass();               // SSAO depth (half-res, RGBA-packed)
    composer.render();
    // live state for the verify harness (extends the __game probe object)
    window.__game.state = { x: nt.x, y: nt.y, z: nt.z, modelYaw, yaw, speed,
                            started: gameStarted, go: raceGo,
                            dormant: npcs.reduce((a, n) => a + (n.dormant ? 1 : 0), 0) };
    fCount++; fTime += dt;
    if (fTime >= 0.5) {
      const fps = fCount / fTime;
      fpsEl.textContent = Math.round(fps) + ' fps';
      // ADAPTIVE QUALITY: sustained low fps sheds cost tiers instead of
      // letting the game lag — resolution first, then bloom, then frozen
      // shadow updates. Never steps back up mid-run (avoids oscillation).
      lowT = fps < 28 ? lowT + 1 : 0;
      if (lowT >= 4 && qTier === 0) {
        qTier = 1; renderer.setPixelRatio(STYLE_PR || 1);
        composer.setPixelRatio && composer.setPixelRatio(STYLE_PR || 1);
        console.log('[game] adaptive quality: resolution tier (fps rescue)');
      } else if (lowT >= 8 && qTier === 1) {
        qTier = 2; bloom.enabled = false;
        console.log('[game] adaptive quality: bloom off');
      } else if (lowT >= 12 && qTier === 2) {
        qTier = 3; renderer.shadowMap.autoUpdate = false;
        console.log('[game] adaptive quality: shadows frozen');
      }
      fCount = 0; fTime = 0;
    }
  });

  addEventListener('resize', () => {
    if (camera.isPerspectiveCamera) {
      camera.aspect = innerWidth / innerHeight;
    } else {
      const oa = innerWidth / innerHeight;
      const os = VIEW === 'side' ? 9 : 16;
      camera.left = -os * oa; camera.right = os * oa;
      camera.top = os; camera.bottom = -os;
    }
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight, false);   // keep CSS 100% fill; only resize the buffer
    composer.setSize(innerWidth, innerHeight);
    _dRT.setSize(innerWidth >> 1, innerHeight >> 1);
    ssao.uniforms.res.value.set(innerWidth, innerHeight);
    if (stylePass) stylePass.uniforms.res.value.set(innerWidth, innerHeight);
  });
  // FIT AFTER LAYOUT SETTLES (2026-07-08): the first frame can capture a stale
  // innerWidth (Firefox measured the canvas smaller than the window → black
  // gap). Re-fit once the layout is final.
  requestAnimationFrame(() => dispatchEvent(new Event('resize')));
  addEventListener('load', () => dispatchEvent(new Event('resize')));
  console.log('[game] ready:', SPEC.title);
}

main().catch(e => fail(e.message || String(e)));
