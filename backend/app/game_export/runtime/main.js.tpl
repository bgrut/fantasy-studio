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
import { N8AOPass } from './vendor/n8ao.module.js';
import { CSM } from './vendor/jsm/csm/CSM.js';
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
  function _sirenLoop(actx, master) {
    // distant siren: two slow alternating tones, very quiet, far-city feel
    const osc = actx.createOscillator(), g2 = actx.createGain();
    osc.type = 'sine'; g2.gain.value = 0;
    osc.connect(g2); g2.connect(master);
    osc.start();
    const t0 = actx.currentTime;
    g2.gain.setValueAtTime(0, t0);
    g2.gain.linearRampToValueAtTime(0.016, t0 + 0.8);
    for (let k2 = 0; k2 < 6; k2++) {
      osc.frequency.setValueAtTime(660, t0 + k2 * 0.55);
      osc.frequency.linearRampToValueAtTime(880, t0 + k2 * 0.55 + 0.5);
    }
    g2.gain.linearRampToValueAtTime(0, t0 + 3.6);
    setTimeout(() => { try { osc.stop(); } catch (e) {} }, 4200);
    setTimeout(() => _sirenLoop(actx, master), 28000 + Math.random() * 42000);
  }
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
      // city nights get distant sirens instead of crickets (Phase 120)
      if (window.__isCity && (sky === 'night' || sky === 'dusk') && SPEC.style !== 'horror') {
        setTimeout(() => { if (ambientOn && !sfxMuted) _sirenLoop(actx, actx.destination); },
                   9000 + Math.random() * 15000);
      }
      // night crickets: sparse randomized chirps (skip horror = dead silence sells it)
      if ((sky === 'night' || sky === 'dusk') && SPEC.style !== 'horror' && !window.__isCity) {
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
  // QUALITY PRESETS (Phase 116): ultra (default) / balanced / performance —
  // set from the studio (localStorage) or a ?q= override. The FPS governor
  // still steps quality down dynamically on weak machines.
  const QUALITY = (new URLSearchParams(location.search).get('q')
    || (function () { try { return localStorage.getItem('fs_quality'); } catch (e) { return null; } })()
    || 'ultra');
  const QCFG = {
    ultra:       { dpr: Math.min(devicePixelRatio, 2),   msaa: 4, shadow: 4096 },
    balanced:    { dpr: Math.min(devicePixelRatio, 1.5), msaa: 4, shadow: 2048 },
    performance: { dpr: 1,                               msaa: 0, shadow: 2048 },
  }[QUALITY] || { dpr: Math.min(devicePixelRatio, 2), msaa: 4, shadow: 4096 };
  renderer.setPixelRatio(QCFG.dpr);
  renderer.setSize(innerWidth, innerHeight, false);   // false: don't set inline px style — CSS fills
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  // AgX (Arc A, 2026-07-28): Blender-4-default tonemapper — best hue
  // preservation under bright light (ACES skews skin/saturated paint toward
  // orange). AgX runs ~1 stop flatter, so exposure is compensated below and
  // the grade pass adds the punch back deliberately.
  renderer.toneMapping = THREE.AgXToneMapping;
  // Phase 65: per-environment exposure; snow is high-albedo — damp it further
  // so arctic scenes read as LIT SNOW instead of a white void.
  renderer.toneMappingExposure = ((SKY[SPEC.world.sky] || SKY.day).exp || 0.75)
    * (SPEC.world.weather === 'snow' ? 0.86 : 1.0)
    // high-albedo grounds (desert sand, beach) wash out like snow does —
    // same damp, keyed on the actual ground color instead of a name list
    * ((0.299 * SPEC.world.ground_color[0] + 0.587 * SPEC.world.ground_color[1]
        + 0.114 * SPEC.world.ground_color[2]) > 0.62 ? 0.88 : 1.0)
    * 1.35;   // AgX compensation: ~1 stop flatter than the old ACES curve
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
  // PHASE 140 — SCENE-IMAGE PANORAMA (the mint.gg pattern, local): the
  // user's dropped image, SDXL-expanded to a 360 equirect, IS the world:
  // visible backdrop + PMREM light source in one. Any sky mood; beats the
  // HDRI when set. Loads async and hides the procedural dome + clouds.
  if (SPEC.world.pano) {
    new THREE.TextureLoader().load(SPEC.world.pano, (pt2) => {
      pt2.mapping = THREE.EquirectangularReflectionMapping;
      pt2.colorSpace = THREE.SRGBColorSpace;
      const pmP = new THREE.PMREMGenerator(renderer);
      scene.environment = pmP.fromEquirectangular(pt2).texture;
      pmP.dispose();
      if ('environmentIntensity' in scene) scene.environmentIntensity = 0.62;
      scene.background = pt2;
      scene.backgroundIntensity = 1.15;
      // dark source images (dusk/night photos) need a lift or the whole
      // world reads murky — pano worlds get a brighter floor of light
      if ('environmentIntensity' in scene) {
        scene.environmentIntensity = Math.max(scene.environmentIntensity, 0.85);
      }
      renderer.toneMappingExposure *= 1.18;
      if (window.__skyDome) window.__skyDome.visible = false;
      if (window.__clouds) for (const sp of window.__clouds) sp.visible = false;
      console.log('[game] scene panorama world: ' + SPEC.world.pano);
      // PHASE B — PARALLAX DOME: displace a sphere by the panorama's depth
      // map so near scenery sits close and far scenery sits far — REAL
      // parallax as the player moves (the walkable-splat feel), replacing
      // the flat infinity backdrop. Falls back silently to the flat pano.
      if (SPEC.world.pano_depth && !SPEC.world.splat) {   // splat lift replaces the dome
        const dim = new Image();
        dim.onload = () => {
          try {
            const dc = document.createElement('canvas');
            dc.width = dim.width; dc.height = dim.height;
            const dg = dc.getContext('2d');
            dg.drawImage(dim, 0, 0);
            const dd = dg.getImageData(0, 0, dc.width, dc.height).data;
            const sampleD = (u, v) => {
              const x = Math.min(dc.width - 1, Math.max(0, Math.round(u * (dc.width - 1))));
              const y = Math.min(dc.height - 1, Math.max(0, Math.round(v * (dc.height - 1))));
              return dd[(y * dc.width + x) * 4] / 255;
            };
            const dgeo = new THREE.SphereGeometry(1, 128, 64);
            const dpa = dgeo.attributes.position;
            const duv = dgeo.attributes.uv;
            for (let i = 0; i < dpa.count; i++) {
              const d = sampleD(duv.getX(i), duv.getY(i));
              // depth 1 = near -> 45m; depth 0 = far -> capped 340m. The
              // dome is SCENERY parallax, not walls — pulling near regions
              // closer than ~45m turned them into giant facets (verified).
              const r = Math.min(340, 45 / Math.max(d, 0.14));
              dpa.setXYZ(i, dpa.getX(i) * r, dpa.getY(i) * r + 1.6, dpa.getZ(i) * r);
            }
            const dome = new THREE.Mesh(dgeo, new THREE.MeshBasicMaterial({
              map: pt2, side: THREE.BackSide, fog: false,
              toneMapped: true }));
            dome.scale.x = -1;              // equirect faces inward correctly
            dome.frustumCulled = false;
            dome.renderOrder = -1;
            scene.add(dome);
            console.log('[game] parallax dome active');
          } catch (e) { console.warn('[game] parallax dome skipped: ' + e.message); }
        };
        dim.src = SPEC.world.pano_depth;
      }
    }, undefined, () => console.warn('[game] pano skipped'));
  }
  if (SPEC.world.sky !== 'night') {
    const sky = new Sky();
    sky.scale.setScalar(4000);
    scene.add(sky);
    window.__skyDome = sky;             // r15: HDRI background hides this
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
    // UNIVERSAL ENV (Tier 2): skies without the atmosphere model (night,
    // interiors) still need image-based light or PBR materials read dead.
    // A tinted gradient env is cheap and grounds every material response.
    if (!scene.environment) {
      try {
        const pm2 = new THREE.PMREMGenerator(renderer);
        const es2 = new THREE.Scene();
        es2.background = new THREE.Color(pal.sky).lerp(new THREE.Color(0xffffff), 0.2);
        scene.environment = pm2.fromScene(es2, 0.02).texture;
        pm2.dispose();
      } catch (e) {}
    }
    if ('environmentIntensity' in scene) scene.environmentIntensity = 0.62;
    // HDRI IBL (Arc B slice, 2026-07-28): a real captured environment beats
    // any procedural one — correct ambient color + reflections on every PBR
    // material. CC0 Poly Haven capture bundled per sky mood at export; loads
    // async and replaces the procedural env when ready (sky dome stays the
    // visible background so the horizon art direction is unchanged).
    if (SPEC.world.hdri && !SPEC.world.pano) {
      import('./vendor/jsm/loaders/RGBELoader.js').then(({ RGBELoader }) => {
        new RGBELoader().load(SPEC.world.hdri, (tex) => {
          tex.mapping = THREE.EquirectangularReflectionMapping;
          const pmH = new THREE.PMREMGenerator(renderer);
          const envH = pmH.fromEquirectangular(tex).texture;
          pmH.dispose();
          scene.environment = envH;
          if ('environmentIntensity' in scene) scene.environmentIntensity = 0.5;
          // r15 PHOTOGRAPHIC SKY: the HDRI was IBL-only — the VISIBLE sky
          // stayed a procedural gradient (the '2000s' backdrop). For
          // photoreal outdoor moods the real captured sky (actual clouds,
          // real horizon glow) IS the background now; the procedural dome
          // + cloud sprites hide so they don't occlude it.
          if ((SPEC.style || 'default') === 'default'
              && ['day', 'sunset', 'overcast', 'dusk'].includes(SPEC.world.sky)) {
            scene.background = tex;
            scene.backgroundIntensity = SPEC.world.sky === 'day' ? 1.0 : 0.9;
            if (window.__skyDome) window.__skyDome.visible = false;
            if (window.__clouds) {
              for (const sp of window.__clouds) sp.visible = false;
            }
            console.log('[game] HDRI sky background active');
          } else {
            tex.dispose();
          }
          console.log('[game] HDRI environment: ' + SPEC.world.hdri);
        }, undefined, () => console.warn('[game] HDRI env skipped — procedural stays'));
      }).catch(() => {});
    }
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
    if (!(((SPEC.world || {}).level || {}).osm) && !(((SPEC.world || {}).level || {}).interior)
        && !SPEC.world.pano) {   // image worlds: the PANORAMA is the horizon
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
    // UNIVERSAL ENV for flat skies (night/space): tinted gradient env so
    // PBR materials keep a live response after dark
    try {
      const pm3 = new THREE.PMREMGenerator(renderer);
      const es3 = new THREE.Scene();
      es3.background = new THREE.Color(pal.sky).lerp(new THREE.Color(0xffffff), 0.15);
      scene.environment = pm3.fromScene(es3, 0.02).texture;
      pm3.dispose();
      if ('environmentIntensity' in scene) scene.environmentIntensity = 0.4;
    } catch (e) {}
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

  // r11 LIGHTING POLISH: flat ambience was killing depth — drop the hemi
  // fill 15% and push the sun 12% so shadowed faces separate from lit ones
  // (the AAA contrast ratio), with the HDRI env carrying more of the fill.
  const hemi = new THREE.HemisphereLight(pal.sky, 0x3a3f35, pal.amb * 0.85);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(pal.sunCol || 0xffffff, pal.sun * 1.12);
  sun.position.set(...pal.sunPos);
  sun.castShadow = true;
  sun.shadow.mapSize.set(QCFG.shadow, QCFG.shadow);
  // fit the shadow frustum to the VISIBLE play area (48 m), not the whole
  // world — 4096 texels over 96 m = crisp contact shadows, console-style
  const sc = Math.min(SPEC.world.size_m * 0.5, 48);
  Object.assign(sun.shadow.camera, { left: -sc, right: sc, top: sc, bottom: -sc, far: 400 });
  sun.shadow.camera.updateProjectionMatrix();
  scene.add(sun);
  // CASCADED SHADOWS (Arc A round 3, 2026-07-28): big worlds/cities get
  // 3-cascade sun shadows — crisp near the camera AND still shadowed at
  // distance, instead of one 48m fitted box with a bare horizon. Small
  // worlds keep the proven fitted map (lower risk, same look). The CSM
  // cascade lights REPLACE the sun's light+shadow contribution; materials
  // are patched by a periodic traversal so late-spawned meshes join in.
  let csm = null;
  if (SPEC.world.size_m > 120 && QUALITY !== 'performance') {
    try {
      csm = new CSM({
        maxFar: 260, cascades: 3, mode: 'practical',
        shadowMapSize: 2048,
        lightDirection: new THREE.Vector3(...pal.sunPos).multiplyScalar(-1).normalize(),
        lightIntensity: pal.sun,
        camera, parent: scene,
      });
      for (const l of csm.lights) l.color.set(pal.sunCol || 0xffffff);
      csm.fade = true;
      csm.updateFrustums();
      sun.castShadow = false;
      sun.intensity = 0;                 // cascades carry the sun now
      const _csmSeen = new WeakSet();
      window.__csmPatch = () => scene.traverse((o) => {
        if (!o.material) return;
        const ms = Array.isArray(o.material) ? o.material : [o.material];
        for (const m of ms) {
          if ((m.isMeshStandardMaterial || m.isMeshPhysicalMaterial
               || m.isMeshLambertMaterial || m.isMeshPhongMaterial)
              && !_csmSeen.has(m)) { csm.setupMaterial(m); _csmSeen.add(m); }
        }
      });
    } catch (e) { console.warn('[game] CSM unavailable: ' + e.message); csm = null; }
  }

  // HERO RIM LIGHT (Phase 116): the classic AAA separator — a cool
  // back-light opposite the sun that only reads on silhouette edges.
  // Position follows the player every frame (updated in the main loop).
  const rim = new THREE.DirectionalLight(0xbfd8ff, 1.1);
  rim.castShadow = false;
  scene.add(rim);
  scene.add(rim.target);
  const _sunDirN = new THREE.Vector3(...pal.sunPos).normalize();

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
  window.__isCity = !!OSM;
  if (OSM && LVL && LVL.landmarks) LVL.landmarks = [];   // no 30m trees on sidewalks                          // ambient (module scope) reads this
  const INTERIOR = (LVL && LVL.interior) || null;   // Phase 95: room levels
  const gcol = new THREE.Color(...SPEC.world.ground_color);
  {
    // SATURATION FLOOR (Phase 76): LLM ground colors trend pastel — real
    // grass/soil is richer. Only colored grounds are lifted (snow/sand with
    // near-zero saturation stay untouched).
    const _h = {}; gcol.getHSL(_h);
    if (_h.s > 0.08 && _h.s < 0.3) gcol.setHSL(_h.h, 0.34, Math.min(_h.l, 0.42));
  }
  const TEXN = (LVL && LVL.osm) ? 2048 : (LVL ? 1024 : 256);   // cities need the res for road markings
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
    // CENTER DASHES + CROSSWALKS (Phase 119): road markings painted into
    // the same ground canvas — lane dashes along every street, zebra
    // stripes where road ENDPOINTS meet (real OSM intersections).
    ctx.globalAlpha = 0.5; ctx.strokeStyle = '#c9c37a';
    ctx.setLineDash([Math.max(2, 3 / gsize * TEXN), Math.max(2, 4 / gsize * TEXN)]);
    ctx.lineWidth = Math.max(2, 0.5 / gsize * TEXN);
    for (const r of OSM.roads) {
      ctx.beginPath();
      r.pts.forEach(([x, z], i) => i ? ctx.lineTo(W2T(x), W2T(z)) : ctx.moveTo(W2T(x), W2T(z)));
      ctx.stroke();
    }
    ctx.setLineDash([]); ctx.globalAlpha = 1;
    window.__junctions = [];
    const _ends = {};
    for (const r of OSM.roads) {
      for (const p2 of [r.pts[0], r.pts[r.pts.length - 1]]) {
        const k = Math.round(p2[0] / 4) + ',' + Math.round(p2[1] / 4);
        (_ends[k] = _ends[k] || { x: p2[0], z: p2[1], n: 0, hd: r }).n++;
      }
    }
    ctx.fillStyle = '#d8d8d8'; ctx.globalAlpha = 0.55;
    for (const k in _ends) {
      const j = _ends[k];
      if (j.n < 3) continue;                       // true intersections only
      window.__junctions.push([j.x, j.z]);
      const hp = j.hd.pts, a2 = Math.atan2(hp[1][0] - hp[0][0], hp[1][1] - hp[0][1]);
      const stripeW = Math.max(1, 0.6 / gsize * TEXN);
      for (let si = -3; si <= 3; si++) {
        const off = si * 1.1;
        const sx2 = j.x + Math.cos(a2) * off, sz2 = j.z - Math.sin(a2) * off;
        ctx.save();
        ctx.translate(W2T(sx2), W2T(sz2));
        ctx.rotate(-a2);
        ctx.fillRect(-stripeW / 2, -Math.max(2, 2.6 / gsize * TEXN), stripeW, Math.max(4, 5.2 / gsize * TEXN));
        ctx.restore();
      }
    }
    ctx.globalAlpha = 1;
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
  // PANO GROUND (140D, 'you don't make it the ground'): in image worlds the
  // floor texture IS the photo's floor, reprojected onto the plane at bake
  // time — beach sand underfoot is the image's sand, continuous with the
  // horizon. Replaces the painted canvas + macro tint entirely.
  let panoGroundTex = null;
  if (SPEC.world.pano_ground) {
    panoGroundTex = new THREE.TextureLoader().load(SPEC.world.pano_ground);
    panoGroundTex.wrapS = panoGroundTex.wrapT = THREE.ClampToEdgeWrapping;
    panoGroundTex.colorSpace = THREE.SRGBColorSpace;
    panoGroundTex.anisotropy = 8;
    panoGroundTex.repeat.set(gsize / 240, gsize / 240);   // bake spans ±120m
    panoGroundTex.offset.set(0.5 - gsize / 480, 0.5 - gsize / 480);
  }
  const gmat = new THREE.MeshStandardMaterial({
    map: panoGroundTex || gtex, roughness: 0.96,
    bumpMap: btex, bumpScale: panoGroundTex ? 0.12 : 0.35 });
  // MACRO VARIATION (Phase 74): the tiled detail map repeats every 8 m, so
  // from any distance the ground reads as one flat tone. A second LOW-FREQ
  // canvas is sampled in WORLD coordinates (1:1 across the map, no tiling)
  // and multiplied over the albedo — big soft meadow/soil drifts like real
  // terrain, for one extra texture fetch.
  if (!panoGroundTex) {          // photo floor owns the albedo — no tint mixing
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
  // PURE SCENE floor (2026-08-04): image worlds get a FLAT walkable plane —
  // procedural hills punched through the panorama as giant mismatched cones
  // (playtest). mint-style: the image owns all relief; the floor is level.
  if (SPEC.world.pano && LVL && LVL.heights) {
    LVL.heights = LVL.heights.map(() => 0);
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
    // HORIZON SKIRT (Phase 122): beyond the painted map, a vast apron in
    // the same ground tone runs to 6x the world size — fog fades it into
    // the sky, so every outdoor world ends gracefully instead of at a cliff
    if (!INTERIOR && !SPEC.world.pano) {   // pano worlds: photo floor ends at its own horizon
      const skirtC = gcol.clone().offsetHSL(0, -0.04, -0.02);
      const skirt = new THREE.Mesh(
        new THREE.RingGeometry(gsize * 0.495, gsize * 6, 48, 1),
        new THREE.MeshStandardMaterial({ color: skirtC, roughness: 1.0 }));
      skirt.rotation.x = -Math.PI / 2;
      skirt.position.y = -0.06;
      skirt.receiveShadow = true;
      scene.add(skirt);
    }
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
  const _flatStyle = (SPEC.style || 'default') === 'cartoon';
  function cartoonizeTexture(mm) {
    // TRUE-CARTOON fills (Phase 132): blur away fur/noise detail, posterize
    // to a handful of colors, resaturate — fox fur becomes clean orange
    const img2 = mm.map && mm.map.image;
    if (!img2 || !img2.width) return;
    try {
      const c3 = document.createElement('canvas');
      c3.width = c3.height = 256;
      const g3 = c3.getContext('2d');
      g3.filter = 'blur(5px) saturate(1.6)';
      g3.drawImage(img2, 0, 0, 256, 256);
      g3.filter = 'none';
      const d3 = g3.getImageData(0, 0, 256, 256);
      // DOMINANT-PALETTE quantize (v2): find the 5 most common coarse colors
      // and snap every pixel to the nearest — genuine flat cel regions, not
      // per-channel confetti
      const hist2 = new Map();
      for (let i2 = 0; i2 < d3.data.length; i2 += 4) {
        const k2 = ((d3.data[i2] >> 5) << 6) | ((d3.data[i2 + 1] >> 5) << 3) | (d3.data[i2 + 2] >> 5);
        hist2.set(k2, (hist2.get(k2) || 0) + 1);
      }
      const pal2 = [...hist2.entries()].sort((a2, b2) => b2[1] - a2[1]).slice(0, 5)
        .map(([k2]) => [((k2 >> 6) & 7) * 36 + 18, ((k2 >> 3) & 7) * 36 + 18, (k2 & 7) * 36 + 18]);
      for (let i2 = 0; i2 < d3.data.length; i2 += 4) {
        let bi2 = 0, bd2 = 1e9;
        for (let p2 = 0; p2 < pal2.length; p2++) {
          const dr = d3.data[i2] - pal2[p2][0], dg = d3.data[i2 + 1] - pal2[p2][1], db = d3.data[i2 + 2] - pal2[p2][2];
          const dd2 = dr * dr + dg * dg + db * db;
          if (dd2 < bd2) { bd2 = dd2; bi2 = p2; }
        }
        d3.data[i2] = pal2[bi2][0]; d3.data[i2 + 1] = pal2[bi2][1]; d3.data[i2 + 2] = pal2[bi2][2];
      }
      g3.putImageData(d3, 0, 0);
      const t3 = new THREE.CanvasTexture(c3);
      t3.colorSpace = THREE.SRGBColorSpace;
      t3.flipY = mm.map.flipY;
      mm.map = t3;
      mm.normalMap = null;
      mm.needsUpdate = true;
    } catch (e) {}
  }
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
    // AUTOMOTIVE CLEARCOAT (Phase 134/B): real paint is clear lacquer over
    // pigment — the physical clearcoat layer + a strong env feed makes
    // showroom shots read 'wet'. Standard material was the old ceiling.
    root.traverse(o => {
      if (!o.isMesh) return;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      const out = mats.map(m => {
        if (!m || !m.isMeshStandardMaterial) return m;
        despeckleTexture(m);
        const pm = new THREE.MeshPhysicalMaterial();
        THREE.MeshStandardMaterial.prototype.copy.call(pm, m);
        pm.clearcoat = 1.0;
        pm.clearcoatRoughness = 0.08;
        pm.roughness = 0.34;
        pm.metalness = 0.25;
        pm.envMapIntensity = 1.5;
        pm.needsUpdate = true;
        return pm;
      });
      o.material = Array.isArray(o.material) ? out : out[0];
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
  function roadDist(x, z) {
    // distance to the nearest OSM street centerline — scatter/props must
    // never plant a tree in the middle of an avenue (2026-07-27 London)
    if (!OSM || !OSM.roads) return 1e9;
    let best = 1e9;
    for (const r of OSM.roads) {
      const p = r.pts;
      for (let i = 0; i < p.length - 1; i++) {
        const ax2 = p[i][0], az2 = p[i][1], bx2 = p[i + 1][0], bz2 = p[i + 1][1];
        const dx2 = bx2 - ax2, dz2 = bz2 - az2;
        const L2 = dx2 * dx2 + dz2 * dz2 || 1e-9;
        const t2 = Math.max(0, Math.min(1, ((x - ax2) * dx2 + (z - az2) * dz2) / L2));
        const d2 = Math.hypot(x - (ax2 + t2 * dx2), z - (az2 + t2 * dz2));
        if (d2 < best) best = d2;
        if (best < 1) return best;
      }
    }
    return best;
  }
  function inBldg(x, z, pad = 1.5) {
    for (const b of bldBoxes) {
      if (x > b[0] - pad && x < b[2] + pad && z > b[1] - pad && z < b[3] + pad) return true;
    }
    return false;
  }
  if (OSM && OSM.buildings && OSM.buildings.length) {
    // FACADE BUCKETS (Phase 118): 0 = procedural window grid (keeps the
    // night glow), 1 = glass tower, 2 = brick walk-up, 3 = pre-war stone.
    // Tall core buildings lean glass; the rest mix — one merged mesh per
    // bucket, so a whole city is 5 draw calls.
    const wallBuckets = [[], [], [], [], [], [], [], []], capGeos = [];
    const roofSpots = [];
    const tintA = new THREE.Color(0x8d8a84), tintB = new THREE.Color(0x5f6b78);
    const rngB = mulberry32(SPEC.seed + 77);
    // ExtrudeGeometry groups: materialIndex 0 = caps (roof/underside after the
    // rotate), 1 = side walls. Split so walls get the facade texture and roofs
    // stay plain — window grids on rooftops read as a bug from the follow-cam.
    function splitGroups(geo, bucket) {
      // DENSITY ARC r2: per-BUILDING tone painted into the vertex colors —
      // photo-facade buckets merge a whole district into one mesh, so every
      // tower shared one identical tint (the 'box city' tell). A weathered
      // tone spread per building breaks the clone skyline at zero extra
      // draw calls (materials below get vertexColors: true).
      const tone = 0.72 + rngB() * 0.36;
      const warm = (rngB() - 0.5) * 0.10;
      for (const g of geo.groups) {
        const sub = new THREE.BufferGeometry();
        for (const name of ['position', 'normal', 'uv', 'color']) {
          const a = geo.attributes[name];
          sub.setAttribute(name, new THREE.BufferAttribute(
            a.array.slice(g.start * a.itemSize, (g.start + g.count) * a.itemSize), a.itemSize));
        }
        if (bucket > 0 && g.materialIndex !== 0) {
          // r7 GI-LITE: vertical ambient-occlusion gradient baked into the
          // vertex colors — walls darken toward the street (ground bounce
          // shadowing) exactly like baked GI reads. The cheapest big
          // photoreal lever: real city renderers (streets-gl) do the same.
          const ca = sub.attributes.color;
          const pa = sub.attributes.position;
          for (let i = 0; i < ca.count; i++) {
            const y = pa.getY(i);
            const gAO = 0.68 + 0.32 * Math.min(Math.max(y / 7.5, 0), 1);
            // r8 PLINTH: a distinctly darker neutral ground-floor band —
            // real buildings have stone bases/storefront framing; bare
            // facade texture running into the sidewalk is a game-city tell
            const plinth = y < 4.0 ? 0.62 : 1.0;
            const pw = y < 4.0 ? 0.3 : 1.0;      // desaturate the warm shift
            ca.setXYZ(i, (tone + warm * pw) * gAO * plinth,
                      tone * gAO * plinth,
                      (tone - warm * 0.6 * pw) * gAO * plinth);
          }
        }
        (g.materialIndex === 0 ? capGeos : wallBuckets[bucket]).push(sub);
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
        // MANHATTAN PROFILE (Phase 118): heights rise toward the city core —
        // skyscraper center, mid-rise ring, low-rise edges. Reads as downtown
        // from every camera angle.
        const _half = SPEC.world.size_m * 0.5;
        const _core = Math.max(0, 1 - Math.hypot(cx, cz) / (_half * 0.85));
        const h = Math.min(Math.max((b.h || 9) * (1 + 2.6 * _core * _core), 4), 55);
        const geo = new THREE.ExtrudeGeometry(shape, { depth: h, bevelEnabled: false });
        geo.rotateX(-Math.PI / 2);                                // extrude up
        const gy = hAt(cx, cz);
        geo.translate(0, gy, 0);
        const tint = tintA.clone().lerp(tintB, rngB()).offsetHSL(0, 0, (rngB() - 0.5) * 0.12);
        const nv = geo.attributes.position.count, cols = new Float32Array(nv * 3);
        for (let i = 0; i < nv; i++) { cols[i * 3] = tint.r; cols[i * 3 + 1] = tint.g; cols[i * 3 + 2] = tint.b; }
        geo.setAttribute('color', new THREE.BufferAttribute(cols, 3));
        // photo facades ONLY by day (2026-07-28: the procedural grid reads
        // as placeholder in daylight); at night it keeps a 25% share for
        // the lit-window checkerboard until photo facades learn to glow
        const _night = ['night', 'dusk', 'sunset'].includes(SPEC.world.sky);
        // r7: seven facade families (was three) — a real skyline mix.
        // Towers: two glass looks + concrete + stone; mid-rise: two bricks
        // + limestone + stone. Night keeps a 20% procedural share for the
        // lit-checkerboard variety.
        const _r = rngB();
        const _bkt = h > 26
          ? (_r < 0.35 ? 1 : _r < 0.6 ? 4 : _r < 0.8 ? 6 : 3)
          : (_night && rngB() < 0.2 ? 0
             : (_r < 0.28 ? 2 : _r < 0.52 ? 5 : _r < 0.76 ? 7 : 3));
        splitGroups(geo, _bkt);
        // r14 SETBACKS: real towers STEP BACK as they rise — a single
        // extruded prism is why buildings read as 'geometric shapes'.
        // Tall buildings gain 1-2 shrinking tiers above the base (same
        // facade bucket + tint, so they read as one building).
        if (h > 30) {
          const tiers = h > 44 ? 2 : 1;
          let topY = gy + h;
          for (let ti2 = 1; ti2 <= tiers; ti2++) {
            const shrink = 1 - 0.15 * ti2;
            const th2 = h * (0.38 - 0.1 * ti2);
            const s2h = new THREE.Shape();
            b.pts.forEach(([px, pz], i) => {
              const sx5 = cx + (px - cx) * shrink;
              const sz5 = cz + (pz - cz) * shrink;
              i ? s2h.lineTo(sx5, -sz5) : s2h.moveTo(sx5, -sz5);
            });
            const tg = new THREE.ExtrudeGeometry(s2h, { depth: th2, bevelEnabled: false });
            tg.rotateX(-Math.PI / 2);
            tg.translate(0, topY, 0);
            const nv2 = tg.attributes.position.count;
            const cols2 = new Float32Array(nv2 * 3);
            for (let i = 0; i < nv2; i++) {
              cols2[i * 3] = tint.r; cols2[i * 3 + 1] = tint.g; cols2[i * 3 + 2] = tint.b;
            }
            tg.setAttribute('color', new THREE.BufferAttribute(cols2, 3));
            splitGroups(tg, _bkt);
            topY += th2;
          }
        }
        if (h >= 16 && (mxx - mnx) > 7 && (mxz - mnz) > 7) {
          roofSpots.push([cx, cz, gy + h, (mxx - mnx), (mxz - mnz)]);
        }
        bldBoxes.push([mnx, mnz, mxx, mxz]);
        // CONVEX HULL collider (2026-07-27 'invisible walls'): the old
        // axis-aligned box overhung the street for any diagonal footprint.
        try {
          const hullPts = new Float32Array(b.pts.length * 6);
          b.pts.forEach(([px3, pz3], pi3) => {
            hullPts[pi3 * 6] = px3;     hullPts[pi3 * 6 + 1] = gy;     hullPts[pi3 * 6 + 2] = pz3;
            hullPts[pi3 * 6 + 3] = px3; hullPts[pi3 * 6 + 4] = gy + h; hullPts[pi3 * 6 + 5] = pz3;
          });
          const hull = RAPIER.ColliderDesc.convexHull(hullPts);
          if (hull) world.createCollider(hull);
          else throw new Error('hull failed');
        } catch (e) {
          world.createCollider(RAPIER.ColliderDesc
            .cuboid((mxx - mnx) / 2, h / 2, (mxz - mnz) / 2)
            .setTranslation(cx, gy + h / 2, cz));
        }
      } catch (e) { /* one bad footprint never kills the city */ }
    }
    if (wallBuckets.some(b => b.length)) {
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
      // photo facade materials (SDXL pack): one tile ~= 18m x 12m of building
      const _fLoad = new THREE.TextureLoader();
      // r13: PER-FAMILY TILE CALIBRATION — one 12x8m tile for every photo
      // made wide-window facades read STRETCHED (a brick photo with 4 big
      // windows became 3m panes). Each family now tiles at the scale its
      // photo implies.
      const _fSize = {
        facade_glass: [12, 8], facade_glass2: [12, 8],
        facade_brick: [9, 6], facade_brick2: [7.5, 5],
        facade_stone: [10, 6.6], facade_concrete: [10, 6.6],
        facade_limestone: [9, 6],
      };
      const _fTex = (n, suffix) => {
        const t = _fLoad.load('textures/' + n + (suffix || '') + '.jpg');
        const [tw, th] = _fSize[n] || [12, 8];
        t.wrapS = t.wrapT = THREE.RepeatWrapping;
        t.repeat.set(1 / tw, 1 / th);
        if (!suffix) t.colorSpace = THREE.SRGBColorSpace;
        t.anisotropy = renderer.capabilities.getMaxAnisotropy();
        return t;
      };
      const _fPair = (n) => ({ map: _fTex(n), normalMap: _fTex(n, '_n'),
        normalScale: new THREE.Vector2(0.6, 0.6) });
      const _wallMats = [
        new THREE.MeshStandardMaterial({ vertexColors: true, map: facadeTex,
          emissive: 0xffc873, emissiveMap: litTex, emissiveIntensity: 0.4,
          roughness: 0.85, metalness: 0.08 }),
        new THREE.MeshStandardMaterial({ ..._fPair('facade_glass'),
          vertexColors: true, roughness: 0.35, metalness: 0.55 }),
        new THREE.MeshStandardMaterial({ ..._fPair('facade_brick'),
          vertexColors: true, roughness: 0.9, metalness: 0.03 }),
        new THREE.MeshStandardMaterial({ ..._fPair('facade_stone'),
          vertexColors: true, roughness: 0.85, metalness: 0.04 }),
        new THREE.MeshStandardMaterial({ ..._fPair('facade_glass2'),
          vertexColors: true, roughness: 0.3, metalness: 0.6 }),
        new THREE.MeshStandardMaterial({ ..._fPair('facade_brick2'),
          vertexColors: true, roughness: 0.92, metalness: 0.02 }),
        new THREE.MeshStandardMaterial({ ..._fPair('facade_concrete'),
          vertexColors: true, roughness: 0.88, metalness: 0.03 }),
        new THREE.MeshStandardMaterial({ ..._fPair('facade_limestone'),
          vertexColors: true, roughness: 0.8, metalness: 0.04 }),
      ];
      // r13 ALIGNED NIGHT WINDOWS: the old shared glow mask floated
      // misaligned over each photo's own printed windows ('blotchy orange
      // smears'). The mask is now DERIVED from the facade itself — detect
      // dark cells (glass) in the loaded photo, light a random ~third of
      // exactly those cells. Glow lands where the windows actually are.
      if (SPEC.world.sky === 'night' || SPEC.world.sky === 'dusk') {
        const FAMS = [[1, 'facade_glass'], [2, 'facade_brick'],
          [3, 'facade_stone'], [4, 'facade_glass2'], [5, 'facade_brick2'],
          [6, 'facade_concrete'], [7, 'facade_limestone']];
        for (const [mi, fn] of FAMS) {
          _fLoad.load('textures/' + fn + '.jpg', (t2) => {
            try {
              const img = t2.image;
              const c = document.createElement('canvas');
              c.width = c.height = 256;
              const g = c.getContext('2d');
              g.drawImage(img, 0, 0, 256, 256);
              const d = g.getImageData(0, 0, 256, 256).data;
              const CELL = 16, N = 256 / CELL;
              const cell = new Float32Array(N * N);
              let avg = 0;
              for (let cy = 0; cy < N; cy++) for (let cx = 0; cx < N; cx++) {
                let s2 = 0;
                for (let y = 0; y < CELL; y += 2) for (let x = 0; x < CELL; x += 2) {
                  const o = (((cy * CELL + y) * 256) + cx * CELL + x) * 4;
                  s2 += 0.299 * d[o] + 0.587 * d[o + 1] + 0.114 * d[o + 2];
                }
                cell[cy * N + cx] = s2 / 64;
                avg += s2 / 64;
              }
              avg /= N * N;
              const rngW2 = mulberry32(SPEC.seed + 404 + mi);
              g.clearRect(0, 0, 256, 256);
              g.fillStyle = '#000000'; g.fillRect(0, 0, 256, 256);
              for (let cy = 0; cy < N; cy++) for (let cx = 0; cx < N; cx++) {
                if (cell[cy * N + cx] < avg * 0.78 && rngW2() < 0.34) {
                  g.fillStyle = rngW2() < 0.75 ? '#e8b268' : '#b8cfe0';
                  g.fillRect(cx * CELL + 2, cy * CELL + 2, CELL - 4, CELL - 4);
                }
              }
              const gt = new THREE.CanvasTexture(c);
              gt.wrapS = gt.wrapT = THREE.RepeatWrapping;
              gt.repeat.copy(_wallMats[mi].map.repeat);
              gt.colorSpace = THREE.SRGBColorSpace;
              const m = _wallMats[mi];
              m.emissive = new THREE.Color(0xffffff);
              m.emissiveMap = gt;
              m.emissiveIntensity = 0.7;
              m.needsUpdate = true;
            } catch (e) { /* glow is best-effort */ }
          });
        }
      }
      for (let bi = 0; bi < 8; bi++) {
        if (!wallBuckets[bi].length) continue;
        const wm = new THREE.Mesh(mergeGeometries(wallBuckets[bi], false), _wallMats[bi]);
        wm.castShadow = true; wm.receiveShadow = true;
        scene.add(wm);
      }
      const roofs = new THREE.Mesh(mergeGeometries(capGeos, false),
        new THREE.MeshStandardMaterial({ vertexColors: true, color: 0x77746e,
          roughness: 0.96, metalness: 0.02 }));
      roofs.castShadow = true; roofs.receiveShadow = true;
      scene.add(roofs);
      // r11 CORNICES: clone every roof cap, scale 5% wider about its own
      // center and drop it 0.45m — a projecting ledge under every roofline.
      // Breaks the extruded-box silhouette (the AC/GTA depth cue) for the
      // whole city in ONE merged mesh; below-ground underside clones bury
      // themselves harmlessly.
      {
        const cornices = [];
        for (const cg of capGeos) {
          const cc = cg.clone();
          cc.computeBoundingBox();
          const cb = cc.boundingBox;
          if ((cb.max.y + cb.min.y) / 2 < 3) continue;   // skip undersides
          const ccx = (cb.min.x + cb.max.x) / 2, ccz = (cb.min.z + cb.max.z) / 2;
          cc.translate(-ccx, 0, -ccz);
          cc.scale(1.05, 1, 1.05);
          cc.translate(ccx, -0.45, ccz);
          cornices.push(cc);
        }
        if (cornices.length) {
          const cor = new THREE.Mesh(mergeGeometries(cornices, false),
            new THREE.MeshStandardMaterial({ color: 0x5e5b55,
              roughness: 0.92, metalness: 0.02, side: THREE.DoubleSide }));
          cor.castShadow = true;
          scene.add(cor);
        }
      }
      // ROOFTOP CLUTTER (Phase 118): water towers + AC units — the skyline
      // detail that says 'real city'. Instanced; capped for perf.
      if (roofSpots.length) {
        const rngR = mulberry32(SPEC.seed + 909);
        const spots = roofSpots.slice(0, 120);
        const drum = new THREE.InstancedMesh(
          new THREE.CylinderGeometry(1.3, 1.3, 2.4, 10),
          new THREE.MeshStandardMaterial({ color: 0x6e5744, roughness: 0.9 }), spots.length);
        const cone = new THREE.InstancedMesh(
          new THREE.ConeGeometry(1.5, 1.1, 10),
          new THREE.MeshStandardMaterial({ color: 0x5c4938, roughness: 0.9 }), spots.length);
        const acs = new THREE.InstancedMesh(
          new THREE.BoxGeometry(1.3, 0.8, 1.3),
          new THREE.MeshStandardMaterial({ color: 0x9aa0a6, roughness: 0.6, metalness: 0.4 }),
          spots.length * 2);
        const M4 = new THREE.Matrix4();
        let di = 0, ai = 0;
        for (const [rcx, rcz, rtop, rw, rd] of spots) {
          const tx = rcx + (rngR() - 0.5) * (rw - 5);
          const tz = rcz + (rngR() - 0.5) * (rd - 5);
          if (rngR() < 0.6) {
            M4.makeTranslation(tx, rtop + 1.2, tz); drum.setMatrixAt(di, M4);
            M4.makeTranslation(tx, rtop + 2.95, tz); cone.setMatrixAt(di, M4);
            di++;
          }
          for (let a = 0; a < 2; a++) {
            if (rngR() < 0.75) {
              M4.makeTranslation(rcx + (rngR() - 0.5) * (rw - 4), rtop + 0.4,
                                 rcz + (rngR() - 0.5) * (rd - 4));
              acs.setMatrixAt(ai++, M4);
            }
          }
        }
        drum.count = di; cone.count = di; acs.count = ai;
        for (const im of [drum, cone, acs]) {
          im.instanceMatrix.needsUpdate = true;
          im.castShadow = true;
          scene.add(im);
        }
      }
      // STREET FURNITURE (Phase 120): traffic lights at intersections +
      // hydrants mid-block — instanced, capped, collider-free (thin poles).
      const _jx = (window.__junctions || []).slice(0, 40);
      if (_jx.length) {
        const poleG = new THREE.CylinderGeometry(0.09, 0.11, 5.2, 6);
        const headG = new THREE.BoxGeometry(0.42, 1.1, 0.34);
        const poleM = new THREE.MeshStandardMaterial({ color: 0x2c2f33, roughness: 0.7, metalness: 0.5 });
        const headM = new THREE.MeshStandardMaterial({ color: 0x1e2124, roughness: 0.55,
          emissive: 0x30ff66, emissiveIntensity: 0.9 });
        const poles = new THREE.InstancedMesh(poleG, poleM, _jx.length);
        const heads = new THREE.InstancedMesh(headG, headM, _jx.length);
        const MM = new THREE.Matrix4();
        const rngS = mulberry32(SPEC.seed + 515);
        _jx.forEach(([jx2, jz2], ji) => {
          const ox = jx2 + 4.5 * Math.sign(rngS() - 0.5 || 1), oz = jz2 + 4.5 * Math.sign(rngS() - 0.5 || 1);
          const gy2 = hAt(ox, oz);
          MM.makeTranslation(ox, gy2 + 2.6, oz); poles.setMatrixAt(ji, MM);
          MM.makeTranslation(ox, gy2 + 5.0, oz); heads.setMatrixAt(ji, MM);
        });
        for (const im of [poles, heads]) { im.instanceMatrix.needsUpdate = true; im.castShadow = true; scene.add(im); }
        // r6 LIGHT POOLS: at night every lamp casts a warm additive pool on
        // the pavement — the missing streetlight glow that makes night
        // streets read as LIT instead of ambient-flat. Zero real lights:
        // radial-gradient decals, one instanced mesh.
        if (SPEC.world.sky === 'night' || SPEC.world.sky === 'dusk') {
          const pc = document.createElement('canvas'); pc.width = pc.height = 128;
          const px2 = pc.getContext('2d');
          const pg = px2.createRadialGradient(64, 64, 4, 64, 64, 62);
          pg.addColorStop(0, 'rgba(255,206,130,0.55)');
          pg.addColorStop(0.5, 'rgba(255,190,110,0.22)');
          pg.addColorStop(1, 'rgba(255,180,100,0)');
          px2.fillStyle = pg; px2.fillRect(0, 0, 128, 128);
          const pt = new THREE.CanvasTexture(pc);
          const poolG = new THREE.CircleGeometry(4.4, 20).rotateX(-Math.PI / 2);
          const poolM = new THREE.MeshBasicMaterial({ map: pt, transparent: true,
            blending: THREE.AdditiveBlending, depthWrite: false });
          const pools = new THREE.InstancedMesh(poolG, poolM, _jx.length);
          const rngS2 = mulberry32(SPEC.seed + 515);   // SAME seed = same offsets
          _jx.forEach(([jx2, jz2], ji) => {
            const ox = jx2 + 4.5 * Math.sign(rngS2() - 0.5 || 1);
            const oz = jz2 + 4.5 * Math.sign(rngS2() - 0.5 || 1);
            MM.makeTranslation(ox, hAt(ox, oz) + 0.07, oz);
            pools.setMatrixAt(ji, MM);
          });
          pools.instanceMatrix.needsUpdate = true;
          pools.renderOrder = 4;
          scene.add(pools);
          // lamp heads glow warm at night instead of reading as gray blobs
          headM.emissive = new THREE.Color(0xffc880);
          headM.emissiveIntensity = 1.6;
        }
        const hydG = new THREE.CylinderGeometry(0.16, 0.2, 0.8, 8);
        const hydM = new THREE.MeshStandardMaterial({ color: 0xb03028, roughness: 0.6 });
        const nHyd = Math.min((OSM.roads || []).length, 40);
        const hyds = new THREE.InstancedMesh(hydG, hydM, nHyd);
        let hc = 0;
        for (const r of (OSM.roads || []).slice(0, nHyd)) {
          const mid = r.pts[Math.floor(r.pts.length / 2)];
          const hd2 = Math.atan2(r.pts[r.pts.length - 1][0] - r.pts[0][0],
                                 r.pts[r.pts.length - 1][1] - r.pts[0][1]);
          const hx = mid[0] + Math.cos(hd2) * ((r.w || 7) / 2 + 1.6);
          const hz = mid[1] - Math.sin(hd2) * ((r.w || 7) / 2 + 1.6);
          if (inBldg(hx, hz, 0.4)) continue;
          MM.makeTranslation(hx, hAt(hx, hz) + 0.4, hz);
          hyds.setMatrixAt(hc++, MM);
        }
        hyds.count = hc; hyds.instanceMatrix.needsUpdate = true; hyds.castShadow = true;
        scene.add(hyds);
      }
      // STREET FURNITURE r3 (2026-07-30): dumpsters, trash cans, benches —
      // the sidewalk clutter that separates 'render' from 'street'. All
      // procedural + instanced on the sidewalk band, hydrant-style.
      {
        const rngF = mulberry32(SPEC.seed + 616);
        const MM2 = new THREE.Matrix4(), Q2 = new THREE.Quaternion();
        const S1 = new THREE.Vector3(1, 1, 1), E2 = new THREE.Euler(), PV = new THREE.Vector3();
        const mkIM = (geo, mat, n) => {
          const im = new THREE.InstancedMesh(geo, mat, n);
          im.castShadow = im.receiveShadow = true;
          return im;
        };
        const dump = mkIM(new THREE.BoxGeometry(1.9, 1.15, 1.05),
          new THREE.MeshStandardMaterial({ color: 0x2e4d33, roughness: 0.85, metalness: 0.35 }), 26);
        const lid = mkIM(new THREE.BoxGeometry(1.95, 0.1, 1.1),
          new THREE.MeshStandardMaterial({ color: 0x233728, roughness: 0.8, metalness: 0.4 }), 26);
        const can = mkIM(new THREE.CylinderGeometry(0.3, 0.26, 0.85, 10),
          new THREE.MeshStandardMaterial({ color: 0x3a3d42, roughness: 0.9, metalness: 0.55 }), 52);
        const woodM = new THREE.MeshStandardMaterial({ color: 0x6e4f30, roughness: 0.92 });
        const seat = mkIM(new THREE.BoxGeometry(1.7, 0.08, 0.5), woodM, 26);
        const back = mkIM(new THREE.BoxGeometry(1.7, 0.45, 0.07), woodM, 26);
        let nd = 0, ncn = 0, nb = 0;
        // r10 PLACEMENT FIX: furniture floating mid-sidewalk read as
        // MISPLACED (user callout). Real streets put benches/dumpsters/cans
        // AGAINST BUILDING WALLS — same nearest-road edge projection as the
        // awnings, then 0.9m out from the wall, back to the building.
        for (const b of (OSM.buildings || []).slice(0, 200)) {
          if (nd >= 26 && ncn >= 52 && nb >= 26) break;
          if (rngF() > 0.5) continue;
          let mnx = 1e9, mnz = 1e9, mxx = -1e9, mxz = -1e9;
          for (const p of b.pts) {
            mnx = Math.min(mnx, p[0]); mxx = Math.max(mxx, p[0]);
            mnz = Math.min(mnz, p[1]); mxz = Math.max(mxz, p[1]);
          }
          const cx4 = (mnx + mxx) / 2, cz4 = (mnz + mxz) / 2;
          const hx4 = (mxx - mnx) / 2, hz4 = (mxz - mnz) / 2;
          if (hx4 < 2 || hz4 < 2) continue;
          let bd2 = 1e9, bx2 = 0, bz2 = 0;
          for (const r of OSM.roads || []) for (const p of r.pts) {
            const d = (p[0] - cx4) ** 2 + (p[1] - cz4) ** 2;
            if (d < bd2) { bd2 = d; bx2 = p[0]; bz2 = p[1]; }
          }
          if (bd2 > 42 * 42) continue;
          const dxx = bx2 - cx4, dzz = bz2 - cz4;
          const dll = Math.hypot(dxx, dzz) || 1;
          const nxx = dxx / dll, nzz = dzz / dll;
          const tt = Math.min(hx4 / Math.max(Math.abs(nxx), 1e-6),
                              hz4 / Math.max(Math.abs(nzz), 1e-6));
          // slide along the wall a little so items don't stack with awnings
          const sx4 = -nzz, sz4 = nxx;
          const slide = (rngF() - 0.5) * Math.min(hx4, hz4) * 1.2;
          const fx2 = cx4 + nxx * (tt + 0.9) + sx4 * slide;
          const fz2 = cz4 + nzz * (tt + 0.9) + sz4 * slide;
          {
            if (Math.hypot(fx2, fz2) < 12 || inBldg(fx2, fz2, 0.15)) continue;
            const gy3 = hAt(fx2, fz2);
            const yaw = Math.atan2(nxx, nzz);   // face the street, back to wall
            Q2.setFromEuler(E2.set(0, yaw, 0));
            const pick = rngF();
            if (pick < 0.3 && nd < 26) {
              MM2.compose(PV.set(fx2, gy3 + 0.58, fz2), Q2, S1); dump.setMatrixAt(nd, MM2);
              MM2.compose(PV.set(fx2, gy3 + 1.2, fz2), Q2, S1); lid.setMatrixAt(nd, MM2);
              nd++;
            } else if (pick < 0.62 && ncn < 52) {
              MM2.compose(PV.set(fx2, gy3 + 0.43, fz2), Q2, S1); can.setMatrixAt(ncn++, MM2);
            } else if (nb < 26) {
              MM2.compose(PV.set(fx2, gy3 + 0.45, fz2), Q2, S1); seat.setMatrixAt(nb, MM2);
              MM2.compose(PV.set(fx2 - Math.sin(yaw) * 0.24, gy3 + 0.72,
                                 fz2 - Math.cos(yaw) * 0.24), Q2, S1); back.setMatrixAt(nb, MM2);
              nb++;
            }
          }
        }
        dump.count = lid.count = nd; can.count = ncn; seat.count = back.count = nb;
        for (const im of [dump, lid, can, seat, back]) {
          im.instanceMatrix.needsUpdate = true; scene.add(im);
        }
      }
      // r13 PLACEMENT VALIDATORS: axis-aligned bbox edges lied for rotated
      // footprints (signs floating off corners) and per-road offsets landed
      // trees ON crossing roads. Real geometry tests, used by everything
      // placed from here on.
      const _segD = (px, pz, x1, z1, x2, z2) => {
        const dx = x2 - x1, dz = z2 - z1;
        const L2 = dx * dx + dz * dz;
        const t = L2 ? Math.max(0, Math.min(1, ((px - x1) * dx + (pz - z1) * dz) / L2)) : 0;
        return Math.hypot(px - (x1 + dx * t), pz - (z1 + dz * t));
      };
      const _roadSegs = [];
      for (const r of OSM.roads || []) {
        const hw = (r.w || 7) / 2;
        for (let i = 0; i < r.pts.length - 1; i++) {
          _roadSegs.push([r.pts[i][0], r.pts[i][1], r.pts[i + 1][0], r.pts[i + 1][1], hw]);
        }
      }
      const _onRoad = (px, pz, pad) => {
        for (const s of _roadSegs) {
          if (_segD(px, pz, s[0], s[1], s[2], s[3]) < s[4] + pad) return true;
        }
        return false;
      };
      const _polyEdgeD = (pts, px, pz) => {
        let m = 1e9;
        for (let i = 0; i < pts.length; i++) {
          const a = pts[i], b2 = pts[(i + 1) % pts.length];
          m = Math.min(m, _segD(px, pz, a[0], a[1], b2[0], b2[1]));
        }
        return m;
      };
      // r8 AWNINGS: tilted storefront canopies on road-facing building
      // bases — with plinths + these, ground floors read as SHOPS instead
      // of texture meeting pavement. Instanced, per-instance color.
      if (OSM.buildings && OSM.buildings.length && OSM.roads && OSM.roads.length) {
        const rngA = mulberry32(SPEC.seed + 606);
        const awnG = new THREE.BoxGeometry(3.4, 0.16, 1.2);
        awnG.translate(0, 0, 0.6);
        const awnM = new THREE.MeshStandardMaterial({ roughness: 0.85 });
        const maxA = Math.min(OSM.buildings.length, 70);
        const awn = new THREE.InstancedMesh(awnG, awnM, maxA);
        const AC = [new THREE.Color(0x7a2e2e), new THREE.Color(0x2e5a3a),
                    new THREE.Color(0x2e3a5e), new THREE.Color(0x4a4a4a),
                    new THREE.Color(0x7a5a2e)];
        const M4 = new THREE.Matrix4(), Q4 = new THREE.Quaternion();
        const E4 = new THREE.Euler(), S4 = new THREE.Vector3(1, 1, 1);
        let na = 0;
        for (const b of OSM.buildings.slice(0, 140)) {
          if (na >= maxA) break;
          if (rngA() > 0.55) continue;
          let mnx = 1e9, mnz = 1e9, mxx = -1e9, mxz = -1e9;
          for (const p of b.pts) {
            mnx = Math.min(mnx, p[0]); mxx = Math.max(mxx, p[0]);
            mnz = Math.min(mnz, p[1]); mxz = Math.max(mxz, p[1]);
          }
          const cx2 = (mnx + mxx) / 2, cz2 = (mnz + mxz) / 2;
          const hx2 = (mxx - mnx) / 2, hz2 = (mxz - mnz) / 2;
          if (hx2 < 2.2 || hz2 < 2.2) continue;
          // nearest road point -> awning faces the street
          let bd = 1e9, bx = 0, bz = 0;
          for (const r of OSM.roads) for (const p of r.pts) {
            const d = (p[0] - cx2) ** 2 + (p[1] - cz2) ** 2;
            if (d < bd) { bd = d; bx = p[0]; bz = p[1]; }
          }
          if (bd > 45 * 45) continue;
          const dx2 = bx - cx2, dz2 = bz - cz2;
          const dl = Math.hypot(dx2, dz2) || 1;
          const nx2 = dx2 / dl, nz2 = dz2 / dl;
          const t = Math.min(hx2 / Math.max(Math.abs(nx2), 1e-6),
                             hz2 / Math.max(Math.abs(nz2), 1e-6));
          const ex = cx2 + nx2 * t, ez = cz2 + nz2 * t;
          E4.set(-0.22, Math.atan2(nx2, nz2), 0);
          Q4.setFromEuler(E4);
          if (_polyEdgeD(b.pts, ex, ez) > 1.4) continue;   // r13: real wall only
          M4.compose(new THREE.Vector3(ex, hAt(ex, ez) + 3.0, ez), Q4, S4);
          awn.setMatrixAt(na, M4);
          awn.setColorAt(na, AC[Math.floor(rngA() * AC.length)]);
          na++;
        }
        awn.count = na;
        awn.instanceMatrix.needsUpdate = true;
        if (awn.instanceColor) awn.instanceColor.needsUpdate = true;
        awn.castShadow = true;
        scene.add(awn);
      }
      // r9 STREET TREES: rows of canopies lining every road — the #1
      // enclosure cue in the GTA-loop reference frame. Two instanced
      // meshes (trunks + canopies), ~13m spacing, both sidewalk sides.
      if (OSM.roads && OSM.roads.length) {
        const rngT2 = mulberry32(SPEC.seed + 707);
        const spots = [];
        for (const r of OSM.roads) {
          const off = (r.w || 7) / 2 + 2.1;
          for (let i = 0; i < r.pts.length - 1 && spots.length < 240; i++) {
            const [x1, z1] = r.pts[i], [x2, z2] = r.pts[i + 1];
            const L = Math.hypot(x2 - x1, z2 - z1);
            for (let d = 6; d < L; d += 13) {
              const t = d / L;
              const px3 = x1 + (x2 - x1) * t, pz3 = z1 + (z2 - z1) * t;
              const nx3 = -(z2 - z1) / L * off, nz3 = (x2 - x1) / L * off;
              for (const s of [1, -1]) {
                if (rngT2() > 0.62) continue;
                const tx3 = px3 + nx3 * s, tz3 = pz3 + nz3 * s;
                // r13: also reject spots on ANY road (cross streets used to
                // catch trees mid-asphalt)
                if (!inBldg(tx3, tz3, 1.2) && !_onRoad(tx3, tz3, 1.0)) {
                  spots.push([tx3, tz3, 0.85 + rngT2() * 0.5]);
                }
              }
            }
          }
        }
        if (spots.length) {
          const trkG = new THREE.CylinderGeometry(0.14, 0.22, 3.4, 7);
          trkG.translate(0, 1.7, 0);
          const trk = new THREE.InstancedMesh(trkG,
            new THREE.MeshStandardMaterial({ color: 0x5a4632, roughness: 0.95 }),
            spots.length);
          // r10: multi-lobe ORGANIC canopy — a single squashed icosahedron
          // read as a lollipop ('very geometric'). Four overlapping jittered
          // lobes at detail 2 with smooth normals silhouette like foliage.
          const lobes = [];
          const lobeDefs = [[0, 4.15, 0, 1.5], [0.85, 3.75, 0.4, 0.95],
                            [-0.75, 3.9, -0.5, 1.0], [0.15, 4.9, -0.35, 0.85],
                            [-0.3, 3.5, 0.7, 0.8]];
          const rngLb = mulberry32(SPEC.seed + 313);
          for (const [lx2, ly2, lz2, lr] of lobeDefs) {
            const lg = new THREE.IcosahedronGeometry(lr, 2);
            const pa2 = lg.attributes.position;
            for (let vi = 0; vi < pa2.count; vi++) {
              const j = 0.88 + rngLb() * 0.24;   // organic silhouette jitter
              pa2.setXYZ(vi, pa2.getX(vi) * j, pa2.getY(vi) * (0.82 + rngLb() * 0.2),
                         pa2.getZ(vi) * j);
            }
            lg.translate(lx2, ly2, lz2);
            lobes.push(lg);
          }
          const canG = mergeGeometries(lobes, false);
          canG.computeVertexNormals();
          // r11: LEAF TEXTURE on the lobes — the SDXL leaves PBR set breaks
          // up the solid-color surface into visible foliage detail
          const leafT = new THREE.TextureLoader().load('textures/leaves.jpg');
          leafT.wrapS = leafT.wrapT = THREE.RepeatWrapping;
          leafT.repeat.set(2.5, 2.5);
          leafT.colorSpace = THREE.SRGBColorSpace;
          const leafN = new THREE.TextureLoader().load('textures/leaves_n.jpg');
          leafN.wrapS = leafN.wrapT = THREE.RepeatWrapping;
          leafN.repeat.set(2.5, 2.5);
          const can = new THREE.InstancedMesh(canG,
            new THREE.MeshStandardMaterial({ map: leafT, normalMap: leafN,
              normalScale: new THREE.Vector2(0.7, 0.7), roughness: 0.95 }),
            spots.length);
          const M5 = new THREE.Matrix4();
          const CG = [new THREE.Color(0x5a8a42), new THREE.Color(0x6a9a4c),
                      new THREE.Color(0x7aa856), new THREE.Color(0x4f7c3c)];
          spots.forEach(([tx3, tz3, sc], i) => {
            const gy3 = hAt(tx3, tz3);
            M5.makeScale(sc, sc, sc).setPosition(tx3, gy3, tz3);
            trk.setMatrixAt(i, M5); can.setMatrixAt(i, M5);
            can.setColorAt(i, CG[Math.floor(rngT2() * CG.length)]);
          });
          for (const im of [trk, can]) {
            im.instanceMatrix.needsUpdate = true;
            im.castShadow = true; scene.add(im);
          }
          if (can.instanceColor) can.instanceColor.needsUpdate = true;
        }
      }
      // r9 SHOP SIGNS: real TEXT above storefronts — signage density is
      // what makes a street read as a PLACE (the reference frame is full
      // of it). ~14 canvas-text signs on road-facing edges, emissive at
      // night. Individual meshes (14 draw calls, trivial).
      if (OSM.buildings && OSM.buildings.length && OSM.roads && OSM.roads.length) {
        const rngG2 = mulberry32(SPEC.seed + 909);
        const NAMES = ["MARIO'S PIZZA", 'GOLDEN DRAGON', 'CITY DELI',
          "LUCKY'S BAR", 'STAR CAFE', 'BODEGA 24', 'GREEN MARKET',
          'THE ROXY', "JOE'S DINER", 'HOTEL RIALTO', 'CINEMA', 'RECORDS',
          'FLOWERS', 'HARDWARE'];
        const SBG = ['#8a1f1f', '#1f4d8a', '#1f6b3a', '#6b3a8a', '#8a5a1f', '#222222'];
        const _nightS = SPEC.world.sky === 'night' || SPEC.world.sky === 'dusk';
        let ns = 0;
        for (const b of OSM.buildings.slice(0, 300)) {
          if (ns >= 40) break;             // r10: 14 signs vanished in a city
          if (rngG2() > 0.45) continue;
          let mnx = 1e9, mnz = 1e9, mxx = -1e9, mxz = -1e9;
          for (const p of b.pts) {
            mnx = Math.min(mnx, p[0]); mxx = Math.max(mxx, p[0]);
            mnz = Math.min(mnz, p[1]); mxz = Math.max(mxz, p[1]);
          }
          const cx3 = (mnx + mxx) / 2, cz3 = (mnz + mxz) / 2;
          const hx3 = (mxx - mnx) / 2, hz3 = (mxz - mnz) / 2;
          if (hx3 < 3 || hz3 < 3) continue;
          let bd = 1e9, bx = 0, bz = 0;
          for (const r of OSM.roads) for (const p of r.pts) {
            const d = (p[0] - cx3) ** 2 + (p[1] - cz3) ** 2;
            if (d < bd) { bd = d; bx = p[0]; bz = p[1]; }
          }
          if (bd > 40 * 40) continue;
          const dx3 = bx - cx3, dz3 = bz - cz3;
          const dl3 = Math.hypot(dx3, dz3) || 1;
          const nx4 = dx3 / dl3, nz4 = dz3 / dl3;
          const t2 = Math.min(hx3 / Math.max(Math.abs(nx4), 1e-6),
                              hz3 / Math.max(Math.abs(nz4), 1e-6));
          const ex2 = cx3 + nx4 * t2 * 1.01, ez2 = cz3 + nz4 * t2 * 1.01;
          if (_polyEdgeD(b.pts, ex2, ez2) > 1.4) continue;   // r13: real wall only
          if ((b.h || 9) < 5.5) continue;   // r14: no signs above short roofs
          const name = NAMES[ns % NAMES.length];
          const sc2 = document.createElement('canvas');
          sc2.width = 512; sc2.height = 128;
          const sx = sc2.getContext('2d');
          sx.fillStyle = SBG[Math.floor(rngG2() * SBG.length)];
          sx.fillRect(0, 0, 512, 128);
          sx.strokeStyle = 'rgba(255,255,255,0.85)'; sx.lineWidth = 6;
          sx.strokeRect(8, 8, 496, 112);
          sx.fillStyle = _nightS ? '#ffe9b0' : '#f2ede2';
          sx.font = 'bold 58px Arial';
          sx.textAlign = 'center'; sx.textBaseline = 'middle';
          sx.fillText(name, 256, 68);
          const st2 = new THREE.CanvasTexture(sc2);
          st2.colorSpace = THREE.SRGBColorSpace;
          st2.anisotropy = renderer.capabilities.getMaxAnisotropy();
          const sm2 = new THREE.MeshStandardMaterial({ map: st2,
            roughness: 0.6,
            ...(_nightS ? { emissive: new THREE.Color(0xffffff),
                            emissiveMap: st2, emissiveIntensity: 0.75 } : {}) });
          const sign = new THREE.Mesh(new THREE.BoxGeometry(3.4, 0.85, 0.14), sm2);
          sign.position.set(ex2, hAt(ex2, ez2) + 4.55, ez2);
          sign.rotation.y = Math.atan2(nx4, nz4);
          sign.castShadow = true;
          scene.add(sign);
          ns++;
        }
      }
      // REAL ASPHALT STREETS r3 (2026-07-30): the 'Google Maps' unlock.
      // Roads were only a tint painted into the ground canvas — the city
      // read as one endless pale plaza and everything on it looked
      // misplaced. Streets are now REAL geometry: dark PBR asphalt ribbons
      // extruded along every OSM road (one merged mesh) + white center
      // dashes — dark streets vs light sidewalk blocks is what makes a
      // city read as a MAP.
      {
        const roadGeos = [], dashGeos = [], curbGeos = [];
        const strip = (x1, z1, x2, z2, w, y1, y2, vmax) => {
          const dx = x2 - x1, dz = z2 - z1;
          const len = Math.hypot(dx, dz);
          if (len < 0.4) return null;
          const nx = -dz / len * w, nz = dx / len * w;
          const g = new THREE.BufferGeometry();
          g.setAttribute('position', new THREE.BufferAttribute(new Float32Array([
            x1 + nx, y1, z1 + nz, x1 - nx, y1, z1 - nz, x2 + nx, y2, z2 + nz,
            x1 - nx, y1, z1 - nz, x2 - nx, y2, z2 - nz, x2 + nx, y2, z2 + nz]), 3));
          // r8: metric UVs — the texture tiled ONCE across the full road
          // width (14m of asphalt from one 1K image = mushy oversized
          // cracks). Now one repeat per ~5m in both axes.
          const v = vmax || len / 5;
          const u = vmax ? 1 : (w * 2) / 5;
          g.setAttribute('uv', new THREE.BufferAttribute(new Float32Array([
            0, 0, u, 0, 0, v, u, 0, u, v, 0, v]), 2));
          g.computeVertexNormals();
          return g;
        };
        for (const r of OSM.roads || []) {
          const w = (r.w || 7) / 2 + 0.25;
          for (let i = 0; i < r.pts.length - 1; i++) {
            const [x1, z1] = r.pts[i], [x2, z2] = r.pts[i + 1];
            const y1 = hAt(x1, z1) + 0.05, y2 = hAt(x2, z2) + 0.05;
            const g = strip(x1, z1, x2, z2, w, y1, y2);
            if (g) roadGeos.push(g);
            // r14: flat curb strips REMOVED — they z-fought and showed their
            // floating gap as streaky bands at grazing angles (playtest
            // screenshots). Real instanced curb boxes are built below.
            // center dashes: 1.8m on / 4m off along the segment
            const segL = Math.hypot(x2 - x1, z2 - z1);
            for (let d = 1; d + 1.8 < segL; d += 5.8) {
              const t0 = d / segL, t1 = (d + 1.8) / segL;
              const dg = strip(
                x1 + (x2 - x1) * t0, z1 + (z2 - z1) * t0,
                x1 + (x2 - x1) * t1, z1 + (z2 - z1) * t1,
                0.09, y1 + 0.03, y2 + 0.03, 1);
              if (dg) dashGeos.push(dg);
            }
          }
        }
        if (roadGeos.length) {
          const at = new THREE.TextureLoader().load('textures/asphalt.jpg');
          at.wrapS = at.wrapT = THREE.RepeatWrapping;
          at.colorSpace = THREE.SRGBColorSpace;
          at.anisotropy = renderer.capabilities.getMaxAnisotropy();
          // charcoal multiplier: the SDXL asphalt photo is LIGHT gray — at
          // 0x8f9096 the streets read identical to the concrete sidewalks
          // (proved by a road running straight through spawn, invisible)
          // r15 WET NIGHT ASPHALT: at night the road turns glossy and picks
          // up the HDRI/neon environment — the SSR wet-street look without
          // SSR. Day stays matte.
          const _wetN = SPEC.world.sky === 'night' || SPEC.world.sky === 'dusk';
          const road = new THREE.Mesh(mergeGeometries(roadGeos, false),
            new THREE.MeshStandardMaterial({ map: at, color: 0x686b73,
              roughness: _wetN ? 0.42 : 0.96, metalness: _wetN ? 0.12 : 0.0,
              envMapIntensity: _wetN ? 1.5 : 1.0, side: THREE.DoubleSide }));
          road.receiveShadow = true;
          scene.add(road);
          const dash = new THREE.Mesh(mergeGeometries(dashGeos, false),
            new THREE.MeshBasicMaterial({ color: 0xd8d8d2, side: THREE.DoubleSide }));
          scene.add(dash);
          // r14 REAL CURBS: solid instanced boxes (top + side faces) per
          // road-segment side — an actual 6-inch step, nothing to z-fight
          {
            const cg2 = new THREE.BoxGeometry(1, 0.15, 0.3);
            cg2.translate(0, 0.075, 0);
            // pieces of ~6m, each midpoint-tested against ALL roads so curbs
            // never run across an intersection
            let cap2 = 0;
            for (const s of _roadSegs) cap2 += (Math.ceil(Math.hypot(s[2] - s[0], s[3] - s[1]) / 6) + 1) * 2;
            const curb = new THREE.InstancedMesh(cg2,
              new THREE.MeshStandardMaterial({ color: 0xaaa8a0, roughness: 0.9 }),
              Math.min(cap2, 6000));
            const CM = new THREE.Matrix4(), CQ = new THREE.Quaternion();
            const CE = new THREE.Euler(), CS = new THREE.Vector3();
            let nc2 = 0;
            for (const s of _roadSegs) {
              const len = Math.hypot(s[2] - s[0], s[3] - s[1]);
              if (len < 1) continue;
              const yawC = Math.atan2(s[2] - s[0], s[3] - s[1]);
              const ux = (s[2] - s[0]) / len, uz = (s[3] - s[1]) / len;
              const oxc = -uz * (s[4] + 0.42), ozc = ux * (s[4] + 0.42);
              for (let d0 = 0; d0 < len; d0 += 6) {
                const pl = Math.min(6, len - d0);
                if (pl < 0.8) continue;
                const midd = d0 + pl / 2;
                for (const sd of [1, -1]) {
                  if (nc2 >= 6000) break;
                  const mxc = s[0] + ux * midd + oxc * sd;
                  const mzc = s[1] + uz * midd + ozc * sd;
                  if (_onRoad(mxc, mzc, 0.22)) continue;   // crossing street
                  CE.set(0, yawC, 0); CQ.setFromEuler(CE);
                  CS.set(0.3, 1, pl);
                  CM.compose(new THREE.Vector3(mxc, hAt(mxc, mzc), mzc), CQ, CS);
                  curb.setMatrixAt(nc2++, CM);
                }
              }
            }
            curb.count = nc2;
            curb.instanceMatrix.needsUpdate = true;
            curb.receiveShadow = true; curb.castShadow = true;
            scene.add(curb);
          }
        }
      }
      // NEON SIGNS (Phase 120, night streets): emissive storefront strips on
      // building faces near roads — the bloom layer that sells 'city at night'
      if (['night', 'dusk', 'sunset'].includes(SPEC.world.sky)) {
        const rngNe = mulberry32(SPEC.seed + 606);
        const neonCols = [0xff3d7a, 0x35d0ff, 0xffd23d, 0x7cff4a, 0xc86bff];
        let placedN = 0;
        for (const bb2 of bldBoxes) {
          if (placedN >= 36 || rngNe() < 0.45) continue;
          const faces = [
            [(bb2[0] + bb2[2]) / 2, bb2[1] - 0.15, 0],
            [(bb2[0] + bb2[2]) / 2, bb2[3] + 0.15, 0],
            [bb2[0] - 0.15, (bb2[1] + bb2[3]) / 2, Math.PI / 2],
            [bb2[2] + 0.15, (bb2[1] + bb2[3]) / 2, Math.PI / 2]];
          const f = faces[Math.floor(rngNe() * 4)];
          const nw = 2.2 + rngNe() * 2.4;
          const sgn = new THREE.Mesh(new THREE.PlaneGeometry(nw, 0.7),
            new THREE.MeshStandardMaterial({ color: 0x101014, side: THREE.DoubleSide,
              emissive: neonCols[Math.floor(rngNe() * neonCols.length)],
              emissiveIntensity: 2.4 }));
          sgn.position.set(f[0], hAt(f[0], f[1]) + 3.1, f[1]);
          sgn.rotation.y = f[2];
          scene.add(sgn);
          placedN++;
        }
      }
      // DISTANT SKYLINE (Phase 122): silhouette towers past the map edge —
      // a city that visibly CONTINUES instead of stopping at the last block
      {
        const rngSk = mulberry32(SPEC.seed + 1213);
        const nSk = 60;
        const skGeo = new THREE.BoxGeometry(1, 1, 1);
        const skMat = new THREE.MeshStandardMaterial({
          map: _fTex('facade_glass'),
          color: new THREE.Color(pal.sky).lerp(new THREE.Color(0x555b66), 0.5),
          roughness: 0.7, fog: true });
        skMat.map = skMat.map.clone();
        skMat.map.repeat.set(0.4, 0.25);             // whole-face panels at distance
        skMat.map.needsUpdate = true;
        const skyline = new THREE.InstancedMesh(skGeo, skMat, nSk);
        const MS = new THREE.Matrix4(), QS = new THREE.Quaternion(), VS = new THREE.Vector3();
        for (let si = 0; si < nSk; si++) {
          const a3 = (si / nSk) * Math.PI * 2 + rngSk() * 0.09;
          const d3 = gsize * (0.85 + rngSk() * 0.45);   // beyond fog near — always hazed
          const w3 = 12 + rngSk() * 18, h3 = 14 + rngSk() * 34;
          MS.compose(VS.set(Math.cos(a3) * d3, h3 / 2 - 1, Math.sin(a3) * d3),
                     QS.setFromAxisAngle(new THREE.Vector3(0, 1, 0), rngSk() * Math.PI),
                     new THREE.Vector3(w3, h3, w3 * (0.7 + rngSk() * 0.6)));
          skyline.setMatrixAt(si, MS);
        }
        skyline.instanceMatrix.needsUpdate = true;
        scene.add(skyline);
      }
      console.log('[game] OSM city "' + (OSM.place || '?') + '": ' + bldBoxes.length +
                  ' buildings (textured facades), ' + (OSM.roads || []).length + ' roads');
    }
  }
  // ── GAUSSIAN-SPLAT WORLD (Phase 136, Tier 1): a captured/downloaded
  // .ply/.splat becomes the visual world — physics, quests and the cine
  // camera live inside it. The 617KB renderer loads ONLY when used.
  if (SPEC.world.splat) {
    try {
      const GS = await import('./vendor/gaussian-splats-3d.module.js');
      const sv = new GS.DropInViewer({ gpuAcceleratedSort: false,
                                       sharedMemoryForWorkers: false });
      // 137.2 auto-fit: export computed rotation/scale/lift from the splat's
      // real bounds — object-scale splats become a ~40m walkable diorama
      const sf = SPEC.world.splat_fit || null;
      await sv.addSplatScene(SPEC.world.splat, {
        showLoadingUI: false, progressiveLoad: true,
        ...(sf ? { rotation: sf.rotation, position: sf.position,
                   scale: [sf.scale, sf.scale, sf.scale] } : {}) });
      scene.add(sv);
      console.log('[game] splat world loaded: ' + SPEC.world.splat);
    } catch (e) {
      console.warn('[game] splat world failed (' + e.message + ') — mesh world stays');
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
  // PURE SCENE WORLD (2026-08-04, user callout 'separate it from our other
  // scene'): when a scene-image world is attached, the IMAGE is the scenery
  // — procedural scatter (trees/rocks/bushes), grass and landmark giants
  // stand down so they stop burying the panorama + lifted splats. Terrain,
  // objectives, NPCs and placed items stay.
  const PURE_SCENE = !!SPEC.world.pano;
  for (const sct of PURE_SCENE ? [] : (SPEC.world.scatter || [])) {
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
                  || roadDist(x, z) < 7.5
                  || (clusterN(x, z) < 0.45 && tries < 22)) && tries < 30);
        places.push({ x, z, s: 1 + (rng() - 0.5) * 2 * sct.scale_jitter, rot: rng() * Math.PI * 2,
                      // DENSITY ARC r2: real trees LEAN a few degrees — a
                      // perfectly plumb forest is the #1 'toy world' tell
                      lx: (rng() - 0.5) * 0.10, lz: (rng() - 0.5) * 0.10 });
      }
      const M = new THREE.Matrix4(), T = new THREE.Matrix4(), SV = new THREE.Vector3();
      const LR = new THREE.Matrix4(), _eul = new THREE.Euler();
      const jitC = new THREE.Color();
      for (const p of parts) {
        const im = new THREE.InstancedMesh(p.geo, p.mat, N);
        im.castShadow = true;
        im.frustumCulled = false;
        for (let i = 0; i < N; i++) {
          const pl = places[i];
          T.makeRotationY(pl.rot).scale(SV.set(pl.s, pl.s, pl.s));
          LR.makeRotationFromEuler(_eul.set(pl.lx || 0, 0, pl.lz || 0));
          T.premultiply(LR);
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

  // ── ROOM BUILDER (Phase 95/99): builds a room-plan at any x-offset —
  // used by full INTERIOR levels (offset 0) and by ENTERABLE buildings in
  // exterior worlds (offset far past the map edge; a door teleports you in).
  function buildRooms(PLAN, OX) {
    const IK = PLAN.kind || 'castle';
    const WH = PLAN.wall_h || 4.0, WT = PLAN.wall_t || 0.5;
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
    const bx = PLAN.bounds[0], bz = PLAN.bounds[1];
    const fmat = new THREE.MeshStandardMaterial({
      map: itex(floorFile, bx / 4, bz / 4), roughness: 0.9 });
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(bx, bz), fmat);
    floor.rotation.x = -Math.PI / 2; floor.position.set(OX, 0.02, 0);
    floor.receiveShadow = true;
    scene.add(floor);
    if (OX !== 0) {                                  // enterable: needs own ground collider
      world.createCollider(RAPIER.ColliderDesc.cuboid(bx / 2, 0.1, bz / 2)
        .setTranslation(OX, -0.08, 0));
    }
    const FLR = PLAN.floors || 1;
    const topY = WH * FLR;
    const cmatI = new THREE.MeshStandardMaterial({
      map: itex(wallFile, bx / 6, bz / 6), roughness: 1.0, color: 0x9a948c });
    const ceil = new THREE.Mesh(new THREE.PlaneGeometry(bx, bz), cmatI);
    ceil.rotation.x = Math.PI / 2; ceil.position.set(OX, topY, 0);
    scene.add(ceil);
    const wmat = new THREE.MeshStandardMaterial({
      map: itex(wallFile, 3, 1.2), roughness: 0.95 });
    const DOOR_W = 2.4, DOOR_H = Math.min(3.0, WH - 0.6);
    function seg(cx, cz, ln, rot, y0, hgt, thick) {
      const m = new THREE.Mesh(new THREE.BoxGeometry(ln, hgt, thick), wmat);
      m.position.set(cx + OX, y0 + hgt / 2, cz);
      m.rotation.y = rot ? Math.PI / 2 : 0;
      m.castShadow = m.receiveShadow = true;
      scene.add(m);
      const rr = rot ? [thick / 2, hgt / 2, ln / 2] : [ln / 2, hgt / 2, thick / 2];
      world.createCollider(RAPIER.ColliderDesc.cuboid(...rr)
        .setTranslation(cx + OX, y0 + hgt / 2, cz));
    }
    for (const [cx, cz, ln, rot, door] of PLAN.walls) {
      if (door < 0) { seg(cx, cz, ln, rot, 0, WH, WT); continue; }
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
    for (const [px2, pz2] of PLAN.pillars || []) {
      const pm = new THREE.Mesh(new THREE.BoxGeometry(0.9, WH, 0.9), wmat);
      pm.position.set(px2 + OX, WH / 2, pz2);
      pm.castShadow = pm.receiveShadow = true;
      scene.add(pm);
      world.createCollider(RAPIER.ColliderDesc.cuboid(0.45, WH / 2, 0.45)
        .setTranslation(px2 + OX, WH / 2, pz2));
    }
    // ── SECOND STORY (moon plan 2.4): solid upper walls, a mezzanine slab
    // with a stair opening, and a real staircase (0.28m steps — the
    // character controller's autostep walks them naturally)
    if (FLR === 2) {
      for (const [cx, cz, ln, rot] of PLAN.walls) {
        seg(cx, cz, ln, rot, WH, WH, WT);            // upper walls, no doors
      }
      const hw3 = PLAN.rooms[0][2] / 2, hd3 = PLAN.rooms[0][3] / 2;
      const stW = 2.2;                               // stair + opening width
      const stX = -hw3 + 1.0 + stW / 2;              // along the west hall wall
      const nSteps = Math.ceil(WH / 0.28);
      const runL = nSteps * 0.42;
      const stZ0 = -Math.min(hd3 - 1.5, runL / 2);
      const slabM = new THREE.MeshStandardMaterial({
        map: itex(floorFile, bx / 5, bz / 5), roughness: 0.9 });
      const holeX0 = stX - stW / 2 - 0.2, holeX1 = stX + stW / 2 + 0.2;
      const holeZ0 = stZ0 - 0.4, holeZ1 = stZ0 + runL + 1.6;
      const slabs = [
        [(-bx / 2 + holeX0) / 2, (holeX0 + bx / 2), 0, bz],            // west of hole
        [(holeX1 + bx / 2) / 2, (bx / 2 - holeX1), 0, bz],             // east of hole
        [(holeX0 + holeX1) / 2, holeX1 - holeX0, (-bz / 2 + holeZ0) / 2, holeZ0 + bz / 2],
        [(holeX0 + holeX1) / 2, holeX1 - holeX0, (holeZ1 + bz / 2) / 2, bz / 2 - holeZ1],
      ];
      for (const [scx, sw, scz, sd] of slabs) {
        if (sw < 0.3 || sd < 0.3) continue;
        const sl = new THREE.Mesh(new THREE.BoxGeometry(sw, 0.3, sd), slabM);
        sl.position.set(scx + OX, WH - 0.15, scz);
        sl.receiveShadow = sl.castShadow = true;
        scene.add(sl);
        world.createCollider(RAPIER.ColliderDesc.cuboid(sw / 2, 0.15, sd / 2)
          .setTranslation(scx + OX, WH - 0.15, scz));
      }
      const stepM = new THREE.MeshStandardMaterial({
        map: itex('stone', 2, 0.5), roughness: 0.95 });
      for (let k = 0; k < nSteps; k++) {
        const sh2 = (k + 1) * (WH / nSteps);
        const sm2 = new THREE.Mesh(new THREE.BoxGeometry(stW, sh2, 0.42), stepM);
        sm2.position.set(stX + OX, sh2 / 2, stZ0 + k * 0.42 + 0.21);
        sm2.castShadow = sm2.receiveShadow = true;
        scene.add(sm2);
        world.createCollider(RAPIER.ColliderDesc.cuboid(stW / 2, sh2 / 2, 0.21)
          .setTranslation(stX + OX, sh2 / 2, stZ0 + k * 0.42 + 0.21));
      }
      // upstairs torches so the mezzanine isn't a void
      window.__torches = window.__torches || [];
      for (const tz2 of [-hd3 * 0.4, hd3 * 0.4]) {
        const pl2 = new THREE.PointLight(0xff9a3d, 12, 12, 1.8);
        pl2.position.set(OX, WH * 1.6, tz2);
        scene.add(pl2);
        window.__torches.push(pl2);
      }
      window.__floors2 = true;
      // WINDOW LIGHT SHAFTS: glowing high windows + slanted translucent
      // beams — the classic cheap volumetric that sells 'interior day'
      const winM = new THREE.MeshBasicMaterial({ color: 0xfff3d6 });
      const shaftM = new THREE.MeshBasicMaterial({
        color: 0xffeebb, transparent: true, opacity: 0.10,
        side: THREE.DoubleSide, depthWrite: false });
      for (let k = 0; k < 3; k++) {
        const wz = -hd3 + (k + 0.7) * (hd3 * 2 / 3.4);
        const win = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 1.8), winM);
        win.position.set(hw3 - 0.28 + OX, WH * 1.45, wz);
        win.rotation.y = -Math.PI / 2;
        scene.add(win);
        const shaft = new THREE.Mesh(new THREE.PlaneGeometry(1.4, WH * 1.7), shaftM);
        shaft.position.set(hw3 - 2.2 + OX, WH * 0.75, wz);
        shaft.rotation.set(0, -Math.PI / 2, 0.42);
        scene.add(shaft);
      }
    }
    const flameG = new THREE.SphereGeometry(0.09, 6, 5);
    const flameM = new THREE.MeshBasicMaterial({ color: 0xffb347 });
    window.__torches = window.__torches || [];
    for (const [tx, tz] of (PLAN.torches || []).slice(0, 10)) {
      const pl = new THREE.PointLight(0xff9a3d, 14, 13, 1.8);
      pl.position.set(tx + OX, WH * 0.62, tz);
      scene.add(pl);
      const fm = new THREE.Mesh(flameG, flameM);
      fm.position.copy(pl.position);
      scene.add(fm);
      window.__torches.push(pl);
    }
    // KIND DECOR (moon plan 2.4): castles hang banners + a carpet runner
    // down the hall; houses get warm rugs. Cheap planes, big identity.
    if (IK === 'castle') {
      const rngD2 = mulberry32((SPEC.seed || 1) + 881);
      const bmatD = new THREE.MeshStandardMaterial({
        color: 0x7a1f24, roughness: 0.9, side: THREE.DoubleSide });
      const hw2 = PLAN.rooms[0][2] / 2, hd2 = PLAN.rooms[0][3] / 2;
      for (let k = 0; k < 4; k++) {                  // wall banners
        const bz2 = -hd2 + (k + 0.5) * (hd2 * 2 / 4);
        for (const sd of [-1, 1]) {
          const bn = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 2.4), bmatD);
          bn.position.set(sd * (hw2 - 0.32) + OX, WH * 0.55, bz2 + 1.6);
          bn.rotation.y = sd > 0 ? -Math.PI / 2 : Math.PI / 2;
          scene.add(bn);
        }
      }
      const cmatD = new THREE.MeshStandardMaterial({ color: 0x6e1d22, roughness: 1.0 });
      const runner = new THREE.Mesh(new THREE.PlaneGeometry(2.4, hd2 * 2 - 3), cmatD);
      runner.rotation.x = -Math.PI / 2;
      runner.position.set(OX, 0.04, 0);
      runner.receiveShadow = true;
      scene.add(runner);
    } else if (IK === 'house') {
      const rugC = [0x8a4a3b, 0x3f5a7a, 0x6e5a2f];
      let ri = 0;
      for (const [rcx, rcz, rrw, rrd] of PLAN.rooms.slice(1)) {
        const rug = new THREE.Mesh(
          new THREE.PlaneGeometry(Math.min(rrw - 2, 3.2), Math.min(rrd - 2, 2.4)),
          new THREE.MeshStandardMaterial({ color: rugC[ri++ % 3], roughness: 1.0 }));
        rug.rotation.x = -Math.PI / 2;
        rug.position.set(rcx + OX, 0.04, rcz);
        rug.receiveShadow = true;
        scene.add(rug);
      }
    }
    (async () => {
      const cache = {};
      for (const [name, fx, fz, fyaw] of PLAN.furniture || []) {
        try {
          if (!cache[name]) cache[name] = await loadGLB('props/' + name + '.glb');
          const inst = cache[name].scene.clone(true);
          inst.position.set(fx + OX, 0, fz);
          inst.rotation.y = fyaw;
          inst.traverse(o => { if (o.isMesh) { o.castShadow = true; } });
          scene.add(inst);
          const bb = new THREE.Box3().setFromObject(inst);
          const sz = bb.getSize(new THREE.Vector3());
          world.createCollider(RAPIER.ColliderDesc.cuboid(
            Math.max(sz.x, 0.2) / 2, Math.max(sz.y, 0.2) / 2, Math.max(sz.z, 0.2) / 2)
            .setTranslation(fx + OX, sz.y / 2, fz));
        } catch (e) { /* missing prop file: skip */ }
      }
    })();
    return { WH: WH * FLR, entryZ: -PLAN.rooms[0][3] / 2 + 2.2 };
  }
  if (INTERIOR) {
    buildRooms(INTERIOR, 0);
    // indoor mood: dim the sun, warm the ambience, pull fog off, close camera
    sun.intensity *= 0.35;
    hemi.intensity *= 0.55;
    if (scene.fog) { scene.fog.near = 60; scene.fog.far = 160; }
    scene.background = new THREE.Color(0x0d0c0a);
    SPEC.camera.distance_m = Math.min(SPEC.camera.distance_m || 6, 4.6);
  }
  // ── ENTERABLE BUILDING (moon plan 2.2): an exterior world with a castle/
  // house gets a REAL door — walk to the glowing doorway and step into a
  // generated interior (built past the map edge); an exit door leads back.
  window.__doorway = null;
  if (!INTERIOR && LVL && LVL.enterable) {
    const EPLAN = LVL.enterable.plan;
    const EOX = SPEC.world.size_m * 2.2;
    const eb = buildRooms(EPLAN, EOX);
    const [dx2, dz2] = LVL.enterable.door;
    const dy2 = hAt(dx2, dz2);
    // glowing doorway marker outside
    const dgeo = new THREE.PlaneGeometry(1.8, 2.6);
    const dmat2 = new THREE.MeshBasicMaterial({
      color: 0xffc46b, transparent: true, opacity: 0.45, side: THREE.DoubleSide });
    const doorM = new THREE.Mesh(dgeo, dmat2);
    doorM.position.set(dx2, dy2 + 1.3, dz2);
    scene.add(doorM);
    const glow2 = new THREE.PointLight(0xffb347, 6, 9, 1.8);
    glow2.position.set(dx2, dy2 + 2.0, dz2);
    scene.add(glow2);
    // matching exit marker inside (at the hall's entry door)
    const exitM = doorM.clone();
    exitM.position.set(EOX, 1.3, eb.entryZ - 3.2);
    scene.add(exitM);
    window.__doorway = {
      out: [dx2, dz2], inSpawn: [EOX, eb.entryZ + 1.0],
      exit: [EOX, eb.entryZ - 3.2], wallH: eb.WH, cool: 0 };
  }

  // GRASS: instanced cross-blades on the terrain, thinned along the walking
  // path — the "flat green plane" is gone. (Gated off for cities/snow.)
  if (!PURE_SCENE && (SPEC.world.scatter || []).length && SPEC.world.grass !== false) {
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
    // DENSITY ARC r2: ultra tier earns a thicker meadow (~1.5x blades) —
    // undergrowth density is the cheapest 'lived-in world' signal we have
    const GN = Math.min(QUALITY === 'ultra' ? 21000 : 13000,
                        Math.floor(GR * GR * (QUALITY === 'ultra' ? 3.2 : 2.2)));
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
  if (!PURE_SCENE && LVL && LVL.landmarks && landmarkAsset) {
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
  // ── ABILITY VFX (2026-07-29): element aura + movement trail bound to the
  // hero. The element comes from the PROMPT THEME (backend infers water/
  // fire/frost/… only when the character concept calls for it — a
  // waterbender hovers inside orbiting water, a fire dragon sheds embers,
  // a plain knight gets NOTHING). Additive Points, CPU-stepped; ~210
  // particles ≈ 0.2 ms.
  const VFX = (() => {
    const EL = {
      water:    { a: 0x2fb9ff, b: 0x9fe8ff, orbit: 1, rise: -0.2, size: 0.34, spin: 1.6 },
      fire:     { a: 0xff7a1a, b: 0xffd75e, orbit: 0, rise: 1.4,  size: 0.30, spin: 0.8 },
      frost:    { a: 0x9fd8ff, b: 0xffffff, orbit: 1, rise: -0.5, size: 0.22, spin: 0.7 },
      electric: { a: 0xb388ff, b: 0xf3ecff, orbit: 1, rise: 0.0,  size: 0.20, spin: 3.2 },
      shadow:   { a: 0x5e3d8f, b: 0x9f7fe8, orbit: 0, rise: 0.5,  size: 0.42, spin: 0.5 },
      nature:   { a: 0x59c94f, b: 0xd8f77a, orbit: 1, rise: 0.35, size: 0.24, spin: 0.9 },
      arcane:   { a: 0xc86bff, b: 0x7fd7ff, orbit: 1, rise: 0.25, size: 0.26, spin: 2.2 },
      wind:     { a: 0xdfe8ee, b: 0xffffff, orbit: 1, rise: 0.15, size: 0.28, spin: 2.6 },
    }[SPEC.player.vfx || ''];
    if (!EL) return null;
    const tex = (() => {
      const c = document.createElement('canvas'); c.width = c.height = 64;
      const g = c.getContext('2d');
      const r = g.createRadialGradient(32, 32, 2, 32, 32, 30);
      r.addColorStop(0, 'rgba(255,255,255,1)');
      r.addColorStop(0.45, 'rgba(255,255,255,0.5)');
      r.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = r; g.fillRect(0, 0, 64, 64);
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
      return t;
    })();
    const mk = (n, size, color) => {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position',
        new THREE.BufferAttribute(new Float32Array(n * 3).fill(-999), 3));
      const p = new THREE.Points(geo, new THREE.PointsMaterial({
        map: tex, color, size, transparent: true, opacity: 0.85,
        depthWrite: false, blending: THREE.AdditiveBlending }));
      p.frustumCulled = false; p.renderOrder = 9; scene.add(p);
      return p;
    };
    const AN = 80, TN = 110;
    const aura = mk(AN, EL.size, EL.a);
    const trail = mk(TN, EL.size * 0.8, EL.b);
    const tp = new Float32Array(TN * 3), tl = new Float32Array(TN);
    let ti = 0, prev = null, phase = Math.random() * 9;
    return { step(dt, pp) {
      phase += dt * EL.spin;
      const hh = P.height_m || 1.7;
      const cy = pp.y + hh * 0.55;
      const ap = aura.geometry.attributes.position.array;
      for (let i = 0; i < AN; i++) {
        const f = i / AN, a = phase + f * Math.PI * 2;
        if (EL.orbit) {
          // orbiting ribbon (water/frost/arcane…): hugs the TORSO (anchor
          // tuned 2026-07-29 — it floated over the head and read detached)
          const rad = 0.5 + 0.2 * Math.sin(f * 19.0 + phase * 0.9);
          ap[i * 3]     = pp.x + Math.cos(a) * rad;
          ap[i * 3 + 1] = pp.y + hh * 0.42 + Math.sin(a * 2.0 + f * 9.0) * hh * 0.3;
          ap[i * 3 + 2] = pp.z + Math.sin(a) * rad;
        } else {
          // rising wisps (fire/shadow): respawn at feet, drift upward
          const cyc = (phase * (0.35 + f * 0.8) + f * 7.0) % 1.0;
          const rad = 0.45 * (1.0 - cyc * 0.5);
          ap[i * 3]     = pp.x + Math.cos(a * 3.1) * rad;
          ap[i * 3 + 1] = pp.y + 0.15 + cyc * hh * 1.15;
          ap[i * 3 + 2] = pp.z + Math.sin(a * 3.1) * rad;
        }
      }
      aura.geometry.attributes.position.needsUpdate = true;
      const sp = prev ? Math.hypot(pp.x - prev.x, pp.z - prev.z) / Math.max(dt, 1e-4) : 0;
      if (prev && sp > 1.2) {
        for (let k = 0; k < 3; k++) {
          ti = (ti + 1) % TN; tl[ti] = 1.0;
          tp[ti * 3]     = pp.x + (Math.random() - 0.5) * 0.5;
          tp[ti * 3 + 1] = cy - hh * 0.25 + (Math.random() - 0.5) * 0.5;
          tp[ti * 3 + 2] = pp.z + (Math.random() - 0.5) * 0.5;
        }
      }
      const rp = trail.geometry.attributes.position.array;
      for (let i = 0; i < TN; i++) {
        if (tl[i] > 0) {
          tl[i] -= dt * 0.9;
          tp[i * 3 + 1] += EL.rise * dt;
          rp[i * 3] = tp[i * 3]; rp[i * 3 + 1] = tp[i * 3 + 1]; rp[i * 3 + 2] = tp[i * 3 + 2];
        } else { rp[i * 3 + 1] = -999; }
      }
      trail.geometry.attributes.position.needsUpdate = true;
      prev = { x: pp.x, y: pp.y, z: pp.z };
    } };
  })();

  // ── MINIMAP (r12, 2026-07-30): circular GTA-style map for city games —
  // roads + building footprints pre-rendered once, live player wedge +
  // objective dot composited per frame. The reference frame has one; a
  // minimap is a shockingly large perceived-quality cue.
  const MINIMAP = (() => {
    if (!OSM || !OSM.roads || !OSM.roads.length) return null;
    const base = document.createElement('canvas');
    base.width = base.height = 160;
    const bx = base.getContext('2d');
    const half2 = SPEC.world.size_m / 2;
    const w2m = (v) => 80 + (v / half2) * 74;
    bx.fillStyle = 'rgba(10,12,18,0.85)';
    bx.beginPath(); bx.arc(80, 80, 78, 0, Math.PI * 2); bx.fill();
    bx.save();
    bx.beginPath(); bx.arc(80, 80, 76, 0, Math.PI * 2); bx.clip();
    bx.fillStyle = 'rgba(96,102,118,0.4)';
    for (const b of OSM.buildings || []) {
      bx.beginPath();
      b.pts.forEach((p, i) => i ? bx.lineTo(w2m(p[0]), w2m(p[1]))
                                : bx.moveTo(w2m(p[0]), w2m(p[1])));
      bx.closePath(); bx.fill();
    }
    bx.strokeStyle = 'rgba(215,220,230,0.85)';
    bx.lineCap = 'round';
    for (const r of OSM.roads) {
      bx.lineWidth = Math.max(1.6, ((r.w || 7) / half2) * 74);
      bx.beginPath();
      r.pts.forEach((p, i) => i ? bx.lineTo(w2m(p[0]), w2m(p[1]))
                                : bx.moveTo(w2m(p[0]), w2m(p[1])));
      bx.stroke();
    }
    bx.restore();
    const cv = document.createElement('canvas');
    cv.width = cv.height = 160;
    cv.style.cssText = 'position:fixed;left:14px;bottom:14px;width:150px;'
      + 'height:150px;border-radius:50%;border:2px solid rgba(255,255,255,0.22);'
      + 'z-index:12;box-shadow:0 4px 18px rgba(0,0,0,0.5);pointer-events:none;';
    document.body.appendChild(cv);
    const mx = cv.getContext('2d');
    const dirV = new THREE.Vector3();
    const goal = LVL && LVL.goal;
    return { step(pp) {
      mx.clearRect(0, 0, 160, 160);
      mx.drawImage(base, 0, 0);
      if (goal) {
        mx.fillStyle = '#ffd166';
        mx.beginPath();
        mx.arc(w2m(goal[0]), w2m(goal[1]), 4.2, 0, Math.PI * 2);
        mx.fill();
      }
      camera.getWorldDirection(dirV);
      mx.save();
      mx.translate(w2m(pp.x), w2m(pp.z));
      mx.rotate(Math.PI - Math.atan2(dirV.x, dirV.z));
      mx.fillStyle = '#5cffc9';
      mx.strokeStyle = 'rgba(0,0,0,0.55)'; mx.lineWidth = 1.4;
      mx.beginPath();
      mx.moveTo(0, -6.5); mx.lineTo(4.4, 4.6); mx.lineTo(-4.4, 4.6);
      mx.closePath(); mx.fill(); mx.stroke();
      mx.restore();
    } };
  })();

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
      if (window.__restoreProg) window.__restoreProg();   // saved upgrades return
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
              if (m.map) { if (_flatStyle) cartoonizeTexture(m); else despeckleTexture(m); }
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
        // DENSITY ARC (2026-07-29): kill the clone army — each rival vehicle
        // gets its own paint hue (racing-field palette), cloned materials so
        // the player's car is untouched.
        if (ent.behavior === 'vehicle') {
          // r6 FIX: TRELLIS cars carry paint in the TEXTURE (material.color
          // stays white) so the old HSL shift never fired — rivals stayed a
          // clone army. Hue-rotate the diffuse texture itself via a one-time
          // 1K canvas copy per rival (tires/glass are near-neutral, so the
          // rotation only really moves the paint).
          const deg = Math.floor(30 + rngN() * 300);
          const done = new Map();
          inst.traverse(o => {
            if (!o.isMesh || !o.material) return;
            const ms = Array.isArray(o.material)
              ? o.material.map(m => m.clone()) : [o.material.clone()];
            o.material = Array.isArray(o.material) ? ms : ms[0];
            for (const m of ms) {
              const img = m.map && m.map.image;
              if (img && img.width) {
                if (!done.has(m.map)) {
                  try {
                    const c = document.createElement('canvas');
                    const w = Math.min(img.width, 1024);
                    c.width = w;
                    c.height = Math.max(1, Math.round(img.height * w / img.width));
                    const g2 = c.getContext('2d');
                    g2.filter = 'hue-rotate(' + deg + 'deg) saturate(1.05)';
                    g2.drawImage(img, 0, 0, c.width, c.height);
                    const nt = new THREE.CanvasTexture(c);
                    nt.colorSpace = THREE.SRGBColorSpace;
                    nt.flipY = m.map.flipY;
                    nt.wrapS = m.map.wrapS; nt.wrapT = m.map.wrapT;
                    done.set(m.map, nt);
                  } catch (e) { done.set(m.map, m.map); }
                }
                m.map = done.get(m.map);
                m.needsUpdate = true;
              } else if (m.color) {
                const hsl = {}; m.color.getHSL(hsl);
                if (hsl.s > 0.12 && hsl.l > 0.15 && hsl.l < 0.9) {
                  m.color.setHSL(deg / 360, Math.min(0.85, hsl.s * 1.15), hsl.l);
                }
              }
            }
          });
        }
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
          // 2026-07-27 'duplicate car': 2.4m lanes + 5m rows packed rivals
          // into the player's car (cars are ~2m wide, ~4.5m long). Real grid:
          // 3.4m lanes, 8m rows, and the whole grid starts BEHIND the player.
          const lane = (vehIdx % 2 ? 1 : -1) * (3.4 + Math.floor(vehIdx / 2) * 0.001);
          const back = 8 + Math.floor(vehIdx / 2) * 8;
          holder.position.set(
            PATH[0][0] + rx * lane - Math.sin(hd) * back, 0,
            PATH[0][1] + rz * lane - Math.cos(hd) * back);
          startYaw = hd + (ent.asset === SPEC.player.asset
            ? THREE.MathUtils.degToRad(SPEC.player.yaw_offset_deg || 0) : 0);
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
  // ── XP + LEVEL-UPS (moon plan 3.2): kills and pickups grant XP; each
  // level offers a three-choice upgrade card (roguelike style). The game
  // keeps running behind the card — choosing is part of the flow.
  let xp = 0, plvl = 1;
  const xpNeed = () => 40 * plvl;
  // PERSISTENCE (moon plan 3.2): upgrades survive replays of this game
  // CAMPAIGN (moon plan 3.3): levels inside a Game Project share ONE hero —
  // XP upgrades earned in level 1 carry into level 2 (the hub's URL layout
  // levels/lvl_N/dist identifies the project scope)
  const _projM = location.pathname.match(/^(.*)\/levels\/lvl_\d+\/dist/);
  const _progKey = _projM ? 'fs_prog_proj_' + _projM[1]
                          : 'fs_prog_' + (SPEC.title || 'game');
  const _picks = [];
  function _applyPick(k, silent) {
    if (k === 'heart') { P.hp = (P.hp || 5) + 1; php += 1; }
    else if (k === 'swift') { P.walk_speed *= 1.12; P.run_speed *= 1.12; }
    else if (k === 'power') { atkDmg += 1; }
    _picks.push(k);
    if (!silent) {
      try { localStorage.setItem(_progKey,
        JSON.stringify({ lvl: plvl, picks: _picks })); } catch (e) {}
    }
  }
  window.__restoreProg = () => {          // called once the player is ready
    try {
      const sv = JSON.parse(localStorage.getItem(_progKey) || 'null');
      if (sv && sv.picks) {
        for (const k of sv.picks) _applyPick(k, true);
        plvl = sv.lvl || (sv.picks.length + 1);
        renderHearts();
        if (sv.picks.length) popText('Level ' + plvl + ' hunter returns', '#8de06c');
      }
    } catch (e) {}
  };
  const xpBar = document.createElement('div');
  xpBar.style.cssText = 'position:fixed;top:58px;left:50%;transform:translateX(-50%);'
    + 'width:150px;height:5px;background:rgba(255,255,255,0.15);border-radius:3px;z-index:5';
  const xpFill = document.createElement('div');
  xpFill.style.cssText = 'height:100%;width:0%;background:#8de06c;border-radius:3px;'
    + 'transition:width 0.25s';
  xpBar.appendChild(xpFill);
  const lvlChip = document.createElement('div');
  lvlChip.style.cssText = 'position:absolute;left:-34px;top:-7px;color:#8de06c;'
    + 'font:700 12px system-ui;text-shadow:0 1px 3px #000';
  lvlChip.textContent = 'Lv 1';
  xpBar.appendChild(lvlChip);
  document.body.appendChild(xpBar);
  function addXP(n) {
    xp += n;
    while (xp >= xpNeed()) { xp -= xpNeed(); plvl++; lvlChip.textContent = 'Lv ' + plvl; levelCard(); }
    xpFill.style.width = Math.min(100, xp / xpNeed() * 100) + '%';
  }
  function levelCard() {
    sfx('pickup');
    const wrap = document.createElement('div');
    wrap.style.cssText = 'position:fixed;inset:0;display:flex;align-items:center;'
      + 'justify-content:center;gap:14px;z-index:40;background:rgba(8,6,14,0.45)';
    const mk = (icon, name, desc, fn) => {
      const c = document.createElement('button');
      c.style.cssText = 'width:150px;padding:18px 10px;border-radius:12px;border:1px solid '
        + 'rgba(255,255,255,0.25);background:rgba(20,16,34,0.92);color:#efeaff;cursor:pointer;'
        + 'font:600 13px system-ui;text-align:center';
      c.innerHTML = '<div style="font-size:30px">' + icon + '</div><div style="margin:6px 0 3px">'
        + name + '</div><div style="font-weight:400;opacity:0.7">' + desc + '</div>';
      c.onclick = () => { fn(); document.body.removeChild(wrap); };
      return c;
    };
    const title = document.createElement('div');
    title.style.cssText = 'position:fixed;top:18%;left:50%;transform:translateX(-50%);'
      + 'color:#ffd257;font:800 22px system-ui;text-shadow:0 2px 8px #000';
    title.textContent = 'LEVEL ' + plvl + ' — choose an upgrade';
    wrap.appendChild(title);
    wrap.appendChild(mk('❤️', '+1 Heart', 'more health',
      () => { _applyPick('heart'); renderHearts(); }));
    wrap.appendChild(mk('⚡', 'Swift', '+12% speed',
      () => { _applyPick('swift'); }));
    wrap.appendChild(mk('⚔️', 'Power', '+1 damage',
      () => { _applyPick('power'); }));
    document.body.appendChild(wrap);
  }
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
    // DEATH HEATMAP (moon plan H4): creators see where players die —
    // recorded here, rendered as markers when Inspect mode opens
    try {
      const dk = 'fs_deaths_' + (SPEC.title || 'game');
      const arr = JSON.parse(localStorage.getItem(dk) || '[]');
      const pp2 = body.translation();
      arr.push([Math.round(pp2.x * 10) / 10, Math.round(pp2.z * 10) / 10]);
      localStorage.setItem(dk, JSON.stringify(arr.slice(-50)));
    } catch (e) {}
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

  // NIGHT HEADLIGHTS (Phase 134/D): driving after dark gets two real
  // spotlights + additive volumetric cones — the Maybach-frame look.
  // Created at LOAD (light count never changes -> no shader recompiles).
  if ((P.mode || 'walk') === 'drive' && ['night', 'dusk'].includes(SPEC.world.sky)) {
    window.__headlights = [];
    // generated car meshes are NOT centered on their own axis — measure the
    // lateral offset once so the beam pair sits on the actual nose center
    const _hbb = new THREE.Box3().setFromObject(pRoot);
    window.__hlOff = { x: (_hbb.min.x + _hbb.max.x) / 2, z: 0 };
    for (const hside of [-0.7, 0.7]) {
      const hl = new THREE.SpotLight(0xfff2d8, 60, 42, 0.42, 0.45, 1.6);
      hl.castShadow = false;
      scene.add(hl); scene.add(hl.target);
      const coneG = new THREE.ConeGeometry(1.7, 9, 16, 1, true);
      coneG.translate(0, -4.5, 0);
      coneG.rotateX(-Math.PI / 2);
      const cone = new THREE.Mesh(coneG, new THREE.MeshBasicMaterial({
        color: 0xfff0c8, transparent: true, opacity: 0.055,
        blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
      scene.add(cone);
      window.__headlights.push({ hl, cone, side: hside });
    }
  }

  // CITY LIFE (Phase 120): in OSM driving games the car mesh is already in
  // memory — clone it into PARKED cars along curbs + a few AMBIENT drivers
  // looping the real streets. Zero extra downloads.
  window.__traffic = [];
  if (OSM && (P.mode || 'walk') === 'drive' && OSM.roads && OSM.roads.length) {
    const rngT = mulberry32(SPEC.seed + 717);
    const carTints = [0xd8d8dc, 0x23252c, 0x8a1f24, 0x2a4d7f, 0xc9a13b, 0x3d3f45];
    const mkCar = (tint) => {
      const c2 = pRoot.clone(true);
      c2.traverse(o => {
        if (!o.isMesh) return;
        o.material = Array.isArray(o.material)
          ? o.material.map(m => m.clone()) : o.material.clone();
        for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
          if (m && m.color) m.color.lerp(new THREE.Color(tint), 0.55);
        }
      });
      const g2 = new THREE.Group();
      g2.add(c2);
      return g2;
    };
    let parked = 0;
    for (const r of OSM.roads) {
      if (parked >= 18) break;
      const hd3 = Math.atan2(r.pts[r.pts.length - 1][0] - r.pts[0][0],
                             r.pts[r.pts.length - 1][1] - r.pts[0][1]);
      for (let fi = 0.25; fi < 1 && parked < 18; fi += 0.34) {
        if (rngT() < 0.45) continue;
        const pi2 = Math.min(Math.floor(fi * (r.pts.length - 1)), r.pts.length - 2);
        const px2 = r.pts[pi2][0], pz2 = r.pts[pi2][1];
        const side = rngT() < 0.5 ? 1 : -1;
        const cx2 = px2 + Math.cos(hd3) * side * ((r.w || 7) / 2 - 0.4);
        const cz2 = pz2 - Math.sin(hd3) * side * ((r.w || 7) / 2 - 0.4);
        if (Math.hypot(cx2, cz2) < 14 || inBldg(cx2, cz2, 0.5)) continue;
        const pc = mkCar(carTints[Math.floor(rngT() * carTints.length)]);
        pc.position.set(cx2, hAt(cx2, cz2), cz2);
        pc.rotation.y = hd3 + (side > 0 ? 0 : Math.PI);
        scene.add(pc);
        parked++;
      }
    }
    for (let ti = 0; ti < 4; ti++) {                 // ambient drivers
      const r = OSM.roads[Math.floor(rngT() * OSM.roads.length)];
      if (!r || r.pts.length < 2) continue;
      const tc = mkCar(carTints[Math.floor(rngT() * carTints.length)]);
      scene.add(tc);
      window.__traffic.push({ obj: tc, pts: r.pts, seg: 0, t: rngT(),
                              speed: 6 + rngT() * 3, dir: 1 });
    }
  }

  // ── PEDESTRIANS (r4, 2026-07-30): ambient walkers on the sidewalk band —
  // the single biggest 'city feels alive' delta after real streets. A
  // lightweight walker bake (7.8MB) is bundled for city levels; skinned
  // clones via SkeletonUtils, walk clip phase-shifted per walker, each
  // following a road polyline OFFSET to the sidewalk like the furniture.
  window.__peds = [];
  if (OSM && OSM.roads && OSM.roads.length) {
    (async () => {
      try {
        const { clone: skClone } = await import('./vendor/jsm/utils/SkeletonUtils.js');
        const g = await loadGLB('assets/walker.glb');
        const clips = g.animations || [];
        const walkClip = clips.find(c => /walk/i.test(c.name)) || clips[0];
        const rngP = mulberry32(SPEC.seed + 818);
        for (let i = 0; i < 8; i++) {
          const r = OSM.roads[Math.floor(rngP() * OSM.roads.length)];
          if (!r || r.pts.length < 2) continue;
          const inst = skClone(g.scene);
          const bb = new THREE.Box3().setFromObject(inst);
          inst.scale.multiplyScalar((1.66 + rngP() * 0.14)
            / Math.max(bb.max.y - bb.min.y, 1e-3));
          const bb2 = new THREE.Box3().setFromObject(inst);
          inst.position.y = -bb2.min.y;
          const holder2 = new THREE.Group();
          holder2.add(inst);
          holder2.traverse(o => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
          scene.add(holder2);
          let mixer2 = null;
          if (walkClip) {
            mixer2 = new THREE.AnimationMixer(inst);
            const act = mixer2.clipAction(walkClip);
            act.timeScale = 0.9 + rngP() * 0.3;
            act.play();
            mixer2.update(rngP() * 2.5);      // phase-shift: no synchronized march
          }
          window.__peds.push({ obj: holder2, mixer: mixer2, pts: r.pts,
            seg: Math.max(0, Math.floor(rngP() * (r.pts.length - 1))), t: rngP(),
            speed: 1.1 + rngP() * 0.6, dir: rngP() < 0.5 ? 1 : -1,
            side: ((r.w || 7) / 2 + 1.4 + rngP() * 0.8) * (rngP() < 0.5 ? 1 : -1) });
        }
        console.log('[game] pedestrians: ' + window.__peds.length);
      } catch (e) { console.warn('[game] pedestrians skipped: ' + e.message); }
    })();
  }

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
      if (m && m.map) { if (_flatStyle) cartoonizeTexture(m); else despeckleTexture(m); }
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
  // CINEMATIC MODE (Phase 134/A): 'V' or the 🎥 chip — the camera hands
  // off to a choreographed move (FPV chase for driving, low orbit for
  // heroes) with the cine post stack on. Auto-returns after 22s.
  let cineOn = false, cineT = 0;
  const _cinePrevCam = new THREE.Vector3();
  function setCine(on) {
    if (on && VIEW !== '3d') return;     // choreography is a 3D-camera art
    cineOn = on; cineT = 0;
    if (!on) { camera.rotation.z = 0; camera.up.set(0, 1, 0); }  // no leftover bank
    cinePass.uniforms.uOn.value = on ? 1 : 0;
    const cb = document.getElementById('cinebtn');
    if (cb) cb.style.opacity = on ? '1' : '0.55';
  }
  {
    const cb = document.createElement('button');
    cb.id = 'cinebtn'; cb.textContent = '🎥';
    cb.title = 'Cinematic camera (V) — stays on until toggled off';
    cb.style.cssText = 'position:fixed;right:14px;bottom:14px;z-index:6;font-size:20px;'
      + 'background:rgba(16,14,28,0.6);border:1px solid rgba(255,255,255,0.2);'
      + 'border-radius:10px;padding:6px 10px;cursor:pointer;opacity:0.55';
    cb.onclick = () => setCine(!cineOn);
    if (VIEW !== '3d') cb.style.display = 'none';
    document.body.appendChild(cb);
  }
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
      addXP(10);
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
    if (e.code === 'KeyV') { e.preventDefault(); setCine(!cineOn); }
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
    // death heatmap markers (H4): red discs where players have died
    if (on && !window.__deathMarks) {
      window.__deathMarks = [];
      try {
        const arr = JSON.parse(localStorage.getItem(
          'fs_deaths_' + (SPEC.title || 'game')) || '[]');
        const dm = new THREE.MeshBasicMaterial({
          color: 0xff2438, transparent: true, opacity: 0.55, depthWrite: false });
        for (const [dx3, dz3] of arr.slice(-50)) {
          const disc = new THREE.Mesh(new THREE.CircleGeometry(0.7, 12), dm);
          disc.rotation.x = -Math.PI / 2;
          disc.position.set(dx3, hAt(dx3, dz3) + 0.06, dz3);
          scene.add(disc);
          window.__deathMarks.push(disc);
        }
        if (arr.length) popText(arr.length + ' recorded deaths shown', '#ff8fa0');
      } catch (e) {}
    } else if (!on && window.__deathMarks) {
      for (const m of window.__deathMarks) scene.remove(m);
      window.__deathMarks = null;
    }
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
    const PHOTO = (SPEC.style || 'default') !== 'cartoon';  // cartoon = FLAT fills
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
                       foliage: 'leaves', needles: 'needles', wall: 'facade_brick' };
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
      if (m.name === 'window' && ['night', 'dusk', 'sunset'].includes(SPEC.world.sky)
          && m.emissive) {                           // homes light up after dark
        m.emissive.setHex(0xffb45c);
        m.emissiveIntensity = 1.4;
        m.needsUpdate = true;
      }
      if (m.map && m.map.anisotropy < 4) {           // crisp at grazing angles
        m.map.anisotropy = renderer.capabilities.getMaxAnisotropy();
        m.map.needsUpdate = true;
      }
      if (!m.isMeshStandardMaterial || m.map || _seen.has(m.uuid)) continue;
        _seen.add(m.uuid);
        if (!o.geometry.attributes.uv) continue;             // needs UVs to texture
        let cls = classify(m);
        if ((m.name || '').toLowerCase() === 'wall') cls = 'wall';   // prop buildings wear brick facade
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
        } else if (_flatStyle) {
          // TRUE-CARTOON props: no texture at all — flat saturated fills
          m.map = null; m.bumpMap = null; m.normalMap = null;
          m.color.offsetHSL(0, 0.14, 0.04);
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
    // (140D: skip when the pano's own floor owns the ground — tiling a
    // generic sand photo over the image's sand is exactly the mismatch
    // the user called out)
    if (PHOTO && !panoGroundTex) {
      const wn = (SPEC.world.name || '').toLowerCase();
      const gname = (SPEC.world.weather === 'snow') ? 'snow'
        : /desert|beach|dune/.test(wn) ? 'sand'
        : /forest|wood|jungle/.test(wn) ? 'forest'
        : /city|street|town|road/.test(wn) ? 'concrete' : 'grass';
      // GROUND LAYERING FLIP (Phase 128, the HD unlock): the old pipeline
      // squeezed the photo into the world-spanning painted canvas (~60px per
      // 9m tile — permanently mushy). Now the TILED PHOTO is the primary
      // albedo at full resolution, and the painted canvas (roads, trails,
      // crosswalks, palette) multiplies on top as a world-space tint via a
      // tiny shader patch. Mid-gray in the canvas = neutral; dark road paint
      // darkens photo concrete into asphalt; grass tint stays green.
      // DENSITY ARC (2026-07-29): gsize/9 left ~9m per texture tile — reads
      // gritty/soft up close ('pixels aren't tight'). ~4.5m per tile doubles
      // texel density underfoot; the world-canvas tint keeps large-scale
      // variation so the tighter repeat doesn't look mechanical.
      // city concrete tightens further (~2.5m): its grout grid at 4.5m read
      // as giant plaza pavers — at sidewalk-joint scale it reads as pavement
      const grep2 = Math.max(20, Math.round(gsize / (gname === 'concrete' ? 2.5 : 4.5)));
      gmat.map = pbr(gname, grep2, true);
      gmat.normalMap = pbr(gname + '_n', grep2, false);
      gmat.normalScale = new THREE.Vector2(0.65, 0.65);
      const worldTint = gtex;                        // the painted canvas
      gmat.onBeforeCompile = (sh) => {
        sh.uniforms.uWorld = { value: worldTint };
        sh.vertexShader = `varying vec2 vUvRaw;
` + sh.vertexShader.replace(
          '#include <uv_vertex>',
          `#include <uv_vertex>
  vUvRaw = uv;`);
        sh.fragmentShader = `uniform sampler2D uWorld;
varying vec2 vUvRaw;
`
          + sh.fragmentShader.replace(
            '#include <map_fragment>',
            `#include <map_fragment>
  vec3 wTint = texture2D(uWorld, vUvRaw).rgb * 2.0;
  diffuseColor.rgb *= clamp(wTint, 0.12, 1.45);`);
      };
      gmat.needsUpdate = true;
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
  // CONSOLE-GRADE IMAGE (Tier 1, 2026-07-27): the default composer target
  // has NO multisampling, so every edge stair-stepped once post-processing
  // was on. A 4x MSAA half-float target kills the shimmer at ~5% GPU cost.
  const _msaaRT = new THREE.WebGLRenderTarget(1, 1, {
    samples: QCFG.msaa, type: THREE.HalfFloatType });
  const composer = new EffectComposer(renderer, _msaaRT);
  // N8AO (Arc A round 2, 2026-07-28): ground-truth ambient occlusion (CC0
  // lib) REPLACES both the RenderPass and the homemade 8-tap SSAO — it
  // renders the scene itself with a true depth+normal AO pass. Half-res is
  // 2-4x faster with near-identical quality at 1080p (research budget).
  const n8ao = new N8AOPass(scene, camera, innerWidth, innerHeight);
  n8ao.configuration.aoRadius = 2.2;
  n8ao.configuration.distanceFalloff = 0.7;
  n8ao.configuration.intensity = 3.1;   // r15: deeper crevice shading
  n8ao.configuration.halfRes = true;
  n8ao.configuration.gammaCorrection = false;   // later passes own the grade
  if (QUALITY === 'performance') n8ao.configuration.aoSamples = 8;
  composer.addPass(n8ao);
  const _legacySSAO = false;   // homemade SSAO retired; block kept for reference
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
  if (_legacySSAO) composer.addPass(ssao);
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
  // r15 GODRAYS: screen-space light shafts from the sun — the single
  // biggest 'photograph' mood cue for scenic worlds (dawn forest, sunset
  // ridge). Radial luminance-thresholded blur toward the sun's screen
  // position; strength eases in/out as the sun enters/leaves frame.
  const godray = (SPEC.world.sky !== 'night') ? new ShaderPass({
    uniforms: { tDiffuse: { value: null },
                uSun: { value: new THREE.Vector2(0.5, 0.8) },
                uStr: { value: 0 } },
    vertexShader: `varying vec2 vUv;
      void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform sampler2D tDiffuse; uniform vec2 uSun;
      uniform float uStr; varying vec2 vUv;
      void main(){
        vec4 c = texture2D(tDiffuse, vUv);
        if (uStr <= 0.001) { gl_FragColor = c; return; }
        vec2 dir = (uSun - vUv) / 22.0;
        vec3 acc = vec3(0.0);
        vec2 p = vUv;
        float w = 1.0;
        for (int i = 0; i < 22; i++) {
          p += dir;
          vec3 s = texture2D(tDiffuse, p).rgb;
          float l = dot(s, vec3(0.299, 0.587, 0.114));
          acc += s * smoothstep(0.62, 1.0, l) * w;
          w *= 0.94;
        }
        c.rgb += acc / 22.0 * uStr;
        gl_FragColor = c;
      }`,
  }) : null;
  if (godray) composer.addPass(godray);
  const _grV1 = new THREE.Vector3(), _grV2 = new THREE.Vector3();
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
    uniforms: { tDiffuse: { value: null }, uT: { value: 0 },
                tint: { value: new THREE.Vector3(gradeTint.r, gradeTint.g, gradeTint.b) } },
    vertexShader: `varying vec2 vUv;
      void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform sampler2D tDiffuse; uniform vec3 tint;
      uniform float uT; varying vec2 vUv;
      void main(){
        vec4 c = texture2D(tDiffuse, vUv);
        float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
        c.rgb = mix(c.rgb, c.rgb * tint, 0.22);          // mood tint
        // FILM PUNCH (Arc A): AgX is deliberately flat — this restores bite
        // the graded way: gentle S-contrast around mid-gray, saturation lift,
        // and a subtle teal-shadow / warm-highlight split tone (the classic
        // blockbuster grade, kept far below music-video strength).
        c.rgb = mix(vec3(l), c.rgb, 1.12);               // saturation
        c.rgb = clamp((c.rgb - 0.5) * 1.07 + 0.5, 0.0, 1.0);  // S-contrast
        float lu = dot(c.rgb, vec3(0.299, 0.587, 0.114));
        vec3 shadowTone = vec3(0.94, 1.0, 1.06);         // teal shadows
        vec3 highTone   = vec3(1.05, 1.0, 0.95);         // warm highlights
        c.rgb *= mix(shadowTone, highTone, smoothstep(0.18, 0.78, lu));
        // r15 FILM GRAIN: live fine-grain dither — kills flat digital
        // gradients, reads as photographed (kept far below visibility
        // as 'noise')
        float gr = fract(sin(dot(vUv * 917.0 + vec2(uT * 0.31, uT * 0.17),
                                 vec2(12.9898, 78.233))) * 43758.5453);
        c.rgb += (gr - 0.5) * 0.018;
        gl_FragColor = c;
      }`,
  });
  composer.addPass(grade);
  // CAS-style SHARPEN (Phase 116): contrast-adaptive 5-tap sharpen as the
  // last color op — the 'broadcast crisp' finish. Adaptive weight backs off
  // on already-high-contrast pixels so it never rings or halos.
  const sharpen = new ShaderPass({
    uniforms: { tDiffuse: { value: null },
                uRes: { value: new THREE.Vector2(innerWidth, innerHeight) },
                uAmt: { value: 0.22 } },
    vertexShader: `varying vec2 vUv;
      void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform sampler2D tDiffuse; uniform vec2 uRes; uniform float uAmt;
      varying vec2 vUv;
      void main(){
        vec2 px = 1.0 / uRes;
        vec3 c = texture2D(tDiffuse, vUv).rgb;
        vec3 n = texture2D(tDiffuse, vUv + vec2(0.0, px.y)).rgb;
        vec3 s = texture2D(tDiffuse, vUv - vec2(0.0, px.y)).rgb;
        vec3 e = texture2D(tDiffuse, vUv + vec2(px.x, 0.0)).rgb;
        vec3 w = texture2D(tDiffuse, vUv - vec2(px.x, 0.0)).rgb;
        vec3 mn = min(c, min(min(n, s), min(e, w)));
        vec3 mx = max(c, max(max(n, s), max(e, w)));
        float contrast = clamp(dot(mx - mn, vec3(0.333)), 0.0, 1.0);
        float amt = uAmt * (1.0 - contrast);        // adaptive: back off on edges
        vec3 sharp = c * (1.0 + 4.0 * amt) - (n + s + e + w) * amt;
        gl_FragColor = vec4(clamp(sharp, 0.0, 4.0), 1.0);
      }`,
  });
  composer.addPass(sharpen);
  // CINEMATIC PASS (Phase 134/A): off during gameplay. When cine mode is
  // on: directional motion blur from camera velocity, lens focus falloff
  // toward frame edges, crushed cinematic grade + vignette + grain — the
  // 'footage, not gameplay' stack.
  const cinePass = new ShaderPass({
    uniforms: { tDiffuse: { value: null },
                uOn: { value: 0 },
                uDir: { value: new THREE.Vector2(1, 0) },
                uStr: { value: 0 },
                uTime: { value: 0 },
                uRes: { value: new THREE.Vector2(innerWidth, innerHeight) } },
    vertexShader: `varying vec2 vUv;
      void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform sampler2D tDiffuse; uniform float uOn;
      uniform vec2 uDir; uniform float uStr; uniform float uTime; uniform vec2 uRes;
      varying vec2 vUv;
      void main(){
        vec4 c = texture2D(tDiffuse, vUv);
        if (uOn < 0.5) { gl_FragColor = c; return; }
        // directional motion blur (camera velocity), 8 taps
        vec2 stepv = uDir * uStr / uRes;
        vec3 acc = c.rgb;
        for (int i = 1; i <= 4; i++) {
          acc += texture2D(tDiffuse, vUv + stepv * float(i)).rgb;
          acc += texture2D(tDiffuse, vUv - stepv * float(i)).rgb;
        }
        c.rgb = acc / 9.0;
        // lens focus falloff: soften toward frame edges (cheap bokeh feel)
        float ed = distance(vUv, vec2(0.5, 0.45));
        if (ed > 0.28) {
          vec2 bpx = 2.6 / uRes * smoothstep(0.28, 0.75, ed);
          vec3 bl = vec3(0.0);
          bl += texture2D(tDiffuse, vUv + vec2(bpx.x, 0.)).rgb;
          bl += texture2D(tDiffuse, vUv - vec2(bpx.x, 0.)).rgb;
          bl += texture2D(tDiffuse, vUv + vec2(0., bpx.y)).rgb;
          bl += texture2D(tDiffuse, vUv - vec2(0., bpx.y)).rgb;
          c.rgb = mix(c.rgb, bl * 0.25, smoothstep(0.28, 0.7, ed) * 0.8);
        }
        // cinematic grade: cool crush + lifted blacks + vignette + grain
        c.rgb = pow(max(c.rgb, vec3(0.0)), vec3(1.12));
        c.rgb = mix(c.rgb, c.rgb * vec3(0.92, 1.0, 1.10), 0.5);
        c.rgb += vec3(0.012, 0.014, 0.02);
        float vg = smoothstep(0.95, 0.35, distance(vUv, vec2(0.5)));
        c.rgb *= 0.55 + 0.45 * vg;
        float gn = fract(sin(dot(vUv * uRes + uTime, vec2(12.9898, 78.233))) * 43758.5453);
        c.rgb += (gn - 0.5) * 0.035;
        gl_FragColor = c;
      }`,
  });
  composer.addPass(cinePass);
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
  const _styleNight = ['night', 'dusk'].includes(SPEC.world.sky);
  const STYLE_CFG = {
    // TRUE CEL (Phase 131): luminance-banded flat fills + thick ink on
    // strong silhouettes only. celBands/inkTh/inkW drive the new path;
    // 'sketch' preserves the old fine-sobel recipe users liked.
    cartoon: { bands: 0, sat: 1.5, exposure: _styleNight ? 1.6 : 1.08, grain: 0,
               edge: 0, gamma: 1.0, celBands: 4,
               inkTh: _styleNight ? 0.14 : 0.22, inkW: 2.6 },
    sketch:  { bands: 5, sat: 1.35, exposure: 1.05, grain: 0, edge: 2.4, gamma: 1.0 },
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
                  celBands: { value: STYLE_CFG.celBands || 0 },
                  inkTh: { value: STYLE_CFG.inkTh || 0 },
                  inkW: { value: STYLE_CFG.inkW || 1.0 },
                  time: { value: 0 },
                  res: { value: new THREE.Vector2(innerWidth, innerHeight) } },
      vertexShader: `varying vec2 vUv;
        void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: `uniform sampler2D tDiffuse;
        uniform float bands; uniform float sat; uniform float exposure;
        uniform float grain; uniform float edge; uniform float time;
        uniform float gamma; uniform vec2 res; varying vec2 vUv;
        uniform float celBands; uniform float inkTh; uniform float inkW;
        float lum(vec2 uv){ return dot(texture2D(tDiffuse, uv).rgb, vec3(.299,.587,.114)); }
        void main(){
          vec4 c = texture2D(tDiffuse, vUv);
          c.rgb *= exposure;
          if (gamma != 1.0) {                     // midtone crush (horror dark)
            c.rgb = pow(max(c.rgb, vec3(0.0)), vec3(gamma));
          }
          if (celBands > 0.5) {                   // TRUE CEL: band the LIGHT,
            float cl = dot(c.rgb, vec3(.299,.587,.114));       // keep the hue
            float cb = floor(cl * celBands + 0.5) / celBands;
            // clamp the ratio — unclamped division CRUSHED dark scenes into
            // speckled black blobs (2026-07-28 night-fox report)
            c.rgb *= clamp((cb + 0.03) / max(cl, 0.05), 0.6, 1.8);
          }
          if (inkTh > 0.0) {                      // thick CLEAN ink: silhouettes
            vec2 pw = inkW / res;                 // only — threshold kills the
            float gx2 = lum(vUv + vec2(pw.x, 0.)) - lum(vUv - vec2(pw.x, 0.));
            float gy2 = lum(vUv + vec2(0., pw.y)) - lum(vUv - vec2(0., pw.y));
            float ink = step(inkTh, length(vec2(gx2, gy2)));
            c.rgb = mix(c.rgb, vec3(0.03, 0.03, 0.06), ink * 0.85);
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
    // OPT-IN ONLY (2026-07-27): auto wheel detection failed twice on real
    // assets — overlays now require explicit per-asset data (spec.player
    // .spin_wheels). A correct-looking car beats spinning wheels.
    if (!SPEC.player.spin_wheels) return;
    const low = pts.filter(q => q[1] < minY + h * 0.28);
    const BINS = 24, hist = new Array(BINS).fill(0);
    const bz = i => minZ + (i + 0.5) / BINS * len;
    for (const q of low) hist[Math.min(BINS - 1, Math.floor((q[2] - minZ) / len * BINS))]++;
    let fi = Math.floor(BINS * 0.6), ri = 0;
    for (let i = Math.floor(BINS * 0.55); i < BINS; i++) if (hist[i] > hist[fi]) fi = i;
    for (let i = 0; i < Math.floor(BINS * 0.45); i++) if (hist[i] > hist[ri]) ri = i;
    // CONFIDENCE GUARD (2026-07-27 London taxi): if the two detected axles
    // are not clearly separated (>42% of car length), the histogram found
    // noise, not wheels — mispositioned overlays look WORSE than none.
    if (Math.abs(bz(fi) - bz(ri)) < len * 0.42) return;
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
    if (speed > 3.2 && kcc.computedGrounded() && _dustT <= 0) {   // running on the ground
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
    if (VFX) VFX.step(dt, nt);          // element aura + trail follow the hero
    if (MINIMAP) MINIMAP.step(nt);      // live city map, view-direction wedge
    if (godray) {                       // sun screen position + eased strength
      _grV1.copy(sun.position).normalize().multiplyScalar(600).add(camera.position);
      _grV2.copy(_grV1).project(camera);
      const on2 = _grV2.z < 1 && _grV2.z > -1
        && Math.abs(_grV2.x) < 1.5 && Math.abs(_grV2.y) < 1.5;
      godray.uniforms.uSun.value.set((_grV2.x + 1) / 2, (_grV2.y + 1) / 2);
      const gb = { day: 0.3, sunset: 0.58, dusk: 0.46, overcast: 0.14 }[SPEC.world.sky] || 0.25;
      godray.uniforms.uStr.value +=
        ((on2 ? gb : 0) - godray.uniforms.uStr.value) * Math.min(1, dt * 3);
    }
    grade.uniforms.uT.value = performance.now() / 1000;   // live film grain

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
    // door teleports (moon plan 2.2)
    if (window.__doorway) {
      const dw = window.__doorway;
      dw.cool = Math.max(0, dw.cool - dt);
      if (!dw.cool) {
        const pp = body.translation();
        if (Math.hypot(pp.x - dw.out[0], pp.z - dw.out[1]) < 1.5) {
          body.setTranslation({ x: dw.inSpawn[0], y: 1.2, z: dw.inSpawn[1] }, true);
          body.setNextKinematicTranslation({ x: dw.inSpawn[0], y: 1.2, z: dw.inSpawn[1] });
          dw.cool = 1.2; sfx('step');
          popText('You step inside…', '#ffc46b');
        } else if (dw.exit
                   && Math.hypot(pp.x - dw.exit[0], pp.z - dw.exit[1]) < 1.2
                   && pp.x > SPEC.world.size_m) {
          const ox3 = dw.out[0], oz3 = dw.out[1] + 2.4;   // land CLEAR of the pad
          const oy2 = hAt(ox3, oz3) + 1.2;
          body.setTranslation({ x: ox3, y: oy2, z: oz3 }, true);
          body.setNextKinematicTranslation({ x: ox3, y: oy2, z: oz3 });
          dw.cool = 1.2; sfx('step');
          popText('Back outside', '#ffc46b');
        }
      }
    }
    // LIVING SUN (moon plan 2.3): the sun drifts ~2.4 deg/min — shadows
    // creep across the ground like real time passing. Skipped indoors.
    if (!INTERIOR && sun && SPEC.world.sky !== 'night') {
      // FIXED 2026-07-24: the rate multiplied by ELAPSED time each frame —
      // the sun accelerated into fast circles. Constant 0.0007 rad/s (~2.4
      // deg/min): shadows creep, they never spin.
      const sr = Math.hypot(sun.position.x, sun.position.z) || 60;
      const sb = Math.atan2(sun.position.z, sun.position.x) + 0.0007 * dt;
      sun.position.x = Math.cos(sb) * sr;
      sun.position.z = Math.sin(sb) * sr;
      if (csm) csm.lightDirection.copy(sun.position).multiplyScalar(-1).normalize();
    }
    if (playerObj) {
      rim.position.set(playerObj.position.x - _sunDirN.x * 14,
                       playerObj.position.y + 9,
                       playerObj.position.z - _sunDirN.z * 14);
      rim.target.position.copy(playerObj.position);
    }
    for (const hh of window.__headlights || []) {
      const hy = modelYaw;
      const hyo = hy + THREE.MathUtils.degToRad(P.yaw_offset_deg || 0);
      const off = window.__hlOff || { x: 0, z: 0 };
      const ox2 = off.x * Math.cos(hyo) + off.z * Math.sin(hyo);
      const oz2 = -off.x * Math.sin(hyo) + off.z * Math.cos(hyo);
      const hx = playerObj.position.x + ox2 + Math.sin(hy) * 2.4 + Math.cos(hy) * hh.side;
      const hz = playerObj.position.z + oz2 + Math.cos(hy) * 2.4 - Math.sin(hy) * hh.side;
      hh.hl.position.set(hx, playerObj.position.y + 0.85, hz);
      hh.hl.target.position.set(hx + Math.sin(hy) * 18, playerObj.position.y + 0.15,
                                hz + Math.cos(hy) * 18);
      hh.cone.position.copy(hh.hl.position);
      hh.cone.rotation.set(0, hy, 0);
    }
    for (const tv of window.__traffic || []) {
      const a2 = tv.pts[tv.seg], b2 = tv.pts[tv.seg + 1];
      const segL = Math.hypot(b2[0] - a2[0], b2[1] - a2[1]) || 1;
      tv.t += (tv.speed * dt * tv.dir) / segL;
      if (tv.t >= 1) { tv.seg++; tv.t = 0;
        if (tv.seg >= tv.pts.length - 1) { tv.dir = 1; tv.seg = 0; } }
      const tx2 = a2[0] + (b2[0] - a2[0]) * tv.t, tz2 = a2[1] + (b2[1] - a2[1]) * tv.t;
      tv.obj.position.set(tx2, hAt(tx2, tz2), tz2);
      tv.obj.rotation.y = Math.atan2(b2[0] - a2[0], b2[1] - a2[1]);
    }
    for (const pd of window.__peds || []) {
      const a3 = pd.pts[pd.seg], b3 = pd.pts[pd.seg + 1];
      if (!a3 || !b3) { pd.seg = 0; continue; }
      const segL = Math.hypot(b3[0] - a3[0], b3[1] - a3[1]) || 1;
      pd.t += (pd.speed * dt * pd.dir) / segL;
      if (pd.t >= 1) { pd.t = 0; pd.seg++;
        if (pd.seg >= pd.pts.length - 1) { pd.seg = pd.pts.length - 2; pd.dir = -1; } }
      else if (pd.t < 0) { pd.t = 1; pd.seg--;
        if (pd.seg < 0) { pd.seg = 0; pd.dir = 1; } }
      const hd5 = Math.atan2(b3[0] - a3[0], b3[1] - a3[1]);
      // walk the SIDEWALK: offset perpendicular from the road centerline
      const px3 = a3[0] + (b3[0] - a3[0]) * pd.t + Math.cos(hd5) * pd.side;
      const pz3 = a3[1] + (b3[1] - a3[1]) * pd.t - Math.sin(hd5) * pd.side;
      // r14 GLITCH FIX: at polyline corners the sidewalk offset JUMPS
      // sideways (visible teleport). Damp position + yaw toward targets.
      const wantY = hd5 + (pd.dir < 0 ? Math.PI : 0);
      if (!pd._init) {
        pd.obj.position.set(px3, hAt(px3, pz3), pz3);
        pd.obj.rotation.y = wantY; pd._init = true;
      } else {
        const k = Math.min(1, dt * 5);
        pd.obj.position.x += (px3 - pd.obj.position.x) * k;
        pd.obj.position.z += (pz3 - pd.obj.position.z) * k;
        pd.obj.position.y = hAt(pd.obj.position.x, pd.obj.position.z);
        let dy = wantY - pd.obj.rotation.y;
        while (dy > Math.PI) dy -= Math.PI * 2;
        while (dy < -Math.PI) dy += Math.PI * 2;
        pd.obj.rotation.y += dy * Math.min(1, dt * 6);
      }
      if (pd.mixer) pd.mixer.update(dt);
    }
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
            addXP(6);
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
      camera.up.set(0, 1, 0);              // never let lookAt roll-flip
      const cd = SPEC.camera.distance_m * camZoom * (inspectOn ? 1.5 : 1);
      let cx = fX + Math.sin(yaw) * Math.cos(pitch) * cd;     // camera BEHIND
      let cz = fZ + Math.cos(yaw) * Math.cos(pitch) * cd;     // (W walks away)
      let cy = fY + Math.sin(pitch) * cd + SPEC.camera.height_m * 0.4;
      // INTERIOR (2026-07-23): never rise above the ceiling — the camera
      // outside the roof showed a void where the player should be
      if (INTERIOR) cy = Math.min(cy, (INTERIOR.wall_h || 4.0) * (INTERIOR.floors || 1) - 0.35);
      if (window.__doorway && fX > SPEC.world.size_m) {
        cy = Math.min(cy, window.__doorway.wallH - 0.35);
      }
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
    if (cineOn) {                        // CINEMATIC CAMERA override
      cineT += dt;
      // PERSISTENT (2026-07-29): cinematic POV is the hyper-real view — it
      // stays on until the player toggles it off (V / 🎥). No auto-timeout.
      const cp = playerObj.position;
      if ((P.mode || 'walk') === 'drive') {
        // FPV chase: low, off-shoulder, banking with lateral velocity
        const back = 6.5 + Math.sin(cineT * 0.35) * 1.5;
        const side = Math.sin(cineT * 0.22) * 4.2;
        const cyaw = modelYaw;
        camera.position.set(
          cp.x - Math.sin(cyaw) * back + Math.cos(cyaw) * side,
          cp.y + 1.1 + Math.sin(cineT * 0.5) * 0.5,
          cp.z - Math.cos(cyaw) * back - Math.sin(cyaw) * side);
        camera.lookAt(cp.x + Math.sin(cyaw) * 6, cp.y + 0.6, cp.z + Math.cos(cyaw) * 6);
        camera.rotation.z = THREE.MathUtils.clamp(-side * 0.02, -0.12, 0.12);
      } else {
        // hero orbit: slow low dolly circling the subject
        const oa = cineT * 0.28;
        const orad = 4.6 + Math.sin(cineT * 0.4) * 1.2;
        camera.position.set(cp.x + Math.cos(oa) * orad,
                            cp.y + 1.3 + Math.sin(cineT * 0.3) * 0.7,
                            cp.z + Math.sin(oa) * orad);
        camera.lookAt(cp.x, cp.y + P.height_m * 0.55, cp.z);
      }
      // SAFETY (audit): the choreographed camera obeys the same physics as
      // the gameplay camera — pull in front of any wall, stay under
      // interior ceilings. No clipping through castles or city blocks.
      if (INTERIOR) {
        camera.position.y = Math.min(camera.position.y,
          (INTERIOR.wall_h || 4.0) * (INTERIOR.floors || 1) - 0.4);
      }
      {
        const hx2 = cp.x, hy2 = cp.y + (P.height_m || 1) * 0.6, hz2 = cp.z;
        let dx3 = camera.position.x - hx2, dy3 = camera.position.y - hy2, dz3 = camera.position.z - hz2;
        const dl3 = Math.hypot(dx3, dy3, dz3) || 1;
        dx3 /= dl3; dy3 /= dl3; dz3 /= dl3;
        const ray3 = new RAPIER.Ray({ x: hx2, y: hy2, z: hz2 }, { x: dx3, y: dy3, z: dz3 });
        const hit3 = world.castRay(ray3, dl3, true, undefined, undefined, collider, body);
        if (hit3 && hit3.timeOfImpact > 0.01) {
          const t3 = Math.max(hit3.timeOfImpact - 0.3, 0.5);
          camera.position.set(hx2 + dx3 * t3, hy2 + dy3 * t3, hz2 + dz3 * t3);
          camera.lookAt(cp.x, cp.y + (P.height_m || 1) * 0.55, cp.z);
        }
      }
      // motion-blur direction/strength from camera velocity (view space)
      const cvel = camera.position.clone().sub(_cinePrevCam);
      const lv = cvel.applyQuaternion(camera.quaternion.clone().invert());
      // 2026-07-29 'too much': blur is a seasoning — cap ~9px total reach
      const sp2 = Math.min(lv.length() / Math.max(dt, 1e-3), 16);
      cinePass.uniforms.uDir.value.set(lv.x, -lv.y).normalize();
      cinePass.uniforms.uStr.value = sp2 * 0.15;
      cinePass.uniforms.uTime.value = performance.now() / 1000;
    }
    _cinePrevCam.copy(camera.position);
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
    if (_legacySSAO) renderDepthPrepass();   // retired: N8AO owns depth now
    if (csm) {
      csm.update();
      window.__csmFrame = (window.__csmFrame || 0) + 1;
      if (window.__csmFrame % 60 === 1) window.__csmPatch();  // catch spawns
    }
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
    n8ao.setSize(innerWidth, innerHeight);
    if (csm) csm.updateFrustums();
    sharpen.uniforms.uRes.value.set(innerWidth, innerHeight);
    cinePass.uniforms.uRes.value.set(innerWidth, innerHeight);
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
