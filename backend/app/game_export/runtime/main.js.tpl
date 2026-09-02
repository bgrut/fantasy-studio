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

// ── SILHOUETTE PACK (2026-08-25): the seed decides the SHAPES ──────────
// Palettes made every world light differently; this makes them GROW
// differently. One seeded identity — tree archetype, proportions, mountain
// jaggedness — read by every generator that stamps the horizon, so two
// valleys are never planted with the same tree. Biome words nudge the
// archetype (deserts lean dead wood, snow leans pine); the seed decides
// within the nudge. Top-level const: everything below main() can read it.
const SIL = (() => {
  const r = mulberry32(((SPEC.seed || 1) >>> 0) + 8181);
  const wname = ((SPEC.world || {}).name || '') + ' ' + ((SPEC.world || {}).sky || '');
  const snowy = (SPEC.world || {}).weather === 'snow' || /arctic/.test(wname);
  let arch;
  // an explicit tree word in the prompt outranks every roll: the pack's
  // first field test planted dead snags in "a pine forest" (2026-08-25)
  const flora = ((SPEC.world || {}).flora || '');
  if (/pine|fir|spruce|conifer/.test(flora)) arch = 'pine';
  else if (/birch|oak|willow|maple|jungle/.test(flora)) arch = 'broadleaf';
  else if (/palm|cypress/.test(flora)) arch = 'cypress';
  else if (/dead|cactus/.test(flora)) arch = 'dead';
  else if (/desert|canyon|mars|volcano/.test(wname)) arch = r() < 0.55 ? 'dead' : 'cypress';
  else if (snowy) arch = r() < 0.8 ? 'pine' : 'dead';
  else arch = ['pine', 'broadleaf', 'cypress', 'pine', 'broadleaf', 'dead'][Math.floor(r() * 6)];
  const out = {
    arch,
    trunkH: 2.0 + r() * 1.6,
    tiers: 2 + Math.floor(r() * 3),        // pine cone stacks
    spread: 0.8 + r() * 0.7,               // canopy width multiplier
    squash: 0.72 + r() * 0.6,              // broadleaf lobe flattening
    gnarl: r(),                            // dead-branch chaos
    mtnJag: 0.10 + r() * 0.26,             // ridge displacement (was 0.22 fixed)
    mtnSeg: 6 + Math.floor(r() * 6),       // ridge facet count (was 7-10)
  };
  window.__sil = out;          // harness: silhouette identity is assertable
  return out;
})();

async function main() {
  await RAPIER.init();
  // ── WORLD PALETTE (2026-08-25): the preset is a BASE, not a verdict ──
  // Two hundred prompts used to produce two hundred worlds lit by seven
  // hardcoded rigs — 'day' was always the same sun at [40,80,30]. Now the
  // extractor may author a color script, and underneath it the seed jitters
  // azimuth and hue so even two builds of one prompt light differently.
  // Every downstream consumer already reads `pal`, so this one intercept is
  // the entire system.
  const pal = (() => {
    const base = Object.assign({}, SKY[SPEC.world.sky] || SKY.day);
    const PW = SPEC.world.palette || {};
    const hx = v => (typeof v === 'string' && /^#?[0-9a-fA-F]{6}$/.test(v))
      ? parseInt(v.replace('#', ''), 16) : null;
    if (hx(PW.sky) !== null) base.sky = hx(PW.sky);
    if (hx(PW.fog) !== null) base.fog = hx(PW.fog);
    if (hx(PW.sun_color) !== null) base.sunCol = hx(PW.sun_color);
    if (PW.sun_intensity > 0) base.sun = PW.sun_intensity;
    if (PW.ambient > 0) base.amb = PW.ambient;
    if (PW.exposure > 0) base.exp = PW.exposure;
    // sun direction: authored angles win; otherwise jitter the preset's
    // azimuth +/-40deg and elevation +/-18% — the difference between two
    // "misty dawn" worlds is which shoulder the light falls over
    const rj = mulberry32((SPEC.seed || 1) + 3131);
    const bp = base.sunPos;
    const bEl = Math.asin(Math.max(0.05, Math.min(1, bp[1] / Math.hypot(bp[0], bp[1], bp[2]))));
    const bAz = Math.atan2(bp[2], bp[0]);
    const az = PW.sun_azimuth_deg >= 0 ? PW.sun_azimuth_deg * Math.PI / 180
             : bAz + (rj() - 0.5) * 1.4;
    const el = PW.sun_elevation_deg >= 4 ? PW.sun_elevation_deg * Math.PI / 180
             : Math.max(0.08, bEl * (0.82 + rj() * 0.36));
    const R = 95;
    base.sunPos = [Math.cos(el) * Math.cos(az) * R, Math.sin(el) * R,
                   Math.cos(el) * Math.sin(az) * R];
    // unauthored worlds still drift in hue: +/-0.035 on sky and fog together,
    // so the pair stays a family instead of splitting
    if (hx(PW.sky) === null && hx(PW.fog) === null) {
      const dh = (rj() - 0.5) * 0.07;
      for (const k of ['sky', 'fog']) {
        const c = new THREE.Color(base[k]);
        c.offsetHSL(dh, (rj() - 0.5) * 0.06, 0);
        base[k] = c.getHex();
      }
    }
    window.__accent = hx(PW.accent);      // mission color, read by beacon+ring
    return base;
  })();

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

  // ── CONTINUOUS AUDIO (2026-08-07) ────────────────────────────────────
  // sfx() covers one-shots. What a street actually sounds like is
  // CONTINUOUS: an engine whose pitch tracks your right foot, footsteps at
  // your own cadence, tyres complaining in a hard turn, and a bed of distant
  // traffic that never quite stops. A silent city reads as a tech demo no
  // matter how good the facades are.
  //
  // Everything is SYNTHESISED — oscillators and shaped noise, no audio files
  // at all. That keeps the hard constraint (local, free, commercially safe)
  // trivially satisfied and adds nothing to the export payload.
  let _audPX = 0, _audPZ = 0;      // last frame's player position
  const AUD = { ready: false, eng: null, engF: null, engG: null,
                amb: null, ambG: null, scrubG: null, walked: 0 };
  function audioNoiseBuffer(sec) {
    const N = Math.floor(actx.sampleRate * sec);
    const buf = actx.createBuffer(1, N, actx.sampleRate);
    const d = buf.getChannelData(0);
    // brown-ish noise: integrated white, which sits far lower than white and
    // is what distant traffic and tyre roar actually sound like
    let last = 0;
    for (let i = 0; i < N; i++) {
      const w = Math.random() * 2 - 1;
      last = (last + 0.02 * w) / 1.02;
      d[i] = last * 3.5;
    }
    return buf;
  }
  function audioInit() {
    // must follow a user gesture, so this is called from the START button
    if (AUD.ready || sfxMuted) return;
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      if (!actx) actx = new AC();
      if (actx.state === 'suspended') actx.resume();
      // ENGINE: two detuned saws through a lowpass. One oscillator is a
      // buzzer; the beat between two is what reads as a motor.
      AUD.engG = actx.createGain(); AUD.engG.gain.value = 0;
      AUD.engF = actx.createBiquadFilter();
      AUD.engF.type = 'lowpass'; AUD.engF.frequency.value = 340; AUD.engF.Q.value = 6;
      AUD.eng = [];
      for (const det of [0, 7]) {
        const o = actx.createOscillator();
        o.type = 'sawtooth'; o.frequency.value = 42; o.detune.value = det;
        o.connect(AUD.engF); o.start();
        AUD.eng.push(o);
      }
      AUD.engF.connect(AUD.engG); AUD.engG.connect(actx.destination);
      // TYRE SCRUB: noise band that only opens up under lateral load
      const nb = audioNoiseBuffer(2);
      const scr = actx.createBufferSource();
      scr.buffer = nb; scr.loop = true;
      const scrF = actx.createBiquadFilter();
      scrF.type = 'bandpass'; scrF.frequency.value = 1600; scrF.Q.value = 1.2;
      AUD.scrubG = actx.createGain(); AUD.scrubG.gain.value = 0;
      scr.connect(scrF); scrF.connect(AUD.scrubG);
      AUD.scrubG.connect(actx.destination); scr.start();
      // CITY BED: the same noise, filtered right down — the hum you stop
      // hearing until it is missing
      const amb = actx.createBufferSource();
      amb.buffer = nb; amb.loop = true;
      const ambF = actx.createBiquadFilter();
      ambF.type = 'lowpass'; ambF.frequency.value = 420;
      AUD.ambG = actx.createGain();
      AUD.ambG.gain.value = (OSM && OSM.roads && OSM.roads.length) ? 0.055 : 0.0;
      amb.connect(ambF); ambF.connect(AUD.ambG);
      AUD.ambG.connect(actx.destination); amb.start();
      AUD.amb = amb;
      AUD.ready = true;
      // same reason window.__game exists: the shot harness has to be able
      // to assert on the audio graph, and "I heard it" is not a check
      window.__audio = () => ({ ready: AUD.ready, state: actx.state,
        engineHz: AUD.eng[0].frequency.value,
        engineGain: +AUD.engG.gain.value.toFixed(4),
        scrubGain: +AUD.scrubG.gain.value.toFixed(4),
        ambGain: +AUD.ambG.gain.value.toFixed(4) });
    } catch (e) { /* never let audio break the game */ }
  }
  function audioStep(surface) {
    if (!AUD.ready || sfxMuted) return;
    try {
      const src = actx.createBufferSource();
      src.buffer = audioNoiseBuffer(0.12);
      const f = actx.createBiquadFilter();
      f.type = 'bandpass';
      f.frequency.value = surface === 'road' ? 900 : 620;   // asphalt vs slab
      f.Q.value = 0.9;
      const g = actx.createGain();
      const t0 = actx.currentTime;
      g.gain.setValueAtTime(0.10, t0);
      g.gain.exponentialRampToValueAtTime(0.0007, t0 + 0.11);
      src.connect(f); f.connect(g); g.connect(actx.destination);
      src.start(t0); src.stop(t0 + 0.13);
    } catch (e) { /* ignore */ }
  }
  function audioFrame(dt, moved) {
    if (!AUD.ready || sfxMuted) return;
    try {
      const t = actx.currentTime;
      if (DRIVING) {
        const kmh = Math.hypot(carVX, carVZ) * 3.6;
        // fundamental climbs with road speed but never idles below a rumble
        const f0 = 42 + Math.min(kmh, 150) * 0.72;
        for (const o of AUD.eng) o.frequency.setTargetAtTime(f0, t, 0.08);
        AUD.engF.frequency.setTargetAtTime(320 + f0 * 7, t, 0.08);
        AUD.engG.gain.setTargetAtTime(0.055 + Math.min(kmh / 150, 1) * 0.05, t, 0.1);
        // Real tyre noise is about SLIP ANGLE, not steering input: the
        // component of world velocity running across the nose rather than
        // along it. That is already computed by the drift model, so the
        // scrub rises exactly when the car is actually sliding.
        const fx9 = Math.sin(modelYaw), fz9 = Math.cos(modelYaw);
        const lat = Math.min(Math.abs(carVX * fz9 - carVZ * fx9) / 7, 1);
        AUD.scrubG.gain.setTargetAtTime(lat * 0.06, t, 0.06);
        AUD.walked = 0;
      } else {
        AUD.engG.gain.setTargetAtTime(0, t, 0.15);
        AUD.scrubG.gain.setTargetAtTime(0, t, 0.1);
        // a step every ~0.78m of ground covered, so cadence follows the
        // player's real speed instead of a fixed timer
        AUD.walked += moved;
        if (AUD.walked > 0.78) {
          AUD.walked = 0;
          audioStep(typeof _onRoad === 'function' ? 'road' : 'slab');
        }
      }
    } catch (e) { /* ignore */ }
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
  // ── STYLE IDENTITY (2026-08-25): the UI is part of the art direction ─
  // A style was a post-shader — the same HUD font, the same rounded chrome,
  // whether the game was a watercolor cartoon or a horror crawl. The frame
  // changed and the FRAME AROUND THE FRAME never did, which is half of why
  // styles read as filters. body gets a style class and one injected sheet;
  // !important is deliberate — the HUD is built with inline cssText, and a
  // stylesheet only outranks inline styles when it says so.
  // (SPEC.style read directly: the STYLE const lives thousands of lines
  // down and reading it here would be TRAP 1.)
  {
    const _st = SPEC.style || 'default';
    document.body.classList.add('style-' + _st);
    const FONTS = {
      cartoon: '"Comic Sans MS", "Chalkboard SE", "Segoe UI", cursive',
      sketch: '"Segoe Print", "Bradley Hand", cursive',
      anime: '"Trebuchet MS", "Segoe UI", sans-serif',
      horror: 'Georgia, "Times New Roman", serif',
      pixel: '"Courier New", monospace',
    };
    const css = [];
    if (FONTS[_st]) {
      css.push('body.style-' + _st + ', body.style-' + _st + ' * '
        + '{ font-family: ' + FONTS[_st] + ' !important; }');
    }
    if (_st === 'cartoon') {
      css.push('body.style-cartoon #hud h1 { color:#ffde59 !important; '
        + '-webkit-text-stroke: 1.5px #4a2c00; letter-spacing: 0.5px; }');
      css.push('body.style-cartoon #startbtn, body.style-cartoon .card '
        + '{ border-radius: 26px !important; }');
      css.push('body.style-cartoon #hearts { font-size: 26px !important; }');
    } else if (_st === 'horror') {
      css.push('body.style-horror #hud h1 { color:#b01818 !important; '
        + 'letter-spacing: 4px; text-shadow: 0 0 14px #600 !important; }');
      css.push('body.style-horror #startbtn, body.style-horror .card '
        + '{ border-radius: 0 !important; }');
      css.push('body.style-horror #startbtn { background:#7a1010 !important; '
        + 'color:#e8dcc8 !important; }');
    } else if (_st === 'anime') {
      css.push('body.style-anime #hud h1 { color:#ff7ab8 !important; '
        + '-webkit-text-stroke: 1px #fff; }');
    } else if (_st === 'pixel') {
      css.push('body.style-pixel canvas { image-rendering: pixelated !important; }');
      css.push('body.style-pixel #hud h1 { text-transform: uppercase; '
        + 'letter-spacing: 2px; }');
    }
    if (css.length) {
      const el = document.createElement('style');
      el.textContent = css.join('\n');
      document.head.appendChild(el);
    }
    // pixel style earns its name: a QUARTER-res framebuffer stretched with
    // nearest-neighbor IS the aesthetic — banding alone never was
    if (_st === 'pixel') QCFG.dpr = Math.max(0.32, QCFG.dpr * 0.38);
  }
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
  renderer.toneMappingExposure = (pal.exp || 0.75)
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
      // NEUTRAL EXPOSURE (2026-08-05): panoramas are brightness-normalised
      // at bake time now, so the blanket +18% lift that blew out bright
      // photos is gone. One neutral setting works for every image.
      scene.backgroundIntensity = 1.0;
      if ('environmentIntensity' in scene) {
        scene.environmentIntensity = Math.max(scene.environmentIntensity, 0.7);
      }
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
  // DARK WORLDS SKIP THE ATMOSPHERE (2026-08-25). 'space' had no cfg entry
  // here, so it fell through to the DAY atmosphere — turbidity 6, sun at 35
  // degrees — and every starless-night prompt got a pale blue daytime dome
  // behind its dark fog. Night already knew the answer: flat palette
  // background + starfield. Space joins it, and so does any AUTHORED palette
  // whose sky is genuinely dark — a committed #0a0618 must never be handed
  // to a shader whose whole job is simulating daylight scattering.
  const _palLum = (() => { const c = new THREE.Color(pal.sky);
    return 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b; })();
  const _darkWorld = SPEC.world.sky === 'night' || SPEC.world.sky === 'space'
    || (!!SPEC.world.palette && _palLum < 0.22);
  window.__darkWorld = _darkWorld;
  if (!_darkWorld) {
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
        // A COMMITTED palette must not be washed toward white by its own
        // ambient light: the synthwave test came out pale lavender because
        // this env gradient lightened a #0a0618 sky by 20% white and then
        // LIT the whole world with it. Authored palettes blend sky->fog
        // (their own family); preset skies keep the old lift.
        es2.background = SPEC.world.palette
          ? new THREE.Color(pal.sky).lerp(new THREE.Color(pal.fog), 0.5)
          : new THREE.Color(pal.sky).lerp(new THREE.Color(0xffffff), 0.2);
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
      // the auto-texture sweep was draping 'stone' slabs over these cones'
      // 0-1 UVs — a 300m ridge wearing a 3m slab photo stretched 100x is
      // the single most "2003" surface in every valley shot. Sculpted
      // low-poly + vertex colour + distance fog is the intended look.
      mmat.userData.noAutoTex = true;
      const ring = new THREE.Group();
      const NPK = 11;
      for (let i = 0; i < NPK; i++) {
        const a = (i / NPK) * Math.PI * 2 + rngM() * 0.35;
        const dist = gsizeM * (0.78 + rngM() * 0.28);
        const hgt = gsizeM * (0.10 + rngM() * 0.14);
        const rad = hgt * (1.5 + rngM() * 0.9);
        const geo = new THREE.ConeGeometry(rad, hgt, SIL.mtnSeg + Math.floor(rngM() * 3), 3);
        const posA = geo.attributes.position;
        const col = new Float32Array(posA.count * 3);
        for (let v = 0; v < posA.count; v++) {
          const vx = posA.getX(v), vy = posA.getY(v), vz = posA.getZ(v);
          const n = Math.sin(vx * 0.9 + i * 7) * Math.cos(vz * 1.1 + i * 3);
          posA.setX(v, vx * (1 + n * SIL.mtnJag));
          posA.setZ(v, vz * (1 + n * SIL.mtnJag));
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
      // NIGHT CITY WALLS WERE UNLIT (2026-08-05). At 0.4 the flat-sky env gave
      // vertical surfaces almost nothing, and an OSM city is nearly all
      // vertical surface: facades rendered as black voids with the emissive
      // windows floating on top, which is what "the buildings feel geometric"
      // actually looked like. No facade texture, normal map or cornice can
      // show through zero light. A real night street is lit by skyglow and
      // bounce, so the city gets a much stronger env; enclosed levels keep
      // 0.4 because their walls are lit by their own lamps and a bright env
      // flattens them. Read straight off SPEC, not the OSM const — that is
      // declared ~100 lines below and would be in its temporal dead zone.
      const _isCity = !!(SPEC.world.level && SPEC.world.level.osm);
      // 2.4 chosen from a live sweep against the noir grade, not guessed: it
      // is the point where brick, stone and glass each read as their own
      // material and the window reveals cast, while the street still reads as
      // night. The grade's exposure is deliberately left alone.
      if ('environmentIntensity' in scene) scene.environmentIntensity = _isCity ? 2.4 : 0.4;
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
  // ground bounce joins the palette family — a fixed moss-grey underside
  // is why authored worlds still lit like the default one from below
  const hemi = new THREE.HemisphereLight(pal.sky,
    SPEC.world.palette ? new THREE.Color(pal.fog).multiplyScalar(0.45).getHex()
                       : 0x3a3f35,
    pal.amb * 0.85);
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
  // ENTERABLE VENUES (2026-08-05): the multi-building city heist. One entry
  // per building — {plan, door:[x,z], ox, label}. The legacy single
  // `enterable` is just a one-element list with no explicit offset.
  // Declared UP here with the other level constants: the OSM building pass,
  // the NPC spawner and the minimap all read it hundreds of lines earlier
  // than the door builder runs, and a `const` read inside its temporal dead
  // zone takes the whole runtime down with it (three times, one morning).
  const ENTERABLES = (LVL && LVL.enterables && LVL.enterables.length)
    ? LVL.enterables
    : ((LVL && LVL.enterable) ? [LVL.enterable] : []);
  // declared HERE, not beside the combat globals: the start-screen controls
  // line reads it long before those run, and a `const` in the temporal dead
  // zone takes the whole runtime down with it
  const HAS_GUARDS = (SPEC.entities || []).some(e => e.behavior === 'guard');
  // STEAL A CAR (2026-08-05): walking and driving were two separate games —
  // a heist could end by "escaping to the getaway car" you were never able to
  // get into. `DRIVING` is the RUNTIME half of SPEC.player.mode: the physics
  // branch reads `DRIVE || DRIVING`, so the arcade car model (and its lateral
  // grip-bleed drift) is reused verbatim rather than forked.
  // Declared UP here with the other level constants: the minimap closure and
  // the E-key handler are both built hundreds of lines earlier than the car
  // system, and a `let` read inside its temporal dead zone takes the whole
  // runtime down (three times, one morning — see ENTERABLES above).
  let DRIVING = false;
  window.__cars = [];        // parked, drivable — the minimap reads it lazily
  window.__inCar = null;
  // A BURGLAR STARTS AT THE DOOR (2026-08-05): interiors spawned the player
  // dead-centre in the entry hall — in the open, in every patrol's sightline,
  // with nothing to duck behind. Start at the near wall by the doorway, the
  // way someone who just picked the lock would actually be standing.
  // Declared up HERE with the other level constants, not down by the physics
  // body: NPC spawning reads it ~1700 lines earlier, and a `const` in the
  // temporal dead zone takes the whole runtime down.
  const _sp = { x: 0, z: 0 };
  if (INTERIOR && INTERIOR.rooms && INTERIOR.rooms.length) {
    const h0 = INTERIOR.rooms[0];
    _sp.x = h0[0];
    _sp.z = h0[1] - h0[3] / 2 + 3.0;   // clear of the wall: at 1.8 m the
                                       // capsule was embedded and immovable
  }
  // wall segments [x1,z1,x2,z2] that block a guard's line of sight
  const SIGHT = [];
  function canSee(ax, az, bx, bz) {
    for (const [x1, z1, x2, z2] of SIGHT) {
      // segment/segment intersection — eye ray vs wall
      const d1x = bx - ax, d1z = bz - az, d2x = x2 - x1, d2z = z2 - z1;
      const den = d1x * d2z - d1z * d2x;
      if (Math.abs(den) < 1e-9) continue;            // parallel
      const s = ((x1 - ax) * d2z - (z1 - az) * d2x) / den;
      const u = ((x1 - ax) * d1z - (z1 - az) * d1x) / den;
      if (s > 0.02 && s < 0.98 && u >= 0 && u <= 1) return false;
    }
    return true;
  }
  const gcol = new THREE.Color(...SPEC.world.ground_color);
  {
    // SATURATION FLOOR (Phase 76): LLM ground colors trend pastel — real
    // grass/soil is richer. Only colored grounds are lifted (snow/sand with
    // near-zero saturation stay untouched).
    const _h = {}; gcol.getHSL(_h);
    if (_h.s > 0.08 && _h.s < 0.3) gcol.setHSL(_h.h, 0.34, Math.min(_h.l, 0.42));
  }
  // 2048 for ANY level (2026-08-25): nature worlds ran 1024 over 220m+ —
  // ~4.7 px/m, the giant green blur behind every 'looks like 2003' read.
  const TEXN = LVL ? 2048 : 256;
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
  // fine speckle (pebbles / grass tufts) — but not on a lake bed, where
  // gcol-green flecks read as drowned grass
  for (let i = 0; i < TEXN * 26; i++) {
    const sh = (rngTex() - 0.5) * 0.22;
    const c2 = gcol.clone().offsetHSL(0, (rngTex() - 0.5) * 0.06, sh * 0.5);
    const px9 = rngTex() * TEXN, py9 = rngTex() * TEXN;
    if (LVL && LVL.regions) {
      const nR9 = LVL.grid_n;
      const id9 = LVL.regions.grid[
        Math.min(nR9 - 1, Math.floor(py9 / TEXN * nR9)) * nR9
        + Math.min(nR9 - 1, Math.floor(px9 / TEXN * nR9))];
      if (id9 >= 0 && LVL.regions.palette[id9].kind === 'water') continue;
    }
    ctx.fillStyle = '#' + c2.getHexString();
    ctx.fillRect(px9, py9, 1 + rngTex() * 2, 1 + rngTex() * 2);
  }
  // ── SEMANTIC LAYOUT (2026-08-25, phase 2): the region grid the level
  // planner rasterized. One lookup serves the ground paint here, the
  // vegetation gates below, and anything else that wants to know what kind
  // of place a point is.
  const regionAt = (x, z) => {
    const R = LVL && LVL.regions;
    if (!R) return null;
    const nR = LVL.grid_n;
    const j = Math.max(0, Math.min(nR - 1, Math.round((x / gsize + 0.5) * (nR - 1))));
    const i = Math.max(0, Math.min(nR - 1, Math.round((z / gsize + 0.5) * (nR - 1))));
    const id = R.grid[i * nR + j];
    if (id < 0) return null;
    return { kind: R.palette[id].kind, w: R.w[i * nR + j] };
  };
  window.__regionAt = regionAt;
  if (!OSM && LVL && LVL.regions) {
    // painted as soft radial blobs, one per claimed cell — they overlap into
    // organic patches and the speckle pass after this keeps the grain on top
    const RCOL = {
      water: new THREE.Color(0x2b4a45),          // the bed seen through water
      forest: gcol.clone().offsetHSL(0.015, 0.06, -0.065),
      village: gcol.clone().lerp(new THREE.Color(0x77664a), 0.72),
      meadow: gcol.clone().offsetHSL(-0.01, 0.05, 0.045),
      rock: new THREE.Color(0x86837a),
      sand: new THREE.Color(0xc7b28a),
      hill: gcol.clone().lerp(new THREE.Color(0x8b8474), 0.55),
    };
    const nR = LVL.grid_n, cell = TEXN / nR;
    for (let i = 0; i < nR; i++) {
      for (let j = 0; j < nR; j++) {
        const id = LVL.regions.grid[i * nR + j];
        if (id < 0) continue;
        const col = RCOL[LVL.regions.palette[id].kind];
        if (!col) continue;
        const w = LVL.regions.w[i * nR + j];
        const cx = (j + 0.5) * cell, cy = (i + 0.5) * cell, r = cell * 1.45;
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
        const hex = '#' + col.getHexString();
        g.addColorStop(0, hex + Math.round(Math.min(0.92, w) * 255)
          .toString(16).padStart(2, '0'));
        g.addColorStop(1, hex + '00');
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, 7); ctx.fill();
      }
    }
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
    // DETAIL ALBEDO (2026-08-25): the painted canvas carries the LAYOUT
    // (regions, trails, roads) but at map scale it can never carry GRAIN.
    // A real tiled texture sampled in world metres supplies it — the same
    // texel-density lesson the facades learned, applied to the floor. The
    // family follows the ground colour, so snow worlds get snow grain and
    // deserts get sand, without a new spec field.
    let detailTex = null;
    if (!OSM) {
      const _dh = {}; gcol.getHSL(_dh);
      const _dn = SPEC.world.weather === 'snow' ? 'snow'
        : (_dh.s < 0.10 ? 'stone'
        : (_dh.h > 0.16 && _dh.h < 0.45 ? 'grass'
        : (_dh.l > 0.55 ? 'sand' : 'soil')));
      detailTex = new THREE.TextureLoader().load('textures/' + _dn + '.jpg');
      detailTex.wrapS = detailTex.wrapT = THREE.RepeatWrapping;
      detailTex.colorSpace = THREE.SRGBColorSpace;
      detailTex.anisotropy = 8;
    }
    gmat.onBeforeCompile = sh => {
      sh.uniforms.macroMap = { value: macroTex };
      sh.uniforms.macroSize = { value: gsize };
      sh.uniforms.detailMap = { value: detailTex };
      sh.uniforms.detailOn = { value: detailTex ? 1.0 : 0.0 };
      sh.vertexShader = sh.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vMacroW;')
        .replace('#include <worldpos_vertex>',
                 '#include <worldpos_vertex>\nvMacroW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
      sh.fragmentShader = sh.fragmentShader
        .replace('#include <common>',
                 '#include <common>\nuniform sampler2D macroMap; uniform float macroSize; varying vec3 vMacroW;')
        .replace('#include <common>\nuniform sampler2D macroMap;',
                 '#include <common>\nuniform sampler2D detailMap; uniform float detailOn; uniform sampler2D macroMap;')
        .replace('#include <map_fragment>',
                 `#include <map_fragment>
                  { vec3 m = texture2D(macroMap, clamp(vMacroW.xz / macroSize + 0.5, 0.0, 1.0)).rgb;
                    diffuseColor.rgb *= mix(vec3(1.0), m * 2.0, 0.5);
                    if (detailOn > 0.5) {
                      // two octaves at 2.7m and 13m: grain up close, patchiness
                      // at distance, and the mismatch hides both tilings
                      vec3 d1 = texture2D(detailMap, vMacroW.xz / 2.7).rgb;
                      vec3 d2 = texture2D(detailMap, vMacroW.xz / 13.0).rgb;
                      vec3 dt = mix(d1, d2, 0.42);
                      diffuseColor.rgb *= mix(vec3(1.0), dt * 1.9, 0.62);
                    } }`);
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
      const _acc = window.__accent;
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(1.5, 0.09, 10, 40),
        new THREE.MeshStandardMaterial({ color: _acc || 0xb9a0ff,
          emissive: _acc || 0x7c5cff, emissiveIntensity: 2.2 }));
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
  // ── A CHARACTER MUST NOT BE A WHITE CUTOUT (2026-08-07 r2) ────────────
  // Two defects, both of which end in the same flat white silhouette:
  //   * glTF defaults metallicFactor to 1.0, and a baked character that
  //     never wrote a metallicRoughness texture inherits it. At metalness 1
  //     the albedo contributes no diffuse at all.
  //   * some baked bodies carry a material with NO map, left at pure white.
  //     Any night-grade emissive lift then has nothing but white to lift.
  // Fixing this inside prepModel was not enough: material and texture
  // assignment finishes AFTER the loader callback in some GLBs, so the pass
  // ran against materials that were still defaults and the correction was
  // silently undone. deChalk is therefore re-run once the scene has settled.
  function deChalk(root) {
    if (!root) return;
    root.traverse(o => {
      if (!o.isMesh || !o.material) return;
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        if (!m || m.metalness === undefined) continue;
        // PEOPLE ARE DIELECTRIC. Every baked character here ships a
        // metallicRoughness TEXTURE and no metallicFactor, so glTF defaults
        // the factor to 1.0 and the body renders as polished metal — it
        // mirrors the sky and comes out a white cutout however the scene is
        // lit. The asset is not at fault: its baseColorTexture is present
        // and correct, which is why "missing texture" was the wrong theory
        // twice. Respecting the metalness map here would mean respecting a
        // value no baker chose, so skin and cloth are forced dielectric and
        // the map is dropped with it. Genuinely metallic characters (armour)
        // would need this as an explicit per-asset opt-in.
        if (m.metalness > 0.6) {
          m.metalnessMap = null;
          m.metalness = 0.05;
          if (!m.roughnessMap && m.roughness >= 0.99) m.roughness = 0.78;
          m.needsUpdate = true;
        }
        // NO RECOLOURING HERE. An untextured white body at spawn is usually
        // a texture that has not DECODED yet, not one that is missing: the
        // same build shows map=NONE at 8s and a fully textured shirt a few
        // seconds later. base color multiplies the map, so tinting it to
        // hide the gap would permanently grey the costume once it arrives.
        // The emissive lift is dropped instead, which is what turned the
        // untextured moment into a glowing white cutout rather than a dull
        // grey one.
        // NEVER TINT AN UNTEXTURED MATERIAL. I did, twice, reasoning that a
        // material still missing its albedo after a settle delay was missing
        // it for good. It is a RACE, not a permanent state: the same build
        // shows the hero textured on one run and bare on the next, because a
        // 4K map inside a 38MB GLB does not always decode inside the window.
        // Base colour MULTIPLIES the map, so a tint applied during that gap
        // survives the texture's arrival and greys the costume permanently —
        // which is precisely the grey character being reported. Only the
        // emissive lift is dropped, since that is what turns the bare moment
        // into a glowing cutout instead of a plain one.
        if (!m.map && m.emissive && m.emissive.getHex() !== 0) {
          m.emissive.setScalar(0);
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
          if (!m) continue;
          m.side = THREE.DoubleSide;
          // SKIN AND CLOTH ARE NOT METAL (2026-08-07). glTF defaults
          // metallicFactor to 1.0, and a baked character that never wrote a
          // metallicRoughness texture inherits it — so the albedo contributes
          // NO diffuse and the model is lit only by reflections. On the hero
          // the moonlit-grade emissive then supplies the only visible signal
          // and he renders as a flat white cutout in any dark street, which
          // is exactly how this surfaced. A metalness map means the asset
          // meant it; a bare factor of 1 never does.
          if (m.metalness !== undefined && !m.metalnessMap && m.metalness > 0.6) {
            m.metalness = 0.05;
            if (!m.roughnessMap && m.roughness >= 0.99) m.roughness = 0.78;
            m.needsUpdate = true;
          }
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
        // MeshPhysicalMaterial reports isMeshStandardMaterial too, so this
        // pass was quietly overwriting the parametric car's own paint
        // (metalness 0.85 -> 0.25, roughness 0.22 -> 0.34) and undoing the
        // whole point of e17d2f7. Anything already authored physical was
        // authored deliberately — leave it alone. (2026-08-06)
        if (m.isMeshPhysicalMaterial) return m;
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
    // ── TEXEL DENSITY, IN REAL METRES (2026-08-06) ───────────────────────
    // Per family: [tileW_m, tileH_m, bays_in_photo, storeys_in_photo].
    // The metres are DERIVED, not chosen: each photo was measured (vertical
    // autocorrelation of its row luminance) to count how many storeys and
    // bays it actually depicts, then multiplied by a real storey height
    // (3.0-4.6m by building type) and a real bay width (2.7-4.4m).
    //
    // r13 sized every tile at 8m or less TALL, so a photo showing 6-8
    // storeys of windows was crushed into one storey of building: windows
    // came out postage-stamp sized and a tower wore the same image ~20x.
    // That single number is what read as "a textured box" from the street —
    // no albedo, normal map or cornice can survive wrong texel density.
    // r16 recalibration: the storey counts are now MEASURED, not eyeballed.
    // Two independent passes over each photo (luminance autocorrelation, and
    // connected-component labelling of the same windowness mask the runtime
    // derives) agreed on glass/brick/brick2/concrete; stone and limestone were
    // settled by rendering candidate storey lines over the photo and picking
    // the one that lands on the cornices. limestone's repeating unit turned
    // out to be TWO grand 5m storeys, not three — which is why its band of
    // ornament was repeating at the wrong pitch.
    // Bays are the less trustworthy axis (the detector locks onto paired
    // sashes rather than the bay rhythm), so they carry a visual count.
    const _FTILE = [
      [6, 6, 4, 2],                 // 0 procedural window grid (canvas, 6m tile)
      [26.8, 27.4, 10.3, 7.4],      // 1 facade_glass      2.6m pane / 3.7m storey
      [25.6, 15.2, 7.3, 4.6],       // 2 facade_brick      3.5m bay  / 3.3m storey
      [22.8, 33.3, 6.5, 10.4],      // 3 facade_stone      composite, 10 storeys
      [20.8, 20.4, 8, 6],           // 4 facade_glass2     diagrid, panel-scaled
      [18.7, 17.2, 5.5, 4],         // 5 facade_brick2     4 tall loft storeys
      [23.5, 27.9, 6.9, 9],         // 6 facade_concrete   9 balcony storeys
      [11.3, 10, 2.5, 2],           // 7 facade_limestone  2 grand 5m storeys
    ];
    // Masonry gets horizontal storey courses; curtain wall gets vertical
    // mullion fins. Getting this backwards is one of the loudest "generated
    // building" tells there is — a glass tower with stone sill bands, or a
    // brownstone with aluminium fins, reads wrong before you can say why.
    const _GLASSY = new Set([1, 4]);
    // ── DISTRICT COHERENCE (2026-08-06) ──────────────────────────────────
    // The facade family was picked per building from height plus a coin
    // flip, so a brownstone, a limestone and a diagrid tower stood shoulder
    // to shoulder on one block. That is the AI-slop read: every piece is
    // defensible and the street is nonsense. Real cities agree over a few
    // blocks at a time, so the family is now a property of a ~110m DISTRICT
    // and each building draws from that district's two-family palette.
    const _DGRID = 110;
    const _DPAL = [
      { tall: [1, 4], low: [7, 3] },   // financial — glass over stone bases
      { tall: [6, 3], low: [2, 5] },   // pre-war mixed — concrete/stone + brick
      { tall: [4, 1], low: [5, 2] },   // loft district — brick walk-ups
      { tall: [3, 6], low: [3, 7] },   // civic/stone
    ];
    function districtPal(px, pz) {
      const k = Math.floor((px + 4096) / _DGRID) * 1471
              + Math.floor((pz + 4096) / _DGRID) * 5273;
      const s = Math.abs(Math.sin(k * 0.6180339 + SPEC.seed * 0.0137) * 43758.5453) % 1;
      return _DPAL[Math.floor(s * _DPAL.length) % _DPAL.length];
    }
    // ── PUNCHED FACADE (2026-08-06 r3): masonry buildings stop wearing a
    // photograph of windows and start HAVING windows.
    //
    // Trying to align real openings to a photo's printed ones failed: the
    // storey pitch measures cleanly out of every photo but the bay pitch does
    // not, so sills landed on brick as often as on glass. The way every
    // procedural city tool answers this is not to measure harder — it is to
    // GENERATE the facade and drop the photo, because you cannot punch a hole
    // where a picture has already painted one.
    //
    // The wall becomes a grid of solid boxes: a pier between every bay, a
    // spandrel between every storey, standing 0.42m proud of a plain backing
    // wall. The GAPS between those boxes are the openings, so the jambs, head
    // and sill are real surfaces at real depth — they shade themselves, they
    // shift as you walk past, and they notch the corner against the sky. No
    // boolean, no runtime triangulation.
    //
    // Wall material is plain masonry at brick-sized texel density, which is
    // the trade that buys all of the above.
    const _FACADE = {
      0: { tex: 'stucco', tile: 3.0, st: 3.2, bay: 3.0, pier: 1.40, spand: 1.20 },
      2: { tex: 'brick',  tile: 2.2, st: 3.3, bay: 2.9, pier: 1.50, spand: 1.30 },
      3: { tex: 'ashlar', tile: 2.4, st: 3.6, bay: 3.4, pier: 1.70, spand: 1.40 },
      5: { tex: 'brick',  tile: 2.6, st: 4.0, bay: 3.5, pier: 1.40, spand: 1.30 },
      6: { tex: 'panel',  tile: 3.6, st: 3.1, bay: 3.2, pier: 1.00, spand: 1.10 },
      7: { tex: 'ashlar', tile: 2.6, st: 4.2, bay: 3.8, pier: 1.90, spand: 1.60 },
    };
    const WT = 0.42;                  // wall thickness == window reveal depth
    // Per-building variation. "Each building can be a bit different" is not a
    // nicety: an identical bay rhythm down a whole street is the clone-army
    // read that survives every other fix.
    function facadeOf(bkt, seedx, seedz) {
      const f = _FACADE[bkt];
      if (!f) return null;
      let s = Math.abs(Math.sin(seedx * 51.17 + seedz * 13.71) * 43758.5453) % 1;
      const nx = () => (s = (s * 9301 + 49297 / 233280) % 1);
      return { tex: f.tex, tile: f.tile,
               st: f.st * (0.94 + nx() * 0.14),
               bay: f.bay * (0.90 + nx() * 0.22),
               pier: f.pier * (0.86 + nx() * 0.30),
               spand: f.spand * (0.88 + nx() * 0.26) };
    }
    const _FFAM = [null, 'facade_glass', 'facade_brick', 'facade_stone',
      'facade_glass2', 'facade_brick2', 'facade_concrete', 'facade_limestone'];
    const _storeyH = (bkt) => _FTILE[bkt][1] / _FTILE[bkt][3];
    // Rewrite the side-wall UVs of one extruded footprint so the texture is
    // laid out in METRES ALONG THE REAL WALL rather than in ExtrudeGeometry's
    // default coordinates. Three defects go away at once:
    //   * default side-wall U is the vertex's world x OR z, whichever varies
    //     more — so any wall not axis-aligned wears the photo compressed by
    //     cos(angle) (a 45 deg wall, by 1.41x).
    //   * U restarted mid-window at every corner; now each edge starts on a
    //     bay boundary and fits a whole number of bays.
    //   * default V is 1 - extrudeDepth, which runs the photo UPSIDE DOWN;
    //     ground-floor detail landed at the roofline.
    // Non-indexed only (ExtrudeGeometry is); each side quad spans exactly one
    // footprint edge, so a triangle is matched to its edge by centroid.
    function metricWallUV(geo, pts, baseY, hh, bkt) {
      if (geo.index) return;
      const T = _FTILE[bkt] || _FTILE[0];
      const bayW = T[0] / T[2], stH = T[1] / T[3];
      // PHASE, PER BUILDING: neighbours sharing a family used to start the
      // same photo at the same pixel, so a distinctive feature (limestone's
      // ornamented bay especially) lined up across the whole street and the
      // block read as one building stamped out repeatedly. Shifted by a WHOLE
      // number of cells, so the storey grid the trim geometry is placed on is
      // untouched and a window still maps onto a window. Hashed from the
      // footprint centre rather than drawn from rngB, so adding it does not
      // reshuffle the city every existing seed generates.
      const _hsh = Math.abs(Math.sin(pts[0][0] * 12.9898 + pts[0][1] * 78.233) * 43758.5453);
      const phU = (Math.floor(_hsh * 97) % 7) * bayW;
      const phV = (Math.floor(_hsh * 31) % 5) * stH;
      // metres -> uv scale. The building height is snapped to whole storeys
      // before it gets here, so this is 1.0 for the main mass and only bends
      // for setback tiers.
      const kv = Math.max(1, Math.round(hh / stH)) * stH / Math.max(hh, 0.01);
      const E = [];
      for (let i = 0; i < pts.length; i++) {
        const a = pts[i], c = pts[(i + 1) % pts.length];
        const dx = c[0] - a[0], dz = c[1] - a[1];
        const L = Math.hypot(dx, dz);
        if (L < 0.05) continue;
        E.push([a[0], a[1], dx / L, dz / L, L,
                Math.max(1, Math.round(L / bayW)) * bayW / L]);
      }
      if (!E.length) return;
      const pos = geo.attributes.position, uv = geo.attributes.uv;
      for (const g of geo.groups) {
        if (g.materialIndex === 0) continue;          // caps keep their own UVs
        const end = g.start + g.count;
        for (let i = g.start; i + 2 < end; i += 3) {
          const mx = (pos.getX(i) + pos.getX(i + 1) + pos.getX(i + 2)) / 3;
          const mz = (pos.getZ(i) + pos.getZ(i + 1) + pos.getZ(i + 2)) / 3;
          let be = E[0], bd = 1e9;
          for (const e of E) {
            const t = Math.max(0, Math.min(1,
              ((mx - e[0]) * e[2] + (mz - e[1]) * e[3]) / e[4]));
            const d = Math.hypot(mx - (e[0] + e[2] * e[4] * t),
                                 mz - (e[1] + e[3] * e[4] * t));
            if (d < bd) { bd = d; be = e; }
          }
          for (let k = 0; k < 3; k++) {
            const j = i + k;
            const along = (pos.getX(j) - be[0]) * be[2]
                        + (pos.getZ(j) - be[1]) * be[3];
            uv.setXY(j, along * be[5] + phU, (pos.getY(j) - baseY) * kv + phV);
          }
        }
      }
      uv.needsUpdate = true;
    }
    // A BBOX FACE IS NOT A WALL (2026-08-06). Projecting a footprint's centre
    // outward to its axis-aligned bounding box lands INSIDE the building for
    // anything that is not an axis-aligned rectangle, and a buried prop is
    // simply an invisible one — that is how the fire-escape pass first
    // shipped 24 landings and showed none. Everything hung on a facade picks
    // the real polygon EDGE facing the road and takes its outward normal from
    // the edge itself. Function declaration: it is read above where the
    // const helpers below are declared, and a const would be in its TDZ.
    function faceEdge(pts, cx, cz, bx, bz, minLen) {
      let bi = -1, bd = 1e9, nx = 0, nz = 0;
      for (let i = 0; i < pts.length; i++) {
        const a = pts[i], c = pts[(i + 1) % pts.length];
        const ex = c[0] - a[0], ez = c[1] - a[1];
        const L = Math.hypot(ex, ez);
        if (L < (minLen || 2)) continue;
        const mx = (a[0] + c[0]) / 2, mz = (a[1] + c[1]) / 2;
        let px = -ez / L, pz = ex / L;
        if ((mx - cx) * px + (mz - cz) * pz < 0) { px = -px; pz = -pz; }
        const d = Math.hypot(mx - bx, mz - bz);
        if (d < bd) { bd = d; bi = i; nx = px; nz = pz; }
      }
      if (bi < 0) return null;
      const a = pts[bi], c = pts[(bi + 1) % pts.length];
      return { x: (a[0] + c[0]) / 2, z: (a[1] + c[1]) / 2, nx, nz,
               len: Math.hypot(c[0] - a[0], c[1] - a[1]) };
    }
    // inBldg() tests axis-aligned bounding boxes, which is the right cheap
    // answer for "can the player walk here" and the WRONG one for a prop
    // deliberately placed 0.9m off a wall: on a diagonal footprint that point
    // is outside the building but well inside its box, so the box test was
    // throwing away exactly the placements the edge picker had just got
    // right (5 pieces of street furniture survived out of ~23 candidates).
    // This is the honest test — even-odd crossing against the real polygon.
    function inFootprint(x, z) {
      for (const b2 of OSM.buildings) {
        const q = b2.pts;
        let hit = false;
        for (let i = 0, j = q.length - 1; i < q.length; j = i++) {
          if ((q[i][1] > z) !== (q[j][1] > z)
              && x < (q[j][0] - q[i][0]) * (z - q[i][1])
                     / ((q[j][1] - q[i][1]) || 1e-9) + q[i][0]) hit = !hit;
        }
        if (hit) return true;
      }
      return false;
    }
    // Merged per masonry TEXTURE, not per building: four draw calls carry
    // every punched facade in the city.
    const wallBoxes = { brick: [], ashlar: [], stucco: [], panel: [] };
    const backGeos = [];                       // the plain wall behind the reveals
    const glassI = [];                         // [x,y,z,yaw,w,h,lit,r,g,b]
    const _BOX1 = new THREE.BoxGeometry(1, 1, 1);
    // Backstop only. A 78m tower on a long block is a few hundred boxes, so a
    // dense downtown scan stays well inside this; a pathological footprint set
    // must not be able to spend the whole load budget on masonry. Declared
    // ABOVE the functions that read it — a const/let read before its
    // declaration kills the entire runtime with no build error.
    let _boxN = 0;
    const BOX_MAX = 26000;
    const _bM = new THREE.Matrix4(), _bQ = new THREE.Quaternion();
    const _bE = new THREE.Euler(), _bV = new THREE.Vector3(), _bS = new THREE.Vector3();
    // One box of the wall grid. UVs are projected in METRES on the face's own
    // plane rather than left at BoxGeometry's per-face 0..1, or the brick
    // would smear differently on every pier — which is the whole reason these
    // are merged geometry and not an InstancedMesh.
    function wallBox(sink, ax, az, ux, uz, nx, nz, along, y, w, hh, gy, tone, th) {
      const t = th || WT;
      const g = _BOX1.clone();
      _bE.set(0, Math.atan2(nx, nz), 0); _bQ.setFromEuler(_bE);
      // seated so the OUTER face lands on the wall plane whatever the
      // thickness — that is what lets a sill stand proud of its own spandrel
      _bV.set(ax + ux * along - nx * (WT - t / 2), y, az + uz * along - nz * (WT - t / 2));
      _bS.set(w, hh, t);
      g.applyMatrix4(_bM.compose(_bV, _bQ, _bS));
      const pos = g.attributes.position, nor = g.attributes.normal, uv = g.attributes.uv;
      const cols = new Float32Array(pos.count * 3);
      for (let i = 0; i < pos.count; i++) {
        const px = pos.getX(i), py = pos.getY(i), pz = pos.getZ(i);
        const al = (px - ax) * ux + (pz - az) * uz;
        const ou = (px - ax) * nx + (pz - az) * nz;
        const ny = nor.getY(i), nxx = nor.getX(i), nzz = nor.getZ(i);
        if (Math.abs(ny) > 0.7) uv.setXY(i, al, ou);                    // sill / soffit
        else if (Math.abs(nxx * ux + nzz * uz) > 0.7) uv.setXY(i, ou, py - gy);  // jamb
        else uv.setXY(i, al, py - gy);                                  // face
        // the same ground-bounce gradient the photo walls carry, so the two
        // families of building still light alike
        const gAO = 0.66 + 0.34 * Math.min(Math.max((py - gy) / 8, 0), 1);
        // reveal faces sit inside the opening and must read darker than the
        // face, or the depth is thrown away by uniform shading
        const inset = Math.abs(ny) > 0.7 || Math.abs(nxx * ux + nzz * uz) > 0.7 ? 0.72 : 1;
        cols[i * 3] = tone.r * gAO * inset;
        cols[i * 3 + 1] = tone.g * gAO * inset;
        cols[i * 3 + 2] = tone.b * gAO * inset;
      }
      g.setAttribute('color', new THREE.BufferAttribute(cols, 3));
      sink.push(g);
      _boxN++;
    }
    // The wall grid for one building: a pier on every bay boundary, a
    // spandrel on every storey line. What is LEFT between them is the window.
    function buildPunched(pts, cx, cz, gy, h, F, tint, wantShop) {
      const sink = wallBoxes[F.tex] || wallBoxes.brick;
      const nSt = Math.max(1, Math.round(h / F.st));
      const rngQ = mulberry32(Math.floor(Math.abs(cx) * 131 + Math.abs(cz) * 977) + 5);
      // colour varies per building but stays out of the texture's way — the
      // brick's own hue has to survive, or every wall goes the same grey
      const tv = 0.78 + rngQ() * 0.34, tw2 = (rngQ() - 0.5) * 0.14;
      const tone = new THREE.Color(tv + tw2, tv, tv - tw2 * 0.7);
      // Some buildings are mostly awake at 2am and some are mostly asleep.
      // A single global lit fraction gave every tower the same even sprinkle,
      // which is a texture, not a city.
      const litBias = 0.45 + rngQ() * 1.25;
      let ccx = 0, ccz = 0;
      for (const q of pts) { ccx += q[0]; ccz += q[1]; }
      ccx /= pts.length; ccz /= pts.length;
      for (let i = 0; i < pts.length; i++) {
        const a = pts[i], c = pts[(i + 1) % pts.length];
        const dx = c[0] - a[0], dz = c[1] - a[1];
        const L = Math.hypot(dx, dz);
        if (L < 1.0) continue;
        const ux = dx / L, uz = dz / L;
        const mx = (a[0] + c[0]) / 2, mz = (a[1] + c[1]) / 2;
        let nx = -uz, nz = ux;
        if ((mx - ccx) * nx + (mz - ccz) * nz < 0) { nx = -nx; nz = -nz; }
        if (L < F.bay * 1.25 || _boxN > BOX_MAX) {
          // too narrow to punch — leave it solid rather than emit a sliver of
          // window jammed against two corners
          wallBox(sink, a[0], a[1], ux, uz, nx, nz, L / 2, gy + h / 2, L, h, gy, tone);
          continue;
        }
        const nb = Math.max(1, Math.round(L / F.bay)), bw = L / nb;
        // never let the pier eat more than half the bay: at 0.74 a narrow bay
        // produced a sub-0.55m opening, the glazing was skipped entirely, and
        // that whole building came out as a grid of blind slots
        const pw = Math.min(F.pier, bw * 0.52);
        const sh2 = Math.min(F.spand, F.st * 0.60);
        // SHOPFRONT: a New York ground floor is glass, not the same punched
        // window as floor six. Without this the whole city reads as public
        // housing — it was the loudest thing wrong with the first punch.
        const sh0 = Math.min(0.42, sh2);
        const stY = (s) => gy + s * F.st + (s === 0 ? sh0 : sh2);   // window head
        // piers, one per bay boundary. The end ones overhang the corner on
        // purpose: two edges' end piers overlap there, so a corner is solid
        // masonry rather than a window wrapping an arris. Slightly thicker
        // than the spandrels, which gives the wall a vertical rhythm instead
        // of one flat plane with holes in it.
        // SHOP SPAN (2026-08-06): a retail ground floor is ONE long run of
        // glass. Carrying the upstairs pier rhythm down to the pavement is
        // what made a street of shops read as public housing. Program decides,
        // so a cafe opens up and an apartment block does not.
        const shop = wantShop && nSt >= 2 && L > F.bay * 2.2;
        const shopTop = gy + F.st;
        for (let k = 0; k <= nb; k++) {
          if (shop && k > 0 && k < nb) {
            wallBox(sink, a[0], a[1], ux, uz, nx, nz, k * bw,
                    (shopTop + gy + h) / 2, pw, gy + h - shopTop, gy, tone, WT + 0.07);
          } else {
            wallBox(sink, a[0], a[1], ux, uz, nx, nz, k * bw, gy + h / 2, pw, h, gy,
                    tone, WT + 0.07);
          }
        }
        for (let s = 0; s <= nSt; s++) {
          const top = s === nSt;
          const bh2 = top ? sh2 : (s === 0 ? sh0 : sh2);
          const y = top ? gy + h - sh2 / 2 : gy + s * F.st + bh2 / 2;
          wallBox(sink, a[0], a[1], ux, uz, nx, nz, L / 2, y, L + 0.02, bh2, gy, tone);
          // SILL COURSE on top of each spandrel and LINTEL under the next —
          // every opening gets a lip above it and a shelf below it, both
          // standing proud enough to throw their own shadow line. Continuous
          // per storey rather than per window: one box instead of one per
          // bay, and a continuous sill course is what a brownstone has.
          if (!top) {
            wallBox(sink, a[0], a[1], ux, uz, nx, nz, L / 2,
                    gy + s * F.st + bh2 + 0.055, L + 0.30, 0.11, gy, tone, WT + 0.17);
          }
          if (s > 0) {
            wallBox(sink, a[0], a[1], ux, uz, nx, nz, L / 2,
                    gy + s * F.st - 0.07, L + 0.22, 0.14, gy, tone, WT + 0.10);
          }
        }
        // glazing sits on the backing wall, so it is seen down a real reveal
        const ww = bw - pw;
        for (let s = 0; s < nSt; s++) {
          const y0 = stY(s);
          const y1 = gy + (s + 1) * F.st - (s === nSt - 1 ? sh2 : 0);
          if (y1 - y0 < 0.6) continue;
          if (shop && s === 0) {
            // one pane for the whole span, lit warm: a shop at night is the
            // brightest thing at street level and it is what you walk past
            glassI.push([mx - nx * (WT - 0.05), (y0 + y1) / 2, mz - nz * (WT - 0.05),
                         Math.atan2(nx, nz), L - pw * 1.15, y1 - y0, 0.02]);
            continue;
          }
          for (let k = 0; k < nb; k++) {
            const al = (k + 0.5) * bw;
            // shop windows are lit far more often than flats, and they are
            // the ones at eye level
            const r2 = s === 0 ? rngQ() * 0.35 : Math.min(0.999, rngQ() * litBias);
            glassI.push([a[0] + ux * al - nx * (WT - 0.04), (y0 + y1) / 2,
                         a[1] + uz * al - nz * (WT - 0.04),
                         Math.atan2(nx, nz), ww, y1 - y0, r2]);
          }
        }
      }
    }
    const wallBuckets = [[], [], [], [], [], [], [], []], capGeos = [];
    const roofSpots = [];
    // [pts, topY] for the topmost slab of every building — the parapet pass
    // below needs the polygon of the LAST setback tier, which nothing else
    // keeps hold of.
    const capRings = [];
    // [pts, cx, cz, groundY, height, bucket] — the fire-escape pass below runs
    // long after this loop and needs the height that MANHATTAN PROFILE derived
    // here, which is not recoverable from b.h alone.
    // Every decoration pass downstream MUST iterate this and not OSM.buildings.
    // OSM.buildings includes footprints the spawn/path cull threw away, so a
    // pass that walks the raw list hangs its awnings and shop signs in the
    // empty air where a building was never built — which is exactly what
    // "GOLDEN DRAGON floating in the street" was. (2026-08-06)
    const feCand = [];
    // LAND USE. A city is not a texture problem: an apartment block with a
    // restaurant sign on it, or a tower with no ground floor, reads wrong no
    // matter how good the facade is. Program drives signage, shopfronts and
    // awnings so the street tells you what each building IS.
    const _PROGNAMES = {
      cafe: ['STAR CAFE', 'BEAN & BAR', 'CAFE ROMA', 'DAILY GRIND', 'ESPRESSO'],
      restaurant: ["MARIO'S PIZZA", 'GOLDEN DRAGON', "JOE'S DINER", 'SUSHI KO',
        'CITY DELI', 'NOODLE HOUSE'],
      store: ['GREEN MARKET', 'RECORDS', 'FLOWERS', 'HARDWARE', 'BODEGA 24',
        'LAUNDROMAT', 'PHARMACY'],
      bar: ["LUCKY'S BAR", 'THE ROXY', 'CINEMA', 'JAZZ CLUB'],
      hotel: ['HOTEL RIALTO', 'THE CARLYLE', 'GRAND HOTEL'],
    };
    const _SHOPPROG = new Set(['cafe', 'restaurant', 'store', 'bar']);
    function programFor(h, rnd) {
      if (h > 42) return rnd < 0.82 ? 'office' : 'hotel';
      if (h > 24) return rnd < 0.42 ? 'office' : rnd < 0.62 ? 'hotel' : 'apartment';
      if (rnd < 0.34) return 'apartment';
      if (rnd < 0.52) return 'store';
      if (rnd < 0.68) return 'restaurant';
      if (rnd < 0.82) return 'cafe';
      return rnd < 0.92 ? 'bar' : 'apartment';
    }
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
      // A DOOR NEEDS ITS BUILDING (2026-08-05): footprints picked as heist
      // venues are exempt from the cull. Python already checked they clear
      // the path and the spawn, and a culled venue would leave a glowing
      // doorway standing in open air with nothing behind it.
      if (b.enter === undefined) {
        if (Math.hypot(cx, cz) < 9) continue;                     // spawn stays open
        if (goalPos && Math.hypot(cx - goalPos.x, cz - goalPos.z) < 8) continue;
        if (pathDist(cx, cz) < CORR + Math.max(mxx - mnx, mxz - mnz) / 2) continue;
      }
      try {
        const shape = new THREE.Shape();
        b.pts.forEach(([px, pz], i) => i ? shape.lineTo(px, -pz) : shape.moveTo(px, -pz));
        // MANHATTAN PROFILE (Phase 118): heights rise toward the city core —
        // skyscraper center, mid-rise ring, low-rise edges. Reads as downtown
        // from every camera angle.
        const _half = SPEC.world.size_m * 0.5;
        const _core = Math.max(0, 1 - Math.hypot(cx, cz) / (_half * 0.85));
        // r3: NYC has almost no 1-2 storey buildings. The old floor of 4m let
        // OSM's missing-height default drop bungalows into midtown, which is
        // what made the block read as a suburb with towers behind it. Floor is
        // now four storeys and the core reaches genuinely tall.
        const _h0 = Math.min(Math.max((b.h || 12) * (1 + 2.9 * _core * _core), 13.5), 78);
        const gy = hAt(cx, cz);
        const tint = tintA.clone().lerp(tintB, rngB()).offsetHSL(0, 0, (rngB() - 0.5) * 0.12);
        // photo facades ONLY by day (2026-07-28: the procedural grid reads
        // as placeholder in daylight); at night it keeps a 25% share for
        // the lit-window checkerboard until photo facades learn to glow
        const _night = ['night', 'dusk', 'sunset'].includes(SPEC.world.sky);
        // r7: seven facade families (was three) — a real skyline mix.
        // Towers: two glass looks + concrete + stone; mid-rise: two bricks
        // + limestone + stone. Night keeps a 20% procedural share for the
        // lit-checkerboard variety.
        // (2026-08-06: the family is now chosen BEFORE the geometry, because
        // it decides the storey height the mass is quantised to. The rngB()
        // call ORDER is unchanged so the same seed still builds the same city.)
        // OSM names the use for roughly 40% of a Manhattan extract; the
        // district palette answers for the rest. The TAG wins where it
        // exists: an office tower standing in a brick district is a real
        // thing and reads as one, whereas a brownstone dropped into a glass
        // district reads as a bug.
        // (rngB() is now consumed exactly twice per building instead of
        // once-or-twice depending on the branch, which is what made the
        // family assignment drift with the night flag.)
        const _use = (b.use || '').toLowerCase();
        const _resid = /apartment|residential|house|terrace|dormitor/.test(_use);
        const _comm = /office|commercial|hotel|retail|shop|supermarket|mall|bank/.test(_use);
        const _pal = districtPal(cx, cz);
        const _r = rngB(), _r2 = rngB();
        const _bkt = _h0 > 26
          ? (_comm ? (_r < 0.6 ? 1 : 4) : _resid ? 6 : _pal.tall[_r < 0.62 ? 0 : 1])
          : (_night && _r2 < 0.16 ? 0
             : _resid ? (_r < 0.55 ? 2 : 5)
             : _comm ? (_r < 0.5 ? 7 : 3)
             : _pal.low[_r < 0.62 ? 0 : 1]);
        // STOREY-QUANTISED MASS (2026-08-06): snap the extrusion to a whole
        // number of the family's storeys. The roofline then lands on a floor
        // line instead of slicing a window row in half — and for a punched
        // facade it also means the top storey is a whole storey, so the wall
        // grid closes cleanly under the parapet instead of ending mid-window.
        const _prog = programFor(_h0, rngB());
        // Ground-floor retail is near-universal here: a 40-storey tower
        // still has a deli in its base. Only a pure residential block
        // keeps a blank street wall (it gets fire escapes and a stoop
        // instead). Gating this on _prog gave a city with five shops in it.
        const _shop = _prog !== 'apartment';
        const _fac = facadeOf(_bkt, mnx, mnz);
        const _sh = _fac ? _fac.st : _storeyH(_bkt);
        const h = Math.max(_fac ? 2 : 1, Math.round(_h0 / _sh)) * _sh;
        const geo = new THREE.ExtrudeGeometry(shape, { depth: h, bevelEnabled: false });
        geo.rotateX(-Math.PI / 2);                                // extrude up
        geo.translate(0, gy, 0);
        const nv = geo.attributes.position.count, cols = new Float32Array(nv * 3);
        for (let i = 0; i < nv; i++) { cols[i * 3] = tint.r; cols[i * 3 + 1] = tint.g; cols[i * 3 + 2] = tint.b; }
        geo.setAttribute('color', new THREE.BufferAttribute(cols, 3));
        if (_fac) {
          // PUNCHED FACADE. The extrusion is kept only for its roof cap and
          // for a backing wall set WT inside the footprint — that backing is
          // what you see through every opening, so the recess is real depth
          // and not a painted shadow.
          for (const g2 of geo.groups) {
            if (g2.materialIndex === 0) {
              const sub = new THREE.BufferGeometry();
              for (const nmA of ['position', 'normal', 'uv', 'color']) {
                const at = geo.attributes[nmA];
                sub.setAttribute(nmA, new THREE.BufferAttribute(
                  at.array.slice(g2.start * at.itemSize,
                                 (g2.start + g2.count) * at.itemSize), at.itemSize));
              }
              capGeos.push(sub);
            }
          }
          let rSum = 0;
          for (let i = 0; i < b.pts.length; i++) {
            const q1 = b.pts[i], q2 = b.pts[(i + 1) % b.pts.length];
            rSum += Math.hypot((q1[0] + q2[0]) / 2 - cx, (q1[1] + q2[1]) / 2 - cz);
          }
          const shr = Math.max(0.55, 1 - WT / Math.max(rSum / b.pts.length, 1.2));
          const bPts = b.pts.map(([px, pz]) => [cx + (px - cx) * shr, cz + (pz - cz) * shr]);
          const bShape = new THREE.Shape();
          bPts.forEach(([px, pz], i) => i ? bShape.lineTo(px, -pz) : bShape.moveTo(px, -pz));
          const bg2 = new THREE.ExtrudeGeometry(bShape, { depth: h, bevelEnabled: false });
          bg2.rotateX(-Math.PI / 2); bg2.translate(0, gy, 0);
          for (const g2 of bg2.groups) {
            if (g2.materialIndex === 0) continue;                 // its cap is buried
            const sub = new THREE.BufferGeometry();
            for (const nmA of ['position', 'normal', 'uv']) {
              const at = bg2.attributes[nmA];
              sub.setAttribute(nmA, new THREE.BufferAttribute(
                at.array.slice(g2.start * at.itemSize,
                               (g2.start + g2.count) * at.itemSize), at.itemSize));
            }
            backGeos.push(sub);
          }
          buildPunched(b.pts, cx, cz, gy, h, _fac, tint, _shop);
        } else {
          metricWallUV(geo, b.pts, gy, h, _bkt);
          splitGroups(geo, _bkt);
        }
        feCand.push([b.pts, cx, cz, gy, h, _bkt, tint, _prog, _sh, _shop]);
        let _capPts = b.pts, _capTop = gy + h;
        // r14 SETBACKS: real towers STEP BACK as they rise — a single
        // extruded prism is why buildings read as 'geometric shapes'.
        // Tall buildings gain 1-2 shrinking tiers above the base (same
        // facade bucket + tint, so they read as one building).
        if (h > 30) {
          const tiers = h > 44 ? 2 : 1;
          let topY = gy + h;
          for (let ti2 = 1; ti2 <= tiers; ti2++) {
            const shrink = 1 - 0.15 * ti2;
            // tiers are storey-quantised too, or the setback line cuts a
            // window row and the whole point of the snap is lost
            const th2 = Math.max(1, Math.round(h * (0.38 - 0.1 * ti2) / _sh)) * _sh;
            const tPts = b.pts.map(([px, pz]) =>
              [cx + (px - cx) * shrink, cz + (pz - cz) * shrink]);
            const s2h = new THREE.Shape();
            tPts.forEach(([sx5, sz5], i) => i ? s2h.lineTo(sx5, -sz5) : s2h.moveTo(sx5, -sz5));
            const tg = new THREE.ExtrudeGeometry(s2h, { depth: th2, bevelEnabled: false });
            tg.rotateX(-Math.PI / 2);
            tg.translate(0, topY, 0);
            const nv2 = tg.attributes.position.count;
            const cols2 = new Float32Array(nv2 * 3);
            for (let i = 0; i < nv2; i++) {
              cols2[i * 3] = tint.r; cols2[i * 3 + 1] = tint.g; cols2[i * 3 + 2] = tint.b;
            }
            tg.setAttribute('color', new THREE.BufferAttribute(cols2, 3));
            metricWallUV(tg, tPts, topY, th2, _bkt);
            splitGroups(tg, _bkt);
            topY += th2;
            _capPts = tPts; _capTop = topY;
          }
        }
        if (h >= 8) capRings.push([_capPts, _capTop]);
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
    // ── ASSEMBLE THE PUNCHED FACADES ─────────────────────────────────────
    {
      const _mLoad = new THREE.TextureLoader();
      const _mTex = (n, sfx, tile) => {
        const t = _mLoad.load('textures/' + n + (sfx || '') + '.jpg');
        t.wrapS = t.wrapT = THREE.RepeatWrapping;
        t.repeat.set(1 / tile, 1 / tile);        // UVs are already in metres
        if (!sfx) t.colorSpace = THREE.SRGBColorSpace;
        t.anisotropy = renderer.capabilities.getMaxAnisotropy();
        return t;
      };
      const _TILE = { brick: 2.2, ashlar: 2.4, stucco: 3.0, panel: 3.6 };
      const _ROUGH = { brick: 0.94, ashlar: 0.86, stucco: 0.93, panel: 0.88 };
      // ── WALL TEXTURES ARE DRAWN, NOT PHOTOGRAPHED (2026-08-06) ──────────
      // The library's stone.jpg is fieldstone RUBBLE and its concrete.jpg is
      // paving slabs. Both are fine on the ground and both read as a castle
      // the moment they go on a wall at storey scale — which is exactly how
      // the first punched city came out. brick.jpg is the one that works, so
      // it stays; the rest are drawn, which also means the coursing pitch is
      // right by construction instead of by tiling luck.
      const _mkWall = (kind) => {
        const N = 512, c = document.createElement('canvas');
        c.width = c.height = N;
        const g = c.getContext('2d');
        const rn = mulberry32(SPEC.seed + 4400 + kind.charCodeAt(0));
        if (kind === 'ashlar') {
          // cut limestone: 0.4m courses, 1.2m blocks, running bond. This is
          // what pre-war New York is actually faced with.
          g.fillStyle = '#5f584c'; g.fillRect(0, 0, N, N);      // joint
          const rows = 6, ch = N / rows, bl = N / 2;
          for (let r = 0; r < rows; r++) {
            const off = (r % 2) ? bl / 2 : 0;
            for (let k = -1; k < 3; k++) {
              const x = k * bl + off, y = r * ch;
              const v = 168 + Math.floor(rn() * 44);
              g.fillStyle = 'rgb(' + v + ',' + (v - 7) + ',' + (v - 20) + ')';
              g.fillRect(x + 2.5, y + 2.5, bl - 5, ch - 5);
              g.fillStyle = 'rgba(112,104,90,' + (0.04 + rn() * 0.10) + ')';
              g.fillRect(x + 2.5, y + 2.5 + (ch - 5) * 0.62, bl - 5, (ch - 5) * 0.38);
            }
          }
        } else if (kind === 'stucco') {
          g.fillStyle = '#b5ac9c'; g.fillRect(0, 0, N, N);
          for (let i = 0; i < 2400; i++) {
            const d2 = rn() < 0.5;
            g.fillStyle = d2 ? 'rgba(148,140,126,0.10)' : 'rgba(208,200,186,0.10)';
            g.beginPath(); g.arc(rn() * N, rn() * N, 2 + rn() * 13, 0, 6.2832); g.fill();
          }
          for (let i = 0; i < 44; i++) {          // rain staining, always down
            g.fillStyle = 'rgba(124,116,102,' + (0.03 + rn() * 0.06) + ')';
            g.fillRect(rn() * N, rn() * N, 3 + rn() * 9, 40 + rn() * 190);
          }
        } else if (kind === 'panel') {
          g.fillStyle = '#a6a29a'; g.fillRect(0, 0, N, N);
          for (let i = 0; i < 1900; i++) {
            g.fillStyle = 'rgba(150,147,140,' + (0.04 + rn() * 0.07) + ')';
            g.beginPath(); g.arc(rn() * N, rn() * N, 1 + rn() * 8, 0, 6.2832); g.fill();
          }
          g.strokeStyle = 'rgba(118,115,108,0.6)'; g.lineWidth = 3;
          for (const t of [0.5, N / 2 + 0.5]) {
            g.beginPath(); g.moveTo(t, 0); g.lineTo(t, N); g.stroke();
            g.beginPath(); g.moveTo(0, t); g.lineTo(N, t); g.stroke();
          }
          for (let i = 0; i < 26; i++) {          // form-tie holes
            g.fillStyle = 'rgba(108,104,98,0.5)';
            g.beginPath(); g.arc(rn() * N, rn() * N, 2.5, 0, 6.2832); g.fill();
          }
        }
        return c;
      };
      // relief straight off the drawn albedo: the joints ARE the height
      // field, so they cannot drift out of register with the courses
      const _normalOf = (cv, amp) => {
        const N = cv.width;
        const src = cv.getContext('2d').getImageData(0, 0, N, N).data;
        const L = new Float32Array(N * N);
        for (let i = 0, q = 0; i < N * N; i++, q += 4) {
          L[i] = (0.299 * src[q] + 0.587 * src[q + 1] + 0.114 * src[q + 2]) / 255;
        }
        const nc = document.createElement('canvas');
        nc.width = nc.height = N;
        const ng = nc.getContext('2d'), img = ng.createImageData(N, N);
        const at = (x, y) => L[(((y % N) + N) % N) * N + (((x % N) + N) % N)];
        for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
          const gx = at(x + 1, y) - at(x - 1, y), gy2 = at(x, y + 1) - at(x, y - 1);
          const q = (y * N + x) * 4;
          img.data[q] = Math.max(0, Math.min(255, (-gx * amp + 0.5) * 255));
          img.data[q + 1] = Math.max(0, Math.min(255, (gy2 * amp + 0.5) * 255));
          img.data[q + 2] = 255; img.data[q + 3] = 255;
        }
        ng.putImageData(img, 0, 0);
        return nc;
      };
      const _canvasTex = (cv, tile, srgb) => {
        const t = new THREE.CanvasTexture(cv);
        t.wrapS = t.wrapT = THREE.RepeatWrapping;
        t.repeat.set(1 / tile, 1 / tile);
        if (srgb) t.colorSpace = THREE.SRGBColorSpace;
        t.anisotropy = renderer.capabilities.getMaxAnisotropy();
        return t;
      };
      for (const key of Object.keys(wallBoxes)) {
        const list = wallBoxes[key];
        if (!list.length) continue;
        let mp, nm;
        if (key === 'brick') {
          mp = _mTex(key, '', _TILE[key]);
          nm = _mTex(key, '_n', _TILE[key]);
        } else {
          const cv = _mkWall(key);
          mp = _canvasTex(cv, _TILE[key], true);
          nm = _canvasTex(_normalOf(cv, key === 'ashlar' ? 3.2 : 1.4), _TILE[key], false);
        }
        const m = new THREE.Mesh(mergeGeometries(list, false),
          new THREE.MeshStandardMaterial({
            map: mp, normalMap: nm,
            normalScale: new THREE.Vector2(1.1, 1.1),
            vertexColors: true, roughness: _ROUGH[key], metalness: 0.02 }));
        m.castShadow = m.receiveShadow = true;
        scene.add(m);
        for (const g2 of list) g2.dispose();
      }
      console.log('[facade] wallBoxes=' + Object.keys(wallBoxes).map(k => k + ':' + wallBoxes[k].length).join(' ')
        + ' backGeos=' + backGeos.length + ' capGeos=' + capGeos.length + ' glass=' + glassI.length);
      if (backGeos.length) {
        // deliberately dark and matte: this is what you look at down every
        // reveal, and a bright backing throws the depth away
        const backM = new THREE.MeshStandardMaterial({ color: 0x27241f,
          roughness: 0.97, metalness: 0.0 });
        backM.userData.noAutoTex = true;
        const bm = new THREE.Mesh(mergeGeometries(backGeos, false), backM);
        bm.receiveShadow = true;
        bm.name = 'BACKING';
        scene.add(bm);
        for (const g2 of backGeos) g2.dispose();
      }
      if (glassI.length) {
        const _night2 = SPEC.world.sky === 'night' || SPEC.world.sky === 'dusk';
        const litFrac = _night2 ? 0.42 : 0.0;
        const pane = new THREE.PlaneGeometry(1, 1);
        // ── PANE TEXTURE (2026-08-06) ───────────────────────────────────
        // A lit window was an untextured plane with a per-instance colour:
        // at street level that is a blank cream rectangle 3m across, and it
        // was the loudest remaining "textured box" tell once the facade got
        // real openings. A window needs a frame, a mullion and a transom
        // (that is what tells you which way is up and how big it is) and a
        // top-down brightness falloff, because rooms are lit from the
        // ceiling. One shared 128px canvas — both materials use it, so the
        // instancing and the draw-call count are untouched.
        const wc = document.createElement('canvas');
        wc.width = wc.height = 128;
        {
          const wx2 = wc.getContext('2d');
          const grd = wx2.createLinearGradient(0, 0, 0, 128);
          grd.addColorStop(0, '#ffffff');
          grd.addColorStop(0.55, '#e2e2e2');
          grd.addColorStop(1, '#9c9c9c');
          wx2.fillStyle = grd; wx2.fillRect(0, 0, 128, 128);
          wx2.fillStyle = '#2a2724';
          wx2.fillRect(0, 0, 128, 7); wx2.fillRect(0, 121, 128, 7);
          wx2.fillRect(0, 0, 7, 128); wx2.fillRect(121, 0, 7, 128);
          wx2.fillRect(61, 0, 6, 128);            // mullion
          wx2.fillRect(0, 52, 128, 5);            // transom
        }
        const paneTex = new THREE.CanvasTexture(wc);
        paneTex.colorSpace = THREE.SRGBColorSpace;
        paneTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
        const lit = [], dark = [];
        for (const w of glassI) (w[6] < litFrac ? lit : dark).push(w);
        const place = (arr, mat, cast) => {
          if (!arr.length) return;
          const im = new THREE.InstancedMesh(pane, mat, arr.length);
          const M = new THREE.Matrix4(), Q = new THREE.Quaternion();
          const E = new THREE.Euler(), V = new THREE.Vector3(), S = new THREE.Vector3();
          const C = new THREE.Color();
          arr.forEach((w, i) => {
            E.set(0, w[3], 0); Q.setFromEuler(E);
            V.set(w[0], w[1], w[2]); S.set(w[4], w[5], 1);
            im.setMatrixAt(i, M.compose(V, Q, S));
            const wr = (w[6] * 7919) % 1, wr2 = (w[6] * 104729) % 1;
            if (cast) {
              // Warm tungsten with the odd cold fluorescent, and a wide spread
              // of BRIGHTNESS. Every lit pane at full value was the giveaway
              // in the first punch: a row of identical cream rectangles reads
              // as cardboard, because no two rooms are ever lit the same.
              const v = 0.34 + wr2 * 0.66;
              if (wr < 0.82) C.setRGB(v, v * (0.68 + wr * 0.1), v * (0.36 + wr * 0.2));
              else C.setRGB(v * 0.72, v * 0.86, v);
            } else {
              // unlit glass is not black — it is a dark mirror of the night
              // sky, and a little variation stops the grid reading as print
              C.setRGB(0.16 + wr * 0.10, 0.19 + wr * 0.11, 0.26 + wr * 0.13);
            }
            im.setColorAt(i, C);
          });
          im.instanceMatrix.needsUpdate = true;
          if (im.instanceColor) im.instanceColor.needsUpdate = true;
          im.receiveShadow = !cast;
          scene.add(im);
        };
        // lit panes are self-luminous, so Basic — a StandardMaterial would
        // need a real light behind every window and the light budget is 4
        // toneMapped stays ON: unmapped, every lit pane clipped to the same
        // flat cream and the whole street lit up like paper
        // toneMapped:false — a lit window is a LIGHT SOURCE, and running it
        // through the tone curve with everything else landed it at the same
        // value as pale paint. Letting it clip is what makes it read as lit.
        place(lit, new THREE.MeshBasicMaterial({ map: paneTex, toneMapped: false }), true);
        // 2026-08-06: this was a near-mirror (roughness 0.12, env 1.6) over a
        // near-white base, so on a night city every unlit pane sampled the
        // warm sky and came back a streaky brown panel — the windows read as
        // WOOD, which is the opposite of the depth the reveal just bought.
        // Real glass at night is nearly black and only catches a sheen at
        // grazing angles: dark base, environment demoted to a highlight.
        // 2026-08-06: this was metalness 0.6 at envMapIntensity 1.6. A metal
        // has no diffuse and tints its reflection by its base colour, so each
        // unlit pane became a coloured mirror of a warm night sky and the
        // whole grid read as WOOD PANELLING — the opposite of the depth the
        // reveal had just bought. Glass is a DIELECTRIC: metalness 0, so the
        // dark blue comes through and the environment is only a sheen.
        // The base stays white because the per-instance colour above is what
        // carries the tint; darkening both would crush the panes to black.
        // Glass wants the same treatment: a whole city of panes at one
        // roughness reads as printed-on. Three grades of grime, split by
        // instance so the tower still draws in three calls rather than one
        // per window.
        const _thirds = [[], [], []];
        dark.forEach((w9, i9) => _thirds[i9 % 3].push(w9));
        [[0.16, 0.62], [0.30, 0.42], [0.46, 0.26]].forEach(([rg, ev], gi) => {
          place(_thirds[gi], new THREE.MeshStandardMaterial({ map: paneTex,
            roughness: rg, metalness: 0.0, envMapIntensity: ev,
            color: 0xffffff }), false);
        });
      }
    }
    if (wallBuckets.some(b => b.length) || capGeos.length) {
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
        const _accW = window.__accent !== null && window.__accent !== undefined
          ? '#' + window.__accent.toString(16).padStart(6, '0') : null;
        fx.fillStyle = lit ? (_accW && rngW() < 0.5 ? _accW : '#e8d9a8')
                           : (rngW() < 0.5 ? '#2c3138' : '#3d4550');
        fx.fillRect(x, y, 40, 76);
        fx.strokeStyle = '#5b5b60'; fx.lineWidth = 3; fx.strokeRect(x, y, 40, 76);
        fx.fillStyle = '#77767c'; fx.fillRect(x - 4, y + 76, 48, 6);   // sill
        if (lit) {
          ex.fillStyle = (window.__accent !== null && window.__accent !== undefined
            && rngW() < 0.6)
            ? '#' + window.__accent.toString(16).padStart(6, '0') : '#cfa96a';
          ex.fillRect(x, y, 40, 76);
        }
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
      // r13 calibrated per family by eye; r15 replaced those numbers with the
      // measured ones in _FTILE above, so the material repeat and the UVs
      // baked into the walls cannot drift apart — they read the same table.
      const _fSize = {};
      _FFAM.forEach((n, i) => { if (n) _fSize[n] = [_FTILE[i][0], _FTILE[i][1]]; });
      const _fTex = (n, suffix) => {
        const t = _fLoad.load('textures/' + n + (suffix || '') + '.jpg');
        const [tw, th] = _fSize[n] || [12, 8];
        t.wrapS = t.wrapT = THREE.RepeatWrapping;
        t.repeat.set(1 / tw, 1 / th);
        if (!suffix) t.colorSpace = THREE.SRGBColorSpace;
        t.anisotropy = renderer.capabilities.getMaxAnisotropy();
        return t;
      };
      // negative Y: metricWallUV runs V UPWARD (so the photo is the right way
      // up on the wall), where ExtrudeGeometry's default ran it downward.
      // The tangent frame follows the UVs, so without the sign flip every
      // window reveal derived from the photo would light as if it PROTRUDED.
      const _fPair = (n) => ({ map: _fTex(n), normalMap: _fTex(n, '_n'),
        normalScale: new THREE.Vector2(0.6, -0.6) });
      // Only the families that actually have geometry get built. Since the
      // masonry families became punched geometry, loading all seven photo
      // sets was ~48MB of VRAM and twelve texture decodes for materials
      // nothing referenced. (2026-08-06 r3)
      const _wallSpec = [null, [0.35, 0.55], [0.9, 0.03], [0.85, 0.04],
        [0.3, 0.6], [0.92, 0.02], [0.88, 0.03], [0.8, 0.04]];
      const _wallMats = _wallSpec.map((sp, bi) => {
        if (!wallBuckets[bi].length) return null;
        if (bi === 0) {
          return new THREE.MeshStandardMaterial({ vertexColors: true, map: facadeTex,
            emissive: 0xffc873, emissiveMap: litTex, emissiveIntensity: 0.4,
            roughness: 0.85, metalness: 0.08 });
        }
        return new THREE.MeshStandardMaterial({ ..._fPair(_FFAM[bi]),
          vertexColors: true, roughness: sp[0], metalness: sp[1] });
      });
      // ── FACADE RELIEF, DERIVED FROM THE PHOTO (2026-08-05) ───────────────
      // Ported from tools/facadelab. The lab's finding is that RELIEF, not
      // albedo, is what stops an extruded footprint reading as a box: window
      // reveals and storey ledges have to catch raking light and cast their
      // own shadows. The lab draws those reveals by hand, which it can only do
      // because it also draws its own albedo.
      //
      // Here the albedo is a photo, so hand-drawn reveals would land in the
      // wrong places — the exact misalignment r13 already hit with the night
      // glow ('blotchy orange smears'). The relief is therefore DERIVED from
      // each photo. A facade photo is LIT, and on a lit facade whatever
      // protrudes is bright and whatever is recessed sits in shadow, so the
      // baked lighting IS a height field. High-passing the luminance (which
      // discards the photo's overall gradient and keeps its local structure)
      // recovers it aligned by construction — for brick, stone and glass
      // alike, without needing to know what a window looks like.
      //
      // Once per FAMILY, not per building: seven texture sets for an entire
      // city, so the merged facade buckets still draw as one mesh each and
      // VRAM does not scale with the number of buildings.
      const _RFAMS = _FFAM.map((n, i) => [i, n])
        .filter(e => e[1] && wallBuckets[e[0]].length);
      {
        const AN = 512;                 // analysis + normal-map resolution
        const AO_N = 256;               // AO/roughness are low-frequency
        // wrapping separable box blur: the facade tiles, so a clamped blur
        // would leave a visible band down every seam in the city
        const boxBlur = (src, R) => {
          const tmp = new Float32Array(AN * AN), out = new Float32Array(AN * AN);
          const inv = 1 / (2 * R + 1);
          const wrap = v => ((v % AN) + AN) % AN;
          for (let y = 0; y < AN; y++) {
            const row = y * AN;
            let acc = 0;
            for (let k = -R; k <= R; k++) acc += src[row + wrap(k)];
            for (let x = 0; x < AN; x++) {
              tmp[row + x] = acc * inv;
              acc -= src[row + wrap(x - R)];
              acc += src[row + wrap(x + R + 1)];
            }
          }
          for (let x = 0; x < AN; x++) {
            let acc = 0;
            for (let k = -R; k <= R; k++) acc += tmp[wrap(k) * AN + x];
            for (let y = 0; y < AN; y++) {
              out[y * AN + x] = acc * inv;
              acc -= tmp[wrap(y - R) * AN + x];
              acc += tmp[wrap(y + R + 1) * AN + x];
            }
          }
          return out;
        };
        const lumOf = (img, n) => {
          const c = document.createElement('canvas');
          c.width = c.height = n;
          const g = c.getContext('2d', { willReadFrequently: true });
          g.drawImage(img, 0, 0, n, n);
          return g.getImageData(0, 0, n, n).data;
        };
        for (const [mi, fn] of _RFAMS) {
          _fLoad.load('textures/' + fn + '.jpg', (t2) => {
            // the _n companion carries the fine grain (brick courses, stone
            // pitting) that a high-pass at this radius cannot see. Blended in
            // rather than replaced, so the derived relief supplies the storey
            // scale and the photo's own map supplies the millimetre scale.
            _fLoad.load('textures/' + fn + '_n.jpg', (tn) => {
              try {
                const d = lumOf(t2.image, AN);
                const dn = lumOf(tn.image, AN);
                // these two loads exist only to be READ; the material keeps its
                // own copy of the albedo and gets a generated normal below
                t2.dispose(); tn.dispose();
                const L = new Float32Array(AN * AN);
                for (let i = 0, p = 0; i < AN * AN; i++, p += 4) {
                  L[i] = (0.299 * d[p] + 0.587 * d[p + 1] + 0.114 * d[p + 2]) / 255;
                }
                const Lb = boxBlur(L, 14);
                const H0 = new Float32Array(AN * AN);
                for (let i = 0; i < AN * AN; i++) {
                  H0[i] = Math.max(-1, Math.min(1, (L[i] - Lb[i]) * 3.4));
                }
                // JPEG grain is high-pass too, so it survives the filter and a
                // Sobel turns it into per-pixel noise that shimmers across a
                // whole wall once normalScale is high enough to be worth
                // having. Facade relief is a storey-scale feature; smoothing
                // below that scale costs nothing real.
                const H = boxBlur(H0, 2);
                // WINDOWNESS: recessed (locally dark) = glass. Drives both
                // the gloss and the occlusion, which is the lab's point that
                // one uniform sheen across a facade is what reads as plastic.
                const W = new Float32Array(AN * AN);
                for (let i = 0; i < AN * AN; i++) W[i] = Math.max(0, Math.min(1, -H[i] * 1.6));
                const Wb = boxBlur(W, 5);

                // ---- normal map: Sobel of the height field, plus the photo's
                const nc = document.createElement('canvas');
                nc.width = nc.height = AN;
                const ng = nc.getContext('2d');
                const nimg = ng.createImageData(AN, AN);
                const at = (x, y) => H[(((y % AN) + AN) % AN) * AN + (((x % AN) + AN) % AN)];
                for (let y = 0; y < AN; y++) for (let x = 0; x < AN; x++) {
                  const gx = (at(x + 1, y - 1) + 2 * at(x + 1, y) + at(x + 1, y + 1))
                           - (at(x - 1, y - 1) + 2 * at(x - 1, y) + at(x - 1, y + 1));
                  const gy = (at(x - 1, y + 1) + 2 * at(x, y + 1) + at(x + 1, y + 1))
                           - (at(x - 1, y - 1) + 2 * at(x, y - 1) + at(x + 1, y - 1));
                  const p = (y * AN + x) * 4;
                  // tangent-space linear blend: offsets add, then re-centre
                  const bx = (dn[p] / 255 - 0.5) * 0.32;
                  const by = (dn[p + 1] / 255 - 0.5) * 0.32;
                  const nx = Math.max(-0.5, Math.min(0.5, -gx * 0.30 + bx));
                  const ny = Math.max(-0.5, Math.min(0.5, gy * 0.30 + by));
                  nimg.data[p] = (nx + 0.5) * 255;
                  nimg.data[p + 1] = (ny + 0.5) * 255;
                  nimg.data[p + 2] = 255;
                  nimg.data[p + 3] = 255;
                }
                ng.putImageData(nimg, 0, 0);

                // ---- roughness + AO, at quarter area (both low-frequency)
                const rc = document.createElement('canvas');
                rc.width = rc.height = AO_N;
                const rg = rc.getContext('2d');
                const rimg = rg.createImageData(AO_N, AO_N);
                const ac = document.createElement('canvas');
                ac.width = ac.height = AO_N;
                const ag = ac.getContext('2d');
                const aimg = ag.createImageData(AO_N, AO_N);
                const base = _wallMats[mi].roughness;
                const st = AN / AO_N;
                for (let y = 0; y < AO_N; y++) for (let x = 0; x < AO_N; x++) {
                  const s = (y * st) * AN + (x * st);
                  // glass is near-mirror, the masonry around it stays matte —
                  // the single biggest reason a facade stops looking printed
                  const r = base * (1 - 0.72 * W[s]);
                  const o = 1 - 0.55 * Wb[s];
                  const p = (y * AO_N + x) * 4;
                  rimg.data[p] = rimg.data[p + 1] = rimg.data[p + 2] = r * 255;
                  aimg.data[p] = aimg.data[p + 1] = aimg.data[p + 2] = o * 255;
                  rimg.data[p + 3] = aimg.data[p + 3] = 255;
                }
                rg.putImageData(rimg, 0, 0);
                ag.putImageData(aimg, 0, 0);
                // GRIME drives roughness, not colour: a dirt streak that stays
                // glossy reads as wet paint (facadelab). Vertical streaking
                // under sills is what stops a wall looking freshly extruded.
                const rngG = mulberry32(SPEC.seed + 850 + mi);
                rg.globalAlpha = 0.5;
                for (let i = 0; i < 90; i++) {
                  rg.fillStyle = `rgba(255,255,255,${0.10 + rngG() * 0.22})`;
                  rg.fillRect(rngG() * AO_N, rngG() * AO_N,
                              1 + rngG() * 3, 15 + rngG() * 70);
                }
                rg.globalAlpha = 1;

                // ---- LIT WINDOWS, SHAPED BY THE MASK (2026-08-05)
                // r13 lit whole 16px cells of a fixed grid. That grid is not
                // any photo's window grid, so the glow landed as rectangles
                // sitting BETWEEN windows — invisible while the walls were
                // black, obvious the moment they were lit. The windowness mask
                // is already aligned to the real openings, so it supplies the
                // SHAPE and the coarse grid is demoted to only choosing which
                // ones are switched on.
                let ec2 = null;
                if (SPEC.world.sky === 'night' || SPEC.world.sky === 'dusk') {
                  ec2 = document.createElement('canvas');
                  ec2.width = ec2.height = AO_N;
                  const eg = ec2.getContext('2d');
                  const eimg = eg.createImageData(AO_N, AO_N);
                  const CG = 16, NC = Math.ceil(AO_N / CG);
                  const rngL = mulberry32(SPEC.seed + 404 + mi);
                  const on = new Uint8Array(NC * NC), hue = new Float32Array(NC * NC);
                  for (let i = 0; i < NC * NC; i++) {
                    on[i] = rngL() < 0.32 ? 1 : 0;
                    hue[i] = rngL();
                  }
                  for (let y = 0; y < AO_N; y++) for (let x = 0; x < AO_N; x++) {
                    const ci = ((y / CG) | 0) * NC + ((x / CG) | 0);
                    // the BLURRED mask, so a whole pane lights rather than the
                    // one darkest sliver inside it — a lit window is a filled
                    // rectangle of light, not an outline
                    const w = Wb[(y * st) * AN + (x * st)];
                    const p = (y * AO_N + x) * 4;
                    const lit = on[ci] && w > 0.20 ? Math.min(1, (w - 0.20) * 3.4) : 0;
                    const warm = hue[ci] < 0.75;
                    eimg.data[p] = lit * (warm ? 232 : 184);
                    eimg.data[p + 1] = lit * (warm ? 178 : 207);
                    eimg.data[p + 2] = lit * (warm ? 104 : 224);
                    eimg.data[p + 3] = 255;
                  }
                  eg.putImageData(eimg, 0, 0);
                }

                const m = _wallMats[mi];
                const mk = (cv, ch) => {
                  const t = new THREE.CanvasTexture(cv);
                  t.wrapS = t.wrapT = THREE.RepeatWrapping;
                  t.repeat.copy(m.map.repeat);
                  t.anisotropy = renderer.capabilities.getMaxAnisotropy();
                  if (ch !== undefined) t.channel = ch;
                  return t;
                };
                if (m.normalMap) m.normalMap.dispose();
                m.normalMap = mk(nc);
                // the photo's own _n shipped at 0.6 and read as a faint
                // texture; the derived map carries actual window reveals, so
                // it is worth pushing to where raking light bites
                m.normalScale.set(1.35, -1.35);   // see _fPair: V runs upward
                m.roughnessMap = mk(rc);
                m.roughness = 1.0;          // absolute value lives in the map
                m.aoMap = mk(ac, 1);        // channel 1 => reads uv1
                m.aoMapIntensity = 0.85;
                // glass needs something to reflect or it resolves to a flat
                // dark panel however good the albedo is (facadelab)
                m.envMapIntensity = /glass/.test(fn) ? 1.5 : 0.9;
                if (ec2) {
                  if (m.emissiveMap) m.emissiveMap.dispose();
                  m.emissive = new THREE.Color(0xffffff);
                  m.emissiveMap = mk(ec2);
                  m.emissiveMap.colorSpace = THREE.SRGBColorSpace;
                  m.emissiveIntensity = 0.85;
                }
                m.needsUpdate = true;
              } catch (e) { /* relief is an enhancement, never a hard gate */ }
            });
          });
        }
      }
      // r13's night-window glow lived here. It is now produced by the
      // facade-relief pass above, from the same windowness mask that
      // drives the reveals — one image analysis, and the glow cannot
      // drift out of alignment with the relief because they share a mask.
      for (let bi = 0; bi < 8; bi++) {
        if (!wallBuckets[bi].length) continue;
        const wg = mergeGeometries(wallBuckets[bi], false);
        // aoMap samples the SECOND uv set. ExtrudeGeometry ships only one, so
        // without this the ambient occlusion derived above is silently
        // ignored — no error, just a flatter city and wasted texture memory
        // (facadelab, 2026-08-05). The extrude UVs are already in metres, so
        // copying them is exactly the mapping the AO map was built against.
        wg.setAttribute('uv1', wg.attributes.uv);
        const wm = new THREE.Mesh(wg, _wallMats[bi]);
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
      // ── PARAPETS (2026-08-06, the outline half of the facade work) ───────
      // The cornice above hangs a ledge UNDER the roofline. What was still
      // missing is the wall that stands ABOVE it: on a real building the
      // facade continues past the roof deck as a 0.8-1.2m parapet, and the
      // roof you never see is behind it. Without one the roofline is a clean
      // shear against the sky, which is the single strongest "extruded box"
      // read — and unlike everything else on a facade, a normal map cannot
      // fake it, because it is a silhouette.
      // One InstancedMesh of unit boxes scaled per edge: whole city, 1 draw
      // call, no colliders (nothing can reach roof height on foot).
      if (capRings.length) {
        const PH = 0.95, PT = 0.42, PCAP = 1200;
        const par = new THREE.InstancedMesh(
          new THREE.BoxGeometry(1, 1, 1),
          new THREE.MeshStandardMaterial({ color: 0x6b6760, roughness: 0.93,
            metalness: 0.02, vertexColors: false }), PCAP);
        const MP = new THREE.Matrix4(), QP = new THREE.Quaternion();
        const EP = new THREE.Euler(), SP = new THREE.Vector3(), VP = new THREE.Vector3();
        let np = 0;
        for (const [pts, topY] of capRings) {
          if (np >= PCAP) break;
          let ccx = 0, ccz = 0;
          for (const q of pts) { ccx += q[0]; ccz += q[1]; }
          ccx /= pts.length; ccz /= pts.length;
          for (let i = 0; i < pts.length && np < PCAP; i++) {
            const a = pts[i], c = pts[(i + 1) % pts.length];
            const dx = c[0] - a[0], dz = c[1] - a[1];
            const L = Math.hypot(dx, dz);
            if (L < 1.5) continue;
            const ux = dx / L, uz = dz / L;
            const mx = (a[0] + c[0]) / 2, mz = (a[1] + c[1]) / 2;
            // inward = toward the footprint centroid, so the parapet sits ON
            // the slab instead of hanging off it
            let ix = -uz, iz = ux;
            if ((mx - ccx) * ix + (mz - ccz) * iz > 0) { ix = -ix; iz = -iz; }
            const off = PT / 2 - 0.05;      // 5cm proud: catches raking light
            EP.set(0, Math.atan2(-uz, ux), 0);
            QP.setFromEuler(EP);
            // overlap the corners by PT so two runs meet in a solid quoin
            SP.set(L + PT, PH, PT);
            VP.set(mx + ix * off, topY + PH / 2 - 0.12, mz + iz * off);
            MP.compose(VP, QP, SP);
            par.setMatrixAt(np++, MP);
          }
        }
        par.count = np;
        par.instanceMatrix.needsUpdate = true;
        par.castShadow = par.receiveShadow = true;
        scene.add(par);
        // ROOFTOP BULKHEADS: the stair/lift head that pokes above every real
        // roof. Cheap, but it is a second silhouette event above the parapet,
        // which is what stops a skyline reading as a bar chart.
        const rngK = mulberry32(SPEC.seed + 313);
        const blk = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1),
          new THREE.MeshStandardMaterial({ color: 0x5d5a55, roughness: 0.9 }), 160);
        let nk = 0;
        for (const [pts, topY] of capRings) {
          if (nk >= 160) break;
          if (rngK() > 0.45) continue;
          let mnx = 1e9, mnz = 1e9, mxx = -1e9, mxz = -1e9, ccx = 0, ccz = 0;
          for (const q of pts) {
            mnx = Math.min(mnx, q[0]); mxx = Math.max(mxx, q[0]);
            mnz = Math.min(mnz, q[1]); mxz = Math.max(mxz, q[1]);
            ccx += q[0]; ccz += q[1];
          }
          ccx /= pts.length; ccz /= pts.length;
          const bw = Math.min(4.2, (mxx - mnx) * 0.34), bd3 = Math.min(4.2, (mxz - mnz) * 0.34);
          if (bw < 2 || bd3 < 2) continue;
          const bh3 = 2.4 + rngK() * 1.4;
          SP.set(bw, bh3, bd3);
          QP.identity();
          VP.set(ccx + (rngK() - 0.5) * (mxx - mnx - bw) * 0.5, topY + bh3 / 2,
                 ccz + (rngK() - 0.5) * (mxz - mnz - bd3) * 0.5);
          MP.compose(VP, QP, SP);
          blk.setMatrixAt(nk++, MP);
        }
        blk.count = nk;
        blk.instanceMatrix.needsUpdate = true;
        blk.castShadow = blk.receiveShadow = true;
        scene.add(blk);
      }
      // ── THE FACADE AS GEOMETRY, NOT AS A PHOTO (2026-08-06 r2) ───────────
      // A photograph has no parallax and no silhouette. Every depth cue in it
      // was baked at the photographer's light angle, so it does not move when
      // you move and it does not change when the sun does — which is exactly
      // the two things the eye checks. That is why a well-lit, correctly
      // scaled photo facade STILL reads as a box with a picture on it.
      //
      // So the wall gets real projecting geometry, lit by the real scene
      // lights: a plinth the building stands on, a course at every storey
      // line, and a pier at every corner. Cheap in the only way that matters
      // — five instanced meshes for an entire city.
      //
      // These land on the STOREY GRID rather than on individual windows, and
      // that is a deliberate limit. The storey period measures cleanly out of
      // every photo; the bay period does not (windows come in irregular pairs
      // and the detector locks onto the wrong rhythm), so window-aligned
      // sills would sit on brick as often as on glass. Horizontal courses
      // need only the number this engine already trusts enough to quantise
      // building heights to.
      if (feCand.length) {
        const CAP_B = 6000, CAP_F = 3600, CAP_P = 900, CAP_L = 1400;
        // Untinted pale stone made the trim read as a separate pile of slabs
        // leaning on the building. Each instance is coloured from its own
        // building's tint (a shade lighter, the way real stone trim sits
        // against brick), so the courses belong to the wall they grow out of.
        const stoneM = new THREE.MeshStandardMaterial({ color: 0xffffff,
          roughness: 0.95, metalness: 0.02 });
        const finM = new THREE.MeshStandardMaterial({ color: 0xffffff,
          roughness: 0.42, metalness: 0.72 });
        const U1 = new THREE.BoxGeometry(1, 1, 1);
        const mkI = (mat, n) => {
          const im = new THREE.InstancedMesh(U1, mat, n);
          im.castShadow = im.receiveShadow = true;
          return im;
        };
        const band = mkI(stoneM, CAP_B);      // storey course
        const fin = mkI(finM, CAP_F);         // curtain-wall mullion
        const pier = mkI(stoneM, CAP_P);      // corner pier / quoin
        const base = mkI(stoneM, CAP_L);      // plinth
        const bcap = mkI(stoneM, CAP_L);      // plinth cap
        let nb2 = 0, nf2 = 0, npr = 0, nbs = 0;
        const MB = new THREE.Matrix4(), QB = new THREE.Quaternion();
        const EB = new THREE.Euler(), SB = new THREE.Vector3(), VB = new THREE.Vector3();
        // a box of thickness t whose centre sits this far along the outward
        // normal projects exactly `p` proud of the wall and stays keyed into
        // it by the remainder — floating trim is worse than none
        const seat = (p, t) => p - t / 2;
        const trimC = new THREE.Color();
        for (const [pts, bcx, bcz, gy7, h7, bkt7, tint7] of feCand) {
          trimC.copy(tint7 || new THREE.Color(0x8a857c)).multiplyScalar(1.18);
          const T7 = _FTILE[bkt7] || _FTILE[0];
          const stH = T7[1] / T7[3], bayW7 = T7[0] / T7[2];
          const nSt7 = Math.max(1, Math.round(h7 / stH));
          const glassy = _GLASSY.has(bkt7);
          // A LOW base course, not a whole storey (2026-08-06 r3): a
          // full-height plinth boarded the shopfronts up and the street lost
          // its ground floor. Real buildings have a water table around knee
          // to waist height and glass above it.
          const PB = _FACADE[bkt7] ? 1.05 : Math.min(Math.max(stH, 3.2), 5.5);
          let ccx = 0, ccz = 0;
          for (const q of pts) { ccx += q[0]; ccz += q[1]; }
          ccx /= pts.length; ccz /= pts.length;
          for (let i = 0; i < pts.length; i++) {
            const a = pts[i], c = pts[(i + 1) % pts.length];
            const dx = c[0] - a[0], dz = c[1] - a[1];
            const L7 = Math.hypot(dx, dz);
            if (L7 < 2.2) continue;
            const ux = dx / L7, uz = dz / L7;
            const mx = (a[0] + c[0]) / 2, mz = (a[1] + c[1]) / 2;
            let nx = -uz, nz = ux;                    // outward
            if ((mx - ccx) * nx + (mz - ccz) * nz < 0) { nx = -nx; nz = -nz; }
            EB.set(0, Math.atan2(-uz, ux), 0);        // local X runs the edge
            QB.setFromEuler(EB);
            const put = (im, idx, along, y, sx, sy, sz, d) => {
              SB.set(sx, sy, sz);
              VB.set(a[0] + ux * along + nx * d, y, a[1] + uz * along + nz * d);
              MB.compose(VB, QB, SB);
              im.setMatrixAt(idx, MB);
              im.setColorAt(idx, trimC);
            };
            // PLINTH: a building standing ON something instead of sprouting
            // out of the pavement. Also hides the ground-floor seam where the
            // facade photo used to run straight into the kerb.
            if (nbs < CAP_L) {
              put(base, nbs, L7 / 2, gy7 + PB / 2, L7 + 0.3, PB, 0.26, seat(0.13, 0.26));
              put(bcap, nbs, L7 / 2, gy7 + PB, L7 + 0.48, 0.14, 0.34, seat(0.20, 0.34));
              nbs++;
            }
            if (glassy) {
              // MULLION FINS: the vertical blades that give a curtain wall its
              // corduroy of shadow and its only real depth. Spaced on the
              // photo's own pane rhythm so they agree with the printed glazing.
              const nf3 = Math.max(2, Math.round(L7 / Math.max(bayW7, 1.6)));
              for (let k = 0; k <= nf3 && nf2 < CAP_F; k++) {
                put(fin, nf2++, (k / nf3) * L7, gy7 + PB + (h7 - PB) / 2,
                    0.13, h7 - PB, 0.26, seat(0.17, 0.26));
              }
            } else if (!_FACADE[bkt7]) {
              // STOREY COURSES, for any family that did NOT get a punched
              // facade. Where the wall is a real grid of piers and spandrels
              // the spandrels already ARE the courses, and stacking these on
              // top of them just doubles every shadow line.
              for (let s = 1; s < nSt7 && nb2 < CAP_B; s++) {
                const y7 = gy7 + s * stH;
                if (y7 < gy7 + PB + 0.4) continue;        // swallowed by the plinth
                // Deep enough to catch light and throw a line of shadow, no
                // deeper: at the first tuning these projected ~20cm and the
                // building read as a stack of pancakes. A sill course is a
                // few centimetres of stone, not a balcony.
                const major = (s % 3) === 0;             // every third reads deeper
                put(band, nb2++, L7 / 2, y7,
                    L7 + (major ? 0.28 : 0.16), major ? 0.14 : 0.085,
                    major ? 0.24 : 0.17,
                    seat(major ? 0.10 : 0.055, major ? 0.24 : 0.17));
              }
            }
          }
          // CORNER PIERS: real buildings turn a corner with something — a
          // quoin, a pilaster, a structural pier. An unarticulated 90 deg
          // arris is the most box-like thing a building can do, and it is the
          // first thing the eye lands on at street level.
          if (h7 >= 7) {
            for (let i = 0; i < pts.length && npr < CAP_P; i++) {
              const pv = pts[(i - 1 + pts.length) % pts.length];
              const q = pts[i], nx2 = pts[(i + 1) % pts.length];
              const e1x = q[0] - pv[0], e1z = q[1] - pv[1];
              const e2x = nx2[0] - q[0], e2z = nx2[1] - q[1];
              const l1 = Math.hypot(e1x, e1z), l2 = Math.hypot(e2x, e2z);
              if (l1 < 2.2 || l2 < 2.2) continue;
              // only where the wall actually TURNS — a near-straight vertex
              // from a noisy OSM trace would stud the wall with random posts
              const dot = (e1x * e2x + e1z * e2z) / (l1 * l2);
              if (dot > 0.72) continue;
              const w7 = glassy ? 0.36 : 0.52;
              SB.set(w7, h7, w7);
              EB.set(0, Math.atan2(-e1z / l1, e1x / l1), 0);
              QB.setFromEuler(EB);
              VB.set(q[0], gy7 + h7 / 2, q[1]);
              MB.compose(VB, QB, SB);
              pier.setColorAt(npr, trimC);
              pier.setMatrixAt(npr++, MB);
            }
          }
        }
        band.count = nb2; fin.count = nf2; pier.count = npr;
        base.count = nbs; bcap.count = nbs;
        for (const im of [band, fin, pier, base, bcap]) {
          im.instanceMatrix.needsUpdate = true;
          if (im.instanceColor) im.instanceColor.needsUpdate = true;
          if (im.count) scene.add(im);
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
        // built buildings only — a bench against a wall that was culled is a
        // bench in the middle of an empty plaza (2026-08-06)
        for (const [bpts] of feCand) {
          const b = { pts: bpts };
          if (nd >= 26 && ncn >= 52 && nb >= 26) break;
          if (rngF() > 0.5) continue;
          let mnx = 1e9, mnz = 1e9, mxx = -1e9, mxz = -1e9;
          for (const p of b.pts) {
            mnx = Math.min(mnx, p[0]); mxx = Math.max(mxx, p[0]);
            mnz = Math.min(mnz, p[1]); mxz = Math.max(mxz, p[1]);
          }
          const cx4 = (mnx + mxx) / 2, cz4 = (mnz + mxz) / 2;
          if ((mxx - mnx) < 4 || (mxz - mnz) < 4) continue;
          let bd2 = 1e9, bx2 = 0, bz2 = 0;
          for (const r of OSM.roads || []) for (const p of r.pts) {
            const d = (p[0] - cx4) ** 2 + (p[1] - cz4) ** 2;
            if (d < bd2) { bd2 = d; bx2 = p[0]; bz2 = p[1]; }
          }
          if (bd2 > 42 * 42) continue;
          // 2026-08-06: this used the bbox projection the fire escapes were
          // already fixed away from, so on any non-rectangular footprint the
          // bench was inside the lobby. Same edge picker now.
          const fe2 = faceEdge(b.pts, cx4, cz4, bx2, bz2, 3);
          if (!fe2) continue;
          const nxx = fe2.nx, nzz = fe2.nz;
          // slide along the wall a little so items don't stack with awnings
          const sx4 = -nzz, sz4 = nxx;
          const slide = (rngF() - 0.5) * Math.max(0, fe2.len - 2.4);
          const fx2 = fe2.x + nxx * 0.9 + sx4 * slide;
          const fz2 = fe2.z + nzz * 0.9 + sz4 * slide;
          {
            if (Math.hypot(fx2, fz2) < 12 || inFootprint(fx2, fz2)) continue;
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
      // the scene audit (init scope, defined much later) needs this test but
      // cannot see a block-scoped const — hand it out through window
      window.__onRoadChk = _onRoad;
      // ── IS THIS POINT ON A CROSSING STREET? (2026-08-06) ───────────────
      // Kerbs and the pavement band have to stop where another street cuts
      // through, and _onRoad cannot answer that: the test point sits only
      // ~0.4m outside its OWN carriageway, so any pad wide enough to catch a
      // real crossing also rejects every kerb on the street it belongs to.
      // That is why the pad was pinned at 0.22, and why kerb bars were left
      // lying across wide or oblique junctions. Segments running nearly
      // PARALLEL to the piece are the same street (or its continuation) by
      // definition and are skipped, which frees the pad to be honest.
      const _onCross = (px, pz, ux, uz, pad) => {
        for (const s of _roadSegs) {
          const L2 = Math.hypot(s[2] - s[0], s[3] - s[1]);
          if (L2 < 0.5) continue;
          const vx = (s[2] - s[0]) / L2, vz = (s[3] - s[1]) / L2;
          if (Math.abs(vx * ux + vz * uz) > 0.85) continue;
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
      // published for the minimap, which runs far below this and must not
      // draw blocks the cull never built
      window.__builtFootprints = feCand.map(e => ({ pts: e[0] }));
      // r8 AWNINGS: tilted storefront canopies on road-facing building
      // bases — with plinths + these, ground floors read as SHOPS instead
      // of texture meeting pavement. Instanced, per-instance color.
      if (OSM.buildings && OSM.buildings.length && OSM.roads && OSM.roads.length) {
        const rngA = mulberry32(SPEC.seed + 606);
        // 2026-08-06: 3.4m was narrower than the shop it belonged to, so
        // it read as a canopy over a doorway. A real storefront awning
        // spans the whole bay and projects far enough to shade the glass.
        const awnG = new THREE.BoxGeometry(4.4, 0.18, 1.45);
        awnG.translate(0, 0, 0.72);
        const awnM = new THREE.MeshStandardMaterial({ roughness: 0.85 });
        const maxA = Math.min(OSM.buildings.length, 70);
        const awn = new THREE.InstancedMesh(awnG, awnM, maxA);
        // the muted set read as tasteful, which is the one thing a New
        // York awning never is -- these are the fascia palette
        const AC = [new THREE.Color(0xc8102e), new THREE.Color(0x0a7d3e),
                    new THREE.Color(0x1b52a4), new THREE.Color(0xd81b7a),
                    new THREE.Color(0xe8541f), new THREE.Color(0xf2b400),
                    new THREE.Color(0x00857a), new THREE.Color(0x141414)];
        const M4 = new THREE.Matrix4(), Q4 = new THREE.Quaternion();
        const E4 = new THREE.Euler(), S4 = new THREE.Vector3(1, 1, 1);
        let na = 0;
        // built buildings only, and only ones with a shop under them — an
        // awning over an apartment lobby is furniture nobody ordered
        for (const [bpts, cx2, cz2, gyA, hA, bktA, tintA2, progA, fstA, fcA9]
             of feCand) {
          if (na >= maxA) break;
          if (!fcA9) continue;                     // no shopfront, no awning
          if (rngA() > 0.8) continue;
          let mnx = 1e9, mnz = 1e9, mxx = -1e9, mxz = -1e9;
          for (const p of bpts) {
            mnx = Math.min(mnx, p[0]); mxx = Math.max(mxx, p[0]);
            mnz = Math.min(mnz, p[1]); mxz = Math.max(mxz, p[1]);
          }
          if ((mxx - mnx) < 4.4 || (mxz - mnz) < 4.4) continue;
          const b = { pts: bpts };
          // nearest road point -> awning faces the street
          let bd = 1e9, bx = 0, bz = 0;
          for (const r of OSM.roads) for (const p of r.pts) {
            const d = (p[0] - cx2) ** 2 + (p[1] - cz2) ** 2;
            if (d < bd) { bd = d; bx = p[0]; bz = p[1]; }
          }
          if (bd > 45 * 45) continue;
          // 2026-08-06: was the bbox projection, then a _polyEdgeD < 1.4m
          // rescue test that silently DROPPED every awning on a diagonal
          // footprint. Picking the real edge means none of them are lost.
          const fe = faceEdge(b.pts, cx2, cz2, bx, bz, 3.6);
          if (!fe) continue;
          const nx2 = fe.nx, nz2 = fe.nz;
          const slideA = (rngA() - 0.5) * Math.max(0, fe.len - 3.8);
          const ex = fe.x + nx2 * 0.05 - nz2 * slideA;
          const ez = fe.z + nz2 * 0.05 + nx2 * slideA;
          E4.set(-0.22, Math.atan2(nx2, nz2), 0);
          Q4.setFromEuler(E4);
          // 2026-08-07: the awning sat at 3.0m and the fascia sign at 2.7m,
          // so a 1.2m-deep canopy hung directly in FRONT of the shop name
          // and hid it from any street-level angle. Real storefronts stack
          // them the other way: canopy at head height, sign band above it.
          M4.compose(new THREE.Vector3(ex, hAt(ex, ez) + 2.35, ez), Q4, S4);
          awn.setMatrixAt(na, M4);
          awn.setColorAt(na, AC[Math.floor(rngA() * AC.length)]);
          na++;
        }
        awn.count = na;
        awn.instanceMatrix.needsUpdate = true;
        // -- PROJECTING FLAGS (2026-08-06) -------------------------------
        // Every Lower Manhattan photo has them: a staff angled up out of the
        // facade above head height with a flag hanging off it. They break the
        // wall plane at exactly the height the follow-cam looks at, and cost
        // two instanced meshes for the whole city.
        {
          const rngFl = mulberry32(SPEC.seed + 4141);
          const maxF = 26;
          const poleG2 = new THREE.CylinderGeometry(0.045, 0.045, 2.1, 6);
          poleG2.rotateZ(Math.PI / 2);            // lie along local X...
          poleG2.rotateY(Math.PI / 2);            // ...then out along local Z
          poleG2.translate(0, 0, 1.05);
          const clothG = new THREE.BoxGeometry(0.04, 0.62, 1.05);
          clothG.translate(0, -0.34, 1.35);
          const poleM2 = new THREE.MeshStandardMaterial({ color: 0x2a2c30,
            metalness: 0.7, roughness: 0.42 });
          const clothM = new THREE.MeshStandardMaterial({ roughness: 0.86,
            side: THREE.DoubleSide });
          const flP = new THREE.InstancedMesh(poleG2, poleM2, maxF);
          const flC = new THREE.InstancedMesh(clothG, clothM, maxF);
          const FC = [new THREE.Color(0xb22234), new THREE.Color(0x1b3a8a),
                      new THREE.Color(0xf2f2f2), new THREE.Color(0x0a7d3e),
                      new THREE.Color(0xf2b400)];
          const MF2 = new THREE.Matrix4(), QF2 = new THREE.Quaternion();
          const EF2 = new THREE.Euler(), SF2 = new THREE.Vector3(1, 1, 1);
          const VF2 = new THREE.Vector3();
          let nf2 = 0;
          for (const fc of feCand) {
            if (nf2 >= maxF) break;
            const bpts = fc[0], cxF = fc[1], czF = fc[2], gyF = fc[3], hF = fc[4];
            if (hF < 8) continue;
            if (rngFl() > 0.42) continue;
            let bdF = 1e9, bxF = 0, bzF = 0;
            for (const r of OSM.roads || []) for (const q of r.pts) {
              const d = (q[0] - cxF) ** 2 + (q[1] - czF) ** 2;
              if (d < bdF) { bdF = d; bxF = q[0]; bzF = q[1]; }
            }
            if (bdF > 44 * 44) continue;
            const feF = faceEdge(bpts, cxF, czF, bxF, bzF, 3.4);
            if (!feF) continue;
            // slide along the wall so a flag and a shop sign are not fighting
            // for the same square metre of facade
            const txF = -feF.nz, tzF = feF.nx;
            const slideF = (rngFl() - 0.5) * Math.max(0, feF.len - 3.0);
            const fxF = feF.x + txF * slideF, fzF = feF.z + tzF * slideF;
            EF2.set(-0.42, Math.atan2(feF.nx, feF.nz), 0, 'YXZ');
            QF2.setFromEuler(EF2);
            VF2.set(fxF, gyF + 4.6 + rngFl() * 1.2, fzF);
            MF2.compose(VF2, QF2, SF2);
            flP.setMatrixAt(nf2, MF2);
            flC.setMatrixAt(nf2, MF2);
            flC.setColorAt(nf2, FC[Math.floor(rngFl() * FC.length)]);
            nf2++;
          }
          flP.count = flC.count = nf2;
          flP.instanceMatrix.needsUpdate = true;
          flC.instanceMatrix.needsUpdate = true;
          if (flC.instanceColor) flC.instanceColor.needsUpdate = true;
          flP.castShadow = flC.castShadow = true;
          scene.add(flP); scene.add(flC);
          console.log('[game] flags: ' + nf2);
        }
        // ── SIDEWALK KIT (2026-08-06) ──────────────────────────────────
        // Three of the five reference photos are dominated by things that are
        // not buildings and not cars: a sidewalk shed over the pavement, an
        // A-board outside a shop, a rank of newspaper boxes, a standpipe on
        // the wall. They sit at eye level, which is where the follow-cam
        // lives, and their absence is why the pavement read as swept.
        // Everything here is merged or instanced: four draw calls total.
        {
          const rngK = mulberry32(SPEC.seed + 6161);
          const shedFrame = [], shedFascia = [];
          const boards = [], boxSpots = [], pipeSpots = [];
          for (const fc of feCand) {
            const bpts = fc[0], cxK = fc[1], czK = fc[2], gyK = fc[3];
            const hK = fc[4], shopK = fc[9];
            if (hK < 7) continue;
            let bdK = 1e9, bxK = 0, bzK = 0;
            for (const r of OSM.roads || []) for (const q of r.pts) {
              const d = (q[0] - cxK) ** 2 + (q[1] - czK) ** 2;
              if (d < bdK) { bdK = d; bxK = q[0]; bzK = q[1]; }
            }
            if (bdK > 42 * 42) continue;
            const feK = faceEdge(bpts, cxK, czK, bxK, bzK, 5.0);
            if (!feK) continue;
            const nxK = feK.nx, nzK = feK.nz;
            const txK = -nzK, tzK = nxK;              // along the wall
            const eLK = Math.min(feK.len, 20);
            // A SIDEWALK SHED, on about one building in six. Half of New York
            // is under one at any time and nothing else says the city is
            // being worked on rather than modelled.
            if (rngK() < 0.17 && eLK > 8) {
              const DECK = 3.9, DEP = 2.3;
              const nPost = Math.max(3, Math.round(eLK / 2.7));
              for (let k = 0; k <= nPost; k++) {
                const al = -eLK / 2 + k * (eLK / nPost);
                for (const dp of [0.25, DEP - 0.25]) {
                  const px7 = feK.x + txK * al + nxK * dp;
                  const pz7 = feK.z + tzK * al + nzK * dp;
                  const pg7 = new THREE.BoxGeometry(0.13, DECK, 0.13);
                  pg7.translate(px7, gyK + DECK / 2, pz7);
                  shedFrame.push(pg7);
                }
              }
              const dg7 = new THREE.BoxGeometry(eLK, 0.16, DEP);
              dg7.rotateY(Math.atan2(nxK, nzK));
              dg7.translate(feK.x + nxK * (DEP / 2), gyK + DECK, feK.z + nzK * (DEP / 2));
              shedFrame.push(dg7);
              const fg7 = new THREE.BoxGeometry(eLK, 0.62, 0.1);
              fg7.rotateY(Math.atan2(nxK, nzK));
              fg7.translate(feK.x + nxK * (DEP - 0.02), gyK + DECK + 0.36,
                            feK.z + nzK * (DEP - 0.02));
              shedFascia.push(fg7);
            }
            // freestanding kit lives ON the pavement, out from the wall
            const outK = 1.9 + rngK() * 0.7;
            const slideK = (rngK() - 0.5) * Math.max(0, eLK - 3);
            const fxK = feK.x + nxK * outK + txK * slideK;
            const fzK = feK.z + nzK * outK + tzK * slideK;
            if (!inBldg(fxK, fzK, 0.4) && !_onRoad(fxK, fzK, 0.5)
                && Math.hypot(fxK, fzK) > 12) {
              const yawK = Math.atan2(nxK, nzK);
              if (shopK && rngK() < 0.5) boards.push([fxK, fzK, yawK]);
              else if (rngK() < 0.4) boxSpots.push([fxK, fzK, yawK]);
            }
            // standpipe: on the wall, always, because every building has one
            if (rngK() < 0.55) {
              const sl2 = (rngK() - 0.5) * Math.max(0, eLK - 2);
              pipeSpots.push([feK.x + txK * sl2 + nxK * 0.18, gyK,
                              feK.z + tzK * sl2 + nzK * 0.18,
                              Math.atan2(nxK, nzK)]);
            }
          }
          if (shedFrame.length) {
            const fm7 = new THREE.Mesh(mergeGeometries(shedFrame, false),
              new THREE.MeshStandardMaterial({ color: 0x8e9298, metalness: 0.55,
                roughness: 0.6 }));
            fm7.castShadow = fm7.receiveShadow = true;
            scene.add(fm7);
            for (const g7 of shedFrame) g7.dispose();
            const fa7 = new THREE.Mesh(mergeGeometries(shedFascia, false),
              new THREE.MeshStandardMaterial({ color: 0x1f6b45, roughness: 0.88 }));
            fa7.castShadow = true;
            scene.add(fa7);
            for (const g7 of shedFascia) g7.dispose();
            console.log('[game] sidewalk sheds: ' + shedFascia.length);
          }
          // A-BOARD: two leaves leaning together, one instanced mesh
          if (boards.length) {
            const l1 = new THREE.BoxGeometry(0.62, 0.92, 0.04);
            l1.translate(0, 0, 0.13); l1.rotateX(0.20); l1.translate(0, 0.47, 0);
            const l2 = new THREE.BoxGeometry(0.62, 0.92, 0.04);
            l2.translate(0, 0, -0.13); l2.rotateX(-0.20); l2.translate(0, 0.47, 0);
            const ab = new THREE.InstancedMesh(mergeGeometries([l1, l2], false),
              new THREE.MeshStandardMaterial({ color: 0x2b2b2b, roughness: 0.9,
                side: THREE.DoubleSide }), Math.min(boards.length, 30));
            const MK = new THREE.Matrix4(), QK = new THREE.Quaternion();
            const EK = new THREE.Euler(), SK = new THREE.Vector3(1, 1, 1);
            const VK = new THREE.Vector3();
            let nb7 = 0;
            for (const bb of boards) {
              if (nb7 >= 30) break;
              EK.set(0, bb[2], 0); QK.setFromEuler(EK);
              VK.set(bb[0], hAt(bb[0], bb[1]), bb[1]);
              ab.setMatrixAt(nb7++, MK.compose(VK, QK, SK));
            }
            ab.count = nb7; ab.instanceMatrix.needsUpdate = true;
            ab.castShadow = true; scene.add(ab);
            l1.dispose(); l2.dispose();
            console.log('[game] a-boards: ' + nb7);
          }
          // NEWSPAPER BOXES: they come in ranks of two or three, never alone
          if (boxSpots.length) {
            const bxg = new THREE.BoxGeometry(0.44, 1.05, 0.42);
            bxg.translate(0, 0.52, 0);
            const CAPB = 44;
            const nb8 = new THREE.InstancedMesh(bxg,
              new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.25 }),
              CAPB);
            const BC = [new THREE.Color(0xc02a2a), new THREE.Color(0x1c5aa8),
                        new THREE.Color(0x2a2a2a), new THREE.Color(0x1f7a4a),
                        new THREE.Color(0xd8a416)];
            const MK2 = new THREE.Matrix4(), QK2 = new THREE.Quaternion();
            const EK2 = new THREE.Euler(), SK2 = new THREE.Vector3(1, 1, 1);
            const VK2 = new THREE.Vector3();
            let nn = 0;
            for (const bs2 of boxSpots) {
              const rank = 2 + Math.floor(rngK() * 2);
              for (let k = 0; k < rank && nn < CAPB; k++) {
                const off = (k - (rank - 1) / 2) * 0.5;
                const ox2 = bs2[0] + Math.cos(bs2[2]) * off;
                const oz2 = bs2[1] - Math.sin(bs2[2]) * off;
                EK2.set(0, bs2[2], 0); QK2.setFromEuler(EK2);
                VK2.set(ox2, hAt(ox2, oz2), oz2);
                nb8.setMatrixAt(nn, MK2.compose(VK2, QK2, SK2));
                nb8.setColorAt(nn, BC[Math.floor(rngK() * BC.length)]);
                nn++;
              }
            }
            nb8.count = nn; nb8.instanceMatrix.needsUpdate = true;
            if (nb8.instanceColor) nb8.instanceColor.needsUpdate = true;
            nb8.castShadow = true; scene.add(nb8);
            console.log('[game] newspaper boxes: ' + nn);
          }
          // STANDPIPE: the siamese fire connection, brass, on every wall
          if (pipeSpots.length) {
            const st1 = new THREE.CylinderGeometry(0.055, 0.055, 1.0, 8);
            st1.translate(0, 0.5, 0);
            const st2 = new THREE.CylinderGeometry(0.075, 0.075, 0.30, 8);
            st2.rotateZ(Math.PI / 2.6); st2.translate(-0.16, 1.05, 0.06);
            const st3 = new THREE.CylinderGeometry(0.075, 0.075, 0.30, 8);
            st3.rotateZ(-Math.PI / 2.6); st3.translate(0.16, 1.05, 0.06);
            const CAPP = 40;
            const sp7 = new THREE.InstancedMesh(mergeGeometries([st1, st2, st3], false),
              new THREE.MeshStandardMaterial({ color: 0xa8813c, metalness: 0.85,
                roughness: 0.38 }), CAPP);
            const MK3 = new THREE.Matrix4(), QK3 = new THREE.Quaternion();
            const EK3 = new THREE.Euler(), SK3 = new THREE.Vector3(1, 1, 1);
            const VK3 = new THREE.Vector3();
            let np2 = 0;
            for (const ps of pipeSpots) {
              if (np2 >= CAPP) break;
              EK3.set(0, ps[3], 0); QK3.setFromEuler(EK3);
              VK3.set(ps[0], ps[1], ps[2]);
              sp7.setMatrixAt(np2++, MK3.compose(VK3, QK3, SK3));
            }
            sp7.count = np2; sp7.instanceMatrix.needsUpdate = true;
            sp7.castShadow = true; scene.add(sp7);
            st1.dispose(); st2.dispose(); st3.dispose();
            console.log('[game] standpipes: ' + np2);
          }
        }
        if (awn.instanceColor) awn.instanceColor.needsUpdate = true;
        awn.castShadow = true;
        scene.add(awn);
      }
      // ── FIRE ESCAPES (2026-08-05, from facadelab) ────────────────────────
      // The lab's last and strongest street-level cue. A normal map cannot fix
      // an OUTLINE: where a facade meets the sky and where it meets the
      // street are the two places the eye checks for depth, and a zig-zag of
      // landings hung off the face is the one piece of geometry that breaks
      // the flat wall plane at exactly the height the follow-cam looks at.
      // Walk-ups only — a glass tower with a fire escape reads as a mistake.
      // Three instanced meshes for the whole city: +3 draw calls, no colliders
      // (every landing sits above head height, so nothing can walk into one).
      if (feCand.length && OSM.roads && OSM.roads.length) {
        const rngE = mulberry32(SPEC.seed + 4242);
        // brick / stone / limestone / concrete — the lab's brownstone+concrete
        // rule, mapped onto this runtime's seven families. Glass is excluded.
        const WALKUP = new Set([2, 3, 5, 6, 7]);
        const STOREY = 3.4, MAXB = 48, CAP = 260;
        const feM = new THREE.MeshStandardMaterial({ color: 0x1e2025,
          roughness: 0.8, metalness: 0.55 });
        // local +z is the outward wall normal after the yaw below, so the deck
        // is pushed forward half its depth to hang OFF the face rather than
        // straddle it
        const deckG = new THREE.BoxGeometry(2.7, 0.09, 1.15); deckG.translate(0, 0, 0.58);
        const railG = new THREE.BoxGeometry(2.7, 0.85, 0.07);
        const stairG = new THREE.BoxGeometry(0.85, 0.08, 3.0);
        const deck = new THREE.InstancedMesh(deckG, feM, CAP);
        const rail = new THREE.InstancedMesh(railG, feM, CAP);
        const stair = new THREE.InstancedMesh(stairG, feM, CAP);
        const MF = new THREE.Matrix4(), QF = new THREE.Quaternion();
        const EF = new THREE.Euler(), SF = new THREE.Vector3(1, 1, 1);
        const PF = new THREE.Vector3();
        let nf = 0;
        for (const [pts, cx6, cz6, gy6, h6, bkt6] of feCand) {
          if (nf >= CAP) break;
          if (!WALKUP.has(bkt6) || h6 < 9 || h6 > MAXB) continue;
          if (rngE() > 0.8) continue;
          let mnx = 1e9, mnz = 1e9, mxx = -1e9, mxz = -1e9;
          for (const q of pts) {
            mnx = Math.min(mnx, q[0]); mxx = Math.max(mxx, q[0]);
            mnz = Math.min(mnz, q[1]); mxz = Math.max(mxz, q[1]);
          }
          const hx6 = (mxx - mnx) / 2, hz6 = (mxz - mnz) / 2;
          if (hx6 < 3 || hz6 < 3) continue;
          let bd6 = 1e9, bx6 = 0, bz6 = 0;
          for (const r of OSM.roads) for (const q of r.pts) {
            const d6 = (q[0] - cx6) ** 2 + (q[1] - cz6) ** 2;
            if (d6 < bd6) { bd6 = d6; bx6 = q[0]; bz6 = q[1]; }
          }
          if (bd6 > 45 * 45) continue;
          // PICK A REAL WALL, NOT A BBOX FACE. Projecting the centre outward
          // to the bounding box (what the awnings do) lands inside the
          // building for any footprint that is not an axis-aligned rectangle,
          // and a buried fire escape is simply an invisible one — which is how
          // this pass first shipped 24 landings and showed none. Choose the
          // actual polygon EDGE facing the nearest road, and take its outward
          // normal from the edge itself.
          let bE = -1, bEd = 1e9, enx = 0, enz = 0;
          for (let e6 = 0; e6 < pts.length; e6++) {
            const a6 = pts[e6], c6 = pts[(e6 + 1) % pts.length];
            const ex7 = c6[0] - a6[0], ez7 = c6[1] - a6[1];
            const eL = Math.hypot(ex7, ez7);
            if (eL < 4) continue;                    // no room for a landing
            const mx7 = (a6[0] + c6[0]) / 2, mz7 = (a6[1] + c6[1]) / 2;
            // outward = whichever perpendicular steps AWAY from the centroid
            let px7 = -ez7 / eL, pz7 = ex7 / eL;
            if ((mx7 - cx6) * px7 + (mz7 - cz6) * pz7 < 0) { px7 = -px7; pz7 = -pz7; }
            const d7 = Math.hypot(mx7 - bx6, mz7 - bz6);
            if (d7 < bEd) { bEd = d7; bE = e6; enx = px7; enz = pz7; }
          }
          if (bE < 0) continue;
          const a8 = pts[bE], c8 = pts[(bE + 1) % pts.length];
          const ex6 = (a8[0] + c8[0]) / 2, ez6 = (a8[1] + c8[1]) / 2;
          const eLen = Math.hypot(c8[0] - a8[0], c8[1] - a8[1]);
          const nx6 = enx, nz6 = enz;
          const yaw6 = Math.atan2(nx6, nz6);
          EF.order = 'YXZ';                 // yaw to the wall FIRST, then tilt
          EF.set(0, yaw6, 0); QF.setFromEuler(EF);
          // slide along the wall so every building's escape is not dead-centre,
          // bounded by the edge so it cannot hang off the corner
          const tx6 = -nz6, tz6 = nx6;      // wall tangent
          const slide = (rngE() - 0.5) * Math.max(0, eLen - 3.6);
          const px6 = ex6 + tx6 * slide, pz6 = ez6 + tz6 * slide;
          const floors = Math.min(Math.floor(h6 / STOREY) - 1, 7);
          for (let s6 = 1; s6 <= floors && nf < CAP; s6++) {
            const y6 = gy6 + s6 * STOREY;
            MF.compose(PF.set(px6, y6, pz6), QF, SF); deck.setMatrixAt(nf, MF);
            MF.compose(PF.set(px6 + nx6 * 1.1, y6 + 0.45, pz6 + nz6 * 1.1), QF, SF);
            rail.setMatrixAt(nf, MF);
            // the diagonal between landings — the zig-zag that makes the
            // shadow read as a fire escape and not a row of shelves
            EF.set(0.72, yaw6, 0); QF.setFromEuler(EF);
            const zig = s6 % 2 ? 0.95 : -0.95;
            MF.compose(PF.set(px6 + tx6 * zig + nx6 * 0.55, y6 - STOREY / 2,
                              pz6 + tz6 * zig + nz6 * 0.55), QF, SF);
            stair.setMatrixAt(nf, MF);
            EF.set(0, yaw6, 0); QF.setFromEuler(EF);
            nf++;
          }
        }
        deck.count = rail.count = stair.count = nf;
        for (const im of [deck, rail, stair]) {
          im.instanceMatrix.needsUpdate = true;
          im.castShadow = true;
          scene.add(im);
        }
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
          // city trees stay broadleaf (an avenue of dead snags reads as a
          // bug, not a biome) but their PROPORTIONS follow the pack
          const _sw = 0.78 + SIL.spread * 0.38;
          const lobeDefs = [[0, 4.15, 0, 1.5 * _sw], [0.85, 3.75, 0.4, 0.95 * _sw],
                            [-0.75, 3.9, -0.5, 1.0 * _sw], [0.15, 4.9, -0.35, 0.85 * _sw],
                            [-0.3, 3.5, 0.7, 0.8 * _sw]];
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
            // A TREE IS SOLID (2026-08-07). Street trees shipped as pure
            // decoration, so a car drove straight through a 3.4m trunk and
            // the whole street stopped reading as physical. One static
            // cylinder each: no bodies, no simulation cost, and the trunk is
            // the only part worth colliding — clipping a canopy overhead is
            // what real cars do too.
            world.createCollider(RAPIER.ColliderDesc
              .cylinder(1.7 * sc, 0.26 * sc)
              .setTranslation(tx3, gy3 + 1.7 * sc, tz3));
          });
          for (const im of [trk, can]) {
            im.instanceMatrix.needsUpdate = true;
            im.castShadow = true; scene.add(im);
          }
          if (can.instanceColor) can.instanceColor.needsUpdate = true;
        }
      }
      // -- STOREFRONT SIGNAGE + WALL ADS (2026-08-06 r6) -------------------
      // Reference: St Marks Place, Mott Street, Times Square. At street level
      // a New York block is almost entirely SIGN -- a fascia board the full
      // width of the shop, saturated, name in big type, and painted ads on the
      // blank upper walls above it. The previous pass hung one 3.4m panel per
      // building, which reads as a brass plaque rather than a shopfront.
      //
      // Every sign in the city shares ONE atlas and merges into ONE mesh, so
      // all of this costs a single draw call. Per-sign canvases would have
      // been forty textures and forty materials for the same picture.
      if (feCand.length) {
        const rngG2 = mulberry32(SPEC.seed + 909);
        const _nightS = SPEC.world.sky === 'night' || SPEC.world.sky === 'dusk';
        const SLOTS = 16, SW2 = 1024, SH2 = 128;
        const atl = document.createElement('canvas');
        atl.width = SW2; atl.height = SH2 * SLOTS;
        const ag2 = atl.getContext('2d');
        // the fascia colours those streets actually use: saturated,
        // high-contrast, never tasteful
        const SBG = ['#c8102e', '#f2b400', '#d81b7a', '#0a7d3e', '#1b52a4',
                     '#141414', '#e8541f', '#00857a'];
        const GROUPS = [['cafe', 0], ['restaurant', 4], ['store', 8], ['bar', 12]];
        const slotOf = {};
        for (const gi in GROUPS) {
          const prog = GROUPS[gi][0], base = GROUPS[gi][1];
          const pool = _PROGNAMES[prog] || ['SHOP'];
          slotOf[prog] = [];
          for (let k = 0; k < 4; k++) {
            const i = base + k, y0 = i * SH2;
            const bg2 = SBG[Math.floor(rngG2() * SBG.length)];
            ag2.fillStyle = bg2; ag2.fillRect(0, y0, SW2, SH2);
            ag2.fillStyle = 'rgba(0,0,0,0.28)';
            ag2.fillRect(0, y0 + SH2 - 12, SW2, 12);       // shadow under the lip
            ag2.strokeStyle = 'rgba(255,255,255,0.8)'; ag2.lineWidth = 5;
            ag2.strokeRect(9, y0 + 9, SW2 - 18, SH2 - 18);
            const nm = pool[k % pool.length];
            ag2.fillStyle = bg2 === '#f2b400' ? '#1a1a1a' : '#fdf6e8';
            ag2.textAlign = 'center'; ag2.textBaseline = 'middle';
            let fs = 78;
            do { fs -= 4; ag2.font = 'bold ' + fs + 'px Arial'; }
            while (fs > 30 && ag2.measureText(nm).width > SW2 - 90);
            ag2.fillText(nm, SW2 / 2, y0 + SH2 / 2 + 2);
            slotOf[prog].push(i);
          }
        }
        const atlT = new THREE.CanvasTexture(atl);
        atlT.colorSpace = THREE.SRGBColorSpace;
        atlT.anisotropy = renderer.capabilities.getMaxAnisotropy();
        // NO MIPMAPS (2026-08-06). Sixteen shop names share one 1024x2048
        // canvas, so each mip level averages across slot BOUNDARIES — at a
        // grazing angle the lower mips blend one shop's name into the next
        // and the board reads as horizontal smears of two words at once.
        // Padding the slots would not save it: mip 5 and beyond mixes the
        // whole atlas regardless. Anisotropic filtering still handles the
        // grazing case, which is the only place mips were earning anything.
        atlT.generateMipmaps = false;
        atlT.minFilter = THREE.LinearFilter;
        atlT.magFilter = THREE.LinearFilter;
        const quads = [];
        const mkQuad = (sink, qx, qy, qz, nx0, nz0, w, hh, v0, v1, out) => {
          const tx = -nz0, tz = nx0;
          const bx3 = qx + nx0 * out, bz3 = qz + nz0 * out;
          // MIRRORED TEXT (2026-08-06). The tangent below is (-nz, nx),
          // which is exactly the NEGATIVE of the viewer's right hand when
          // they stand outside the wall looking at it (right = forward x up
          // = (nz, -nx) for forward = -n). So U ran right-to-left and every
          // fascia board and wall ad in the city rendered as its own mirror
          // image. Flipping U rather than the tangent leaves the winding and
          // the explicit normals alone.
          // Read from the STREET these quads show their back face, and a
          // back face mirrors its texture — so u has to run the opposite way
          // to the tangent for the text to come out forwards. Settled by
          // photographing signs in play, not by algebra: two earlier passes
          // reasoned it out on paper and got opposite answers, and one of my
          // "mirrored" readings turned out to be a camera stuck inside a
          // building looking at the genuine back of a sign.
          //
          // Corner UVs must also agree per edge. An earlier fix flipped u on
          // three corners and missed the fourth, so the two LEFT corners
          // carried u=1 and u=0 and the texture sheared diagonally across the
          // second triangle — that was the "warped and stretched" report.
          const c6 = [[-1, -1, 1, v0], [1, -1, 0, v0], [1, 1, 0, v1],
                      [-1, -1, 1, v0], [1, 1, 0, v1], [-1, 1, 1, v1]];
          const pos = [], uv = [], nor = [];
          for (const cc of c6) {
            pos.push(bx3 + tx * (w / 2) * cc[0], qy + (hh / 2) * cc[1],
                     bz3 + tz * (w / 2) * cc[0]);
            uv.push(cc[2], cc[3]);
            nor.push(nx0, 0, nz0);
          }
          const q3 = new THREE.BufferGeometry();
          q3.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos), 3));
          q3.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(uv), 2));
          q3.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(nor), 3));
          sink.push(q3);
        };
        let ns = 0;
        for (const fc of feCand) {
          if (ns >= 46) break;
          const bpts = fc[0], cx3 = fc[1], cz3 = fc[2], gy3 = fc[3];
          const h3 = fc[4], prog3 = fc[7], fst3 = fc[8], shop3 = fc[9];
          if (!shop3) continue;                        // residential street wall
          // a tower's ground floor is somebody else's shop, so when the
          // building's own program is not a trade, pick one
          const gk = slotOf[prog3] ? prog3
            : GROUPS[Math.floor(rngG2() * GROUPS.length)][0];
          const slots = slotOf[gk];
          if (!slots) continue;
          if (h3 < 5.5) continue;
          let bd = 1e9, bx = 0, bz = 0;
          for (const r of OSM.roads || []) for (const q of r.pts) {
            const d = (q[0] - cx3) ** 2 + (q[1] - cz3) ** 2;
            if (d < bd) { bd = d; bx = q[0]; bz = q[1]; }
          }
          if (bd > 44 * 44) continue;
          const fe3 = faceEdge(bpts, cx3, cz3, bx, bz, 3.8);
          if (!fe3) continue;
          // the fascia runs the width of the SHOP, not a fixed 3.4m: a board
          // stopping short of the piers is the plaque look all over again
          // The atlas slot is 1024x128 — 8:1. A shop 17m wide stretched that
          // slot to 14:1 and the letters came out drawn out sideways. Real
          // fascia boards are 3-8m and sit centred over the entrance, so the
          // board is capped near the slot's own aspect instead of running the
          // full width of the building.
          const eL3 = Math.max(3.2, Math.min(fe3.len === undefined ? 9 : fe3.len, 17));
          const fascW = Math.min(eL3 * 0.86, 1.05 * 8.4);
          const slot = slots[Math.floor(rngG2() * slots.length)];
          const v0s = 1 - (slot + 1) / SLOTS, v1s = 1 - slot / SLOTS;
          mkQuad(quads, fe3.x, gy3 + (fst3 || 3.3) - 0.22, fe3.z, fe3.nx, fe3.nz,
                 fascW, 1.05, v0s, v1s, 0.17);
          // BLADE SIGN: hung PERPENDICULAR to the wall, which is the one that
          // reads from down the block — a flat fascia disappears the moment
          // you are not standing square to it, and half of Mott Street is
          // these. Width runs along the wall NORMAL, not the wall.
          //
          // A single DoubleSide quad was wrong here: both faces share one set
          // of UVs, so whichever side you did not design for reads mirrored,
          // and a blade is meant to be read from BOTH ends of the block. Two
          // quads back to back, the rear one with U flipped, so each side is
          // correct and the nearer one occludes the other.
          if (rngG2() < 0.55) {
            const by2 = gy3 + (fst3 || 3.3) + 0.95;
            const bx2 = fe3.x, bz2 = fe3.z;
            const px8 = fe3.nx, pz8 = fe3.nz;
            const tx8 = -pz8, tz8 = px8;
            const inR = 0.12, outR = 1.45, bh2 = 0.86;
            const sl8 = (rngG2() - 0.5) * Math.max(0, eL3 - 2.4);
            const ox8 = bx2 + tx8 * sl8, oz8 = bz2 + tz8 * sl8;
            const c8 = [[inR, -1, 0, v0s], [outR, -1, 1, v0s], [outR, 1, 1, v1s],
                        [inR, -1, 0, v0s], [outR, 1, 1, v1s], [inR, 1, 0, v1s]];
            for (const face of [1, -1]) {
              const pos8 = [], uv8 = [], nor8 = [];
              // 1.5cm apart: enough that the near face always wins the depth
              // test, far too little to read as two boards
              // 1.5cm read as z-fighting at street distance and the two
              // faces smeared into each other; a blade is a real board, so
              // give it a board's thickness
              const sh8 = face * 0.045;
              for (const cc of c8) {
                pos8.push(ox8 + px8 * cc[0] + tx8 * sh8,
                          by2 + (bh2 / 2) * cc[1],
                          oz8 + pz8 * cc[0] + tz8 * sh8);
                uv8.push(face > 0 ? cc[2] : 1 - cc[2], cc[3]);
                nor8.push(tx8 * face, 0, tz8 * face);
              }
              const q8 = new THREE.BufferGeometry();
              q8.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos8), 3));
              q8.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(uv8), 2));
              q8.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(nor8), 3));
              quads.push(q8);
            }
          }
          ns++;
        }
        if (quads.length) {
          const sm3 = new THREE.MeshStandardMaterial({ map: atlT, roughness: 0.62,
            side: THREE.DoubleSide });
          if (_nightS) {
            // a shop sign is lit from inside; unlit it is a dark board and the
            // street loses the thing that makes it read as open for business
            sm3.emissive = new THREE.Color(0xffffff);
            sm3.emissiveMap = atlT;
            sm3.emissiveIntensity = 0.95;
          }
          const sMesh = new THREE.Mesh(mergeGeometries(quads, false), sm3);
          sMesh.receiveShadow = true;
          scene.add(sMesh);
          for (const q3 of quads) q3.dispose();
          console.log('[game] storefront signs: ' + ns);
        }
        // -- WALL ADS ------------------------------------------------------
        // The painted brick ad is what fills the blank upper wall in every one
        // of those photos. Square, so its own atlas and its own mesh -- still
        // only one more draw call for the whole city.
        {
          const AD = 512, ADN = 4;
          const ac3 = document.createElement('canvas');
          ac3.width = AD; ac3.height = AD * ADN;
          const dg = ac3.getContext('2d');
          const rngAd = mulberry32(SPEC.seed + 1313);
          const ADS = [['DRINK', 'COLA', '#b3121f', '#f6e7c8'],
                       ['SMOKE', 'LUCKY', '#1d4e89', '#ffe9a8'],
                       ['THE', 'DAILY NEWS', '#141414', '#f2b400'],
                       ['VISIT', 'BROADWAY', '#7a1f6d', '#ffd9f2']];
          for (let i = 0; i < ADN; i++) {
            const l1 = ADS[i][0], l2 = ADS[i][1], bg3 = ADS[i][2], fg3 = ADS[i][3];
            const y0 = i * AD;
            dg.fillStyle = bg3; dg.fillRect(0, y0, AD, AD);
            dg.strokeStyle = 'rgba(255,255,255,0.28)'; dg.lineWidth = 10;
            dg.strokeRect(16, y0 + 16, AD - 32, AD - 32);
            // a painted wall ad is never clean; a clean one reads as a decal
            // stuck on the brick rather than paint soaked into it
            for (let k = 0; k < 260; k++) {
              dg.fillStyle = 'rgba(0,0,0,' + (0.02 + rngAd() * 0.06) + ')';
              dg.fillRect(rngAd() * AD, y0 + rngAd() * AD,
                          2 + rngAd() * 26, 2 + rngAd() * 40);
            }
            dg.fillStyle = fg3; dg.textAlign = 'center'; dg.textBaseline = 'middle';
            dg.font = 'bold 92px Arial';
            dg.fillText(l1, AD / 2, y0 + AD * 0.34);
            let fs2 = 108;
            do { fs2 -= 4; dg.font = 'bold ' + fs2 + 'px Arial'; }
            while (fs2 > 34 && dg.measureText(l2).width > AD - 60);
            dg.fillText(l2, AD / 2, y0 + AD * 0.60);
          }
          const adT = new THREE.CanvasTexture(ac3);
          adT.colorSpace = THREE.SRGBColorSpace;
          adT.anisotropy = renderer.capabilities.getMaxAnisotropy();
          const adQ = [];
          let na2 = 0;
          for (const fc of feCand) {
            if (na2 >= 14) break;
            const bpts = fc[0], cx3 = fc[1], cz3 = fc[2], gy3 = fc[3], h3 = fc[4];
            if (h3 < 17) continue;                     // needs blank wall to carry it
            if (rngAd() > 0.5) continue;
            let bd = 1e9, bx = 0, bz = 0;
            for (const r of OSM.roads || []) for (const q of r.pts) {
              const d = (q[0] - cx3) ** 2 + (q[1] - cz3) ** 2;
              if (d < bd) { bd = d; bx = q[0]; bz = q[1]; }
            }
            if (bd > 52 * 52) continue;
            const fe4 = faceEdge(bpts, cx3, cz3, bx, bz, 3.8);
            if (!fe4) continue;
            const eL4 = fe4.len === undefined ? 9 : fe4.len;
            const wA = Math.min(9, Math.max(4.5, eL4 * 0.55));
            const ai = Math.floor(rngAd() * ADN);
            mkQuad(adQ, fe4.x, gy3 + h3 * 0.58, fe4.z, fe4.nx, fe4.nz, wA, wA,
                   1 - (ai + 1) / ADN, 1 - ai / ADN, 0.13);
            na2++;
          }
          if (adQ.length) {
            const aMesh = new THREE.Mesh(mergeGeometries(adQ, false),
              new THREE.MeshStandardMaterial({ map: adT, roughness: 0.92,
                side: THREE.DoubleSide }));
            aMesh.receiveShadow = true;
            scene.add(aMesh);
            for (const q4 of adQ) q4.dispose();
            console.log('[game] wall ads: ' + na2);
          }
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
          // 2026-08-06: the world ground is shared with forests and deserts,
          // so nobody had ever tuned it AGAINST asphalt. On a night city it
          // came out brighter than every other surface on screen — a white
          // courtyard with a road painted on it, which is exactly how the
          // block read. Knocking it down puts plaza, pavement and asphalt in
          // one believable range, and it means the gaps the pavement band
          // leaves at intersections stop reading as bright holes.
          // Scoped to OSM cities only; every other world keeps its ground.
          // 0.66 was still the brightest surface on screen: city levels run
          // environmentIntensity 2.4 for the facades, and the ground eats
          // all of it. 0.5 is what actually lands under a night sky.
          gmat.color.multiplyScalar(0.5);
          gmat.needsUpdate = true;
          // ZEBRA CROSSWALKS (2026-08-06). Every reference photo has them
          // and the eye reads them as "this is a street" before it reads a
          // single building. They join dashGeos so the whole of the city's
          // white paint stays ONE draw call.
          {
            const rngZ = mulberry32(SPEC.seed + 5151);
            let nz2 = 0;
            for (const j2 of (window.__junctions || []).slice(0, 26)) {
              // the bars run ACROSS the road, so they need the road's
              // direction at this junction, not the junction alone
              let bs = null, bdz = 1e9;
              for (const sg3 of _roadSegs) {
                const mxz2 = (sg3[0] + sg3[2]) / 2, mzz2 = (sg3[1] + sg3[3]) / 2;
                const d2 = (mxz2 - j2[0]) ** 2 + (mzz2 - j2[1]) ** 2;
                if (d2 < bdz) { bdz = d2; bs = sg3; }
              }
              if (!bs) continue;
              const dxz = bs[2] - bs[0], dzz = bs[3] - bs[1];
              const lz = Math.hypot(dxz, dzz) || 1;
              const uxz = dxz / lz, uzz = dzz / lz;
              const hwz = bs[4];
              // set back from the middle of the junction on both approaches
              for (const app of [1, -1]) {
                const bxz = j2[0] + uxz * (hwz + 1.7) * app;
                const bzz = j2[1] + uzz * (hwz + 1.7) * app;
                if (!_onRoad(bxz, bzz, 0.1)) continue;
                const NB = 6;
                for (let k2 = 0; k2 < NB; k2++) {
                  const off = (-hwz + 0.7) + k2 * ((hwz * 2 - 1.4) / (NB - 1));
                  const sx6 = bxz - uzz * off, sz6 = bzz + uxz * off;
                  const bar = new THREE.PlaneGeometry(0.42, 2.4);
                  bar.rotateX(-Math.PI / 2);
                  bar.rotateY(Math.atan2(uxz, uzz));
                  bar.translate(sx6, hAt(sx6, sz6) + 0.022, sz6);
                  // mergeGeometries needs an index attribute on ALL of its
                  // inputs or on NONE. PlaneGeometry is indexed and the road
                  // dashes are not, so pushing these raw killed the whole
                  // merge — and a failed merge here takes the entire runtime
                  // down while the build still reports complete (TRAP 4).
                  dashGeos.push(dashGeos.length && !dashGeos[0].index
                    ? bar.toNonIndexed() : bar);
                  nz2++;
                }
              }
            }
            if (rngZ() < 2) { /* deterministic hook */ }
            console.log('[game] crosswalk bars: ' + nz2);
          }
          const dash = new THREE.Mesh(mergeGeometries(dashGeos, false),
            new THREE.MeshBasicMaterial({ color: 0xd8d8d2, side: THREE.DoubleSide }));
          scene.add(dash);
          // r14 REAL CURBS: solid instanced boxes (top + side faces) per
          // road-segment side — an actual 6-inch step, nothing to z-fight
          {
            // 2026-08-06: the unit box was 0.3 DEEP on Z and the per-piece
            // scale multiplies Z by the piece LENGTH, so a 6m piece drew
            // 1.8m of kerb — the kerb line came out as detached blocks with
            // 4m gaps (visible in playtest shots as rubble on the pavement).
            // The unit box must be 1 on the axis the length scales.
            const cg2 = new THREE.BoxGeometry(1, 0.15, 1);
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
                  // BOTH tests are load-bearing. _onRoad with its tight pad
                  // is what keeps a kerb out of a NEARLY PARALLEL road's
                  // carriageway (a service road beside an avenue) — dropping
                  // it in favour of the crossing test alone put 10% of all
                  // kerb pieces in the roadway, measured. _onCross is what
                  // clears wide and oblique junctions, which the tight pad
                  // cannot reach. Both ends as well as the middle: a 6m bar
                  // half over a junction still reads as a kerb in the road.
                  const e1x = s[0] + ux * d0 + oxc * sd, e1z = s[1] + uz * d0 + ozc * sd;
                  const e2x = s[0] + ux * (d0 + pl) + oxc * sd,
                        e2z = s[1] + uz * (d0 + pl) + ozc * sd;
                  if (_onRoad(mxc, mzc, 0.22) || _onRoad(e1x, e1z, 0.22)
                      || _onRoad(e2x, e2z, 0.22)
                      || _onCross(mxc, mzc, ux, uz, 1.8)
                      || _onCross(e1x, e1z, ux, uz, 1.8)
                      || _onCross(e2x, e2z, ux, uz, 1.8)) continue;
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
          // ── PAVEMENT BAND (2026-08-06) ─────────────────────────────────
          // The kerb was a lip standing on the same pale plaza the whole
          // world is made of, so the street had no pavement — just a road
          // painted on a courtyard. This is a real concrete band behind
          // every kerb, darker and finer-grained than the plaza, so the
          // ground reads street / kerb / pavement / building.
          //
          // It is a WEDGE, not a slab: proud of the plaza at the kerb and
          // feathered back to ground level at the building side. A flat
          // raised slab needs a step at BOTH edges, and the outer step has
          // nothing to justify it — you get a 15cm ledge running down the
          // middle of the pavement. The wedge also means the walk height
          // never changes, so nothing about movement or NPC pathing moves.
          {
            const SW = 4.6, pavGeos = [];
            for (const s of _roadSegs) {
              const len = Math.hypot(s[2] - s[0], s[3] - s[1]);
              if (len < 1.5) continue;
              const ux = (s[2] - s[0]) / len, uz = (s[3] - s[1]) / len;
              const px5 = -uz, pz5 = ux;
              const di = s[4] + 0.57, dou = di + SW;
              for (let d0 = 0; d0 < len; d0 += 4) {
                const pl = Math.min(4, len - d0);
                if (pl < 0.8) continue;
                for (const sd of [1, -1]) {
                  const mid = d0 + pl / 2;
                  const bx5 = s[0] + ux * mid, bz5 = s[1] + uz * mid;
                  const iX = bx5 + px5 * di * sd, iZ = bz5 + pz5 * di * sd;
                  const oX = bx5 + px5 * dou * sd, oZ = bz5 + pz5 * dou * sd;
                  // a crossing street must keep its asphalt: painting the
                  // band over an intersection floats concrete above the road
                  if (_onRoad(iX, iZ, 0.3) || _onRoad(oX, oZ, 0.3)
                      || _onCross(iX, iZ, ux, uz, 1.4)
                      || _onCross(oX, oZ, ux, uz, 1.4)) continue;
                  const aX = s[0] + ux * d0, aZ = s[1] + uz * d0;
                  const cX = s[0] + ux * (d0 + pl), cZ = s[1] + uz * (d0 + pl);
                  const q = [];
                  for (const [bxq, bzq] of [[aX, aZ], [cX, cZ]]) {
                    q.push([bxq + px5 * di * sd, bzq + pz5 * di * sd,
                            hAt(bxq + px5 * di * sd, bzq + pz5 * di * sd) + 0.145]);
                    q.push([bxq + px5 * dou * sd, bzq + pz5 * dou * sd,
                            hAt(bxq + px5 * dou * sd, bzq + pz5 * dou * sd) + 0.012]);
                  }
                  const g5 = new THREE.BufferGeometry();
                  const V = (k) => [q[k][0], q[k][2], q[k][1]];
                  // wind so the face points up on the side being built
                  const order = [0, 1, 2, 1, 3, 2];
                  const pos = [], uvs = [], nrm = [];
                  for (const k of order) {
                    pos.push(...V(k));
                    uvs.push((k < 2 ? 0 : pl) / 2, (k % 2 ? SW : 0) / 2);
                    // the wedge falls 13cm over 4.6m (~1.6 deg): a flat up
                    // normal is correct to the eye and cannot be flipped by
                    // the winding, which computeVertexNormals would do on
                    // whichever side of the road is wound the other way
                    nrm.push(0, 1, 0);
                  }
                  g5.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pos), 3));
                  g5.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(uvs), 2));
                  g5.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(nrm), 3));
                  pavGeos.push(g5);
                }
              }
            }
            if (pavGeos.length) {
              const pl2 = new THREE.TextureLoader();
              // SLAB JOINTS (2026-08-06): plain concrete made the band the
              // same flat grey as the plaza it sits on, so there was no
              // pavement — just a slightly different grey. What reads as a
              // sidewalk at a glance is the JOINT GRID, not the material, so
              // the flags are drawn: 1m slabs with scored joints and a little
              // per-slab tone drift. UV units here are 2m, hence 2x2 slabs.
              const pc3 = document.createElement('canvas');
              pc3.width = pc3.height = 256;
              const pg3 = pc3.getContext('2d');
              const rngP3 = mulberry32(SPEC.seed + 313);
              pg3.fillStyle = '#6e6c67'; pg3.fillRect(0, 0, 256, 256);
              for (let sy = 0; sy < 2; sy++) for (let sx3 = 0; sx3 < 2; sx3++) {
                const v = 118 + Math.floor(rngP3() * 26);
                pg3.fillStyle = `rgb(${v},${v - 2},${v - 6})`;
                pg3.fillRect(sx3 * 128 + 3, sy * 128 + 3, 122, 122);
              }
              // a worn chip here and there, or every flag is identical
              for (let i = 0; i < 60; i++) {
                pg3.fillStyle = `rgba(90,88,84,${0.06 + rngP3() * 0.12})`;
                pg3.fillRect(rngP3() * 256, rngP3() * 256, 2 + rngP3() * 9, 2 + rngP3() * 9);
              }
              const pt2 = new THREE.CanvasTexture(pc3);
              const pn2 = pl2.load('textures/concrete_n.jpg');
              for (const t of [pt2, pn2]) {
                t.wrapS = t.wrapT = THREE.RepeatWrapping;
                t.anisotropy = renderer.capabilities.getMaxAnisotropy();
              }
              pt2.colorSpace = THREE.SRGBColorSpace;
              const pav = new THREE.Mesh(mergeGeometries(pavGeos, false),
                new THREE.MeshStandardMaterial({ map: pt2, normalMap: pn2,
                  normalScale: new THREE.Vector2(0.7, 0.7),
                  color: 0xffffff, roughness: 0.95, metalness: 0.0,
                  side: THREE.DoubleSide }));
              pav.receiveShadow = true;
              scene.add(pav);
              for (const g5 of pavGeos) g5.dispose();
            }
          }
        }
      }
      // NEON SIGNS (Phase 120, night streets): emissive storefront strips on
      // building faces near roads — the bloom layer that sells 'city at night'
      if (['night', 'dusk', 'sunset'].includes(SPEC.world.sky)) {
        const rngNe = mulberry32(SPEC.seed + 606);
        const neonCols = [0xff3d7a, 0x35d0ff, 0xffd23d, 0x7cff4a, 0xc86bff];
        const NEON_WORDS = ['BAR', 'HOTEL', 'LIQUOR', 'OPEN', 'PIZZA', 'DINER',
          'JAZZ', 'TATTOO', 'PAWN', 'MOTEL', 'COFFEE', 'DELI', 'BOOKS', 'LAUNDRY'];
        let placedN = 0;
        // 2026-08-06: these were placed on BOUNDING-BOX faces, so on every
        // building whose footprint is not an axis-aligned rectangle the sign
        // hung in mid-air over the street — a 10m magenta slab floating in
        // front of the camera was the single most broken thing on screen.
        // Same edge picker as everything else that hangs on a facade.
        // ...and the same built-buildings-only rule: the edge picker cannot
        // save a sign whose building does not exist. (2026-08-06)
        for (const [b3pts, , , , , , , , , prog3n] of feCand) {
          const b3 = { pts: b3pts };
          if (placedN >= 36) break;
          if (!prog3n) continue;                   // no shopfront here
          if (rngNe() < 0.45) continue;
          let n3x = 1e9, n3z = 1e9, x3x = -1e9, x3z = -1e9;
          for (const q of b3.pts) {
            n3x = Math.min(n3x, q[0]); x3x = Math.max(x3x, q[0]);
            n3z = Math.min(n3z, q[1]); x3z = Math.max(x3z, q[1]);
          }
          const c3x = (n3x + x3x) / 2, c3z = (n3z + x3z) / 2;
          let d3 = 1e9, r3x = 0, r3z = 0;
          for (const r of OSM.roads || []) for (const q of r.pts) {
            const dd = (q[0] - c3x) ** 2 + (q[1] - c3z) ** 2;
            if (dd < d3) { d3 = dd; r3x = q[0]; r3z = q[1]; }
          }
          if (d3 > 40 * 40) continue;
          const fe4 = faceEdge(b3.pts, c3x, c3z, r3x, r3z, 3.2);
          if (!fe4) continue;
          // 2026-08-06: this was a bare plane whose WHOLE surface was
          // emissive in one colour — a 4m magenta rectangle stuck to a
          // building, which reads as a missing texture, not as signage.
          // The plate is now dark and only the TUBE glows, which is what a
          // neon sign actually is. Text is drawn in canvas: no download, no
          // licence, and legible text is the strongest "this is a place"
          // cue a street has.
          const col = neonCols[Math.floor(rngNe() * neonCols.length)];
          const hexN = '#' + col.toString(16).padStart(6, '0');
          const word = NEON_WORDS[Math.floor(rngNe() * NEON_WORDS.length)];
          const blade = rngNe() < 0.34 && fe4.len > 4;
          const cn = document.createElement('canvas');
          const gx = () => cn.getContext('2d');
          let sgn;
          if (blade) {
            cn.width = 128; cn.height = 320;
            const g6 = gx();
            g6.fillStyle = '#0c0c11'; g6.fillRect(0, 0, 128, 320);
            g6.strokeStyle = hexN; g6.lineWidth = 7;
            g6.shadowColor = hexN; g6.shadowBlur = 16;
            g6.strokeRect(11, 11, 106, 298);
            g6.fillStyle = '#fff6ff';
            g6.font = 'bold 42px Arial';
            g6.textAlign = 'center'; g6.textBaseline = 'middle';
            const letters = word.slice(0, 6).split('');
            letters.forEach((ch, li) =>
              g6.fillText(ch, 64, 52 + li * (216 / Math.max(letters.length - 1, 1))));
          } else {
            cn.width = 320; cn.height = 128;
            const g6 = gx();
            g6.fillStyle = '#0c0c11'; g6.fillRect(0, 0, 320, 128);
            g6.strokeStyle = hexN; g6.lineWidth = 7;
            g6.shadowColor = hexN; g6.shadowBlur = 16;
            g6.strokeRect(11, 11, 298, 106);
            g6.fillStyle = '#fff6ff';
            g6.font = 'bold 56px Arial';
            g6.textAlign = 'center'; g6.textBaseline = 'middle';
            g6.fillText(word, 160, 68);
          }
          const tn = new THREE.CanvasTexture(cn);
          tn.colorSpace = THREE.SRGBColorSpace;
          tn.anisotropy = renderer.capabilities.getMaxAnisotropy();
          // emissive is driven by the MAP, so the dark plate stays dark and
          // only the tube and the letters throw light. A flat `emissive`
          // colour is what made the whole slab glow.
          const mn = new THREE.MeshStandardMaterial({ map: tn, color: 0xffffff,
            side: THREE.DoubleSide, roughness: 0.55,
            emissive: 0xffffff, emissiveMap: tn, emissiveIntensity: 1.9 });
          const nw = blade ? 0.86 : Math.min(1.9 + rngNe() * 1.5, fe4.len * 0.55);
          const nh = blade ? 2.15 : nw * 0.4;
          sgn = new THREE.Mesh(new THREE.PlaneGeometry(nw, nh), mn);
          const yaw6 = Math.atan2(fe4.nx, fe4.nz);
          if (blade) {
            // projecting blade: hangs off the wall face, read down the street
            const outN = 0.10 + nw / 2;
            const sx3 = fe4.x + fe4.nx * outN, sz3 = fe4.z + fe4.nz * outN;
            sgn.position.set(sx3, hAt(sx3, sz3) + 4.3, sz3);
            sgn.rotation.y = yaw6 + Math.PI / 2;
            // A blade is meant to be read from BOTH ends of the block, and a
            // DoubleSide plane shows one set of UVs to both faces — so the far
            // side was always the mirror image. A second plane turned to face
            // the other way carries its own correct copy.
            const back6 = new THREE.Mesh(sgn.geometry, mn);
            back6.position.copy(sgn.position);
            back6.rotation.y = yaw6 - Math.PI / 2;
            back6.translateZ(-0.02);
            scene.add(back6);
          } else {
            const slideN = (rngNe() - 0.5) * Math.max(0, fe4.len - nw - 0.4);
            const sx3 = fe4.x + fe4.nx * 0.12 - fe4.nz * slideN;
            const sz3 = fe4.z + fe4.nz * 0.12 + fe4.nx * slideN;
            sgn.position.set(sx3, hAt(sx3, sz3) + 3.35, sz3);
            sgn.rotation.y = yaw6;
          }
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
  // ── REGION FOREST (2026-08-25): the layout said "forest", so there WILL
  // be one. Scatter assets are the LLM's choice and the library has no tree
  // at all, so a forest region that depended on either could come out as an
  // empty green field — which is exactly how the first build shipped. The
  // same procedural trunk+canopy kit the city plants along streets grows
  // here wherever the region mask says forest: no asset, no LLM, no luck.
  if (!PURE_SCENE && !OSM && LVL && LVL.regions
      && LVL.regions.palette.some(q => q.kind === 'forest')) {
    const rngF2 = mulberry32(SPEC.seed + 6464);
    const spots2 = [];
    const CAP_T = 300;
    for (let t2 = 0; t2 < CAP_T * 14 && spots2.length < CAP_T; t2++) {
      const x = (rngF2() - 0.5) * gsize * 0.94;
      const z = (rngF2() - 0.5) * gsize * 0.94;
      const r2 = regionAt(x, z);
      if (!r2 || r2.kind !== 'forest') continue;
      // density follows the mask: solid heart, ragged edge
      if (rngF2() > r2.w * 1.15) continue;
      if (pathDist(x, z) < CORR * 1.2) continue;
      if (spots2.some(q => (q[0] - x) * (q[0] - x) + (q[1] - z) * (q[1] - z) < 7)) continue;
      spots2.push([x, z, 0.8 + rngF2() * 0.7]);
    }
    if (spots2.length) {
      const trkG2 = new THREE.CylinderGeometry(0.16, 0.26, SIL.trunkH, 7);
      trkG2.translate(0, SIL.trunkH / 2, 0);
      const trk2 = new THREE.InstancedMesh(trkG2,
        new THREE.MeshStandardMaterial({ map: (() => {
          const t = new THREE.TextureLoader().load('textures/bark.jpg');
          t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(1, 2);
          t.colorSpace = THREE.SRGBColorSpace; return t;
        })(), roughness: 0.95 }), spots2.length);
      // the canopy follows the pack: this forest's trees are THIS world's
      // trees, not the universal two-cone pine every level used to plant
      const _cparts = [];
      if (SIL.arch === 'broadleaf') {
        const rLb = mulberry32(SPEC.seed + 979);
        const defs = [[0, 1.1, 0, 1.5], [0.8, 0.8, 0.4, 0.95],
                      [-0.7, 0.9, -0.5, 1.0], [0.1, 1.8, -0.3, 0.85]];
        for (const [lx, ly, lz, lr] of defs) {
          const g = new THREE.IcosahedronGeometry(lr * SIL.spread, 1);
          g.scale(1, SIL.squash, 1);
          g.translate(lx, SIL.trunkH + ly, lz);
          _cparts.push(g);
        }
        if (rLb() < 2) { /* seeded hook */ }
      } else if (SIL.arch === 'cypress') {
        const g = new THREE.ConeGeometry(0.95 * SIL.spread, 5.2, 7);
        g.translate(0, SIL.trunkH + 2.2, 0);
        _cparts.push(g);
      } else if (SIL.arch === 'dead') {
        const rB = mulberry32(SPEC.seed + 717);
        for (let b2 = 0; b2 < 4; b2++) {
          const bl = 1.9 + rB() * 1.4;
          const g = new THREE.CylinderGeometry(0.05, 0.11, bl, 5);
          g.translate(0, bl / 2, 0);
          g.rotateZ(0.5 + rB() * 0.7 * (1 + SIL.gnarl));
          g.rotateY(rB() * Math.PI * 2);
          g.translate(0, SIL.trunkH * 0.75 + rB() * 0.9, 0);
          _cparts.push(g);
        }
      } else {                              // pine, in this world's proportions
        for (let t9 = 0; t9 < SIL.tiers; t9++) {
          const g = new THREE.ConeGeometry(
            Math.max((1.8 - t9 * 0.45) * SIL.spread, 0.5),
            Math.max(3.4 - t9 * 0.7, 1.2), 8);
          g.translate(0, SIL.trunkH + 1.0 + t9 * 1.9, 0);
          _cparts.push(g);
        }
      }
      const canG2 = mergeGeometries(_cparts, false);
      for (const g of _cparts) g.dispose();
      const can2 = new THREE.InstancedMesh(canG2,
        new THREE.MeshStandardMaterial({ vertexColors: false, roughness: 0.9,
          color: SIL.arch === 'dead' ? 0x5b4030 : 0x2d5232 }), spots2.length);
      const M2 = new THREE.Matrix4(), Q2 = new THREE.Quaternion();
      const E2 = new THREE.Euler(), V2 = new THREE.Vector3(), S2 = new THREE.Vector3();
      const C2 = new THREE.Color();
      spots2.forEach(([x, z, sc], i2) => {
        E2.set((rngF2() - 0.5) * 0.08, rngF2() * Math.PI * 2, (rngF2() - 0.5) * 0.08);
        Q2.setFromEuler(E2);
        V2.set(x, hAt(x, z), z);
        S2.set(sc, sc * (0.9 + rngF2() * 0.35), sc);
        M2.compose(V2, Q2, S2);
        trk2.setMatrixAt(i2, M2);
        can2.setMatrixAt(i2, M2);
        can2.setColorAt(i2, C2.setHex(SIL.arch === 'dead' ? 0x5b4030 : 0x2d5232)
          .offsetHSL((rngF2() - 0.5) * 0.03, (rngF2() - 0.5) * 0.1, (rngF2() - 0.5) * 0.08));
      });
      for (const im2 of [trk2, can2]) {
        im2.instanceMatrix.needsUpdate = true;
        im2.castShadow = true; im2.receiveShadow = true;
        scene.add(im2);
      }
      if (can2.instanceColor) can2.instanceColor.needsUpdate = true;
      console.log('[game] region forest: ' + spots2.length + ' trees');
    }
  }
  // vegetation reads the layout: a forest region is where the trees ARE, a
  // lake is where they are not, and a village keeps its clearing open
  const _isTreeAsset = a => /tree|pine|fir|oak|bush|palm|birch|spruce|foliage/i.test(a || '');
  const _isRockAsset = a => /rock|boulder|stone|crag/i.test(a || '');
  const _regReject = (x, z, sct) => {
    const r = window.__regionAt && window.__regionAt(x, z);
    if (!r) return false;
    if (r.kind === 'water' && r.w > 0.18) return true;
    if (r.kind === 'village' && r.w > 0.4) return true;
    if (_isTreeAsset(sct.asset)) {
      if (r.kind === 'forest') return false;
      if ((r.kind === 'rock' || r.kind === 'sand') && r.w > 0.35) return rng() < 0.85;
      return rng() < 0.5;              // thinner everywhere that is not forest
    }
    if (_isRockAsset(sct.asset) && r.kind === 'forest' && r.w > 0.5) return rng() < 0.5;
    return false;
  };
  // inside a forest region the cluster-noise gate stands down — the REGION
  // is the cluster, and punching gaps in it reads as mange, not clearings
  const _regForce = (x, z, sct) => {
    const r = window.__regionAt && window.__regionAt(x, z);
    return !!(r && r.kind === 'forest' && r.w > 0.3 && _isTreeAsset(sct.asset));
  };
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
                  || _regReject(x, z, sct)
                  || (clusterN(x, z) < 0.45 && !_regForce(x, z, sct)
                      && tries < 22)) && tries < 30);
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
    // an office floor is painted board and carpet tile, not keep masonry
    const wallFile = (IK === 'house' || IK === 'office' || IK === 'shop')
      ? 'plaster' : 'stone';
    const floorFile = IK === 'dungeon' ? 'stone'
                    : (IK === 'office' || IK === 'shop' ? 'concrete' : 'planks');
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
      // SIGHT-BLOCKERS (2026-08-05): remember every wall as a 2D segment so
      // guards can't see through them. Without this a sentry two rooms away
      // "spotted" the player through solid stone and the whole patrol
      // converged at once — stealth is meaningless if walls don't block eyes.
      // Only floor-level walls count; the lintel above a doorway (y0 > 0)
      // leaves the doorway see-through, which is correct.
      if (y0 === 0) {
        const hx = rot ? 0 : ln / 2, hz = rot ? ln / 2 : 0;
        SIGHT.push([cx + OX - hx, cz - hz, cx + OX + hx, cz + hz]);
      }
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
        if (OX !== 0) pl2.visible = false;            // see the budget note below
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
    // An office lit by FIRE was the loudest thing left wrong in there: the
    // plan hands every kind the same torch list, so a floor plate with a
    // suspended ceiling had orange flames guttering on its walls. Same
    // positions and the same light-budget behaviour, but cool, high, and
    // without the flame mesh — the fitting is the ceiling troffer instead.
    const _fire = IK !== 'office';
    for (const [tx, tz] of (PLAN.torches || []).slice(0, 10)) {
      const pl = new THREE.PointLight(_fire ? 0xff9a3d : 0xdfeaff,
                                      _fire ? 14 : 11, 13, 1.8);
      pl.position.set(tx + OX, _fire ? WH * 0.62 : WH * 0.92, tz);
      // OFF UNTIL YOU ARE IN THE ROOM (2026-08-05): an offset interior is a
      // building you are not standing in, and four of them is forty point
      // lights. WebGL2 compiles a fixed light count, so blowing the budget
      // makes MeshStandardMaterial fail to LINK and every room renders
      // BLACK — no warning. Invisible lights are skipped by the renderer's
      // traversal entirely; the frame loop's budget pass lights the nearest
      // four once the player is actually inside.
      if (OX !== 0) pl.visible = false;
      scene.add(pl);
      if (_fire) {
        const fm = new THREE.Mesh(flameG, flameM);
        fm.position.copy(pl.position);
        scene.add(fm);
      }
      window.__torches.push(pl);
    }
    // KIND DECOR (moon plan 2.4): castles hang banners + a carpet runner
    // down the hall; houses get warm rugs. Cheap planes, big identity.
    if (IK === 'shop') {
      // ── WHAT MAKES A ROOM READ AS A SHOP (2026-08-07) ──────────────────
      // A counter you stand across, gondola shelving in aisles you walk
      // between, stock on the shelves, a lit sign behind the till. Same
      // reasoning as the office: the identity is in the fittings, not the
      // wall texture, and everything here merges so a store costs a handful
      // of draw calls on top of a whole city.
      const rngS = mulberry32((SPEC.seed || 1) + 611);
      const hwS = PLAN.rooms[0][2] / 2, hdS = PLAN.rooms[0][3] / 2;
      const woodM = new THREE.MeshStandardMaterial({ color: 0x8a6a4a,
        map: itex('planks', 8, 2), roughness: 0.8 });
      // OPT OUT OF THE AUTO-TEXTURER. It claims any untextured standard
      // material, so painted steel shelving and cardboard stock came back
      // wearing BRICK and rubble — a stockroom quarried out of masonry.
      // Deliberately flat materials have to say so.
      const shelfM = new THREE.MeshStandardMaterial({ color: 0xb9bcc2,
        roughness: 0.6, metalness: 0.3 });
      shelfM.userData.noAutoTex = true;
      const stockM = new THREE.MeshStandardMaterial({ color: 0xffffff,
        vertexColors: true, roughness: 0.85 });
      stockM.userData.noAutoTex = true;
      const counter = [], shelves = [], stock = [];
      // SERVICE COUNTER across the back, with a raised top
      const cw = hwS * 1.1;
      const cg = new THREE.BoxGeometry(cw, 1.02, 0.72);
      cg.translate(OX, 0.51, hdS - 2.2); counter.push(cg);
      const ct = new THREE.BoxGeometry(cw + 0.22, 0.07, 0.95);
      ct.translate(OX, 1.06, hdS - 2.2); counter.push(ct);
      // GONDOLA AISLES: double-sided runs with a kick plate and four decks
      const aisles = 3, runL = hdS * 1.15;
      for (let a = 0; a < aisles; a++) {
        const ax2 = OX + (a - (aisles - 1) / 2) * (hwS * 2 / (aisles + 0.6));
        const back = new THREE.BoxGeometry(0.09, 1.85, runL);
        back.translate(ax2, 0.93, -0.6); shelves.push(back);
        for (let d2 = 0; d2 < 4; d2++) {
          for (const side of [-1, 1]) {
            const deck = new THREE.BoxGeometry(0.46, 0.05, runL);
            deck.translate(ax2 + side * 0.27, 0.38 + d2 * 0.46, -0.6);
            shelves.push(deck);
            // stock: little boxes along each deck, colour per instance so a
            // shelf reads as goods rather than one long extruded slab
            const nb2 = Math.max(3, Math.round(runL / 0.55));
            for (let b2 = 0; b2 < nb2; b2++) {
              if (rngS() < 0.22) continue;              // gaps = things sold
              const bw2 = 0.16 + rngS() * 0.14, bh2 = 0.16 + rngS() * 0.16;
              const bx2 = new THREE.BoxGeometry(bw2, bh2, 0.22 + rngS() * 0.12);
              bx2.translate(ax2 + side * (0.27 + rngS() * 0.06),
                            0.38 + d2 * 0.46 + bh2 / 2 + 0.03,
                            -0.6 - runL / 2 + (b2 + 0.5) * (runL / nb2));
              const col = new THREE.Color().setHSL(rngS(), 0.45 + rngS() * 0.3,
                                                   0.42 + rngS() * 0.22);
              const ca2 = new Float32Array(bx2.attributes.position.count * 3);
              for (let v2 = 0; v2 < bx2.attributes.position.count; v2++) {
                ca2[v2 * 3] = col.r; ca2[v2 * 3 + 1] = col.g; ca2[v2 * 3 + 2] = col.b;
              }
              bx2.setAttribute('color', new THREE.BufferAttribute(ca2, 3));
              stock.push(bx2);
            }
          }
        }
      }
      const addMerged = (list, mat, cast) => {
        if (!list.length) return;
        const m2 = new THREE.Mesh(mergeGeometries(list, false), mat);
        m2.castShadow = !!cast; m2.receiveShadow = true;
        scene.add(m2);
        for (const g5 of list) g5.dispose();
      };
      addMerged(counter, woodM, true);
      addMerged(shelves, shelfM, true);
      addMerged(stock, stockM, false);
      // LIT SIGN behind the till — the one warm thing in the room, and the
      // reason a shop reads as open rather than abandoned
      const sc4 = document.createElement('canvas');
      sc4.width = 512; sc4.height = 128;
      const sx4 = sc4.getContext('2d');
      sx4.fillStyle = '#12202b'; sx4.fillRect(0, 0, 512, 128);
      sx4.fillStyle = '#ffd98a';
      sx4.font = 'bold 62px Arial';
      sx4.textAlign = 'center'; sx4.textBaseline = 'middle';
      sx4.fillText('OPEN 24 HRS', 256, 68);
      const st4 = new THREE.CanvasTexture(sc4);
      st4.colorSpace = THREE.SRGBColorSpace;
      const sgn4 = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 0.85),
        new THREE.MeshBasicMaterial({ map: st4, toneMapped: false }));
      sgn4.position.set(OX, 2.15, hdS - 0.28);
      sgn4.rotation.y = Math.PI;
      scene.add(sgn4);
      // ceiling strips, emissive only — a real light per store would eat the
      // WebGL2 light budget and render a BLACK ROOM instead (TRAP 2)
      const strips4 = [];
      for (let r4 = 0; r4 < 3; r4++) {
        const sg5 = new THREE.BoxGeometry(hwS * 1.5, 0.06, 0.3);
        sg5.translate(OX, topY - 0.09, -hdS + (r4 + 0.7) * (hdS * 2 / 3.6));
        strips4.push(sg5);
      }
      addMerged(strips4, new THREE.MeshBasicMaterial({ color: 0xf4f8ff,
        toneMapped: false }), false);
    }
    if (IK === 'office') {
      // ── WHAT MAKES A ROOM READ AS AN OFFICE (2026-08-06 r7) ────────────
      // Not the walls. It is the SUSPENDED CEILING with its T-bar grid and
      // recessed troffers, carpet tile underfoot, a horizon of low
      // partitions, and monitors glowing on desks. Get those four and the
      // space is unmistakable; miss them and plaster walls are just plaster
      // walls. Everything below is drawn or merged — a heist interior is
      // built on top of an entire city and cannot spend draw calls per desk.
      const rngO = mulberry32((SPEC.seed || 1) + 977);
      const hw3 = PLAN.rooms[0][2] / 2, hd3 = PLAN.rooms[0][3] / 2;
      const cv2 = (draw, px) => {
        const c = document.createElement('canvas');
        c.width = c.height = px;
        draw(c.getContext('2d'), px);
        const t = new THREE.CanvasTexture(c);
        t.wrapS = t.wrapT = THREE.RepeatWrapping;
        t.colorSpace = THREE.SRGBColorSpace;
        t.anisotropy = renderer.capabilities.getMaxAnisotropy();
        return t;
      };
      // CARPET TILE: 60cm squares laid quarter-turned, which is why a real
      // office floor has a faint chequer in raking light
      const carpetT = cv2((g5, N5) => {
        g5.fillStyle = '#4a4f57'; g5.fillRect(0, 0, N5, N5);
        for (let ty = 0; ty < 2; ty++) for (let tx = 0; tx < 2; tx++) {
          const v = 70 + Math.floor(rngO() * 10);
          g5.fillStyle = 'rgb(' + v + ',' + (v + 4) + ',' + (v + 11) + ')';
          g5.fillRect(tx * N5 / 2 + 1, ty * N5 / 2 + 1, N5 / 2 - 2, N5 / 2 - 2);
          // fleck, running the other way on alternate tiles
          for (let k = 0; k < 320; k++) {
            g5.fillStyle = 'rgba(' + (v + 26) + ',' + (v + 30) + ',' + (v + 38)
              + ',' + (0.15 + rngO() * 0.3) + ')';
            const fx = tx * N5 / 2 + rngO() * (N5 / 2), fy = ty * N5 / 2 + rngO() * (N5 / 2);
            if ((tx + ty) % 2) g5.fillRect(fx, fy, 1, 3); else g5.fillRect(fx, fy, 3, 1);
          }
        }
      }, 256);
      carpetT.repeat.set(bx / 1.2, bz / 1.2);
      floor.material.map = carpetT;
      floor.material.color.setHex(0xffffff);
      floor.material.roughness = 1.0;
      floor.material.needsUpdate = true;
      // SUSPENDED CEILING: white acoustic tile in a T-bar grid. This is the
      // single most recognisable surface in any commercial interior.
      const ceilT = cv2((g5, N5) => {
        g5.fillStyle = '#9aa0a6'; g5.fillRect(0, 0, N5, N5);      // the bar
        for (let ty = 0; ty < 2; ty++) for (let tx = 0; tx < 2; tx++) {
          g5.fillStyle = '#e9e7e2';
          g5.fillRect(tx * N5 / 2 + 3, ty * N5 / 2 + 3, N5 / 2 - 6, N5 / 2 - 6);
          for (let k = 0; k < 900; k++) {                          // perforation
            g5.fillStyle = 'rgba(150,148,143,' + (0.10 + rngO() * 0.22) + ')';
            g5.fillRect(tx * N5 / 2 + 4 + rngO() * (N5 / 2 - 9),
                        ty * N5 / 2 + 4 + rngO() * (N5 / 2 - 9), 2, 2);
          }
        }
      }, 256);
      ceilT.repeat.set(bx / 1.22, bz / 1.22);
      ceil.material.map = ceilT;
      ceil.material.color.setHex(0xffffff);
      ceil.material.needsUpdate = true;
      // Both of these carry a map ONLY so the late flat-material pass leaves
      // them alone; the point is the tint and a fine grain. At the repeats
      // they shipped with, the partitions read as rendered stucco and the
      // desks as sawn planks — office furniture is nearly plain.
      const partM = new THREE.MeshStandardMaterial({ color: 0x8d97a2,
        map: itex('plaster', 9, 5), roughness: 0.96, side: THREE.DoubleSide });
      const deskM = new THREE.MeshStandardMaterial({ color: 0xbdb4a4,
        map: itex('plaster', 7, 7), roughness: 0.55, metalness: 0.05 });
      const metalM = new THREE.MeshStandardMaterial({ color: 0x2e3236,
        metalness: 0.7, roughness: 0.42 });
      metalM.userData.noAutoTex = true;      // desk legs are steel, not stone
      const parts = [], desks = [], legs = [], screens = [], troffers = [];
      const DESK_H = 0.74, PART_H = 1.32;
      // cubicle runs: a partition spine with desks hung off both sides, which
      // is how a floor plate is actually laid out
      for (let r2 = 0; r2 < 3; r2++) {
        const pz2 = -hd3 + (r2 + 1) * (hd3 * 2 / 4);
        for (const c2 of [-1, 1]) {
          const runW = hw3 * 0.66;
          const pg2 = new THREE.BoxGeometry(runW, PART_H, 0.08);
          pg2.translate(c2 * hw3 * 0.44 + OX, PART_H / 2, pz2);
          parts.push(pg2);
          const nD = Math.max(2, Math.round(runW / 1.7));
          for (let d2 = 0; d2 < nD; d2++) {
            const dxo = c2 * hw3 * 0.44 - runW / 2 + (d2 + 0.5) * (runW / nD) + OX;
            for (const face of [-1, 1]) {
              const dz2 = pz2 + face * 0.42;
              const dg2 = new THREE.BoxGeometry(runW / nD - 0.12, 0.05, 0.72);
              dg2.translate(dxo, DESK_H, dz2);
              desks.push(dg2);
              for (const lx of [-0.4, 0.4]) {
                const lg2 = new THREE.BoxGeometry(0.05, DESK_H, 0.05);
                lg2.translate(dxo + lx * (runW / nD - 0.3), DESK_H / 2, dz2);
                legs.push(lg2);
              }
              // a monitor, on most desks. Lit screens at 2am are the reason
              // an empty office still reads as occupied.
              if (rngO() < 0.78) {
                const mg2 = new THREE.BoxGeometry(0.54, 0.34, 0.03);
                mg2.translate(dxo, DESK_H + 0.26, pz2 + face * 0.14);
                screens.push(mg2);
                const sg2 = new THREE.BoxGeometry(0.09, 0.16, 0.09);
                sg2.translate(dxo, DESK_H + 0.08, pz2 + face * 0.15);
                legs.push(sg2);
              }
            }
          }
        }
      }
      // reception desk, squared to the entry so it reads as the front
      const rd2 = new THREE.BoxGeometry(4.6, 1.05, 0.78);
      rd2.translate(OX, 0.53, -hd3 + 3.2); parts.push(rd2);
      const rt2 = new THREE.BoxGeometry(5.0, 0.08, 1.06);
      rt2.translate(OX, 1.09, -hd3 + 3.2); desks.push(rt2);
      const pMesh = new THREE.Mesh(mergeGeometries(parts, false), partM);
      pMesh.castShadow = pMesh.receiveShadow = true; scene.add(pMesh);
      const dMesh = new THREE.Mesh(mergeGeometries(desks, false), deskM);
      dMesh.castShadow = dMesh.receiveShadow = true; scene.add(dMesh);
      const lMesh = new THREE.Mesh(mergeGeometries(legs, false), metalM);
      lMesh.castShadow = true; scene.add(lMesh);
      for (const g5 of parts.concat(desks, legs)) g5.dispose();
      if (screens.length) {
        const scMesh = new THREE.Mesh(mergeGeometries(screens, false),
          new THREE.MeshBasicMaterial({ color: 0x6fa8c8, toneMapped: false }));
        scene.add(scMesh);
        for (const g5 of screens) g5.dispose();
      }
      // RECESSED TROFFERS on the ceiling grid. Emissive only: the WebGL2
      // light budget is what renders a BLACK ROOM rather than an error, so
      // real lights here would cost the whole interior (TRAP 2).
      for (let r2 = 0; r2 < 4; r2++) {
        for (const c2 of [-1, 0, 1]) {
          const tg2 = new THREE.BoxGeometry(1.2, 0.05, 0.6);
          tg2.translate(c2 * hw3 * 0.52 + OX, topY - 0.06,
                        -hd3 + (r2 + 0.5) * (hd3 * 2 / 4));
          troffers.push(tg2);
        }
      }
      const tMesh = new THREE.Mesh(mergeGeometries(troffers, false),
        new THREE.MeshBasicMaterial({ color: 0xf2f6ff, toneMapped: false }));
      scene.add(tMesh);
      for (const g5 of troffers) g5.dispose();
      // GLAZED MEETING ROOMS: the side rooms get a glass front, which is what
      // stops them reading as store cupboards off a corridor
      const glassRoomM = new THREE.MeshPhysicalMaterial({ color: 0xbcd4dd,
        roughness: 0.08, metalness: 0, transparent: true, opacity: 0.24,
        side: THREE.DoubleSide });
      const mullM = new THREE.MeshStandardMaterial({ color: 0x30343a,
        metalness: 0.6, roughness: 0.4 });
      const glz = [], mull = [];
      for (const rm of PLAN.rooms.slice(1)) {
        const rcx = rm[0], rcz = rm[1], rw2 = rm[2];
        const side = rcx > 0 ? -1 : 1;                 // face back to the floor
        const gx2 = rcx + side * (rw2 / 2);
        const pg5 = new THREE.PlaneGeometry(Math.min(rm[3], 7.5), WH - 0.35);
        pg5.rotateY(side > 0 ? -Math.PI / 2 : Math.PI / 2);
        pg5.translate(gx2 + OX, (WH - 0.35) / 2, rcz);
        glz.push(pg5);
        for (const fy of [0.02, WH - 0.36]) {
          const mg5 = new THREE.BoxGeometry(0.07, 0.09, Math.min(rm[3], 7.5));
          mg5.translate(gx2 + OX, fy + 0.05, rcz);
          mull.push(mg5);
        }
      }
      if (glz.length) {
        const gMesh = new THREE.Mesh(mergeGeometries(glz, false), glassRoomM);
        gMesh.renderOrder = 3; scene.add(gMesh);
        const mMesh = new THREE.Mesh(mergeGeometries(mull, false), mullM);
        scene.add(mMesh);
        for (const g5 of glz.concat(mull)) g5.dispose();
      }
    }
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
  // MANY VENUES (2026-08-05): the same door contract, once per building. Each
  // interior gets its own x-lane past the map edge (Python hands us `ox`), so
  // the player can leave one brownstone, cross the street and break into the
  // next without either interior ever touching the other.
  window.__doorway = null;                  // the venue you are currently in
  window.__doors = [];
  if (!INTERIOR && ENTERABLES.length) {
    const dgeo = new THREE.PlaneGeometry(1.8, 2.6);
    const dmat2 = new THREE.MeshBasicMaterial({
      color: 0xffc46b, transparent: true, opacity: 0.45, side: THREE.DoubleSide });
    window.__torches = window.__torches || [];
    for (let ei = 0; ei < ENTERABLES.length; ei++) {
      const E = ENTERABLES[ei];
      const EOX = (typeof E.ox === 'number') ? E.ox : SPEC.world.size_m * 2.2;
      const eb = buildRooms(E.plan, EOX);
      const [dx2, dz2] = E.door;
      const dy2 = hAt(dx2, dz2);
      const doorM = new THREE.Mesh(dgeo, dmat2);
      doorM.position.set(dx2, dy2 + 1.3, dz2);
      scene.add(doorM);
      const glow2 = new THREE.PointLight(0xffb347, 6, 9, 1.8);
      glow2.position.set(dx2, dy2 + 2.0, dz2);
      scene.add(glow2);
      // the porch lamps ride the SAME budget list as the torches: four doors
      // plus four lit interiors is well past the shader's light slots, and
      // over-budget renders black rather than warning (see buildRooms).
      window.__torches.push(glow2);
      // matching exit marker inside (at the hall's entry door)
      const exitM = new THREE.Mesh(dgeo, dmat2);
      exitM.position.set(EOX, 1.3, eb.entryZ - 3.2);
      scene.add(exitM);
      window.__doors.push({
        out: [dx2, dz2], inSpawn: [EOX, eb.entryZ + 1.0],
        exit: [EOX, eb.entryZ - 3.2], wallH: eb.WH, ox: EOX, cool: 0,
        label: E.label || 'the building',
        bounds: E.plan.bounds || [40, 40],
        // room centres in WORLD space — the guard spawner walks patrol beats
        // through them, and they are the only handle it has on this venue
        rooms: (E.plan.rooms || []).map(r => [r[0] + EOX, r[1]]) });
    }
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
        const _rg = window.__regionAt && window.__regionAt(x, z);
        if (_rg && _rg.kind === 'water' && _rg.w > 0.2) continue;    // no grass in the lake
        if (_rg && (_rg.kind === 'rock' || _rg.kind === 'sand')
            && _rg.w > 0.4 && rngG() < 0.85) continue;
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
    // the minimap has to agree with the world: drawing culled footprints put
    // solid blocks on the map where the player can see open plaza
    for (const b of (window.__builtFootprints || OSM.buildings || [])) {
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
      // heist venues: without these the player has no way to know WHICH of
      // three hundred blocks has a door in it
      for (const E of ENTERABLES) {
        mx.fillStyle = '#ff9f45';
        mx.beginPath();
        mx.arc(w2m(E.door[0]), w2m(E.door[1]), 3.4, 0, Math.PI * 2);
        mx.fill();
      }
      // parked cars: the same "where do I even go" problem the venue dots
      // solve — a getaway car you cannot find is not a getaway car
      for (const c of window.__cars || []) {
        if (c === window.__inCar) continue;          // that one is the arrow
        mx.fillStyle = '#7fd4ff';
        mx.beginPath();
        mx.arc(w2m(c.x), w2m(c.z), 3.0, 0, Math.PI * 2);
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
  let playT = 0;        // seconds since START — NOT page-load time, which is
                        // already ~7s deep by the time anyone clicks through
                        // the title card (the heist grace window needs this)
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
          : HAS_GUARDS
            // a heist teaches its own verbs: creeping and misdirection
            ? 'WASD move · <b>C sneak</b> · <b>Q throw a distraction</b> · Shift run · F attack'
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
      audioInit();                        // engine / footsteps / tyres / city bed
      if (window.__restoreProg) window.__restoreProg();   // saved upgrades return
      if (IS_RACE) startCountdown();
    });
  }

  const npcs = [];
  const rngN = mulberry32(SPEC.seed + 31);
  let vehIdx = 0;                       // starting-grid slot for vehicle rivals
  let gIdx = 0;                         // heist: which room each guard owns
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
        } else if (ent.behavior === 'guide') {
          // a guide you never meet is a guide who never guides: stand them
          // just ahead of the spawn point, in plain sight, facing the player
          holder.position.set(_sp.x + 2.6, 0, _sp.z + 3.4);
          holder.position.y = hAt(holder.position.x, holder.position.z);
          startYaw = Math.PI;
        } else if (ent.behavior === 'guard' && INTERIOR && INTERIOR.rooms
                   && INTERIOR.rooms.length) {
          // HEIST: guards belong to the ROOMS. Spawning them by the usual
          // random spread put sentries in the garden of a house they were
          // meant to be guarding — and their patrol beat walked through
          // walls. Each guard gets its own room and walks a circuit of
          // room centres, so patrols use the doorways like a person would.
          // …and never in the entry hall (rooms[0]) — the player walks in
          // there. Three guards standing on the doormat spotted you at t=0
          // and the heist was over in six seconds.
          const rms = INTERIOR.rooms.length > 1
            ? INTERIOR.rooms.slice(1) : INTERIOR.rooms;
          const home = rms[gIdx % rms.length];
          holder.position.set(home[0], 0, home[1]);
          const beat = [];
          for (let bi = 0; bi < Math.min(3, rms.length); bi++) {
            const r2 = rms[(gIdx + bi) % rms.length];
            beat.push([r2[0], r2[1]]);
          }
          startYaw = rngN() * Math.PI * 2;   // not all facing the door
          holder.userData.fsBeat = beat;
          gIdx++;
        } else if (ent.behavior === 'guard'
                   && window.__doors && window.__doors.length) {
          // CITY HEIST: one sentry per venue before any venue gets two —
          // an unguarded building is free money, and the stealth loop only
          // exists where somebody is watching. Same room-circuit beat as the
          // single-interior case, just in that building's world-space lane.
          const dwG = window.__doors[gIdx % window.__doors.length];
          const rmsG = dwG.rooms.length > 1 ? dwG.rooms.slice(1) : dwG.rooms;
          const homeG = rmsG[Math.floor(gIdx / window.__doors.length) % rmsG.length];
          holder.position.set(homeG[0], 0, homeG[1]);
          const beatG = [];
          for (let bi = 0; bi < Math.min(3, rmsG.length); bi++) {
            beatG.push(rmsG[(gIdx + bi) % rmsG.length].slice());
          }
          startYaw = rngN() * Math.PI * 2;
          holder.userData.fsBeat = beatG;
          holder.userData.fsPen = [dwG.ox - dwG.bounds[0] / 2 + 1,
                                   dwG.ox + dwG.bounds[0] / 2 - 1,
                                   -dwG.bounds[1] / 2 + 1,
                                   dwG.bounds[1] / 2 - 1];
          gIdx++;
        } else if (ent.behavior === 'escort') {
          const aE = rngN() * Math.PI * 2;
          holder.position.set(Math.cos(aE) * 5, 0, Math.sin(aE) * 5);
          // he can NEVER outrun the player at a walk: an escortee who pulls
          // away reads as a stranger leaving, not a charge to protect.
          // SPEC.player, not P — P is declared far below and reading it here
          // is a TDZ that silently deletes the escortee (TRAP 1, sixth time
          // this arc; the entity loop's catch turns the throw into a skip).
          ent.speed = Math.min(ent.speed || 1.6,
                               ((SPEC.player || {}).walk_speed || 2) * 0.8);
          // overhead chip: name + hearts, camera-facing, visible at a glance.
          // Redrawn only when hp changes — a canvas repaint per frame would
          // be pure waste for a value that changes a few times per game.
          const ec9 = document.createElement('canvas');
          ec9.width = 256; ec9.height = 72;
          const eg9 = ec9.getContext('2d');
          const eTex9 = new THREE.CanvasTexture(ec9);
          const chip9 = new THREE.Sprite(new THREE.SpriteMaterial({
            map: eTex9, transparent: true, depthTest: false }));
          // 1.5m wide, not 2.6: at follow-cam distance the first cut covered
          // the courier's whole torso — a nameplate, not a billboard
          chip9.scale.set(1.5, 0.42, 1);
          chip9.position.y = (ent.height_m || 1.7) + 0.55;
          chip9.renderOrder = 8;
          holder.add(chip9);
          holder.userData.fsEscortChip = (hp9, maxHp9, waiting9) => {
            eg9.clearRect(0, 0, 256, 72);
            eg9.fillStyle = 'rgba(10,9,18,0.72)';
            eg9.beginPath(); eg9.roundRect(8, 6, 240, 60, 12); eg9.fill();
            eg9.fillStyle = waiting9 ? '#ffd166' : '#8fe7d0';
            eg9.font = '700 26px system-ui';
            eg9.textAlign = 'center';
            eg9.fillText(waiting9 ? '⏸ ' + (ent.name || 'escort') + ' waits'
                                  : '🛡 ' + (ent.name || 'escort'), 128, 32);
            eg9.font = '400 24px system-ui';
            eg9.fillStyle = '#ff8fa0';
            eg9.fillText('♥'.repeat(Math.max(0, hp9)) + '♡'.repeat(Math.max(0, maxHp9 - hp9)), 128, 58);
            eTex9.needsUpdate = true;
          };
          holder.userData.fsEscortChip(ent.hp || 3, ent.hp || 3, false);
          // the RING is the identifier at any distance and from behind: five
          // similar humans can stand together and only one wears the mission
          // color at his feet. Same visual grammar as the goal ring, so the
          // player has already been taught what a glowing torus means.
          const er9 = new THREE.Mesh(
            new THREE.TorusGeometry(0.85, 0.07, 10, 36),
            new THREE.MeshStandardMaterial({ color: 0x8fe7d0,
              emissive: 0x2fbf9a, emissiveIntensity: 2.4 }));
          er9.rotation.x = Math.PI / 2;
          er9.position.y = 0.12;
          holder.add(er9);
          holder.userData.fsEscortRing = er9;
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
        npcs.push({ obj: holder, down: 0, kx: 0, kz: 0,
                speed: ent.speed || 1.5, behavior: ent.behavior || 'wander',
                    target: null, yaw: startYaw, phase: rngN() * Math.PI * 2,
                    h: ent.height_m || 1.0, name: ent.name,
                    beat: holder.userData.fsBeat || null,   // heist patrol circuit
                    pen: holder.userData.fsPen || null,     // venue he never leaves
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
    window.__alertPeak = 0;             // recomputed by the guards each frame
    for (const n of npcs) {
      if (n.dormant) continue;           // wave-pool members sleep until woken
      // STRUCK BY A CAR (2026-08-07 r2). The first cut only knocked down
      // ambient __peds, but guards, the informant and every wandering
      // entity are `npcs` — a different list on a different update path —
      // so the people you were most likely to aim at were exactly the ones
      // that ignored you. Downed NPCs skip their AI entirely: no patrol, no
      // chase, no attack until they are back on their feet.
      if (n.down > 0) {
        n.down -= dt;
        const kd = Math.min(1, dt * 3.2);
        n.obj.position.x += n.kx * dt;
        n.obj.position.z += n.kz * dt;
        n.kx -= n.kx * kd; n.kz -= n.kz * kd;
        n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z);
        const tg = n.down > 0.6 ? Math.PI / 2 : 0;
        n.obj.rotation.x += (tg - n.obj.rotation.x) * Math.min(1, dt * 7);
        if (n.down <= 0) { n.down = 0; n.obj.rotation.x = 0; }
        continue;
      }
      // death animation: keel over + sink, then remove
      if (n.dead) {
        n.dieT += dt;
        n.obj.rotation.x = Math.min(n.dieT * 4, Math.PI / 2);
        if (n.dieT > 1.4) { scene.remove(n.obj); n.gone = true; }
        continue;
      }
      let tx = null, tz = null;
      if (n.behavior === 'escort' && !won && !lost) {
        // Walks its own road: along the level PATH when one exists, else
        // straight at the goal. Waits when the player falls behind — the
        // escort sets the pace but never abandons its protection.
        if (n._epi === undefined) { n._epi = 0; n._waitSaid = false; }
        const ring9 = n.obj.userData.fsEscortRing;
        if (ring9) {
          const pu = 1 + Math.sin(performance.now() / 300) * 0.12;
          ring9.scale.setScalar(n._waitSaid ? pu * 1.35 : pu);
          ring9.material.emissiveIntensity = n._waitSaid ? 3.4 : 2.4;
        }
        const gp = goalPos;
        if (gp && !n._arrived) {
          const dPl = Math.hypot(playerPos.x - n.obj.position.x,
                                 playerPos.z - n.obj.position.z);
          let wx = gp.x, wz = gp.z;
          if (PATH && PATH.length > 1) {
            while (n._epi < PATH.length - 1
                   && Math.hypot(PATH[n._epi][0] - n.obj.position.x,
                                 PATH[n._epi][1] - n.obj.position.z) < 3.5) n._epi++;
            wx = PATH[n._epi][0]; wz = PATH[n._epi][1];
          }
          const dG = Math.hypot(gp.x - n.obj.position.x, gp.z - n.obj.position.z);
          if (dG < 3.0) {
            n._arrived = true;
            juicePOV = { x: n.obj.position.x, y: n.obj.position.y + (n.h || 1.7) * 0.9,
                         z: n.obj.position.z, lx: playerPos.x, ly: playerPos.y + 1.2,
                         lz: playerPos.z, t: 0 };
            popText((n.name || 'the escort') + ' made it!', '#8fe7d0');
            sfx('win');
          } else if (dPl > 14) {
            // too far ahead of the player: stop and say so, once per stall
            if (!n._waitSaid) {
              popText((n.name || 'the escort') + ' waits for you…', '#ffd166');
              n._waitSaid = true;
              if (n.obj.userData.fsEscortChip)
                n.obj.userData.fsEscortChip(n.hp || 3, n._maxHp || n.hp || 3, true);
            }
          } else {
            if (n._waitSaid && n.obj.userData.fsEscortChip)
              n.obj.userData.fsEscortChip(n.hp || 3, n._maxHp || n.hp || 3, false);
            n._waitSaid = false;
            const dx = wx - n.obj.position.x, dz = wz - n.obj.position.z;
            n.yaw = THREE.MathUtils.damp(n.yaw, Math.atan2(dx, dz), 5, dt);
            n.obj.rotation.y = n.yaw;
            const sp = (n.speed || 1.6) * dt;
            n.obj.position.x += Math.sin(n.yaw) * sp;
            n.obj.position.z += Math.cos(n.yaw) * sp;
            n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z);
          }
          if (n.anim) {
            const moving2 = !n._arrived && dPl <= 14 && dG >= 3.0;
            const want2 = moving2 ? n.anim.walk : n.anim.idle;
            if (want2 && want2 !== n.anim.cur) {
              want2.reset(); want2.crossFadeFrom(n.anim.cur, 0.25, true); want2.play();
              n.anim.cur = want2;
            }
            n.anim.mixer.update(dt);
          }
        }
        continue;
      }
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
        // ESCORT PRIORITY: hostiles hunt whichever of (player, escortee) is
        // nearer — an escort mission where the wolves politely ignore the
        // cargo is not an escort mission.
        {
          let esc = null, ed = 1e9;
          for (const o3 of npcs) {
            if (o3.behavior !== 'escort' || o3.dead || o3._arrived) continue;
            const dd3 = Math.hypot(o3.obj.position.x - n.obj.position.x,
                                   o3.obj.position.z - n.obj.position.z);
            if (dd3 < ed) { ed = dd3; esc = o3; }
          }
          if (esc && ed < d && ed < 16) {
            if (ed > 1.8) { tx = esc.obj.position.x; tz = esc.obj.position.z; }
            else {
              n.cd -= dt;
              if (n.cd <= 0) {
                n.cd = 1.3;
                esc._maxHp = esc._maxHp || esc.hp || 3;
                esc.hp = (esc.hp || 3) - 1;
                if (esc.obj.userData.fsEscortChip)
                  esc.obj.userData.fsEscortChip(esc.hp, esc._maxHp, false);
                for (const m of esc.mats || []) { if (m.emissive) m.emissive.setHex(0xff4444); }
                setTimeout(() => { for (const m of esc.mats || []) { if (m.emissive) m.emissive.setHex(0x000000); } }, 140);
                shakeT = Math.max(shakeT, 0.15);
                popText((esc.name || 'the escort') + ' is under attack!', '#ff8fa0');
                if (esc.hp <= 0 && !esc.dead) {
                  esc.dead = true;
                  burst(esc.obj.position.clone().add(new THREE.Vector3(0, 0.8, 0)), 0xff5c6a);
                  doLose((esc.name || 'The escort') + ' was lost.');
                }
              }
            }
            if (tx !== null) {
              const dx4 = tx - n.obj.position.x, dz4 = tz - n.obj.position.z;
              n.yaw = THREE.MathUtils.damp(n.yaw, Math.atan2(dx4, dz4), 6, dt);
              n.obj.rotation.y = n.yaw;
              const sp4 = n.speed * dt;
              n.obj.position.x += Math.sin(n.yaw) * sp4;
              n.obj.position.z += Math.cos(n.yaw) * sp4;
              n.obj.position.y = hAt(n.obj.position.x, n.obj.position.z);
            }
            if (n.anim) {
              const want4 = tx !== null ? n.anim.run : n.anim.idle;
              if (want4 && want4 !== n.anim.cur) {
                want4.reset(); want4.crossFadeFrom(n.anim.cur, 0.2, true); want4.play();
                n.anim.cur = want4;
              }
              n.anim.mixer.update(dt);
            }
            continue;   // busy with the cargo — skip player logic
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
      } else if (n.behavior === 'guard' && !won && !lost) {
        // ── THE HEIST KIT (2026-08-05): guards are not omniscient. They walk
        // a beat and only care about what their EYES catch — a vision cone,
        // an alert meter that fills with exposure, and a radio call when it
        // tops out. Crouch (C) halves how far they see. This one behavior
        // turns "chase game" into "stealth game".
        if (n.wp === undefined) {
          // indoor guards get a room circuit at spawn; outdoor ones walk a
          // box around their post
          if (!n.beat) {
            const hx = n.obj.position.x, hz = n.obj.position.z;
            const r = 7 + rngN() * 5;
            n.beat = [[hx - r, hz - r], [hx + r, hz - r],
                      [hx + r, hz + r], [hx - r, hz + r]];
          }
          n.wp = 0; n.alert = n.alert || 0;
          n.mode = n.mode || 'patrol'; n.lostT = 0;   // radio may pre-alert us
        }
        const d = Math.hypot(playerPos.x - n.obj.position.x, playerPos.z - n.obj.position.z);
        // CASING GRACE: nobody is looking your way for the first few seconds.
        // A heist has to let you get through the door and read the room.
        const range = (playT < 5) ? 0 : (window.__sneak ? 7 : 14);
        let dA = Math.atan2(playerPos.x - n.obj.position.x,
                            playerPos.z - n.obj.position.z) - n.yaw;
        while (dA > Math.PI) dA -= 2 * Math.PI;
        while (dA < -Math.PI) dA += 2 * Math.PI;
        // seen = inside the cone (~115°), in range, and with a clear line —
        // walls, not distance, are what hide you
        const sees = d < range && (Math.abs(dA) < 1.0 || d < 2.5)
          && canSee(n.obj.position.x, n.obj.position.z, playerPos.x, playerPos.z);
        if (n.mode !== 'chase') {
          if (sees) {
            // SUSPICION TAKES TIME. At the old rate the meter filled in
            // under a second, so "spotted" was indistinguishable from
            // "instantly killed" — there was no moment to duck behind a
            // wall, which is the entire game. ~1.8s point-blank, ~4s at
            // the edge of vision.
            n.alert += dt * (0.62 - 0.34 * (d / range));
            if (n.alert >= 1) {
              n.mode = 'chase';
              popText(`👁 ${n.name || 'guard'} spotted you!`, '#ff6b6b');
              // the radio: only the guard in earshot answers. A 24 m call in
              // a 35 m house summoned the entire patrol at once, which is a
              // firing squad, not a stealth game.
              let called = 0;
              for (const g of npcs) {
                if (g !== n && g.behavior === 'guard' && !g.dead && !g.dormant
                    && Math.hypot(g.obj.position.x - n.obj.position.x,
                                  g.obj.position.z - n.obj.position.z) < 11) {
                  g.mode = 'chase'; g.alert = 1;
                  if (++called >= 1) break;
                }
              }
            }
          } else {
            n.alert = Math.max(0, n.alert - dt * 0.5);
          }
        }
        // the eye: show the worst suspicion in the house so the player can
        // read the danger and react. Stealth without feedback is a coin flip.
        window.__alertPeak = Math.max(window.__alertPeak || 0,
                                      n.mode === 'chase' ? 1 : n.alert);
        // casing: once YOU have had a clear look at him, he goes on the
        // blueprint permanently. Intelligence you gathered, not a wallhack.
        if (!n._seenByPlayer && d < 18
            && canSee(playerPos.x, playerPos.z, n.obj.position.x, n.obj.position.z)) {
          n._seenByPlayer = true;
        }
        if (n.mode === 'chase') {
          n.vjit = 1.5;                        // guards sprint when alerted
          if (d > 1.7) { tx = playerPos.x; tz = playerPos.z; }
          // slower than a monster's bite: a whole patrol converging at the
          // hostile cadence emptied five hearts in two seconds
          else { n.cd -= dt; if (n.cd <= 0) { n.cd = 2.0; playerHit(1); } }
          // breaking line of sight is the escape, not out-running them: in a
          // 35 m house "get 16 m away" was never achievable
          if (!sees && d > 9) {
            n.lostT += dt;
            if (n.lostT > 3) {
              n.mode = 'patrol'; n.alert = 0; n.lostT = 0; n.vjit = 0.55;
              popText(`${n.name || 'guard'} lost you — stay low`, '#9fd8a2');
            }
          } else n.lostT = 0;
        } else if (n.beat) {
          n.vjit = 0.55;                       // an unbothered walking pace
          const w = n.beat[n.wp];
          if (Math.hypot(w[0] - n.obj.position.x, w[1] - n.obj.position.z) < 1.2)
            n.wp = (n.wp + 1) % n.beat.length;
          tx = n.beat[n.wp][0]; tz = n.beat[n.wp][1];
        }
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
      } else if (n.behavior === 'guide') {
        // THE GUIDE: stands their ground, turns to face you, and speaks when
        // you come near. A game should explain itself through a person, not
        // a HUD line the player never reads.
        const d = Math.hypot(playerPos.x - n.obj.position.x, playerPos.z - n.obj.position.z);
        if (d < 14) {
          n.yaw = THREE.MathUtils.damp(
            n.yaw, Math.atan2(playerPos.x - n.obj.position.x,
                              playerPos.z - n.obj.position.z), 5, dt);
          n.obj.rotation.y = n.yaw;
        }
        if (d < 6.5 && !n._said) { n._said = true; sayGuide(n); }
        if (d > 11) n._said = false;      // re-greets after you wander off
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
                               || (n.behavior === 'guard' && n.mode === 'chase')
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
      // stay inside the walls — or, for a heist sentry, inside HIS building.
      // (2026-08-05: this world-bounds clamp yanked every venue guard from
      // x=792 back to x=169, so all four stood in the same empty street and
      // no building had anybody in it.)
      if (n.pen) {
        n.obj.position.x = THREE.MathUtils.clamp(n.obj.position.x, n.pen[0], n.pen[1]);
        n.obj.position.z = THREE.MathUtils.clamp(n.obj.position.z, n.pen[2], n.pen[3]);
      } else {
        const lim = gsize * 0.47;
        n.obj.position.x = THREE.MathUtils.clamp(n.obj.position.x, -lim, lim);
        n.obj.position.z = THREE.MathUtils.clamp(n.obj.position.z, -lim, lim);
      }
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
  // ── ONE BUILDING, SAME RULES AS THE BLOCK (2026-08-06) ─────────────────
  // The city builds its facades as a merged grid of piers and spandrels
  // because it draws forty of them at once. A DROPPED building has the
  // opposite constraint — one instance, placed by hand — so it gets its own
  // assembly here rather than being wedged into the city path. What must not
  // diverge is the RULE: storeys are whole, the wall stands proud of a
  // backing, and the gaps between piers and spandrels are the windows. A
  // dropped brownstone that read differently from the one next door would be
  // worse than no drop at all.
  const FACADE_KIT = {
    brownstone: { tex: 'brick',    st: 3.3, bay: 2.9, pier: 1.5, spand: 1.3,
                  w: 11, d: 9,  storeys: 5, tone: 0x9a6a52, roof: 0x4a4640 },
    skyscraper: { tex: 'concrete', st: 3.1, bay: 3.2, pier: 1.0, spand: 1.1,
                  w: 15, d: 15, storeys: 16, tone: 0xa9a49b, roof: 0x55524c },
    warehouse:  { tex: 'brick',    st: 4.0, bay: 3.5, pier: 1.4, spand: 1.3,
                  w: 16, d: 12, storeys: 4, tone: 0x8d5340, roof: 0x4a4640 },
    storefront: { tex: 'plaster',  st: 3.2, bay: 3.0, pier: 1.2, spand: 1.1,
                  w: 10, d: 8,  storeys: 3, tone: 0xb0a99b, roof: 0x4a4640 },
    limestone:  { tex: 'plaster',  st: 4.2, bay: 3.8, pier: 1.9, spand: 1.6,
                  w: 14, d: 11, storeys: 6, tone: 0xbdb5a4, roof: 0x55524c },
  };
  function buildFacadeBox(kind) {
    const F = FACADE_KIT[kind] || FACADE_KIT.brownstone;
    const g = new THREE.Group();
    const WTP = 0.42;
    const H = F.st * F.storeys;
    const hw = F.w / 2, hd = F.d / 2;
    const texL2 = new THREE.TextureLoader();
    const mtex = (n, sfx) => {
      const t = texL2.load('textures/' + n + (sfx || '') + '.jpg');
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.repeat.set(1 / 2.4, 1 / 2.4);              // UVs below are in metres
      if (!sfx) t.colorSpace = THREE.SRGBColorSpace;
      return t;
    };
    const wallM = new THREE.MeshStandardMaterial({
      map: mtex(F.tex), normalMap: mtex(F.tex, '_n'),
      normalScale: new THREE.Vector2(1.1, 1.1),
      color: new THREE.Color(F.tone), roughness: 0.93, metalness: 0.02 });
    // backing: what you see down every reveal, so it stays dark and matte
    const backM2 = new THREE.MeshStandardMaterial({ color: 0x27241f, roughness: 0.97 });
    backM2.userData.noAutoTex = true;
    const back = new THREE.Mesh(
      new THREE.BoxGeometry(F.w - WTP * 2, H, F.d - WTP * 2), backM2);
    back.position.y = H / 2;
    back.castShadow = back.receiveShadow = true;
    g.add(back);
    const boxes = [], panes = [];
    const B1 = new THREE.BoxGeometry(1, 1, 1);
    const M = new THREE.Matrix4(), Q = new THREE.Quaternion();
    const E = new THREE.Euler(), V = new THREE.Vector3(), S = new THREE.Vector3();
    // four walls; local +Z of each is its outward normal
    const sides = [[0, hd, 0, F.w], [0, -hd, Math.PI, F.w],
                   [hw, 0, Math.PI / 2, F.d], [-hw, 0, -Math.PI / 2, F.d]];
    for (const [sx, sz, yaw, L] of sides) {
      const nx = Math.sin(yaw), nz = Math.cos(yaw);
      const ux = nz, uz = -nx;                      // along the wall
      const ax = sx - ux * L / 2, az = sz - uz * L / 2;
      const nb = Math.max(1, Math.round(L / F.bay)), bw = L / nb;
      const pw = Math.min(F.pier, bw * 0.74);
      const sh = Math.min(F.spand, F.st * 0.6);
      const emit = (along, y, w, hh) => {
        const b = B1.clone();
        E.set(0, yaw, 0); Q.setFromEuler(E);
        V.set(ax + ux * along - nx * (WTP / 2), y, az + uz * along - nz * (WTP / 2));
        S.set(w, hh, WTP);
        b.applyMatrix4(M.compose(V, Q, S));
        // metre UVs on the outward faces so the brick reads at brick size
        const ps = b.attributes.position, no = b.attributes.normal, uv = b.attributes.uv;
        for (let i = 0; i < ps.count; i++) {
          const px = ps.getX(i), py = ps.getY(i), pz = ps.getZ(i);
          const al = (px - ax) * ux + (pz - az) * uz;
          const ou = (px - ax) * nx + (pz - az) * nz;
          if (Math.abs(no.getY(i)) > 0.7) uv.setXY(i, al, ou);
          else if (Math.abs(no.getX(i) * ux + no.getZ(i) * uz) > 0.7) uv.setXY(i, ou, py);
          else uv.setXY(i, al, py);
        }
        boxes.push(b);
      };
      for (let k = 0; k <= nb; k++) emit(k * bw, H / 2, pw, H);
      for (let sI = 0; sI <= F.storeys; sI++) {
        const y = sI === F.storeys ? H - sh / 2 : sI * F.st + sh / 2;
        emit(L / 2, y, L + 0.02, sh);
      }
      const ww = bw - pw;
      if (ww < 0.55) continue;
      for (let sI = 0; sI < F.storeys; sI++) {
        const y0 = sI * F.st + sh;
        const y1 = (sI + 1) * F.st - (sI === F.storeys - 1 ? sh : 0);
        if (y1 - y0 < 0.6) continue;
        for (let k = 0; k < nb; k++) {
          const al = (k + 0.5) * bw;
          const pane = new THREE.PlaneGeometry(ww, y1 - y0);
          pane.rotateY(yaw);
          pane.translate(ax + ux * al - nx * (WTP - 0.04), (y0 + y1) / 2,
                         az + uz * al - nz * (WTP - 0.04));
          panes.push(pane);
        }
      }
    }
    const wm = new THREE.Mesh(mergeGeometries(boxes, false), wallM);
    wm.castShadow = wm.receiveShadow = true;
    g.add(wm);
    for (const b of boxes) b.dispose();
    if (panes.length) {
      // 0.09 roughness against a noon sky is a mirror, which is why these
      // panes read as flat blue cards. The city's own glazing already learned
      // this: mostly a dark, slightly rough reflector.
      const glassM2 = new THREE.MeshStandardMaterial({ color: 0x2b3440,
        roughness: 0.26, metalness: 0.0, envMapIntensity: 0.45 });
      glassM2.userData.noAutoTex = true;
      const gm = new THREE.Mesh(mergeGeometries(panes, false), glassM2);
      g.add(gm);
      for (const q of panes) q.dispose();
    }
    const cap = new THREE.Mesh(new THREE.BoxGeometry(F.w + 0.5, 0.5, F.d + 0.5),
      new THREE.MeshStandardMaterial({ color: F.roof, roughness: 0.94 }));
    cap.position.y = H + 0.25;
    cap.castShadow = true;
    g.add(cap);
    return { g, h: H };
  }
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
    if (FACADE_KIT[kind]) return buildFacadeBox(kind);
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
  // ── AUDIT FIXES (2026-08-25, critique-loop phase 1) ────────────────────
  // After a build, the pipeline loads the game headless, asks the scene to
  // audit itself (window.__audit below), and writes the corrections next to
  // the build as audit_fixes.json. Applied HERE, before anything is built,
  // so a moved placed item moves its collider with it — fixing the mesh
  // after the collider exists would leave an invisible wall at the old spot.
  // Absent file = first build or clean audit; both are fine.
  let __AUDIT_FIX = null;
  try {
    const _afr = await fetch('audit_fixes.json');
    if (_afr.ok) __AUDIT_FIX = await _afr.json();
  } catch (e) { /* no fixes yet — the audit writes them post-build */ }
  window.__AUDIT_FIX = __AUDIT_FIX;
  if (__AUDIT_FIX && Array.isArray(__AUDIT_FIX.fixes)) {
    let _nfx = 0;
    for (const f of __AUDIT_FIX.fixes) {
      const m = /^placed:(\d+)$/.exec(f.id || '');
      if (!m || !f.fix) continue;
      const it = (SPEC.world.placed_items || [])[+m[1]];
      if (!it) continue;
      if (f.fix.hide) { it.__hide = true; _nfx++; continue; }
      it.x += f.fix.dx || 0;
      it.z += f.fix.dz || 0;
      if (f.fix.dy) it.__fy = (it.__fy || 0) + f.fix.dy;
      _nfx++;
    }
    if (_nfx) console.log('[audit] applied ' + _nfx + ' placed-item fix(es)');
  }
  for (const [pIdx, it] of (SPEC.world.placed_items || []).entries()) {
    if (it.__hide) continue;             // audit verdict: no safe spot exists
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
      const gy = hAt(it.x, it.z) + (it.__fy || 0);
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
      // a car beats a readable note on the same key: you are standing at a
      // door handle, not a signpost. Hooked through `window` on purpose —
      // this listener is built ~1300 lines before the car system exists.
      if (gameStarted && window.__carE && window.__carE()) return;
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
  // ── DIALOGUE (2026-08-05): a bottom-of-screen speech panel with the
  // speaker's name — the Pokémon convention, because it is the one every
  // player already knows how to read. Also the general popup layer: any
  // system can say something in character through say().
  function say(who, text, tint) {
    let d = document.getElementById('fsdlg');
    if (!d) {
      d = document.createElement('div');
      d.id = 'fsdlg';
      d.style.cssText = 'position:fixed;left:50%;bottom:34px;transform:translateX(-50%);'
        + 'width:min(680px,88vw);padding:13px 18px 15px;border-radius:12px;'
        + 'background:rgba(9,11,20,.90);border:1px solid rgba(255,255,255,.13);'
        + 'box-shadow:0 10px 34px rgba(0,0,0,.5);z-index:44;pointer-events:none;'
        + 'font:15px/1.5 system-ui;color:#eceaf6;opacity:0;transition:opacity .22s';
      d.innerHTML = '<div id="fsdlgwho" style="font:700 12px system-ui;'
        + 'letter-spacing:.06em;text-transform:uppercase;margin-bottom:5px"></div>'
        + '<div id="fsdlgtxt"></div>';
      document.body.appendChild(d);
    }
    const w = document.getElementById('fsdlgwho');
    w.textContent = who || '';
    w.style.color = tint || '#5cffc9';
    document.getElementById('fsdlgtxt').textContent = text;
    d.style.opacity = '1';
    clearTimeout(window.__dlgT);
    window.__dlgT = setTimeout(() => { d.style.opacity = '0'; },
                               Math.min(9000, 2600 + text.length * 45));
    sfx('pickup');
  }
  // OBJECTIVE BANNER: the wipe across the middle of the screen that tells
  // you the mission just changed. Cheap, and it is most of what makes a
  // game feel like it is reacting to you.
  function banner(text, sub) {
    let b = document.getElementById('fsban');
    if (!b) {
      b = document.createElement('div');
      b.id = 'fsban';
      b.style.cssText = 'position:fixed;left:0;right:0;top:31%;text-align:center;'
        + 'z-index:43;pointer-events:none;opacity:0;transition:opacity .3s,'
        + 'letter-spacing .5s;letter-spacing:.02em';
      b.innerHTML = '<div id="fsbansub" style="font:700 11px system-ui;'
        + 'letter-spacing:.22em;text-transform:uppercase;color:#8f8ba8;'
        + 'margin-bottom:6px">new objective</div>'
        + '<div id="fsbantxt" style="font:700 27px system-ui;color:#fff;'
        + 'text-shadow:0 3px 18px rgba(0,0,0,.75)"></div>';
      document.body.appendChild(b);
    }
    document.getElementById('fsbansub').textContent = sub || 'new objective';
    document.getElementById('fsbantxt').textContent = text;
    b.style.opacity = '1'; b.style.letterSpacing = '.06em';
    clearTimeout(window.__banT);
    window.__banT = setTimeout(() => {
      b.style.opacity = '0'; b.style.letterSpacing = '.02em';
    }, 2400);
  }
  // what the guide says about the step you are actually on
  function guideLine(st) {
    if (!st) return 'That is everything. Get out while you can.';
    const n = st.count, l = st.label || 'them';
    // a city heist has to say WHERE: the loot is behind four doors on the
    // block, and nothing else on screen tells you the glow is a way in
    if (st.kind === 'collect' && ENTERABLES.length > 1)
      return `${n} ${l}, spread across ${ENTERABLES.length} buildings on this `
        + `block. Walk into a glowing doorway to get inside — the amber dots `
        + `on the map are the ways in. Same doorway takes you back out.`;
    if (st.kind === 'collect') return HAS_GUARDS
      ? `Take ${n} ${l} — and mind the patrols. Crouch with C, and if a guard `
        + `is in your way, throw something with Q to pull him off it.`
      : `Find ${n} ${l} for me. They are scattered — look around.`;
    if (st.kind === 'defeat') return `You will have to fight. Put down ${n} ${l} — press F to strike.`;
    if (st.kind === 'escort')
      return `${l ? l[0].toUpperCase() + l.slice(1) : 'Your charge'} walks the road `
        + `on his own — STAY CLOSE or he stops and waits for you. The wolves will `
        + `go for HIM, not you. Keep them off him until he reaches the beacon.`;
    if (st.kind === 'survive') return `Just stay alive. Keep moving and do not let them corner you.`;
    if (st.kind === 'race') return `Beat all ${n} of them to the finish. Shift for speed.`;
    if (st.kind === 'hunt') return `Track ${n} ${l}. Move slow — they bolt if they hear you.`;
    if (st.kind === 'eliminate') return `Last one standing. ${n} rivals, one winner.`;
    if (st.kind === 'score') return `Put ${n} away and it is yours.`;
    if (st.kind === 'capture') return `Hold ${n} ground. Eight seconds each, and do not step off.`;
    return HAS_GUARDS
      ? `You have what you came for. Get to ${l} — that is your way out.`
      : `Make for ${l}. That is where this ends.`;
  }
  function sayGuide(n) {
    // a role, not a species: "MAN" as a speaker name reads like placeholder
    // text. The job the character is doing is what the player should see.
    const role = HAS_GUARDS ? 'Informant'
      : (SPEC.objectives || []).some(o => o.kind === 'race') ? 'Crew Chief'
      : (SPEC.objectives || []).some(o => o.kind === 'hunt') ? 'Tracker'
      : 'Guide';
    say(role, guideLine(steps[stepIdx]), '#ffd166');
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
    if (st.kind === 'escort') return `Escort ${st.label || 'your charge'} to the beacon — keep them alive`;
    return `Reach ${st.label || 'the beacon'}`;
  }
  function stepProgress(st) {
    if (st.kind === 'collect') return `${st._got || 0}/${st.count}`;
    if (st.kind === 'defeat' || st.kind === 'eliminate' || st.kind === 'hunt')
      return `${Math.min(kills - (st._k0 || 0), st.count)}/${st.count}`;
    if (st.kind === 'score') return `${st._goals || 0}/${st.count}`;
    if (st.kind === 'escort') {
      const e5 = npcs.find(nn => nn.behavior === 'escort' && !nn.dead);
      if (!e5 || !goalPos) return '';
      if (e5._arrived) return '100%';
      const dNow = Math.hypot(goalPos.x - e5.obj.position.x, goalPos.z - e5.obj.position.z);
      const d0 = st._d0 || dNow || 1;
      return Math.max(0, Math.min(99, Math.round((1 - dNow / d0) * 100))) + '%';
    }
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
    // NEW-OBJECTIVE BANNER: every step change announces itself, and any
    // guide in the level re-briefs you on the new one next time you pass.
    banner(stepLabel(st));
    for (const g of npcs) { if (g.behavior === 'guide') g._said = false; }
    if (st.kind === 'collect') { st._got = 0; spawnCollectibles(st); }
    if (st.kind === 'defeat' || st.kind === 'eliminate' || st.kind === 'hunt') { st._k0 = kills; }
    if (st.kind === 'score') { st._goals = 0; }
    if (st.kind === 'capture') { st._zi = 0; st._hold = 0; spawnCaptureZones(st); }
    if (st.kind === 'escort') {
      const e6 = npcs.find(nn => nn.behavior === 'escort' && !nn.dead);
      if (e6 && goalPos) st._d0 = Math.hypot(goalPos.x - e6.obj.position.x,
                                             goalPos.z - e6.obj.position.z);
    }
    renderQuest();
  }
  let won_ = false;   // guard alias kept for clarity in doWin
  function doWin(text) {
    if (won || lost) return;
    won = true; won_ = true;
    juiceFly = 0;                          // the world takes a bow
    // the heist take outlives the heist: winnings bank into the campaign
    // hero, so level 2 of a project starts with level 1's money on the books
    if (window.__take > 0) {
      _bank += window.__take;
      _saveProg();
    }
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
    // the take is the heist's score — a number worth beating on a rerun
    document.getElementById('wintext').textContent = window.__take
      ? `${text}  ·  took $${window.__take.toLocaleString()}` : text;
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
  const hostilesExist = (SPEC.entities || []).some(
    e => e.behavior === 'hostile' || e.behavior === 'guard');
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
  // scope resolution, most explicit wins: a spec-stamped project tag (the
  // studio opening a project level), then the exported hub's URL layout,
  // then the single game's own title
  const _progKey = SPEC.project_tag ? 'fs_prog_proj_' + SPEC.project_tag
                 : _projM ? 'fs_prog_proj_' + _projM[1]
                          : 'fs_prog_' + (SPEC.title || 'game');
  const _picks = [];
  let _bank = 0;                 // career haul, paid in on every win
  function _saveProg() {
    try { localStorage.setItem(_progKey,
      JSON.stringify({ lvl: plvl, picks: _picks, bank: _bank })); } catch (e) {}
  }
  function _applyPick(k, silent) {
    if (k === 'heart') { P.hp = (P.hp || 5) + 1; php += 1; }
    else if (k === 'swift') { P.walk_speed *= 1.12; P.run_speed *= 1.12; }
    else if (k === 'power') { atkDmg += 1; }
    _picks.push(k);
    if (!silent) _saveProg();
  }
  window.__restoreProg = () => {          // called once the player is ready
    try {
      const sv = JSON.parse(localStorage.getItem(_progKey) || 'null');
      if (sv && sv.picks) {
        for (const k of sv.picks) _applyPick(k, true);
        plvl = sv.lvl || (sv.picks.length + 1);
        _bank = sv.bank || 0;
        renderHearts();
        if (sv.picks.length) popText('Level ' + plvl + ' hunter returns', '#8de06c');
        if (_bank > 0) popText('Career haul: $' + _bank.toLocaleString(), '#ffd54a');
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
  // ── EVENTS: when <condition> then <reactions> (2026-08-25) ─────────────
  // The verb that turns the objective checklist into a STORY. Every
  // condition reads state the engine already tracks and every action drives
  // a primitive that already exists (popups, guard alerts, win/lose, NPC
  // clones), so the LLM composes drama out of parts that cannot break the
  // game. Function declarations, hoisted on purpose: the frame loop calls
  // stepEvents long after this point, and a const would be one more chance
  // at TRAP 1.
  const EVENTS = (SPEC.events || []).map(e => ({
    when: String(e.when || ''), then: Array.isArray(e.then) ? e.then : [],
    fired: false }));
  let evTimer = null;                     // {left, label, onZero}
  let evPoll = 0;
  function evCollected() {
    let g = 0;
    for (const st of steps || []) if (st.kind === 'collect') g += (st._got || 0);
    return g;
  }
  function evCondition(w) {
    let m;
    if ((m = w.match(/^collected\s*>=\s*(\d+)$/))) return evCollected() >= +m[1];
    if ((m = w.match(/^kills\s*>=\s*(\d+)$/))) return kills >= +m[1];
    if ((m = w.match(/^time\s*>\s*(\d+)$/)))
      return (performance.now() - runT0) / 1000 > +m[1];
    if ((m = w.match(/^hp\s*<=\s*(\d+)$/))) return php <= +m[1];
    if (w === 'alert')
      return npcs.some(nn => nn.behavior === 'guard' && !nn.dead
                             && (nn.mode === 'chase' || (nn.alert || 0) > 0.65));
    return false;                          // unknown grammar: never fires
  }
  function evSpawn(name, count) {
    // clone an NPC that already exists — the grammar promises only "more of
    // what is already in the scene", so there is no asset fetch, no bake,
    // and a spawn cannot fail into a missing-mesh crash
    const src = npcs.find(nn => !nn.dead && nn.name === name)
             || npcs.find(nn => !nn.dead && (nn.behavior === 'guard' || nn.behavior === 'hostile'));
    if (!src) return;
    const bp = body.translation();
    for (let i = 0; i < Math.min(count, 6); i++) {
      try {
        const holder2 = skClone(src.obj);
        const a = Math.random() * Math.PI * 2, r = 11 + Math.random() * 5;
        const sx = bp.x + Math.cos(a) * r, sz = bp.z + Math.sin(a) * r;
        holder2.position.set(sx, hAt(sx, sz), sz);
        holder2.visible = true;
        scene.add(holder2);
        // rebuild the mixer on the CLONE's own skeleton — actions cannot be
        // shared across skClone copies
        let anim2 = null;
        if (src.anim && src.anim.mixer) {
          const inner = holder2.children[0] || holder2;
          const mixer2 = new THREE.AnimationMixer(inner);
          const clipOf = a2 => (a2 && a2.getClip ? a2.getClip() : null);
          const mk = c => (c ? mixer2.clipAction(c) : null);
          anim2 = { mixer: mixer2, idle: mk(clipOf(src.anim.idle)),
                    walk: mk(clipOf(src.anim.walk)), run: mk(clipOf(src.anim.run)),
                    cur: null };
          anim2.cur = anim2.idle || anim2.walk;
          if (anim2.cur) anim2.cur.play();
        }
        const mats2 = [];
        holder2.traverse(o => { if (o.isMesh) {
          o.castShadow = true; o.frustumCulled = false;
          for (const mm of (Array.isArray(o.material) ? o.material : [o.material]))
            if (mm) mats2.push(mm);
        } });
        holder2.userData.fsTag = { type: 'npc', name: src.name || 'reinforcement',
                                   detail: 'hostile · event spawn' };
        npcs.push({ obj: holder2, down: 0, kx: 0, kz: 0,
                    speed: (src.speed || 1.5) * 1.1, behavior: 'hostile',
                    target: null, yaw: Math.random() * Math.PI * 2,
                    phase: Math.random() * Math.PI * 2, h: src.h || 1.0,
                    name: src.name, beat: null, pen: null,
                    hp: src.hp || 3, cd: 0, dead: false, dieT: 0,
                    mats: mats2, anim: anim2, dormant: false });
      } catch (err) { console.warn('[events] spawn failed:', err.message); }
    }
  }
  function evRun(action) {
    let m;
    if ((m = action.match(/^popup:(.+)$/))) { popText(m[1].trim(), '#ffd166'); sfx('beep'); return; }
    if ((m = action.match(/^spawn:\s*([\w ]+?)\s*x(\d+)$/))) { evSpawn(m[1].trim(), +m[2]); return; }
    if (action === 'alertguards') {
      for (const nn of npcs) if (nn.behavior === 'guard' && !nn.dead) {
        nn.mode = 'chase'; nn.alert = 1;
      }
      sfx('hurt');
      return;
    }
    if ((m = action.match(/^timer:(\d+):([^:]+):(lose|win)$/))) {
      evTimer = { left: +m[1], label: m[2].trim(), onZero: m[3] };
      return;
    }
    if ((m = action.match(/^win:(.*)$/))) { doWin(m[1].trim() || undefined); return; }
    if ((m = action.match(/^lose:(.*)$/))) { doLose(m[1].trim() || 'The job went wrong.'); return; }
    console.warn('[events] unknown action:', action);
  }
  function stepEvents(dt) {
    if (!gameStarted || won || lost) return;
    if (evTimer) {
      evTimer.left -= dt;
      if (!window.__evTimerEl) {
        const el = document.createElement('div');
        el.style.cssText = 'position:fixed;top:64px;left:50%;transform:translateX(-50%);'
          + 'font:800 22px system-ui;color:#ff9f5c;background:rgba(10,9,18,.78);'
          + 'border:1px solid rgba(255,159,92,.4);border-radius:10px;'
          + 'padding:6px 18px;z-index:30;pointer-events:none;';
        document.body.appendChild(el);
        window.__evTimerEl = el;
      }
      window.__evTimerEl.textContent =
        evTimer.label + ' — ' + Math.max(0, evTimer.left).toFixed(0) + 's';
      if (evTimer.left <= 0) {
        const z = evTimer; evTimer = null;
        window.__evTimerEl.remove(); window.__evTimerEl = null;
        if (z.onZero === 'lose') doLose(z.label); else doWin();
        return;
      }
    }
    evPoll += dt;
    if (evPoll < 0.4) return;              // conditions are cheap but not free
    evPoll = 0;
    for (const ev of EVENTS) {
      if (ev.fired || !evCondition(ev.when)) continue;
      ev.fired = true;
      shakeT = Math.max(shakeT, 0.4 * FEEL.shake);
      juicePunch = Math.max(juicePunch, 0.7 * FEEL.punch);
      console.log('[events] fired:', ev.when, '->', ev.then.join(' | '));
      for (const a of ev.then) evRun(String(a));
    }
  }
  // harness hooks: assertions need to SEE the events and force one to run.
  // Stashed here and merged where window.__game is CREATED — assigning onto
  // __game at this point in the file was writing to undefined and took the
  // whole runtime down (TRAP 4, again, while this block's own comment was
  // busy congratulating itself about TRAP 1).
  const __evHooks = {
    events: () => EVENTS.map(e => ({ when: e.when, fired: e.fired })),
    trigger: i => { const e = EVENTS[i]; if (!e || e.fired) return false;
      e.fired = true; for (const a of e.then) evRun(String(a)); return true; },
  };
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
  // A blast is the same knockdown the cars use, applied radially — one
  // downed-state machine for being run over and being blown off your feet,
  // so they can never drift apart.
  function detonate(x, y, z) {
    const W = WEAPONS[2], R = W.blast;
    _blastBall.position.set(x, y + 0.9, z);
    _blastBall.visible = true;
    _blastLight.position.set(x, y + 1.2, z);
    _blastLight.distance = R * 3.2;
    blasts.length = 0;                    // one fireball, so one blast at a time
    blasts.push({ obj: _blastBall, light: _blastLight, t: 0, r: R });
    shakeT = Math.max(shakeT, 0.5);
    sfx('hit');
    const knock = (o, rec, isNpc) => {
      const dx7 = o.position.x - x, dz7 = o.position.z - z;
      const d7 = Math.hypot(dx7, dz7);
      if (d7 > R) return;
      const f7 = (1 - d7 / R);
      rec.down = 2.4 + f7 * 1.8;
      rec.kx = (dx7 / (d7 || 1)) * 13 * f7;
      rec.kz = (dz7 / (d7 || 1)) * 13 * f7;
      if (isNpc) {
        rec.hp = (rec.hp || 1) - WEAPONS[2].dmg;
        if (rec.hp <= 0 && !rec.dead) { rec.dead = true; rec.dieT = 0; }
        if (rec.behavior === 'guard') { rec.mode = 'patrol'; rec.alert = 0; }
      } else if (rec.mixer) { rec.mixer.stopAllAction(); }
    };
    for (const nn of npcs) {
      if (nn.dormant || nn.dead) continue;
      knock(nn.obj, nn, true);
    }
    for (const pd of window.__peds || []) knock(pd.obj, pd, false);
    // and it throws YOU, which is what makes a launcher a decision
    const bp8 = body.translation();
    const dxp = bp8.x - x, dzp = bp8.z - z;
    const dp8 = Math.hypot(dxp, dzp);
    if (dp8 < R && !DRIVING) {
      downT = 1.8;
      downVX = (dxp / (dp8 || 1)) * 12 * (1 - dp8 / R);
      downVZ = (dzp / (dp8 || 1)) * 12 * (1 - dp8 / R);
      playerHit(1);
    }
  }
  function playerHit(dmg) {
    if (won || lost) return;
    php = Math.max(0, php - dmg);
    sfx('hurt');
    shakeT = 0.3;                        // impact you can FEEL
    renderHearts();
    dmgEl.style.opacity = '1';
    setTimeout(() => { dmgEl.style.opacity = '0'; }, 160);
    if (php <= 0) doLose(HAS_GUARDS
      ? 'Busted. The guards dragged you out.'   // a heist ends in cuffs
      : 'Overwhelmed by enemies.');
  }

  // ── player: animated GLB + kinematic capsule ─────────────────────────────
  let mixer = null, actions = {}, current = null;
  const P = SPEC.player;
  // ── PARAMETRIC CARS (2026-08-04): image-to-3D is blobby on vehicles
  // because a car is a HARD-SURFACE PARAMETRIC object, not an organic
  // blob — every AI mesh melts the roofline and smears the wheels. Cars
  // are now BUILT IN CODE from ~20 params (the reference image only sets
  // proportions + paint), so panels are crisp, wheels are round, glass
  // is glass. Animals keep the generated-mesh path, where it wins.
  // ── VEHICLE TYPES (2026-08-06) ────────────────────────────────────────
  // One shell, six silhouettes. A street of identical sedans is the same
  // clone-army tell as a street of identical buildings, and every knob
  // these presets turn was already a buildCar parameter — the only new
  // geometry is the pickup bed and the taxi roof light.
  const CAR_TYPES = {
    sedan:  { length: 4.55, width: 1.83, bodyH: 0.60, bodyY: 0.52, cabinLen: 0.42, cabinH: 0.50, cabinX: -0.03, wheelR: 0.33, wheelBase: 0.31 },
    coupe:  { length: 4.30, width: 1.86, bodyH: 0.55, bodyY: 0.47, cabinLen: 0.34, cabinH: 0.44, cabinX: -0.09, wheelR: 0.33, wheelBase: 0.32 },
    suv:    { length: 4.85, width: 1.98, bodyH: 0.80, bodyY: 0.70, cabinLen: 0.50, cabinH: 0.60, cabinX: -0.02, wheelR: 0.41, wheelBase: 0.31 },
    pickup: { length: 5.40, width: 2.00, bodyH: 0.74, bodyY: 0.68, cabinLen: 0.30, cabinH: 0.62, cabinX: 0.13, wheelR: 0.41, wheelBase: 0.33, bed: 1 },
    van:    { length: 5.25, width: 2.02, bodyH: 1.08, bodyY: 0.80, cabinLen: 0.58, cabinH: 0.44, cabinX: -0.11, wheelR: 0.36, wheelBase: 0.33 },
    taxi:   { length: 4.60, width: 1.86, bodyH: 0.62, bodyY: 0.54, cabinLen: 0.44, cabinH: 0.52, cabinX: -0.03, wheelR: 0.34, wheelBase: 0.31, taxi: 1 },
    // 2026-08-07: six silhouettes repeated down a whole avenue still read as
    // a fleet of the same car. These four are the shapes a New York street
    // actually has that the set was missing — the long low one, the tall
    // narrow one, the box truck and the wagon.
    sports: { length: 4.35, width: 1.94, bodyH: 0.46, bodyY: 0.40, cabinLen: 0.30, cabinH: 0.34, cabinX: -0.12, wheelR: 0.34, wheelBase: 0.34 },
    compact:{ length: 3.85, width: 1.70, bodyH: 0.62, bodyY: 0.54, cabinLen: 0.46, cabinH: 0.54, cabinX: -0.01, wheelR: 0.30, wheelBase: 0.30 },
    box:    { length: 6.10, width: 2.18, bodyH: 1.35, bodyY: 0.92, cabinLen: 0.26, cabinH: 0.50, cabinX: 0.30, wheelR: 0.40, wheelBase: 0.34 },
    wagon:  { length: 4.90, width: 1.88, bodyH: 0.66, bodyY: 0.56, cabinLen: 0.56, cabinH: 0.50, cabinX: -0.05, wheelR: 0.34, wheelBase: 0.31 },
  };
  // weighted so the street is mostly ordinary traffic with the odd truck —
  // an even mix reads as a car showroom, not a city
  const CAR_TYPE_KEYS = ['sedan', 'sedan', 'sedan', 'compact', 'compact',
    'coupe', 'suv', 'suv', 'wagon', 'pickup', 'van', 'taxi', 'taxi',
    'sports', 'box'];
  function buildCar(cp) {
    const g = new THREE.Group();
    const T = CAR_TYPES[cp.type] || {};
    const L = cp.length || T.length || 4.4, Wd = cp.width || T.width || 1.85;
    const bodyH = cp.bodyH || T.bodyH || 0.62, bodyY = cp.bodyY || T.bodyY || 0.52;
    const cabLen = cp.cabinLen || T.cabinLen || 0.46, cabH = cp.cabinH || T.cabinH || 0.52;
    const cabX = cp.cabinX !== undefined ? cp.cabinX
               : (T.cabinX !== undefined ? T.cabinX : -0.04);
    const wr = cp.wheelR || T.wheelR || 0.34;
    const paint = new THREE.MeshPhysicalMaterial({
      // real automotive paint is a metallic basecoat under near-perfect
      // lacquer: it is almost ENTIRELY reflection. At metalness 0.55 /
      // roughness 0.28 the body read as flat coloured plastic even with an
      // environment present (measured in tools/carlab).
      // 2026-08-06: metalness 0.85 at envMapIntensity 1.6 is the SAME bug
      // the window glazing had. A metal has almost no diffuse and tints its
      // reflection by its base colour, so at night every car became a mirror
      // of a warm dark sky and the whole fleet came out WOODEN — brown, matte
      // and colourless. Real metallic paint is a thin metal flake suspended in
      // a dielectric binder under clear lacquer: most of what you see is the
      // clearcoat, not raw metal. Low metalness keeps the colour alive under
      // any lighting; clearcoat still supplies the wet highlight.
      // PER-CAR FINISH (2026-08-07). Uniform roughness across a fleet is
      // the single loudest CG-plastic tell there is — twenty cars sharing
      // one lacquer read as twenty copies of one object even in different
      // colours. Each car gets its own place on the scale from a showroom
      // respray to a cab that has not been washed since the spring, keyed
      // off its own paint so it is stable across rebuilds.
      color: new THREE.Color(cp.paint || 0xb5202a), metalness: 0.28,
      ...(() => {
        const h7 = ((cp.paint || 0xb5202a) * 2654435761) % 1000 / 1000;
        const wear = 0.25 + h7 * 0.75;              // 0 pristine .. 1 neglected
        return {
          roughness: 0.22 + wear * 0.36,
          clearcoat: 1.0 - wear * 0.45,
          clearcoatRoughness: 0.03 + wear * 0.22,
          envMapIntensity: 1.15 - wear * 0.5,
        };
      })() });
    const glass = new THREE.MeshPhysicalMaterial({
      color: 0x101418, metalness: 0.1, roughness: 0.06,
      transmission: 0.55, thickness: 0.4, transparent: true, opacity: 0.72 });
    const trim = new THREE.MeshStandardMaterial({
      color: 0x1b1d20, metalness: 0.7, roughness: 0.42 });
    // ── ONE AXIS FOR THE WHOLE CAR (2026-08-06 rewrite) ──────────────────
    // Previously the shell was built on X, spun 90 deg onto Z by itself, and
    // then translated by Wd/2 — but that rotate had already moved the width
    // axis onto X, so the translate slid the BODY 0.9m down the car relative
    // to every wheel, light and grille, and left the shell 0.9m off-centre
    // sideways as well. In game that is exactly what you saw: a black slab
    // with the wheels buried on one side and floating free on the other, and
    // the nose pointing at -Z (backwards) because rotateY(+90) maps +x to -z.
    //
    // The prior fix attempts failed because they moved the rotation around
    // while the FITTINGS stayed in the rotated convention. So: no rotation
    // anywhere in here. The car is authored the way tools/carlab authors it —
    // X along the car, NOSE AT +X, Y up, extrusion across Z — which is the
    // convention alignLongAxis() was written for ("vehicles that lie along X
    // carry the NOSE at +X"). It does the single -90 deg turn onto +Z for the
    // finished model, once, and nothing double-applies.
    //
    // t runs 0 = nose .. 1 = tail, so every fraction below reads as a place
    // on the car. The numbers are carlab's tuned values.
    const NOSE_FALL = 0.16, TAIL_RISE = 0.07, WIND_RAKE = 0.55, BACK_RAKE = 0.62;
    const TRACK_INSET = 0.06;
    const xAt = t => L * 0.5 - t * L;
    const yb = Math.max(0.13, bodyY - bodyH * 0.5);   // sill height (ride)
    const yt = yb + bodyH;                            // beltline
    // cabin as a span of t. Clamped so the windscreen always sits behind the
    // point where the profile has finished climbing over the front wheel —
    // an unclamped truck cabin ran the outline backwards on itself.
    const cabF = Math.min(Math.max(0.5 - cabX - cabLen * 0.5, 0.32), 0.60);
    const cabR = Math.min(cabF + cabLen, 0.90);
    const wsT = Math.min(cabF + WIND_RAKE * 0.14, cabR - 0.10);
    const rrT = Math.max(cabR - BACK_RAKE * 0.10, wsT + 0.06);
    const s = new THREE.Shape();
    // r5: this profile was eight STRAIGHT lines, which is why the car read
    // as folded cardboard however good the paint was. The same control points
    // as quadratics give a crowned bonnet, a curved screen and a rounded tail
    // for no new parameters and no extra draw calls.
    s.moveTo(xAt(0.02), yb + NOSE_FALL * 0.5);        // nose, low
    s.quadraticCurveTo(xAt(0.15), yt - 0.13, xAt(0.30), yt - 0.02);
    s.lineTo(xAt(cabF), yt);                          // beltline
    s.quadraticCurveTo(xAt(cabF + (wsT - cabF) * 0.5), yt + cabH * 0.74,
                       xAt(wsT), yt + cabH);          // windscreen
    s.lineTo(xAt(rrT), yt + cabH);                    // roof
    s.quadraticCurveTo(xAt(rrT + (Math.min(cabR + 0.06, 0.95) - rrT) * 0.55),
                       yt + cabH * 0.5,
                       xAt(Math.min(cabR + 0.06, 0.95)), yt);   // backlight
    s.quadraticCurveTo(xAt(0.93), yt + TAIL_RISE,
                       xAt(0.97), yt - 0.04 + TAIL_RISE);       // tail
    s.lineTo(xAt(0.97), yb);                          // rear valance
    // WHEEL ARCHES (2026-08-06 r7). The sill ran dead straight from tail to
    // nose, so the flank met the ground as one flat slab and the wheels read
    // as cylinders parked beside a wedge. Every car cuts an arch over each
    // axle; that scallop is most of what says "car" from the side. Walking
    // the sill BACKWARD (tail → nose) here because the profile is wound that
    // way — arcs added in the wrong order self-intersect the shape.
    {
      const wb = cp.wheelBase || 0.31;
      const arch = (wr || 0.33) * 1.16;               // arch clears the tyre
      const aR = 1 - wb, aF = wb;                     // rear, front axle (t)
      const halfA = arch / L;                         // arch half-width in t
      s.lineTo(xAt(aR + halfA), yb);                  // sill up to rear arch
      s.quadraticCurveTo(xAt(aR), yb + arch * 0.92,
                         xAt(aR - halfA), yb);        // over the rear wheel
      s.lineTo(xAt(aF + halfA), yb);                  // rocker panel between
      s.quadraticCurveTo(xAt(aF), yb + arch * 0.92,
                         xAt(aF - halfA), yb);        // over the front wheel
    }
    s.lineTo(xAt(0.02), yb);                          // sill to the nose
    s.closePath();
    const depth = Wd - TRACK_INSET * 2;
    const bg = new THREE.ExtrudeGeometry(s, {
      depth, bevelEnabled: true, bevelSize: 0.075,
      bevelThickness: 0.06, bevelSegments: 4, curveSegments: 18 });
    bg.translate(0, 0, -depth / 2);            // straddle the centreline
    // ── THE CAR IS STILL A BOX IN PLAN (2026-08-06 r6) ──────────────────
    // The profile curve fixed the SIDE view, but an extrusion is a constant
    // width from nose to tail with vertical flanks, and that is what still
    // read as a brick: real cars pull in at both ends and lean the glasshouse
    // inboard above the beltline (tumblehome). Both are a cheap deformation
    // of the extruded vertices — no new geometry, no extra draw call.
    {
      const bp = bg.attributes.position;
      const roofY = yt + cabH;
      for (let i = 0; i < bp.count; i++) {
        const x = bp.getX(i), y = bp.getY(i), z = bp.getZ(i);
        const t = Math.min(1, Math.max(0, (L * 0.5 - x) / L));   // 0 nose .. 1 tail
        // full width across the cabin, drawn in toward both ends. Tail pulls
        // in slightly less than the nose, which is what a car actually does.
        const nose = Math.min(1, t / 0.22), tail = Math.min(1, (1 - t) / 0.18);
        const plan = 1 - 0.17 * (1 - nose) - 0.11 * (1 - tail);
        // tumblehome above the beltline, plus a little sill tuck below it
        const above = Math.min(1, Math.max(0, (y - yt) / Math.max(cabH, 1e-3)));
        const below = Math.min(1, Math.max(0, (yb + 0.14 - y) / 0.2));
        const lean = 1 - 0.20 * above * above - 0.06 * below;
        bp.setZ(i, z * plan * lean);
        // crown the roof so it is not a flat plate
        if (y > roofY - 0.02) {
          const across = Math.min(1, Math.abs(z) / (depth * 0.5));
          bp.setY(i, y + 0.030 * (1 - across * across));
        }
      }
      bp.needsUpdate = true;
      bg.computeVertexNormals();
    }
    const body = new THREE.Mesh(bg, paint);
    body.castShadow = body.receiveShadow = true;
    g.add(body);
    // GREENHOUSE: inset glass box so windows read as openings, not decals
    const gh = new THREE.Mesh(new THREE.BoxGeometry(
      (cabR - cabF) * L * 0.82, cabH * 0.86, Wd - 0.16), glass);
    gh.position.set(xAt((cabF + cabR) * 0.5), yt + cabH * 0.52, 0);
    gh.userData.noShadow = 1;
    g.add(gh);
    // WHEELS sit OUTBOARD of the bodyside, not inside it (carlab): a wheel's
    // inner face meets the flank and the tyre stands slightly proud of it.
    // Placed inboard they are simply swallowed by the extrusion.
    const wheelW = Math.max(0.18, Wd * 0.13);
    const halfBody = Wd * 0.5 - TRACK_INSET;
    const trackZ = halfBody + wheelW * 0.5 - 0.03;
    const tyreM = new THREE.MeshStandardMaterial({ color: 0x14161a, roughness: 0.93 });
    const rimM = new THREE.MeshStandardMaterial({ color: 0xc9ced6, metalness: 0.92,
                                                  roughness: 0.22 });
    const archM = new THREE.MeshBasicMaterial({ color: 0x0a0b0e });
    const wb = cp.wheelBase || T.wheelBase || 0.31;
    // 2026-08-06 PERF: these were twelve separate meshes per car. At 60-odd
    // cars on screen that is ~700 draw calls of wheel, and each one paid
    // again in the shadow pass — measured 60fps -> 38fps the moment the kerbs
    // filled up. Same geometry, merged per material: twelve becomes three.
    const tyG = [], hubG = [], arG = [];
    for (const t of [0.5 - wb, 0.5 + wb]) {
      for (const side of [-1, 1]) {
        const wg = new THREE.CylinderGeometry(wr, wr, wheelW, 18);
        wg.rotateX(Math.PI / 2);
        wg.translate(xAt(t), wr, side * trackZ);
        tyG.push(wg);
        const hg = new THREE.CylinderGeometry(wr * 0.56, wr * 0.56, wheelW * 0.55, 14);
        hg.rotateX(Math.PI / 2);
        hg.translate(xAt(t), wr, side * (trackZ + wheelW * 0.26));
        hubG.push(hg);
        // dark disc behind the wheel: reads as a wheel well, which is what
        // stops a cylinder looking stuck onto a flat flank
        const ag = new THREE.CircleGeometry(wr * 1.16, 16);
        if (side < 0) ag.rotateY(Math.PI);
        ag.translate(xAt(t), wr, side * (halfBody - 0.005));
        arG.push(ag);
      }
    }
    const tyres = new THREE.Mesh(mergeGeometries(tyG, false), tyreM);
    tyres.castShadow = true; g.add(tyres);
    const hubs = new THREE.Mesh(mergeGeometries(hubG, false), rimM);
    hubs.userData.noShadow = 1; g.add(hubs);
    const arches = new THREE.Mesh(mergeGeometries(arG, false), archM);
    arches.userData.noShadow = 1; g.add(arches);
    if (T.bed) {
      // a flatbed deck alone still reads as a saloon with a long boot;
      // what says PICKUP is the sidewall standing above the beltline
      const bF = xAt(Math.min(cabR + 0.06, 0.95)), bR = xAt(0.97);
      const bL = Math.abs(bF - bR), bC = (bF + bR) / 2;
      const bw2 = new THREE.Mesh(new THREE.BoxGeometry(bL, 0.32, Wd - 0.10), paint);
      bw2.position.set(bC, yt + 0.16, 0);
      bw2.castShadow = true; g.add(bw2);
      const bin = new THREE.Mesh(new THREE.BoxGeometry(bL - 0.16, 0.28, Wd - 0.38),
        new THREE.MeshStandardMaterial({ color: 0x2a2c30, roughness: 0.88 }));
      bin.position.set(bC, yt + 0.21, 0);
      g.add(bin);
    }
    if (T.taxi) {
      const tl = new THREE.Mesh(new THREE.BoxGeometry(0.58, 0.17, 0.30),
        new THREE.MeshStandardMaterial({ color: 0xf7d045, emissive: 0xf7d045,
                                         emissiveIntensity: 0.7 }));
      tl.position.set(xAt((cabF + cabR) * 0.5), yt + cabH + 0.10, 0);
      g.add(tl);
    }
    // lights + grille: the small reads that sell 'car' at a glance. Same
    // convention as everything else — length on X, lateral on Z.
    for (const sz of [1, -1]) {
      const hlm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.16, Wd * 0.22),
        new THREE.MeshStandardMaterial({ color: 0xfff6e0, emissive: 0xffeec2,
                                         emissiveIntensity: 0.55 }));
      hlm.position.set(L * 0.5 - 0.10, yb + bodyH * 0.62, sz * Wd * 0.28);
      g.add(hlm);
      const tl = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.13, Wd * 0.2),
        new THREE.MeshStandardMaterial({ color: 0x8c1414, emissive: 0xd11a1a,
                                         emissiveIntensity: 0.5 }));
      tl.position.set(-L * 0.5 + 0.08, yb + bodyH * 0.72, sz * Wd * 0.28);
      g.add(tl);
    }
    const grille = new THREE.Mesh(
      new THREE.BoxGeometry(0.07, bodyH * 0.3, Wd * 0.55), trim);
    grille.position.set(L * 0.5 - 0.06, yb + bodyH * 0.34, 0);
    g.add(grille);
    // THE WOODEN CAR, FINALLY (2026-08-25). Every buildCar material is
    // map-less by design — paint is colour under clearcoat, glass is smoked.
    // The auto-texture sweep claims any untextured standard material, and
    // its colour classifier files a car body under 'bark' or 'grain', so
    // every car in the city has been quietly wearing WOODGRAIN, tinted by
    // its own paint. Beige cars read as planks outright; that was the
    // screenshot that finally caught it. Cars declare their own finish.
    g.traverse(o => {
      if (!o.isMesh) return;
      for (const m of (Array.isArray(o.material) ? o.material : [o.material])) {
        if (m) m.userData.noAutoTex = true;
      }
    });
    return g;
  }
  // PROC HERO (2026-08-30): a proc: asset is a sculpted module, not a
  // mesh file. It arrives with named steer/spin pivots and a drive API —
  // the articulation contract the img2threejs lane exists to provide.
  let procRoot = null;
  if (P.asset && P.asset.startsWith('proc:')) {
    const mod = await import('./proc/' + P.asset.slice(5) + '.js');
    procRoot = (mod.createRoadster || mod.default)();
    // proc modules author +Z-forward. The knight taught us facing bugs are
    // settled by MOTION SCREENSHOTS, not convention reasoning: with the pi
    // flip here the user drove the car nose-backwards (headlamps to the
    // chase cam under throttle), so the flip comes out and the tail shot
    // below is the proof either way.
    // a sculpted module's materials are AUTHORED — flat by intent where flat.
    // Without this the auto-texture sweep dressed the white roadster in bark,
    // the same failure the mountain ring and blast glass already taught us.
    procRoot.traverse(o => {
      if (!o.isMesh) return;
      for (const m of (Array.isArray(o.material) ? o.material : [o.material])) {
        if (m) m.userData.noAutoTex = true;
      }
    });
    window.__procDrive = procRoot;
  }
  const pg = procRoot
    ? { scene: procRoot, animations: [] }
    : P.car_params
    ? { scene: buildCar(P.car_params), animations: [] }
    : await loadGLB(P.asset);            // hard fail = visible error
  const { holder, root: pRoot, radius } =
    prepModel(pg, P.height_m, ['fly', 'swim'].includes(P.mode || 'walk'));
  // ORIENTATION (2026-07-06 rewrite — heuristics OUT, baked truth IN):
  // generated assets now leave the bake with render-VERIFIED orientation
  // (silhouette-matched against their reference), so the runtime stops
  // guessing. Only two facts survive here, both render-verified:
  //   drive/swim travel along their long axis → align long axis to +Z
  //   (car nose is +X per the 2026-07-05 axis renders; whale body likewise).
  //   Flyers keep their wingspan lateral — no rotation at all.
  // a sculpted module's orientation is authored, not inferred — the whole
  // point of the contract is that nothing downstream has to guess
  if (!procRoot) alignLongAxis(pRoot, ['drive', 'swim'].includes(P.mode || 'walk'));
  polishVehiclePaint(pRoot, (P.mode || 'walk') === 'drive');
  // ── THE HERO FACED BACKWARDS (2026-08-07) ────────────────────────────
  // modelYaw is atan2(dir.x, dir.z), which points the model's local +Z along
  // the direction of travel. But these meshes are authored with their FRONT
  // on local -Z: hold W and the follow-cam looked straight at the hero's
  // face while he walked away from it. Measured on two different heroes
  // (man and detective, dot = -1.00 both) so it is the player path, not an
  // asset — and it is why four of the five entries in library_heading.json
  // were exactly 180: each was a hand-patch for this same bug. Those entries
  // are correspondingly reduced by 180, so a per-asset override once again
  // means "this asset is unusual", not "the default is broken".
  const FRONT_IS_MINUS_Z = Math.PI;
  holder.rotation.y = FRONT_IS_MINUS_Z + THREE.MathUtils.degToRad(P.yaw_offset_deg || 0);

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
      if (parked >= 30) break;
      const hd3 = Math.atan2(r.pts[r.pts.length - 1][0] - r.pts[0][0],
                             r.pts[r.pts.length - 1][1] - r.pts[0][1]);
      for (let fi = 0.18; fi < 1 && parked < 30; fi += 0.24) {
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
    for (let ti = 0; ti < 9; ti++) {                 // ambient drivers
      const r = OSM.roads[Math.floor(rngT() * OSM.roads.length)];
      if (!r || r.pts.length < 2) continue;
      const tc = mkCar(carTints[Math.floor(rngT() * carTints.length)]);
      scene.add(tc);
      window.__traffic.push({ obj: tc, pts: r.pts, seg: 0, t: rngT(),
                              speed: 6 + rngT() * 3, dir: 1,
                              lane: (r.w || 7) / 4 });
    }
  }

  // ── STREET TRAFFIC ON FOOT (2026-08-06) ────────────────────────────────
  // Ambient cars only ever existed in DRIVE mode, because that mode has a
  // car mesh already loaded to clone. The whole GTA-style demo is played on
  // FOOT, so the streets the city was built for were empty of moving cars —
  // the loudest "this is a diorama" tell left after the pavement. buildCar()
  // is parametric and costs no download, so walk mode gets its own pool.
  //
  // Deliberately NOT car-following/IDM: cars pick a street, hold a lane and
  // hold a speed. They turn around at the end of the polyline and swap to
  // the opposite lane, which is what a real one-way pair looks like from the
  // pavement, and it means nothing can ever drive off the road graph.
  if (OSM && (P.mode || 'walk') === 'walk' && OSM.roads && OSM.roads.length
      && !INTERIOR && VIEW === '3d') {
    const rngT2 = mulberry32(SPEC.seed + 3131);
    const tints2 = [0xd8d8dc, 0x23252c, 0x8a1f24, 0x2a4d7f, 0xc9a13b, 0x3d3f45,
                    0x1f5f52, 0x6d2f6d];
    // longest streets first: a car on a 12m stub spends its life turning round
    const lanes = (OSM.roads || [])
      .filter(r => r.pts && r.pts.length >= 2)
      .map(r => {
        let L = 0;
        for (let i = 0; i < r.pts.length - 1; i++)
          L += Math.hypot(r.pts[i + 1][0] - r.pts[i][0], r.pts[i + 1][1] - r.pts[i][1]);
        return { r, L };
      })
      .filter(o => o.L > 55)
      .sort((a, b2) => b2.L - a.L)
      .slice(0, 20);
    // the 7 cap was set when every car dragged a transmissive greenhouse
    // through its own render pass. The glass is opaque at traffic distance
    // now, so the cap can follow the street count instead of the old cliff.
    const NT = Math.min(18, lanes.length);
    // PARKED CARS (2026-08-06): the parked pass was gated to drive mode, so a
    // walk-mode city had five drivable cars and nothing else at the kerb —
    // every street read as freshly swept. These are scenery: no colliders,
    // for the same reason the drivable ones have none.
    {
      const rngPk = mulberry32(SPEC.seed + 2727);
      window.__parkedSpots = [];
      let nPk = 0;
      for (const r of OSM.roads || []) {
        if (nPk >= 34) break;
        if (!r.pts || r.pts.length < 2) continue;
        for (let i = 0; i < r.pts.length - 1 && nPk < 34; i++) {
          const [x1, z1] = r.pts[i], [x2, z2] = r.pts[i + 1];
          const segL = Math.hypot(x2 - x1, z2 - z1);
          if (segL < 9) continue;
          const ux = (x2 - x1) / segL, uz = (z2 - z1) / segL;
          const hdP = Math.atan2(ux, uz);
          for (let d0 = 5; d0 < segL - 5 && nPk < 34; d0 += 7.5 + rngPk() * 6) {
            if (rngPk() < 0.45) continue;
            const side = rngPk() < 0.5 ? 1 : -1;
            const off = (r.w || 7) / 2 - 1.05;
            const cxP = x1 + ux * d0 - uz * off * side;
            const czP = z1 + uz * d0 + ux * off * side;
            if (Math.hypot(cxP, czP) < 15 || inBldg(cxP, czP, 0.6)) continue;
            if (window.__cars.some(k => Math.hypot(k.x - cxP, k.z - czP) < 7)) continue;
            const tyP = CAR_TYPE_KEYS[Math.floor(rngPk() * CAR_TYPE_KEYS.length)];
            const shP = buildCar({ type: tyP,
              paint: tyP === 'taxi' ? 0xf2b400
                                    : tints2[Math.floor(rngPk() * tints2.length)] });
            shP.rotation.y = -Math.PI / 2;
            shP.traverse(o => {
              if (!o.isMesh) return;
              o.castShadow = !o.userData.noShadow;
              o.receiveShadow = true;
              const ms = Array.isArray(o.material) ? o.material : [o.material];
              if (ms.some(m => m && m.transmission > 0)) {
                o.material = new THREE.MeshStandardMaterial({
                  color: 0x0d1116, metalness: 0.4, roughness: 0.12 });
                o.material.userData.noAutoTex = true;   // smoked glass, never planks
              }
            });
            const gp = new THREE.Group();
            gp.add(shP);
            gp.position.set(cxP, hAt(cxP, czP), czP);
            gp.rotation.y = hdP + (side > 0 ? 0 : Math.PI);
            scene.add(gp);
            window.__parkedSpots.push([cxP, czP]);
            // STEALABLE (2026-08-06): these were built as scenery and never
            // registered, so a street of 34 cars offered five you could take
            // and 29 that ignored you — which reads as broken, not as set
            // dressing. Same shape as the drivable ones, so the E prompt and
            // the drive rig pick them up unchanged.
            // SOLID (2026-08-07). These were left collider-free because a
            // solid car is a box you can be shoved inside on exit — but a
            // street you drive straight through is a worse bug, and it is
            // the one people notice first. The collider is DISABLED while
            // you are driving that particular car, so entering and leaving
            // never fights its own hull.
            const _cc = world.createCollider(RAPIER.ColliderDesc
              .cuboid(0.95, 0.72, 2.15)
              .setTranslation(cxP, hAt(cxP, czP) + 0.72, czP)
              .setRotation({ x: 0, y: Math.sin(gp.rotation.y / 2),
                             z: 0, w: Math.cos(gp.rotation.y / 2) }));
            window.__cars.push({ rig: gp, x: cxP, z: czP, yaw: gp.rotation.y,
                                 col: _cc });
            nPk++;
          }
        }
      }
      console.log('[game] parked cars: ' + nPk);
    }
    for (let ti = 0; ti < NT; ti++) {
      const r = lanes[Math.floor(ti * lanes.length / Math.max(NT, 1))].r;
      const rig2 = new THREE.Group();
      rig2.rotation.order = 'YXZ';
      const ty2 = CAR_TYPE_KEYS[Math.floor(rngT2() * CAR_TYPE_KEYS.length)];
      const shell2 = buildCar({ type: ty2,
        paint: ty2 === 'taxi' ? 0xf2b400
                             : tints2[Math.floor(rngT2() * tints2.length)] });
      shell2.rotation.y = -Math.PI / 2;             // same +X nose -> +Z forward
      shell2.traverse(o => {
        if (!o.isMesh) return;
        o.castShadow = !o.userData.noShadow;
        // TRAP 2 territory: every transmissive greenhouse is its own render
        // pass. Seven of them moving is a framerate cliff, and at traffic
        // distance smoked glass is indistinguishable.
        const mats2 = Array.isArray(o.material) ? o.material : [o.material];
        if (mats2.some(m => m && m.transmission > 0)) {
          o.material = new THREE.MeshStandardMaterial({
            color: 0x0d1116, metalness: 0.4, roughness: 0.12 });
          o.material.userData.noAutoTex = true;   // smoked glass, never planks
        }
      });
      rig2.add(shell2);
      const seg0 = Math.floor(rngT2() * (r.pts.length - 1));
      const hd0 = Math.atan2(r.pts[seg0 + 1][0] - r.pts[seg0][0],
                             r.pts[seg0 + 1][1] - r.pts[seg0][1]);
      rig2.rotation.y = hd0;
      rig2.position.set(r.pts[seg0][0], hAt(r.pts[seg0][0], r.pts[seg0][1]), r.pts[seg0][1]);
      scene.add(rig2);
      // NO COLLIDER, same reason parked cars have none (2026-08-05): being
      // shoved inside geometry is a worse bug than a car clipping you.
      window.__traffic.push({ obj: rig2, pts: r.pts, seg: seg0, t: rngT2(),
                              speed: 7.5 + rngT2() * 4.5, dir: 1, steal: 1,
                              lane: Math.max((r.w || 7) / 4, 1.7) });
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
        // ── CROWD VARIETY (2026-08-07) ─────────────────────────────────
        // One walker cloned ninety times is one person having a very busy
        // day, and hue-rotating their shirt does not change that — the
        // silhouette is what you recognise from across a street. Every
        // walker variant the exporter bundled is loaded and pedestrians
        // draw from the set. Each variant carries its OWN walk clip, so a
        // mixer must be built against the model it belongs to; sharing one
        // clip across skeletons is what makes limbs fly off.
        let _wlist = ['walker.glb'];
        try {
          const _wr = await fetch('assets/walkers.json');
          if (_wr.ok) {
            const _wj = await _wr.json();
            if (Array.isArray(_wj) && _wj.length) _wlist = _wj;
          }
        } catch (e) { /* manifest is an optimisation, never a gate */ }
        const _models = [];
        for (const _wn of _wlist) {
          try {
            const _wg = await loadGLB('assets/' + _wn);
            const _wc = _wg.animations || [];
            const _ww = _wc.find(c => /walk/i.test(c.name)) || _wc[0];
            if (_wg.scene) _models.push({ scene: _wg.scene, walk: _ww });
          } catch (e) { /* a missing variant must not empty the street */ }
        }
        if (!_models.length) return;
        console.log('[game] walker variants: ' + _models.length
                    + ' (' + _wlist.join(', ') + ')');
        const g = { scene: _models[0].scene };
        const walkClip = _models[0].walk;
        const rngP = mulberry32(SPEC.seed + 818);
        const _rcum = [];
        {
          let acc = 0;
          for (const r of OSM.roads) {
            let L = 0;
            for (let i = 0; i < r.pts.length - 1; i++) {
              L += Math.hypot(r.pts[i + 1][0] - r.pts[i][0],
                              r.pts[i + 1][1] - r.pts[i][1]);
            }
            acc += Math.max(L, 1);
            _rcum.push(acc);
          }
        }
        const _pickRoadByLength = (u) => {
          const target = u * _rcum[_rcum.length - 1];
          let lo = 0, hi = _rcum.length - 1;
          while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (_rcum[mid] < target) lo = mid + 1; else hi = mid;
          }
          return OSM.roads[lo];
        };
        // ── WALKER VARIETY (2026-08-06) ────────────────────────────────
        // Every pedestrian was one bake at one height wearing one texture:
        // eight identical people walking the same block. Clothing colour is
        // painted into the walker's TEXTURE (material.color is white), so a
        // material tint does nothing — the same finding the rival cars hit.
        // Hue-rotate the diffuse in a canvas instead, and share the result
        // across a fixed set of buckets so the texture count stays small.
        const _pedTex = new Map();
        const pedSkin = (inst, bucket) => {
          inst.traverse(o => {
            if (!o.isMesh || !o.material) return;
            const ms = Array.isArray(o.material)
              ? o.material.map(m => m.clone()) : [o.material.clone()];
            o.material = Array.isArray(o.material) ? ms : ms[0];
            for (const m of ms) {
              const img = m.map && m.map.image;
              if (!img || !img.width) continue;
              const key = bucket + '|' + (m.map.uuid || '');
              if (!_pedTex.has(key)) {
                try {
                  const c = document.createElement('canvas');
                  const w = Math.min(img.width, 512);
                  c.width = w; c.height = Math.max(1, Math.round(img.height * w / img.width));
                  const g3 = c.getContext('2d');
                  g3.filter = 'hue-rotate(' + (bucket * 51) + 'deg) saturate('
                    + (0.85 + (bucket % 3) * 0.16).toFixed(2) + ') brightness('
                    + (0.86 + (bucket % 4) * 0.09).toFixed(2) + ')';
                  g3.drawImage(img, 0, 0, c.width, c.height);
                  const nt = new THREE.CanvasTexture(c);
                  nt.colorSpace = THREE.SRGBColorSpace;
                  nt.flipY = m.map.flipY;
                  nt.wrapS = m.map.wrapS; nt.wrapT = m.map.wrapT;
                  _pedTex.set(key, nt);
                } catch (e) { _pedTex.set(key, m.map); }
              }
              m.map = _pedTex.get(key);
              m.needsUpdate = true;
            }
          });
        };
        // 2026-08-06 r2: a Manhattan block is CROWDED. The limit is not
        // the draw — it is one AnimationMixer and one skeleton update per
        // walker per frame, so the crowd scales by only paying that for
        // the ones you can actually see (LOD in the step loop below).
        // 2026-08-07: 90 across a whole Manhattan district is a quiet
        // Sunday. The per-frame cost is the mixer and the skeleton update,
        // and both are already gated by the LOD in the step loop, so only
        // the pedestrians actually on screen pay for the extra hundred.
        for (let i = 0; i < 190; i++) {
          // Picking a road uniformly gave a 20m alley the same share of the
          // crowd as a 400m avenue, so ninety people piled into whichever
          // short stubs won the roll and the rest of the city read as empty.
          // Choosing by cumulative LENGTH makes density per metre of
          // pavement even, which is what "scattered everywhere" means.
          const r = _pickRoadByLength(rngP());
          if (!r || r.pts.length < 2) continue;
          // pick the body FIRST — clothing and build come with the model,
          // and the tint below is now only within-variant variation
          const _mv = _models[i % _models.length];
          const inst = skClone(_mv.scene);
          // NO HUE ROTATION when there are real bodies to draw from. The
          // rotation was a stand-in for variety back when the crowd was one
          // model ninety times, and it works on the whole diffuse — skin
          // included — so a third of the street came out green. Four models
          // supply the variety honestly; the tint is kept only for the
          // single-variant fallback, where a colour wheel still beats a
          // literal clone army.
          if (_models.length < 2 && i % 9 !== 0) pedSkin(inst, 1 + (i % 10));
          const bb = new THREE.Box3().setFromObject(inst);
          inst.scale.multiplyScalar((1.56 + rngP() * 0.33)
            / Math.max(bb.max.y - bb.min.y, 1e-3));
          // build: a crowd of one silhouette is still a clone army even in
          // different colours
          const build = 0.90 + rngP() * 0.22;
          inst.scale.x *= build; inst.scale.z *= build;
          const bb2 = new THREE.Box3().setFromObject(inst);
          inst.position.y = -bb2.min.y;
          const holder2 = new THREE.Group();
          holder2.add(inst);
          holder2.traverse(o => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
          scene.add(holder2);
          // strollers and people late for something, not one march tempo
          const spd = 0.8 + rngP() * 1.25;
          let mixer2 = null, _pedAct = null;
          if (_mv.walk) {
            mixer2 = new THREE.AnimationMixer(inst);
            const act = mixer2.clipAction(_mv.walk);
            // clip rate follows ground speed or the fast walkers moonwalk
            act.timeScale = (spd / 1.35) / build;
            act.play();
            _pedAct = act;                    // so a knockdown can resume it
            mixer2.update(rngP() * 2.5);      // phase-shift: no synchronized march
          }
          const _pdir = rngP() < 0.5 ? 1 : -1;
          window.__peds.push({ obj: holder2, mixer: mixer2, pts: r.pts,
            down: 0, kx: 0, kz: 0, spin: 0, _act: _pedAct,
            seg: Math.max(0, Math.floor(rngP() * (r.pts.length - 1))), t: rngP(),
            speed: spd, dir: _pdir,
            // KEEP RIGHT: side was rolled independently of direction, so
            // half the crowd walked head-on into the other half on the
            // same slab. Tying it to dir gives each pavement one dominant
            // flow, with a tenth going against it so it is not a parade.
            side: ((r.w || 7) / 2 + 1.6 + rngP() * 1.6)
                  * (rngP() < 0.9 ? _pdir : -_pdir) });
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
          // 0.34 was tuned against materials whose diffuse was dead, so it
          // had to carry the whole hero. With diffuse restored above it is a
          // lift, not a substitute — anything near the old value re-blows a
          // light-coloured costume out to white.
          m.emissiveMap = m.map; m.emissive.setScalar(0.10); m.needsUpdate = true;
        } else if (m && m.emissive) {
          m.emissive.setScalar(0.12);
        }
      }
    });
  }

  // the settle pass: player, guide and every NPC, after their GLBs, their
  // textures and every night-grade material tweak have all landed
  setTimeout(() => {
    try {
      deChalk(holder);
      for (const n of (npcs || [])) deChalk(n.obj);
      for (const q of (window.__peds || [])) deChalk(q.obj);
    } catch (e) { /* cosmetic pass, never a gate */ }
  }, 4000);

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
    // One group per weapon, all parented to the hand, with only the
    // selected one visible. 2026-08-07: the arsenal switched what F DID but
    // the character kept holding the sword through all of it, which reads
    // as the switch not having worked.
    const wGroups = [];
    const mkPistol = () => {
      const g2 = new THREE.Group();
      const body2 = new THREE.Mesh(new THREE.BoxGeometry(0.032, 0.088, 0.17),
        new THREE.MeshStandardMaterial({ color: 0x24272b, metalness: 0.75, roughness: 0.35 }));
      body2.position.set(0, 0.06, 0.03);
      const barrel = new THREE.Mesh(new THREE.CylinderGeometry(0.011, 0.011, 0.10, 8),
        new THREE.MeshStandardMaterial({ color: 0x36393e, metalness: 0.9, roughness: 0.25 }));
      barrel.rotation.x = Math.PI / 2; barrel.position.set(0, 0.075, 0.15);
      const grip2 = new THREE.Mesh(new THREE.BoxGeometry(0.030, 0.105, 0.045),
        new THREE.MeshStandardMaterial({ color: 0x1a1d21, roughness: 0.85 }));
      grip2.position.set(0, -0.015, -0.015); grip2.rotation.x = -0.25;
      g2.add(body2, barrel, grip2);
      return g2;
    };
    const mkLauncher = () => {
      const g2 = new THREE.Group();
      const tube = new THREE.Mesh(new THREE.CylinderGeometry(0.042, 0.046, 0.56, 12),
        new THREE.MeshStandardMaterial({ color: 0x3d4a37, metalness: 0.5, roughness: 0.6 }));
      tube.rotation.x = Math.PI / 2; tube.position.set(0, 0.07, 0.14);
      const muzzle = new THREE.Mesh(new THREE.CylinderGeometry(0.062, 0.046, 0.09, 12),
        new THREE.MeshStandardMaterial({ color: 0x2b3327, metalness: 0.5, roughness: 0.65 }));
      muzzle.rotation.x = Math.PI / 2; muzzle.position.set(0, 0.07, 0.41);
      const grip3 = new THREE.Mesh(new THREE.BoxGeometry(0.030, 0.10, 0.042),
        new THREE.MeshStandardMaterial({ color: 0x1d2119, roughness: 0.9 }));
      grip3.position.set(0, -0.005, 0.02);
      g2.add(tube, muzzle, grip3);
      return g2;
    };
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
    const wp2 = mkPistol(), wp3 = mkLauncher();
    for (const g3 of [w, wp2, wp3]) {
      g3.traverse(o => {
        if (o.isMesh) { o.castShadow = true; o.material.userData.noAutoTex = true; }
      });
      g3.rotation.x = Math.PI / 2;       // lie along the hand's forward
      handBone.add(g3);
      wGroups.push(g3);
    }
    wp2.visible = false; wp3.visible = false;
    window.__wpnModels = wGroups;
  })();

  // ── ARMS SWING FORWARD, NOT OUTWARD (2026-08-07) ─────────────────────
  // Measured on the running rig: uparm_L.y = +0.82 and uparm_R.y = -0.81,
  // a symmetric 47 degrees of SPLAY carried in every clip. It is baked in
  // because the meshes are bound in a T-pose (pose_templates/biped_depth.png
  // is a flat T) while mocap_retarget builds its arm chain expecting an
  // A-pose — the clip then rotates from a rest position that already had the
  // arms out, so the swing comes out lateral instead of sagittal.
  //
  // The real fix is an A-pose template and re-baked rigs, and that is still
  // the right one. This is the standard interim: a REST-POSE CORRECTION,
  // applied after the mixer writes each frame. It scales down only the splay
  // axis and leaves X — which carries the actual forward swing — untouched,
  // so the walk keeps its motion and loses its chicken wings.
  const _armBones = [];
  let _armScanned = false;
  function scanArms() {
    _armScanned = true;
    scene.traverse(o => {
      if (!o.isSkinnedMesh || !o.skeleton) return;
      for (const bn of o.skeleton.bones) {
        if (/^uparm_[LR]$/i.test(bn.name)) _armBones.push(bn);
      }
    });
  }
  function fixArmSplay() {
    if (!_armScanned) scanArms();
    for (const bn of _armBones) {
      // 0.22 leaves ~10 degrees, which is what a relaxed arm actually does
      bn.rotation.y *= 0.22;
    }
  }

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
    RAPIER.RigidBodyDesc.kinematicPositionBased()
      .setTranslation(_sp.x, spawnHeight(_sp.x, _sp.z), _sp.z));
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
  // SPAWN FACING THE PHOTO (2026-08-04): in image worlds the user's own
  // photograph is preserved verbatim at panorama center (-Z). Opening the
  // game looking anywhere else means the first thing you see is invented
  // filler — 'walking into the image' starts by FACING it.
  let yaw = SPEC.world.pano ? Math.PI : 0;
  let pitch = SPEC.world.pano ? 0.16 : 0.35;
  let dragging = false, px = 0, py = 0;
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
      if (!(n.behavior === 'hostile' || n.behavior === 'flee' || n.behavior === 'guard') || n.dead || n.dormant) continue;
      const d = Math.hypot(n.obj.position.x - playerObj.position.x,
                           n.obj.position.z - playerObj.position.z);
      if (d < bd) { bd = d; best = n; }
    }
    return best;
  }
  // ── ARSENAL (2026-08-07) ─────────────────────────────────────────────
  // Three weapons with genuinely different verbs, switched on 1/2/3 and
  // listed in the Tab panel. Declared here, above everything that reads
  // them: a const read before its declaration takes the whole runtime down
  // with a black page and a build that still reports complete (TRAP 1).
  const WEAPONS = [
    { id: 'blade', name: 'Blade', icon: '🗡', reach: 2.6, dmg: 1,
      cd: 0.55, desc: 'swing at whatever is in front of you' },
    { id: 'pistol', name: 'Pistol', icon: '🔫', reach: 46, dmg: 1,
      cd: 0.32, desc: 'hold F to aim, release to fire' },
    { id: 'launcher', name: 'Launcher', icon: '🧨', reach: 60, dmg: 3,
      cd: 1.5, blast: 7.0, desc: 'lobbed shell — everything nearby goes down' },
  ];
  let weaponIdx = 0, aimT = 0;
  const shells = [], blasts = [];
  // BLAST FX ARE POOLED, NOT CREATED (2026-08-07). Adding a PointLight
  // changes the scene's light COUNT, which invalidates every
  // MeshStandardMaterial shader variant in the world — a single detonation
  // compiled ~66 programs (67 -> 133 measured), and each compile is a
  // synchronous GPU stall. That was the launcher "lag". One light that
  // lives forever at intensity 0 and one reusable fireball keep the light
  // count and the material set completely constant, so a blast costs a
  // matrix update and nothing else.
  const _blastLight = new THREE.PointLight(0xffa040, 0, 30, 2);
  _blastLight.position.set(0, -500, 0);
  const _blastBall = new THREE.Mesh(new THREE.SphereGeometry(1, 14, 10),
    new THREE.MeshBasicMaterial({ color: 0xffb347, transparent: true,
      opacity: 0, depthWrite: false, toneMapped: false }));
  _blastBall.renderOrder = 6;
  _blastBall.visible = false;
  // Added HERE, immediately after the declarations. The first cut put
  // these scene.add calls 180 lines earlier, next to the other one-time
  // setup — which reads a const before its declaration and takes the
  // whole runtime down with a black page while the build still reports
  // complete (TRAP 1). Deliberately NOT registered with __torches: the
  // light-budget culler toggles .visible, and an invisible light also
  // changes the light count and recompiles everything. Intensity 0 is free.
  scene.add(_blastLight);
  scene.add(_blastBall);
  let tgtMark = null;
  // ── LOADOUT (2026-08-07, TAB) ────────────────────────────────────────
  // The verbs were only ever announced once, in a strip of grey text at the
  // top of the screen that scrolls past before you have started playing —
  // so "what can I actually do" had no answer you could ask for. Tab is a
  // panel you can open mid-game. It is built from the SPEC, not hardcoded,
  // so a game without guards does not advertise a distraction it cannot
  // throw and a swimmer is not told to sneak.
  {
    const lo = document.createElement('div');
    lo.style.cssText = 'position:fixed;inset:0;display:none;z-index:34;'
      + 'background:rgba(8,7,14,.72);backdrop-filter:blur(3px);'
      + 'align-items:center;justify-content:center;';
    const rows = [];
    const mode = SPEC.player.mode || 'walk';
    if (ATTACK !== 'none') {
      WEAPONS.forEach((w, i) => rows.push([w.icon, w.name, String(i + 1), w.desc, i]));
    }
    if (typeof HAS_GUARDS !== 'undefined' && HAS_GUARDS) {
      rows.push(['🥫', 'Distraction', 'Q', 'thrown — pulls a guard to the noise']);
      rows.push(['🐈', 'Crouch', 'C', 'halves how far a guard can see you']);
    }
    if (window.__doors && window.__doors.length) {
      rows.push(['📐', 'Blueprint', 'B', 'overlay of the block and its ways in']);
    }
    if (mode === 'walk') rows.push(['🏃', 'Sprint', 'Shift', 'faster on foot, louder too']);
    rows.push(['🚗', 'Hotwire', 'E', 'any car you are standing beside']);
    lo.innerHTML = '<div style="max-width:560px;width:88%;padding:26px 30px;'
      + 'background:rgba(14,12,24,.96);border:1px solid rgba(167,139,250,.4);'
      + 'border-radius:16px;">'
      + '<div style="font:800 20px system-ui;color:#e8e2ff;margin-bottom:4px">Loadout</div>'
      + '<div style="font:400 12px system-ui;color:#8d89a6;margin-bottom:16px">'
      + 'everything this game gave you · Tab to close</div>'
      + rows.map(r => '<div'
        + (r[4] !== undefined ? ` data-slot="${r[4]}"` : '')
        + ' style="display:flex;align-items:center;gap:12px;padding:9px 8px;'
        + 'border-radius:8px;border-top:1px solid rgba(255,255,255,.07);'
        + (r[4] === 0 ? 'background:rgba(167,139,250,.18)' : '') + '">'
        + `<div style="font-size:21px;width:28px;text-align:center">${r[0]}</div>`
        + '<div style="flex:1">'
        + `<div style="font:700 14px system-ui;color:#e8e2ff">${r[1]}</div>`
        + `<div style="font:400 11.5px system-ui;color:#8d89a6">${r[3]}</div></div>`
        + '<kbd style="font:700 12px ui-monospace,monospace;color:#0d0b16;'
        + 'background:#a78bfa;border-radius:6px;padding:4px 9px">'
        + `${r[2]}</kbd></div>`).join('')
      + '</div>';
    document.body.appendChild(lo);
    let loOpen = false;
    addEventListener('keydown', e => {
      if (e.code === 'Tab') {
        e.preventDefault();               // Tab must not walk the DOM focus
        loOpen = !loOpen;
        lo.style.display = loOpen ? 'flex' : 'none';
        return;
      }
      const slot = { Digit1: 0, Digit2: 1, Digit3: 2 }[e.code];
      if (slot === undefined || ATTACK === 'none') return;
      weaponIdx = slot;
      const w2 = WEAPONS[slot];
      if (window.__wpnModels) {
        window.__wpnModels.forEach((g4, i) => { g4.visible = (i === slot); });
      }
      popText(w2.icon + '  ' + w2.name, '#a78bfa');
      if (window.__wpnEl) {
        window.__wpnEl.textContent = w2.icon + ' ' + w2.name;
        window.__wpnEl.style.display = 'block';
      }
      for (const el of lo.querySelectorAll('[data-slot]')) {
        el.style.background = (+el.dataset.slot === slot)
          ? 'rgba(167,139,250,.18)' : 'transparent';
      }
    });
    // a small standing readout, so the current weapon is knowable without
    // opening anything
    if (ATTACK !== 'none') {
      const wl = document.createElement('div');
      wl.style.cssText = 'position:fixed;left:50%;bottom:96px;'
        + 'transform:translateX(-50%);z-index:23;font:700 13px system-ui;'
        + 'color:#e8e2ff;background:rgba(10,9,18,.72);'
        + 'border:1px solid rgba(167,139,250,.35);border-radius:9px;'
        + 'padding:5px 12px;pointer-events:none;';
      wl.textContent = WEAPONS[0].icon + ' ' + WEAPONS[0].name;
      document.body.appendChild(wl);
      window.__wpnEl = wl;
      // AIM RETICLE. Only the pistol has one — a blade has nothing to aim
      // and the launcher is lobbed, so a crosshair on either would be
      // lying about how they work.
      const rt = document.createElement('div');
      rt.style.cssText = 'position:fixed;left:50%;top:50%;width:26px;height:26px;'
        + 'transform:translate(-50%,-50%);z-index:23;display:none;'
        + 'pointer-events:none;';
      rt.innerHTML = '<svg width="26" height="26" viewBox="0 0 26 26">'
        + '<circle cx="13" cy="13" r="9" fill="none" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/>'
        + '<line x1="13" y1="0" x2="13" y2="6" stroke="#ff6a6a" stroke-width="1.6"/>'
        + '<line x1="13" y1="20" x2="13" y2="26" stroke="#ff6a6a" stroke-width="1.6"/>'
        + '<line x1="0" y1="13" x2="6" y2="13" stroke="#ff6a6a" stroke-width="1.6"/>'
        + '<line x1="20" y1="13" x2="26" y2="13" stroke="#ff6a6a" stroke-width="1.6"/>'
        + '<circle id="rtDot" cx="13" cy="13" r="1.6" fill="#ff6a6a"/></svg>';
      document.body.appendChild(rt);
      window.__aimEl = rt;
      window.__aimDot = rt.querySelector('#rtDot');
    }
    const hintL = document.querySelector('#hud .hint');
    if (hintL) hintL.textContent += ' · Tab loadout';
  }
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
      juiceSlow = Math.max(juiceSlow, 0.32 * FEEL.slow);
      juicePunch = Math.max(juicePunch, 0.5 * FEEL.punch);
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
    const WPN = WEAPONS[weaponIdx] || WEAPONS[0];
    // LAUNCHER: a lobbed shell, not a hitscan. It has travel time and an
    // arc, so you lead the shot and you can absolutely catch yourself in
    // your own blast — which is what makes carrying it a decision.
    if (WPN.id === 'launcher') {
      atkCd = WPN.cd;
      sfx('attack');
      const sm = new THREE.Mesh(new THREE.SphereGeometry(0.16, 10, 8),
        new THREE.MeshStandardMaterial({ color: 0x2f3338, metalness: 0.7,
          roughness: 0.35, emissive: 0x662200, emissiveIntensity: 0.8 }));
      sm.userData.noAutoTex = true;
      const bp9 = body.translation();
      sm.position.set(bp9.x + Math.sin(modelYaw) * 0.9, bp9.y + 1.15,
                      bp9.z + Math.cos(modelYaw) * 0.9);
      scene.add(sm);
      shells.push({ obj: sm, life: 3.2,
        vx: Math.sin(modelYaw) * 26, vz: Math.cos(modelYaw) * 26, vy: 6.5 });
      return;
    }
    atkCd = WPN.cd;
    sfx('attack');
    // DISPATCH ON THE SELECTED WEAPON. This branched on ATTACK — the value
    // the SPEC picked once at build time — so in a melee-cast game choosing
    // the pistol still ran a sword swing and nothing left the barrel. The
    // arsenal decides what F does; ATTACK only decides whether F exists.
    const _isRanged = WPN.id === 'pistol';
    // AIM ASSIST: swings snap toward the marked target — you committed to
    // the attack, the game commits to the hit (reach was 2.3m and the angle
    // check punished honest inputs; now 3.2m + auto-face)
    if (!_isRanged) {
      const tn = nearestHostile(MELEE_REACH);
      if (tn) {
        modelYaw = Math.atan2(tn.obj.position.x - playerObj.position.x,
                              tn.obj.position.z - playerObj.position.z);
      }
    } else {
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
          if (!(n.behavior === 'hostile' || n.behavior === 'flee' || n.behavior === 'guard') || n.dead) continue;
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
    // ── THE BLUEPRINT (B): a burglar cases the place before going in.
    // Draws the real floor plan from the interior data — walls, doorways,
    // the loot, the exit, and your own position. Guards appear only where
    // you have actually SEEN them, so the plan is intelligence you gather,
    // not a wallhack. This is the "study the blueprints" half of the genre.
    if (e.code === 'KeyB' && INTERIOR) {
      e.preventDefault();
      let bp = document.getElementById('fsbp');
      if (bp) { bp.remove(); return; }
      bp = document.createElement('div');
      bp.id = 'fsbp';
      bp.style.cssText = 'position:fixed;inset:0;display:flex;align-items:center;'
        + 'justify-content:center;background:rgba(4,10,26,.86);z-index:60;'
        + 'backdrop-filter:blur(2px);font:600 12px system-ui;color:#8ecbff';
      const W = 640, H = 520;
      const cv = document.createElement('canvas');
      cv.width = W; cv.height = H;
      cv.style.cssText = 'max-width:92vw;max-height:80vh;border:1px solid #2b6ea8;'
        + 'border-radius:10px;background:#071427';
      bp.appendChild(cv);
      const cap = document.createElement('div');
      cap.style.cssText = 'position:absolute;bottom:6%;left:0;right:0;text-align:center;'
        + 'color:#5b9fd6;letter-spacing:.04em';
      cap.textContent = 'BLUEPRINT — B to close · guards shown where you have seen them';
      bp.appendChild(cap);
      document.body.appendChild(bp);
      const g = cv.getContext('2d');
      const bx = INTERIOR.bounds[0], bz = INTERIOR.bounds[1];
      const sc = Math.min((W - 70) / bx, (H - 90) / bz);
      const PX = (x) => W / 2 + x * sc, PZ = (z) => H / 2 + z * sc;
      g.fillStyle = '#071427'; g.fillRect(0, 0, W, H);
      // faint drafting grid, like a real plan sheet
      g.strokeStyle = 'rgba(80,150,220,.10)'; g.lineWidth = 1;
      for (let i = 0; i <= W; i += 26) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, H); g.stroke(); }
      for (let i = 0; i <= H; i += 26) { g.beginPath(); g.moveTo(0, i); g.lineTo(W, i); g.stroke(); }
      // rooms
      g.strokeStyle = 'rgba(120,190,255,.30)';
      for (const [cx, cz, rw, rd] of INTERIOR.rooms) {
        g.strokeRect(PX(cx - rw / 2), PZ(cz - rd / 2), rw * sc, rd * sc);
      }
      // walls, with the doorway gap left open exactly as built
      g.strokeStyle = '#7ec4ff'; g.lineWidth = 2.5;
      const DW = 2.4;
      for (const [cx, cz, ln, rot, door] of INTERIOR.walls) {
        const seg2 = (a, b) => {
          g.beginPath();
          if (rot) { g.moveTo(PX(cx), PZ(cz + a)); g.lineTo(PX(cx), PZ(cz + b)); }
          else { g.moveTo(PX(cx + a), PZ(cz)); g.lineTo(PX(cx + b), PZ(cz)); }
          g.stroke();
        };
        if (door < 0) { seg2(-ln / 2, ln / 2); continue; }
        const dC = -ln / 2 + door * ln;
        seg2(-ln / 2, dC - DW / 2);
        seg2(dC + DW / 2, ln / 2);
      }
      // the loot still on the floor
      const st2 = steps[stepIdx];
      if (st2 && st2.kind === 'collect') {
        g.fillStyle = '#ffd54a';
        for (const c of collectibles || []) {
          if (!c.mesh || !c.mesh.parent) continue;
          g.beginPath();
          g.arc(PX(c.mesh.position.x), PZ(c.mesh.position.z), 5, 0, 7);
          g.fill();
        }
      }
      // guards you have actually laid eyes on
      g.fillStyle = '#ff6b6b';
      for (const n of npcs) {
        if (n.behavior !== 'guard' || n.dead || !n._seenByPlayer) continue;
        g.beginPath();
        g.arc(PX(n.obj.position.x), PZ(n.obj.position.z), 5.5, 0, 7);
        g.fill();
      }
      // you
      g.fillStyle = '#5cffc9';
      g.beginPath();
      g.arc(PX(playerObj.position.x), PZ(playerObj.position.z), 5.5, 0, 7);
      g.fill();
      g.fillStyle = '#9fd8ff';
      g.font = '600 11px system-ui';
      g.fillText('YOU', PX(playerObj.position.x) + 9, PZ(playerObj.position.z) + 4);
    }
    // THROW A DISTRACTION (heist kit, Q): stealth is only interesting when
    // you can ACT on the guards, not just avoid them. Lob a stone; whoever
    // is nearest walks over to investigate the clatter, opening the room
    // they were standing in. This is the verb that makes patrols a puzzle.
    if (e.code === 'KeyQ' && HAS_GUARDS && gameStarted && !won && !lost) {
      e.preventDefault();
      if ((window.__throwCd || 0) > playT) return;
      window.__throwCd = playT + 2.2;
      const pp = playerObj.position;
      // lands ~9 m ahead of where the hero faces
      const lx = pp.x + Math.sin(modelYaw) * 9, lz = pp.z + Math.cos(modelYaw) * 9;
      const stone = new THREE.Mesh(
        new THREE.SphereGeometry(0.11, 8, 6),
        new THREE.MeshStandardMaterial({ color: 0x9a9384, roughness: 1 }));
      stone.position.set(pp.x, pp.y + 0.9, pp.z);
      scene.add(stone);
      const t0 = playT, sx = stone.position.x, sy = stone.position.y, sz = stone.position.z;
      const flight = { obj: stone, until: playT + 0.75,
        step: () => {
          const k = Math.min(1, (playT - t0) / 0.75);
          stone.position.set(sx + (lx - sx) * k, sy + (0 - sy) * k + Math.sin(k * Math.PI) * 1.9,
                             sz + (lz - sz) * k);
          if (k >= 1) {
            scene.remove(stone);
            sfx('step'); burst(new THREE.Vector3(lx, 0.2, lz), 0xbdb6a4);
            popText('🪨 clatter — something moved over there', '#bdb6a4');
            let best = null, bd = 26;
            for (const n of npcs) {
              if (n.behavior !== 'guard' || n.dead || n.dormant || n.mode === 'chase') continue;
              const dd = Math.hypot(n.obj.position.x - lx, n.obj.position.z - lz);
              if (dd < bd) { bd = dd; best = n; }
            }
            if (best) {                     // go look, then resume the beat
              best.beat = [[lx, lz]].concat(best.beat || []);
              best.wp = 0; best.alert = 0;
            }
            return true;
          }
          return false;
        } };
      (window.__flights = window.__flights || []).push(flight);
    }
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
    ...__evHooks,
    pos: () => playerObj.position.toArray(), keys, ready: true,
    tp: (x, z) => body.setTranslation({ x, y: spawnHeight(x, z), z }, true),
    attack: doAttack,
    combat: () => ({ hp: php, kills, mode: ATTACK, lost,
                     hostiles: npcs.filter(n => n.behavior === 'hostile' && !n.dead).length }),
    quest: () => ({ step: stepIdx, total: steps.length,
                    active: steps[stepIdx] ? stepLabel(steps[stepIdx]) : null, won }),
    objectives: () => ({ collected: steps.filter(s => s.kind === 'collect').reduce((a, s) => a + (s._got || 0), 0),
                         left: collectibles.filter(c => c.mesh.parent).map(c => c.mesh.position.toArray()) }),
    npcs: () => npcs.filter(n => !n.gone).map(n => ({ behavior: n.behavior, dead: !!n.dead, pos: n.obj.position.toArray(),
                                                      mode: n.mode, alert: n.alert, playT })),
    placed: () => placedItems.map(p => ({ kind: p.it.kind, x: p.it.x, z: p.it.z,
                                          interact: !!p.it.interact, alive: !!p.anim })),
    reading: () => ({ readable: readable ? readable.label : null, open: reading }),
    inspect: on => setInspectOn(on),
    view: VIEW,
    // PERF GATE (2026-08-05): the city merges into a handful of draw calls on
    // purpose, and any facade change that quietly gives buildings their own
    // materials would undo that with no visible symptom until a real city
    // stutters. Exposed so the shotgate can fail the change on the number.
    stats: () => ({ calls: window.__frameCalls | 0,
                    tris: window.__frameTris | 0,
                    programs: renderer.info.programs ? renderer.info.programs.length : -1,
                    textures: renderer.info.memory.textures,
                    geometries: renderer.info.memory.geometries }),
  };
  // aim the follow-cam from the harness. The default framing looks DOWN at
  // the street, so screenshot checks of anything vertical — facades above the
  // first storey especially — were judging a view the shot never contained.
  window.__game.aim = (y, p) => { yaw = y; pitch = Math.max(0.02, p); };
  // scene/renderer handles for the shotgate probes: judging a lighting or
  // material change from screenshots alone is guesswork, and the city's
  // night look is decided by numbers (fog density, env intensity) that a
  // picture cannot report.
  window.__scene = scene;
  window.__camera = camera;   // harness: fov punches are assertable, not vibes window.__renderer = renderer;

  // ── PARKED CARS YOU CAN STEAL ────────────────────────────────────────────
  // The whole bridge between the two demos. Placed HERE, after the player
  // capsule, `playerObj` and `spawnHeight` exist, so enter/exit can move the
  // real body instead of inventing a second one. Nothing about the car is a
  // new physics object: getting in swaps the visible model, points the
  // existing kinematic capsule at the car, and flips `DRIVING`.
  // A REAL ROAD GRAPH IS THE GATE (2026-08-05): the first cut parked cars in
  // any outdoor walking world, which put modern sedans in forest valleys and
  // on castle grounds. A car needs somewhere it could plausibly have been
  // driven and left, and OSM roads are the only honest evidence of that.
  // Interiors are excluded for the obvious reason.
  const CARS_OK = !INTERIOR && !PURE_SCENE && VIEW === '3d'
                  && (P.mode || 'walk') === 'walk'
                  && !!(OSM && OSM.roads && OSM.roads.length);
  let carPrompt = null, nearCar = null, heldCar = null, camDistMul = 1, carCool = 0;
  // ── JUICE (2026-08-25): the camera reacts to what you did ─────────────
  // The lesson from every hand-crafted three.js toy that feels better than
  // an engine twenty times its size: interactions deserve MOMENTS. A pickup
  // punches the lens, a kill dilates time, a fired event shakes the frame,
  // a win earns a flyover, an escort arrival cuts to HIS eyes looking back
  // at you. All state, no allocations; each effect is one number decaying.
  // a cartoon bounces, a horror drags: the same five moments land with
  // style-specific weight. Multipliers only — one table, no new systems.
  const FEEL = ({
    cartoon: { punch: 1.55, slow: 0.7, shake: 0.6 },
    anime:   { punch: 1.3,  slow: 1.1, shake: 0.9 },
    horror:  { punch: 0.35, slow: 1.6, shake: 1.7 },
    pixel:   { punch: 1.2,  slow: 1.0, shake: 1.0 },
  })[SPEC.style] || { punch: 1, slow: 1, shake: 1 };
  let juiceSlow = 0;      // seconds of world slow-mo left (0.3x)
  let juicePunch = 0;     // 0..1 fov kick, decays fast
  let juiceFly = -1;      // >=0: win flyover clock
  let juicePOV = null;    // {x,y,z,lx,ly,lz,t}: brief borrowed-eyes shot
  // KNOCKED DOWN (2026-08-07): seconds left on the floor, and the slide
  // still carrying you. Declared UP here with the other drive state — a
  // const read before its declaration takes the whole runtime down (TRAP 1).
  let downT = 0, downVX = 0, downVZ = 0;
  if (CARS_OK) {
    const rngC = mulberry32(SPEC.seed + 9091);
    const tints = [0x8e1f26, 0x1d2530, 0xb8bcc4, 0x2b4a72, 0xc2a03a, 0x24503c];
    const cand = [];
    for (const r of OSM.roads) {
      if (!r.pts || r.pts.length < 2) continue;
      for (let i = 0; i < r.pts.length - 1; i++) {
        const a = r.pts[i], b = r.pts[i + 1];
        const segL = Math.hypot(b[0] - a[0], b[1] - a[1]);
        if (segL < 8) continue;
        const hd = Math.atan2(b[0] - a[0], b[1] - a[1]);
        for (let f = 0.3; f < 0.95; f += 0.3) {
          const mx3 = a[0] + (b[0] - a[0]) * f, mz3 = a[1] + (b[1] - a[1]) * f;
          const side = rngC() < 0.5 ? 1 : -1;
          const off = Math.max((r.w || 7) / 2 - 1.2, 1.4);   // at the curb
          cand.push([mx3 + Math.cos(hd) * side * off,
                     mz3 - Math.sin(hd) * side * off,
                     hd + (side > 0 ? 0 : Math.PI)]);
        }
      }
    }
    const half3 = SPEC.world.size_m / 2 - 5;
    const ok = cand.filter(c =>
      Math.hypot(c[0] - _sp.x, c[1] - _sp.z) > 11
      && Math.abs(c[0]) < half3 && Math.abs(c[1]) < half3
      && !inBldg(c[0], c[1], 1.0)
      && !ENTERABLES.some(E => Math.hypot(c[0] - E.door[0], c[1] - E.door[1]) < 7))
      .sort((p, q) => Math.hypot(p[0] - _sp.x, p[1] - _sp.z)
                    - Math.hypot(q[0] - _sp.x, q[1] - _sp.z));
    for (const c of ok) {
      if (window.__cars.length >= 5) break;
      // spread them over the map — five cars on one block is a dealership,
      // and the nearest-first sort still guarantees one close to the spawn
      if (window.__cars.some(k => Math.hypot(k.x - c[0], k.z - c[1]) < 24)) continue;
      // a drivable car merged into a scenery one is two cars in the same
      // metre of kerb, and the scenery pass ran first
      if ((window.__parkedSpots || []).some(
          q => Math.hypot(q[0] - c[0], q[1] - c[1]) < 6.5)) continue;
      const rig = new THREE.Group();
      rig.rotation.order = 'YXZ';        // yaw first: body-roll must not steer
      const tyC = CAR_TYPE_KEYS[Math.floor(rngC() * CAR_TYPE_KEYS.length)];
      const shell = buildCar({ type: tyC,
        paint: tyC === 'taxi' ? 0xf2b400
                              : tints[window.__cars.length % tints.length] });
      // buildCar now really does put the nose on +X (before 2026-08-06 its
      // own internal rotateY had already swung it to -Z, so this +90 was
      // compensating for that). -90 deg is what alignLongAxis applies to a
      // baked car asset for the same reason: it maps +X onto the runtime's
      // +Z forward.
      shell.rotation.y = -Math.PI / 2;
      shell.traverse(o => {
        if (!o.isMesh) return;
        // noShadow parts sit inside the car's own silhouette, so they add
        // nothing to the shadow but cost a full extra draw each
        o.castShadow = !o.userData.noShadow;
        o.receiveShadow = true;
        // five transmissive greenhouses would each cost their own render
        // pass; parked glass is flat smoked instead (only the car you drive
        // is close enough for real transmission to read anyway)
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        if (mats.some(m => m && m.transmission > 0)) {
          o.material = new THREE.MeshStandardMaterial({
            color: 0x0d1116, metalness: 0.4, roughness: 0.12 });
          o.material.userData.noAutoTex = true;   // smoked glass, never planks
        }
      });
      rig.add(shell);
      rig.position.set(c[0], hAt(c[0], c[1]), c[1]);
      rig.rotation.y = c[2];
      scene.add(rig);
      // NO COLLIDER, deliberately (2026-08-05): a solid parked car is a box
      // you can be squeezed into on exit, and "player stuck inside geometry"
      // is a worse bug than driving through an unoccupied fender.
      window.__cars.push({ rig, x: c[0], z: c[1], yaw: c[2] });
    }
    if (window.__cars.length) {
      carPrompt = document.createElement('div');
      carPrompt.style.cssText = 'position:fixed;left:50%;bottom:130px;'
        + 'transform:translateX(-50%);font:600 14px system-ui;color:#dff4ff;'
        + 'background:rgba(10,9,18,.78);border:1px solid rgba(127,212,255,.45);'
        + 'border-radius:10px;padding:8px 14px;z-index:24;display:none;'
        + 'pointer-events:none;';
      document.body.appendChild(carPrompt);
      // SPEEDO. Hung on window rather than a module const so nothing in
      // this ~8000-line single scope can read it before its declaration
      // and take the whole runtime down with it (TRAP 1).
      const sp = document.createElement('div');
      sp.style.cssText = 'position:fixed;right:22px;bottom:22px;z-index:24;'
        + 'display:none;color:#dff4ff;text-align:center;'
        + 'background:rgba(10,9,18,.72);border:1px solid rgba(127,212,255,.4);'
        + 'border-radius:50%;padding:6px;pointer-events:none;line-height:0;';
      // ANALOG DIAL (2026-08-07). A digital readout tells you a number; a
      // needle tells you how hard you are pushing without being read at
      // all, which is the only thing that matters at speed. 240 degrees of
      // sweep from -210 to +30, ticks every 20 km/h, redline past 120.
      const SWEEP = 240, A0 = -210, VMAX = 160, R = 46;
      const polar = (deg, rad) => {
        const a = deg * Math.PI / 180;
        return [60 + Math.cos(a) * rad, 60 + Math.sin(a) * rad];
      };
      let ticks = '';
      for (let v = 0; v <= VMAX; v += 20) {
        const ang = A0 + (v / VMAX) * SWEEP;
        const [x1, y1] = polar(ang, R - 3), [x2, y2] = polar(ang, R - 11);
        const hot = v >= 120;
        ticks += `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" `
          + `x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" `
          + `stroke="${hot ? '#ff7a6a' : 'rgba(223,244,255,.55)'}" stroke-width="2"/>`;
        const [tx, ty] = polar(ang, R - 20);
        ticks += `<text x="${tx.toFixed(1)}" y="${(ty + 3).toFixed(1)}" `
          + `fill="rgba(223,244,255,.5)" font-size="8" font-family="system-ui" `
          + `text-anchor="middle">${v}</text>`;
      }
      const arcPt = (v) => polar(A0 + (v / VMAX) * SWEEP, R);
      const [ax0, ay0] = arcPt(0), [ax1, ay1] = arcPt(VMAX);
      const [rx0, ry0] = arcPt(120), [rx1, ry1] = arcPt(VMAX);
      sp.innerHTML = '<svg width="120" height="120" viewBox="0 0 120 120">'
        + `<path d="M${ax0.toFixed(1)} ${ay0.toFixed(1)} A${R} ${R} 0 1 1 `
        + `${ax1.toFixed(1)} ${ay1.toFixed(1)}" fill="none" `
        + 'stroke="rgba(127,212,255,.30)" stroke-width="3"/>'
        + `<path d="M${rx0.toFixed(1)} ${ry0.toFixed(1)} A${R} ${R} 0 0 1 `
        + `${rx1.toFixed(1)} ${ry1.toFixed(1)}" fill="none" `
        + 'stroke="rgba(255,122,106,.75)" stroke-width="3"/>'
        + ticks
        + '<line id="spdNdl" x1="60" y1="60" x2="60" y2="22" stroke="#7fd4ff" '
        + 'stroke-width="3" stroke-linecap="round" '
        + 'transform="rotate(-210 60 60)"/>'
        + '<circle cx="60" cy="60" r="5" fill="#0d0b16" stroke="#7fd4ff" stroke-width="2"/>'
        + '<text id="spdN" x="60" y="86" fill="#eaf7ff" font-size="15" '
        + 'font-weight="800" font-family="system-ui" text-anchor="middle">0</text>'
        + '<text x="60" y="98" fill="rgba(223,244,255,.5)" font-size="7.5" '
        + 'font-family="system-ui" text-anchor="middle" letter-spacing="1.4">KM/H</text>'
        + '</svg>';
      document.body.appendChild(sp);
      window.__speedEl = sp;
      window.__speedN = sp.querySelector('#spdN');
      window.__speedNdl = sp.querySelector('#spdNdl');
      window.__speedMax = 160;
      const hintC = document.querySelector('#hud .hint');
      if (hintC) hintC.textContent += ' · E by a car to drive it';
    }
  }
  function enterCar(c) {
    if (DRIVING || !c || lost) return;
    DRIVING = true; heldCar = c; window.__inCar = c;
    if (c.col) c.col.setEnabled(false);      // never collide with your own car
    holder.visible = false;
    scene.remove(c.rig);
    playerObj.add(c.rig);
    // SPINNING WHEELS FOR STOLEN CARS (2026-08-25): addWheels only ran for
    // born-in-car games, so every car entered with E — the getaway, the
    // synthwave racer, all 34 kerb cars — drove with frozen wheels. Same
    // overlay-wheel pass, applied at the moment of theft; removed on exit
    // so the steering keys stop reaching a parked car's front axle.
    try {
      const _w0 = wheels.length;
      addWheels(c.rig);
      c._wRange = [_w0, wheels.length];
    } catch (e) { c._wRange = null; }
    // playerObj sits at the capsule's FEET, and spawnHeight floats it 0.15 m
    // clear of the terrain — drop the shell back onto its tyres.
    c.rig.position.set(0, -0.14, 0);
    modelYaw = c.yaw;
    carVX = 0; carVZ = 0; vSpeed = 0; vy = 0; prevV = 0;
    window.__sneak = false;
    if (window.__sneakChip) window.__sneakChip.style.display = 'none';
    const ey = spawnHeight(c.x, c.z);
    body.setTranslation({ x: c.x, y: ey, z: c.z }, true);
    body.setNextKinematicTranslation({ x: c.x, y: ey, z: c.z });
    sfx('go');
    popText('Engine on — W to drive, E to get out', '#7fd4ff');
  }
  function exitCar() {
    if (!DRIVING || !heldCar) return;
    const c = heldCar;
    const cx5 = playerObj.position.x, cz5 = playerObj.position.z;
    if (c._wRange) {
      wheels.splice(c._wRange[0], c._wRange[1] - c._wRange[0]);
      c._wRange = null;
    }
    playerObj.remove(c.rig);
    scene.add(c.rig);
    c.rig.position.set(cx5, hAt(cx5, cz5), cz5);
    c.rig.rotation.set(0, modelYaw, 0);
    c.x = cx5; c.z = cz5; c.yaw = modelYaw;
    // STEP OUT, NEVER INTO A WALL (2026-08-05): driver's side first, then
    // passenger side, then behind. Each candidate is ray-tested outward from
    // the driver's seat — a hit means that "pavement" is a building, so the
    // next door is tried. Falling through leaves the player on the car's own
    // (collider-free) spot, which is always escapable.
    let ex = cx5, ez = cz5;
    for (const [sx5, sz5] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
      const dxw = Math.cos(modelYaw) * sx5 + Math.sin(modelYaw) * sz5;
      const dzw = -Math.sin(modelYaw) * sx5 + Math.cos(modelYaw) * sz5;
      const ray = new RAPIER.Ray({ x: cx5, y: hAt(cx5, cz5) + 1.0, z: cz5 },
                                 { x: dxw, y: 0, z: dzw });
      if (world.castRay(ray, 3.4, true, undefined, undefined, collider, body)) continue;
      ex = cx5 + dxw * 2.6; ez = cz5 + dzw * 2.6;
      break;
    }
    DRIVING = false; window.__inCar = null;
    // re-arm on the NEXT frame: re-enabling while the player is still
    // standing in the door well is how you get shoved through a wall
    if (heldCar && heldCar.col) {
      const _rc = heldCar.col;
      setTimeout(() => { try { _rc.setEnabled(true); } catch (e) {} }, 700);
    }
    heldCar = null;
    holder.visible = true;
    holder.rotation.x = 0; holder.rotation.z = 0;
    leanP = 0; leanR = 0;
    carVX = 0; carVZ = 0; vSpeed = 0; vy = 0;
    const ey = spawnHeight(ex, ez);
    body.setTranslation({ x: ex, y: ey, z: ez }, true);
    body.setNextKinematicTranslation({ x: ex, y: ey, z: ez });
    sfx('step');
    popText('Out of the car', '#7fd4ff');
  }
  // keydown REPEATS while E is held — without the cooldown one press
  // toggles in and out of the car a dozen times.
  // Hand a moving traffic car over to the drivable system: pull it out of
  // the traffic list (which is what stops it), keep the exact world transform
  // it had, and enter it. It is an ordinary car from here on — it can be
  // parked, left, and found again.
  function stealCar(tv) {
    const i = (window.__traffic || []).indexOf(tv);
    if (i >= 0) window.__traffic.splice(i, 1);
    const c = { rig: tv.obj, x: tv.obj.position.x, z: tv.obj.position.z,
                yaw: tv.obj.rotation.y };
    window.__cars.push(c);
    popText('Car stolen', '#ffd06a');
    enterCar(c);
  }
  window.__carE = () => {
    if (!CARS_OK) return false;
    if (performance.now() < carCool) return true;
    if (DRIVING) { carCool = performance.now() + 550; exitCar(); return true; }
    if (nearCar) { carCool = performance.now() + 550; enterCar(nearCar); return true; }
    if (window.__nearTraffic) {
      carCool = performance.now() + 550; stealCar(window.__nearTraffic); return true;
    }
    return false;
  };
  function stepCars(dt) {
    if (!CARS_OK || !carPrompt) return;
    camDistMul = THREE.MathUtils.damp(camDistMul, DRIVING ? 1.75 : 1, 3.2, dt);
    if (DRIVING) {
      if (heldCar) {
        heldCar.rig.rotation.set(leanP, modelYaw, leanR);
        heldCar.x = playerObj.position.x;   // keeps the minimap dot on the car
        heldCar.z = playerObj.position.z;
      }
      nearCar = null;
      window.__nearTraffic = null;
      carPrompt.textContent = 'E — get out';
      carPrompt.style.display = 'block';
      if (window.__speedEl) {
        const kph = Math.round(Math.hypot(carVX, carVZ) * 3.6);
        window.__speedEl.style.display = 'block';
        window.__speedN.textContent = kph;
        // the needle lags a little, like a real one — an instant snap reads
        // as a number that happens to be drawn as a line
        const want = -210 + Math.min(kph / window.__speedMax, 1) * 240;
        window.__speedNdlA = window.__speedNdlA === undefined
          ? want : window.__speedNdlA + (want - window.__speedNdlA) * 0.22;
        window.__speedNdl.setAttribute('transform',
          'rotate(' + window.__speedNdlA.toFixed(1) + ' 60 60)');
        window.__speedNdl.setAttribute('stroke', kph > 120 ? '#ff7a6a' : '#7fd4ff');
        window.__speedN.setAttribute('fill', kph > 120 ? '#ffb0a4' : '#eaf7ff');
      }
      return;
    }
    if (window.__speedEl) window.__speedEl.style.display = 'none';
    let best = null, bd = 6.0;
    const pp5 = playerObj.position;
    for (const c of window.__cars) {
      const d = Math.hypot(c.x - pp5.x, c.z - pp5.z);
      if (d < bd) { bd = d; best = c; }
    }
    // CARJACKING (2026-08-06): a moving car you cannot touch is scenery. The
    // reach is a little longer than for a parked one because it is closing on
    // you while you press the key. A parked car still wins a tie — it is the
    // safer read when you are stood between the two.
    let bt = null, btd = 7.5;
    if (!best) {
      for (const tv of window.__traffic || []) {
        if (!tv.steal) continue;
        const d = Math.hypot(tv.obj.position.x - pp5.x, tv.obj.position.z - pp5.z);
        if (d < btd) { btd = d; bt = tv; }
      }
    }
    nearCar = best;
    window.__nearTraffic = bt;
    carPrompt.style.display = (best || bt) ? 'block' : 'none';
    if (best) carPrompt.textContent = 'E — drive';
    else if (bt) carPrompt.textContent = 'E — steal car';
  }
  window.__game.cars = () => window.__cars.map(c => ({ x: c.x, z: c.z }));
  window.__game.driving = () => DRIVING;
  window.__game.nearCar = () => (nearCar ? { x: nearCar.x, z: nearCar.z } : null);

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
    // ── QUALITY PACKS (pivot Move 5): one named grade the whole game wears.
    // Each pack is a coherent exposure/fog/light recipe — the "months of
    // polish" defaults, chosen once instead of dialed per-game.
    const GRADES = {
      cinematic: { exposure: 1.16, fog: 4.5, sun: 2.6 },   // deep contrast, light haze
      noir:      { exposure: 0.72, fog: 9.0, sun: 1.1 },   // heist weather
      golden:    { exposure: 1.28, fog: 6.0, sun: 3.2 },   // late-sun warmth
      retro:     { exposure: 1.05, fog: 1.5, sun: 2.0 },   // flat, clean, arcade
    };
    const applyGrade = g => {
      const gr = GRADES[g];
      if (!gr) return;
      renderer.toneMappingExposure = gr.exposure;
      if (scene.fog) scene.fog.density = gr.fog * 0.01;
      sun.intensity = gr.sun;
    };
    applyGrade(SPEC.grade);
    addEventListener('message', e => {
      if (e.data && e.data.type === 'fs-inspect') setInspectOn(e.data.on);
      // DROP TARGETING (2026-08-06): the studio's asset palette drags a card
      // over the iframe and needs the WORLD point under the cursor. It cannot
      // raycast from out there — an iframe swallows the parent's drag events
      // and the parent has no camera — so it hands us viewport coordinates
      // and we answer with the same fs-pick the click path already emits.
      // Works whether or not Inspect is armed: dropping is its own gesture.
      if (e.data && e.data.type === 'fs-dropat') {
        pickAt(e.data.cx, e.data.cy, 'drop');
      }
      // ── HOT DROP (2026-08-07) ───────────────────────────────────────
      // Placing something used to mean waiting out a full rebuild, which is
      // the one thing this studio is supposed to be better at than everyone
      // else. The runtime already knows how to build every placeable kind —
      // procProp covers the procedural ones and the facade kit builds real
      // buildings — so a drop can just BUILD IT NOW and let the rebuild
      // catch up later to make it permanent.
      if (e.data && e.data.type === 'fs-spawn') {
        try {
          const q = e.data;
          const kind = String(q.kind || 'beacon').toLowerCase();
          const pp = procProp(kind);
          const g9 = pp.g;
          const gy9 = hAt(q.x, q.z);
          g9.position.set(q.x, gy9, q.z);
          g9.traverse(o => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
          g9.userData.fsTag = { type: 'placed', name: kind, kind,
                                detail: kind + ' (live — apply the edit to keep it)' };
          scene.add(g9);
          // a live drop gets the same collider a built one would, or you
          // could walk through the building you just placed
          const bb9 = new THREE.Box3().setFromObject(g9);
          if ((bb9.max.y - bb9.min.y) > 0.5) {
            world.createCollider(RAPIER.ColliderDesc.cuboid(
              Math.max((bb9.max.x - bb9.min.x) / 2 * 0.85, 0.1),
              (bb9.max.y - bb9.min.y) / 2,
              Math.max((bb9.max.z - bb9.min.z) / 2 * 0.85, 0.1))
              .setTranslation(q.x, gy9 + (bb9.max.y - bb9.min.y) / 2, q.z));
          }
          popText(kind + ' placed', '#7fd4ff');
          sfx('pickup');
          window.parent.postMessage({ type: 'fs-spawned', ok: true, kind }, '*');
        } catch (err) {
          window.parent.postMessage({ type: 'fs-spawned', ok: false,
                                      err: String(err && err.message || err) }, '*');
        }
      }
      if (e.data && e.data.type === 'fs-grade') applyGrade(e.data.grade);
      // ── LIVE PATCH (2026-08-05, the studio unlock): edits that only move
      // runtime dials — weather, time of day, fog, speeds, HP — no longer
      // rebuild the world. They apply to the RUNNING game in a frame, so
      // iteration costs a keystroke instead of two minutes. Rebuilding to
      // change one number is what made both users and us go in circles.
      if (e.data && e.data.type === 'fs-patch' && e.data.patch) {
        const q = e.data.patch;
        const done = [];
        try {
          if (q.fog_density !== undefined && scene.fog) {
            scene.fog.density = Math.max(0, q.fog_density) * 0.01;
            done.push('fog → ' + q.fog_density);
          }
          if (q.sun_intensity !== undefined) {
            sun.intensity = q.sun_intensity;
            done.push('sun → ' + q.sun_intensity);
          }
          if (q.exposure !== undefined) {
            renderer.toneMappingExposure = q.exposure;
            done.push('exposure → ' + q.exposure);
          }
          if (q.walk_speed !== undefined) {
            P.walk_speed = q.walk_speed; done.push('walk → ' + q.walk_speed);
          }
          if (q.run_speed !== undefined) {
            P.run_speed = q.run_speed; done.push('run → ' + q.run_speed);
          }
          if (q.player_hp !== undefined) {
            P.hp = Math.max(1, q.player_hp | 0);
            php = Math.max(1, q.player_hp | 0);
            done.push('hp → ' + q.player_hp);
          }
          if (q.enemy_speed !== undefined) {
            for (const n of npcs) {
              if (n.behavior === 'hostile') n.speed = q.enemy_speed;
            }
            done.push('enemy speed → ' + q.enemy_speed);
          }
          if (q.enemy_hp !== undefined) {
            for (const n of npcs) {
              if (n.behavior === 'hostile') n.hp = Math.max(1, q.enemy_hp | 0);
            }
            done.push('enemy hp → ' + q.enemy_hp);
          }
          // weather + time-of-day stay COLD for now: they own particle
          // systems and sky uniforms that need real plumbing, and a
          // half-applied weather change is worse than a clean rebuild.
        } catch (err) {
          window.parent.postMessage({ type: 'fs-patched', ok: false,
                                      error: err.message }, '*');
          return;
        }
        window.parent.postMessage({ type: 'fs-patched', ok: true,
                                    applied: done }, '*');
      }
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
      // A DROP ALWAYS LANDS (2026-08-06). The loop above returns silently when
      // the ray hits nothing — aimed at open sky, through a gap between
      // buildings, or past the terrain edge. The studio arms `pendingDrop` and
      // waits for a reply that never comes, so the drag reads as "nothing
      // happened" with no error anywhere. Fall back to the mathematical ground
      // plane so a drop is never swallowed; only a ray pointing at or above
      // the horizon has no ground answer, and that we report honestly.
      if (kindEv === 'drop') {
        const dir = rc.ray.direction, org = rc.ray.origin;
        if (dir.y < -1e-4) {
          const t = -org.y / dir.y;
          const gx = org.x + dir.x * t, gz = org.z + dir.z * t;
          if (Math.abs(gx) < 4000 && Math.abs(gz) < 4000) {
            window.parent.postMessage({
              type: 'fs-pick', kind: kindEv,
              x: +gx.toFixed(2), z: +gz.toFixed(2), y: 0,
              target: { type: 'ground', name: 'ground',
                        detail: `ground (${gx.toFixed(1)}, ${gz.toFixed(1)})` },
            }, '*');
            return;
          }
        }
        window.parent.postMessage({ type: 'fs-pick', kind: 'dropfail' }, '*');
      }
    };
    window.__game.pick = (cx, cy) => pickAt(cx, cy, 'click');   // test harness
    // ── SCENE AUDIT (2026-08-25): the WorldClaw lesson, locally ──────────
    // Their real contribution is not a model — it is that the agent LOOKS AT
    // what it built and fixes it before anyone sees it. The geometric 80% of
    // that needs no VLM at all: the scene graph knows where the ground is,
    // where every building footprint is, and where every object stands.
    // Floating, buried, and inside-a-wall are arithmetic.
    window.__audit = () => {
      const defects = [];
      const BLDG_KINDS = /brownstone|skyscraper|warehouse|storefront|limestone|building/i;
      const FLYERS = /bird|dragon|drone|ghost|wraith|bee|bat|butterfly|wisp/i;
      const check = (id, obj, kind, allowBldg) => {
        if (!obj || !obj.parent || !obj.visible) return;
        const bb = new THREE.Box3().setFromObject(obj);
        if (!isFinite(bb.min.y) || bb.isEmpty()) return;
        const x = obj.position.x, z = obj.position.z;
        const g = hAt(x, z);
        const lift = bb.min.y - g;
        let type = null, fix = null;
        if (lift > 0.35) { type = 'floating'; fix = { dy: +(-lift).toFixed(2) }; }
        else if (lift < -0.5) { type = 'buried'; fix = { dy: +(-lift).toFixed(2) }; }
        // strictly INSIDE a footprint (negative pad), so a bench against a
        // wall — which is where benches belong — never trips it
        if (!type && !allowBldg && typeof inBldg === 'function' && inBldg(x, z, -0.4)) {
          type = 'in_building';
          // radii must clear a REAL footprint: Manhattan blocks run 20m+
          // across, so an 8m cap could never escape one and everything
          // deep inside got hidden instead of moved (first live test)
          outer: for (const r of [2.5, 4, 6, 8, 11, 15, 20]) {
            for (let k = 0; k < 8; k++) {
              const a = k * Math.PI / 4;
              const cx = x + Math.cos(a) * r, cz = z + Math.sin(a) * r;
              if (inBldg(cx, cz, 0.3)) continue;
              if (window.__onRoadChk && window.__onRoadChk(cx, cz, 0.6)) continue;
              fix = { dx: +(cx - x).toFixed(2), dz: +(cz - z).toFixed(2) };
              break outer;
            }
          }
          if (!fix) fix = { hide: true };   // boxed in on all sides: remove it
        }
        if (type) defects.push({ id, kind, type, x: +x.toFixed(2), z: +z.toFixed(2), fix });
      };
      for (const pI of placedItems) {
        const si = (SPEC.world.placed_items || []).indexOf(pI.it);
        if (si >= 0) check('placed:' + si, pI.obj, pI.it.kind || 'placed',
                           BLDG_KINDS.test(pI.it.kind || ''));
      }
      npcs.forEach((n2, i) => {
        if (n2.dormant || n2.dead) return;
        const kd = ((n2.obj.userData && n2.obj.userData.fsTag) || {}).name || 'npc';
        if (FLYERS.test(kd)) return;
        check('npc:' + i, n2.obj, kd, false);
      });
      (window.__cars || []).forEach((c, i) => {
        if (window.__inCar === c || !c.rig) return;
        check('car:' + i, c.rig, 'car', false);
      });
      return { checked: placedItems.length + npcs.length
                        + (window.__cars || []).length, defects };
    };
    // NPC and car fixes cannot be applied through the spec (they spawn from
    // entities and road seeds, not coordinates), so they are applied to the
    // live objects. Registries fill asynchronously, so retry until landed.
    if (window.__AUDIT_FIX && Array.isArray(window.__AUDIT_FIX.fixes)) {
      const later = window.__AUDIT_FIX.fixes.filter(f => /^(npc|car):/.test(f.id || ''));
      if (later.length) {
        const done = new Set();
        let tries = 0;
        const tick = setInterval(() => {
          tries++;
          for (const f of later) {
            if (done.has(f.id) || !f.fix) continue;
            const kk = f.id.split(':')[0], si = +f.id.split(':')[1];
            const rec = kk === 'npc' ? npcs[si] : (window.__cars || [])[si];
            const o = rec && (rec.obj || rec.rig);
            if (!o) continue;
            if (f.fix.hide) o.visible = false;
            else {
              o.position.x += f.fix.dx || 0;
              o.position.y += f.fix.dy || 0;
              o.position.z += f.fix.dz || 0;
              if (kk === 'car') { rec.x = o.position.x; rec.z = o.position.z; }
            }
            done.add(f.id);
          }
          if (done.size >= later.length || tries > 8) clearInterval(tick);
        }, 1000);
      }
    }
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
      // OPT-OUT (2026-08-06): the sweep claims any untextured standard
      // material. That silently handed a woodgrain albedo to the dark wall
      // behind every window reveal — the surface you look AT down the
      // recess — which reads as a lighting bug rather than a texturing
      // one. Deliberately flat materials now say so and are left alone.
      if (!m.isMeshStandardMaterial || m.map || m.userData.noAutoTex
          || _seen.has(m.uuid)) continue;
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
      // PANO FLOOR IS SACRED (2026-08-04): this enrichment ran AFTER the
      // photo floor was assigned and overwrote it with tiled sand/grass —
      // the user stood on our procedural ground while their image floated
      // as a wall. Image worlds keep the reprojected photo, full stop.
      if (!panoGroundTex) {
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
      }
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
  // no godrays without an atmosphere: 'space' got sun shafts through a
  // starless void, which is what washed the neon test to fog-grey
  const godray = !(['night', 'space'].includes(SPEC.world.sky)
                   || window.__darkWorld) ? new ShaderPass({
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
  let carVX = 0, carVZ = 0;      // world velocity — lateral part is the drift
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
  if (DRIVE && window.__procDrive) {
    // REAL PIVOTS, NOT INFERENCE. addWheels reverse-engineers axle positions
    // from vertex bands and overlays fake wheels on top — the best a baked
    // mesh allows. A sculpted module NAMES its pivots, so the same roll/steer
    // loop drives the actual wheels: fronts steer about their own hubs, all
    // four spin. wr matches the module's WHEEL_R.
    window.__procDrive.traverse(o => {
      if (/^wheel-F[LR]-steer$/.test(o.name)) {
        wheels.push({ g: o, tire: o.children[0], wr: 0.315, front: true });
      } else if (/^wheel-R[LR]-spin$/.test(o.name)) {
        wheels.push({ g: o, tire: o, wr: 0.315, front: false });
      }
    });
  } else if (DRIVE && playerObj.children.length) addWheels(playerObj.children[0]);
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
    const rdt = dt;                       // real dt: camera + juice decay
    if (juiceSlow > 0) { juiceSlow -= rdt; dt *= 0.3; }
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
    if (DRIVE || DRIVING) {
      // CAR PHYSICS: throttle/brake + speed-scaled steering — no crab-walking
      const throttle = raceGo ? -mv.z : 0;          // W/up = forward (after GO)
      const steer = raceGo ? mv.x : 0;
      // a STOLEN car does not inherit the pedestrian's top speed — a detective
      // who runs at 7 m/s would otherwise "drive" at jogging pace.
      const maxV = DRIVING ? (mv.run ? 30 : 19)
                           : (mv.run ? P.run_speed : P.walk_speed);
      if (throttle > 0.05) vSpeed += 11 * throttle * dt;
      else if (throttle < -0.05) vSpeed -= 14 * -throttle * dt;   // brake/reverse
      else vSpeed *= Math.max(0, 1 - 1.6 * dt);                   // coast friction
      vSpeed = THREE.MathUtils.clamp(vSpeed, -maxV * 0.35, maxV);
      const steerAuth = Math.min(Math.abs(vSpeed) / 5, 1);
      // DRIFT (2026-08-04, the gta7 grip model): the car was on RAILS —
      // velocity was always exactly along the nose, so it could never
      // slide. Now world velocity is split into FORWARD + LATERAL each
      // frame and grip bleeds the lateral part away. Hold Shift over
      // 6 m/s and grip drops: momentum carries while the nose swings.
      // That one number is the whole drift model (and it feels better
      // than a half-tuned rigid-body vehicle).
      const sliding = !!mv.run && Math.abs(vSpeed) > 6;
      window.__drifting = sliding;
      modelYaw -= steer * (sliding ? 2.6 : 1.9) * steerAuth
                  * Math.sign(vSpeed || 1) * dt;
      dir.set(Math.sin(modelYaw), 0, Math.cos(modelYaw));
      const fwdV = carVX * dir.x + carVZ * dir.z;
      const latVX = carVX - fwdV * dir.x, latVZ = carVZ - fwdV * dir.z;
      const keepLat = Math.exp(-(sliding ? 0.9 : 9.5) * dt);
      carVX = dir.x * vSpeed + latVX * keepLat;
      carVZ = dir.z * vSpeed + latVZ * keepLat;
      speed = Math.hypot(carVX, carVZ);
      vy = Math.max(vy - 9.81 * dt, -25);
      var desired = { x: carVX * dt, y: vy * dt, z: carVZ * dt };
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
      // SNEAK (the heist kit): hold C/Ctrl to crouch-walk — slower, but
      // guards' vision range halves. The flag is read by guard AI.
      window.__sneak = !!(keys.KeyC || keys.ControlLeft) && !mv.run;
      if (window.__sneak) {
        speed *= 0.45;
        if (!window.__sneakChip) {
          const c = document.createElement('div');
          c.style.cssText = 'position:fixed;left:50%;bottom:64px;transform:translateX(-50%);'
            + 'padding:4px 12px;border-radius:999px;background:rgba(10,12,20,.72);'
            + 'color:#9fd8a2;font:600 12px system-ui;z-index:40;pointer-events:none';
          c.textContent = '🤫 sneaking — guards see half as far';
          document.body.appendChild(c);
          window.__sneakChip = c;
        }
        window.__sneakChip.style.display = '';
      } else if (window.__sneakChip) window.__sneakChip.style.display = 'none';
      if (dir.lengthSq() > 1e-4) {
        dir.normalize().applyAxisAngle(new THREE.Vector3(0, 1, 0), VIEW === '3d' ? yaw : 0);
        modelYaw = dampAngle(modelYaw, Math.atan2(dir.x, dir.z), P.turn_speed, dt);
      }
      // GRAMMAR: jump — grounded Space gives a real ballistic arc through the
      // same collider (platformers unlock from this one verb)
      if (gameStarted && keys.Space && kcc.computedGrounded() && downT <= 0) { vy = 7.2; sfx('step'); }
      vy = Math.max(vy - 9.81 * dt, -25);
      // airborne body language: tilt back on the rise, forward into the fall —
      // the cheap half of jump articulation until the jump clip lands
      const airTilt = kcc.computedGrounded() ? 0
        : THREE.MathUtils.clamp(-vy * 0.035, -0.22, 0.3);
      leanP = THREE.MathUtils.damp(leanP, airTilt, 7, dt);
      holder.rotation.x = leanP;
      // aiming is a walk, not a sprint — the price of the reticle
      const _aimK = 1 - aimT * 0.62;
      var desired = { x: dir.x * speed * _aimK * dt, y: vy * dt,
                      z: dir.z * speed * _aimK * dt };
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
    holder.rotation.y = modelYaw + FRONT_IS_MINUS_Z
                      + THREE.MathUtils.degToRad(P.yaw_offset_deg || 0);
    if (DRIVE || DRIVING) {
      // suspension feel: pitch under accel/brake, roll into turns
      const accel = (vSpeed - prevV) / Math.max(dt, 1e-3); prevV = vSpeed;
      leanP = THREE.MathUtils.damp(leanP,
        THREE.MathUtils.clamp(-accel * 0.012, -0.06, 0.06), 6, dt);
      leanR = THREE.MathUtils.damp(leanR,
        THREE.MathUtils.clamp(mv.x * Math.min(Math.abs(vSpeed) / 8, 1) * 0.07, -0.08, 0.08), 6, dt);
      holder.rotation.x = leanP; holder.rotation.z = leanR;
      if (window.__drifting) {          // exaggerate the lean into a slide
        leanR = THREE.MathUtils.clamp(leanR * 1.6, -0.17, 0.17);
      }
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
    if (gameStarted && !paused && !inspectOn) {
      playT += dt;
      // ── LIGHT BUDGET (2026-08-05): WebGL2 compiles a FIXED number of light
      // slots into every shader. Ten lit torches plus sun and hemi already
      // sat at the ceiling — adding anything (spotlight cookies) made
      // MeshStandardMaterial fail to LINK, which renders a black room rather
      // than logging a warning. Rooms you cannot see do not need to be lit,
      // so only the nearest few torches stay on. This is both the fix and
      // the headroom that lighting work needs.
      if (window.__torches && window.__torches.length > 4 && (window.__ltT || 0) < playT) {
        window.__ltT = playT + 0.25;          // 4Hz is plenty; lights are cheap to toggle
        const px2 = playerObj.position.x, pz2 = playerObj.position.z;
        const ranked = window.__torches
          .map(L => [L, (L.position.x - px2) ** 2 + (L.position.z - pz2) ** 2])
          .sort((a, b) => a[1] - b[1]);
        ranked.forEach(([L], i) => { L.visible = i < 4; });
      }
      if (window.__flights && window.__flights.length) {
        window.__flights = window.__flights.filter(f => !f.step());
      }
      stepNPCs(dt, nt, performance.now() / 1000);
      // SUSPICION HUD (heist kit): an eye that opens as a guard grows sure
      // of you, and goes red the moment you're made.
      if (HAS_GUARDS) {
        const a = window.__alertPeak || 0;
        if (!window.__eyeEl) {
          const e2 = document.createElement('div');
          e2.style.cssText = 'position:fixed;left:50%;top:16px;transform:translateX(-50%);'
            + 'display:flex;align-items:center;gap:7px;padding:5px 13px;border-radius:999px;'
            + 'background:rgba(8,10,16,.66);font:600 12px system-ui;z-index:41;'
            + 'pointer-events:none;transition:opacity .25s';
          e2.innerHTML = '<span id="fseye">👁</span>'
            + '<span style="display:block;width:78px;height:4px;border-radius:2px;'
            + 'background:rgba(255,255,255,.16);overflow:hidden">'
            + '<i id="fsbar" style="display:block;height:100%;width:0;background:#ffd166"></i></span>';
          document.body.appendChild(e2);
          window.__eyeEl = e2;
        }
        const bar = document.getElementById('fsbar');
        window.__eyeEl.style.opacity = a > 0.03 ? '1' : '0';
        if (bar) {
          bar.style.width = Math.min(100, a * 100) + '%';
          bar.style.background = a >= 1 ? '#ff5c5c' : (a > 0.6 ? '#ff9f45' : '#ffd166');
        }
      }
    }
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
      if (st && st.kind === 'escort'
          && npcs.some(nn => nn.behavior === 'escort' && !nn.dead && nn._arrived)) {
        advanceStep();
      }
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
    stepCars(dt);
    // ground actually covered this frame drives footstep cadence, so a
    // sprint sounds like a sprint without a second timer to keep in sync
    stepEvents(dt);
    audioFrame(dt, Math.hypot(playerObj.position.x - _audPX,
                              playerObj.position.z - _audPZ));
    _audPX = playerObj.position.x; _audPZ = playerObj.position.z;
    fixArmSplay();          // after the mixers, before the frame is drawn
    // ── AIMING (2026-08-07) ───────────────────────────────────────────
    // Holding F with the pistol out slows you to a walk, pulls the camera
    // in, and raises a reticle that turns red when a target is actually
    // inside range. Releasing fires. Aiming has to COST something or it is
    // just a crosshair; the movement penalty is that cost.
    {
      const wpnNow = WEAPONS[weaponIdx] || WEAPONS[0];
      const wantAim = !!keys.KeyF && wpnNow.id === 'pistol'
                      && ATTACK !== 'none' && !DRIVING && !lost && downT <= 0;
      aimT = Math.max(0, Math.min(1, aimT + (wantAim ? dt * 6 : -dt * 8)));
      if (window.__aimEl) {
        window.__aimEl.style.display = aimT > 0.05 ? 'block' : 'none';
        window.__aimEl.style.opacity = aimT.toFixed(2);
        if (window.__aimDot && aimT > 0.05) {
          const tgtA = nearestHostile(RANGED_RANGE);
          window.__aimDot.setAttribute('fill', tgtA ? '#6aff8f' : '#ff6a6a');
        }
      }
    }
    // ── SHELLS AND BLASTS ─────────────────────────────────────────────
    for (let i = shells.length - 1; i >= 0; i--) {
      const sh = shells[i];
      sh.life -= dt;
      sh.vy -= 16 * dt;                          // lobbed, not laser-straight
      sh.obj.position.x += sh.vx * dt;
      sh.obj.position.y += sh.vy * dt;
      sh.obj.position.z += sh.vz * dt;
      const gy7 = hAt(sh.obj.position.x, sh.obj.position.z);
      if (sh.obj.position.y <= gy7 + 0.25 || sh.life <= 0) {
        detonate(sh.obj.position.x, gy7, sh.obj.position.z);
        scene.remove(sh.obj);
        shells.splice(i, 1);
      }
    }
    for (let i = blasts.length - 1; i >= 0; i--) {
      const bl = blasts[i];
      bl.t += dt;
      const k7 = bl.t / 0.55;
      if (k7 >= 1) {
        bl.obj.visible = false;           // parked, never removed
        if (bl.light) bl.light.intensity = 0;
        blasts.splice(i, 1);
        continue;
      }
      const r7 = 0.6 + k7 * bl.r;
      bl.obj.scale.setScalar(r7);
      bl.obj.material.opacity = (1 - k7) * 0.9;
      if (bl.light) bl.light.intensity = (1 - k7) * 26;
    }
    // ── THE HERO GETS RUN OVER TOO (2026-08-07) ───────────────────────
    // Traffic that harmlessly passes through you is the same diorama tell
    // as pedestrians it cannot touch. On foot, a car with speed on it puts
    // you on the tarmac: you take a hit, you slide, and you have to get
    // back up before you can move — which is the cost that makes crossing
    // a road mean something.
    if (!DRIVING && !lost && downT <= 0) {
      const pp5 = body.translation();
      for (const tc of window.__traffic || []) {
        if (tc.speed < 2.2) continue;
        const dx5 = pp5.x - tc.obj.position.x, dz5 = pp5.z - tc.obj.position.z;
        if (dx5 * dx5 + dz5 * dz5 > 5.3) continue;          // ~2.3m
        downT = 2.2;
        downVX = Math.sin(tc.obj.rotation.y) * Math.min(tc.speed * 0.7, 11);
        downVZ = Math.cos(tc.obj.rotation.y) * Math.min(tc.speed * 0.7, 11);
        playerHit(1);
        shakeT = Math.max(shakeT, 0.45);
        popText('Knocked down!', '#ff8fa0');
        break;
      }
    }
    if (downT > 0) {
      downT -= dt;
      const pp6 = body.translation();
      const nx6 = pp6.x + downVX * dt, nz6 = pp6.z + downVZ * dt;
      const k6 = Math.min(1, dt * 3.0);
      downVX -= downVX * k6; downVZ -= downVZ * k6;
      const ny6 = spawnHeight(nx6, nz6);
      body.setNextKinematicTranslation({ x: nx6, y: ny6, z: nz6 });
      // flat on your back, then up in the last half second
      holder.rotation.x = downT > 0.55
        ? Math.min(holder.rotation.x + dt * 6, Math.PI / 2)
        : Math.max(holder.rotation.x - dt * 3.4, 0);
      if (downT <= 0) { downT = 0; holder.rotation.x = 0; }
    }
    // door teleports (moon plan 2.2; many venues 2026-08-05)
    if (window.__doors && window.__doors.length) {
      const pp = body.translation();
      const inside = pp.x > SPEC.world.size_m;
      for (const dw of window.__doors) {
        dw.cool = Math.max(0, dw.cool - dt);
        if (dw.cool) continue;
        if (!inside && Math.hypot(pp.x - dw.out[0], pp.z - dw.out[1]) < 1.5) {
          body.setTranslation({ x: dw.inSpawn[0], y: 1.2, z: dw.inSpawn[1] }, true);
          body.setNextKinematicTranslation({ x: dw.inSpawn[0], y: 1.2, z: dw.inSpawn[1] });
          dw.cool = 1.2; sfx('step');
          window.__doorway = dw;             // the camera ceiling follows you in
          popText('Inside ' + dw.label + '…', '#ffc46b');
          break;
        }
        if (inside && dw.exit
            && Math.hypot(pp.x - dw.exit[0], pp.z - dw.exit[1]) < 1.2) {
          const ox3 = dw.out[0], oz3 = dw.out[1] + 2.4;   // land CLEAR of the pad
          const oy2 = hAt(ox3, oz3) + 1.2;
          body.setTranslation({ x: ox3, y: oy2, z: oz3 }, true);
          body.setNextKinematicTranslation({ x: ox3, y: oy2, z: oz3 });
          dw.cool = 1.2; sfx('step');
          window.__doorway = null;
          // THE DOOR IS THE ESCAPE (2026-08-05): a guard left in `chase`
          // steers at the player's world position, and the player is now a
          // city block and eight hundred metres away — the whole patrol
          // would file out of the building and across the void after you.
          // Slipping out the front door is exactly when you lose them.
          for (const g of npcs) {
            if (g.behavior === 'guard') { g.mode = 'patrol'; g.alert = 0; g.lostT = 0; }
          }
          popText('Back on the street', '#ffc46b');
          break;
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
      let a2 = tv.pts[tv.seg], b2 = tv.pts[tv.seg + 1];
      if (!a2 || !b2) { tv.seg = 0; tv.t = 0; continue; }
      const segL = Math.hypot(b2[0] - a2[0], b2[1] - a2[1]) || 1;
      tv.t += (tv.speed * dt * tv.dir) / segL;
      // 2026-08-06: reaching the end used to TELEPORT the car back to the
      // start of the street, in full view. It now turns round and crosses
      // to the opposite lane, which is both continuous and the correct
      // side of the road for the new heading.
      if (tv.t >= 1) {
        tv.t = 0; tv.seg++;
        if (tv.seg >= tv.pts.length - 1) {
          tv.seg = tv.pts.length - 2; tv.t = 1; tv.dir = -1; tv.lane = -tv.lane;
        }
      } else if (tv.t <= 0) {
        tv.t = 1; tv.seg--;
        if (tv.seg < 0) { tv.seg = 0; tv.t = 0; tv.dir = 1; tv.lane = -tv.lane; }
      }
      a2 = tv.pts[tv.seg]; b2 = tv.pts[tv.seg + 1];
      if (!a2 || !b2) continue;
      const hdT = Math.atan2(b2[0] - a2[0], b2[1] - a2[1]);
      const lane = tv.lane || 0;
      const tx2 = a2[0] + (b2[0] - a2[0]) * tv.t + Math.cos(hdT) * lane;
      const tz2 = a2[1] + (b2[1] - a2[1]) * tv.t - Math.sin(hdT) * lane;
      tv.obj.position.set(tx2, hAt(tx2, tz2), tz2);
      let dyT = hdT + (tv.dir < 0 ? Math.PI : 0) - tv.obj.rotation.y;
      while (dyT > Math.PI) dyT -= Math.PI * 2;
      while (dyT < -Math.PI) dyT += Math.PI * 2;
      tv.obj.rotation.y += dyT * Math.min(1, dt * 4);
      // GETTING RUN OVER (2026-08-06). Only while ON FOOT: inside a car
      // the capsule rides at the same place as the bonnet, and every
      // overtake would read as a collision.
      if (!DRIVING && tv.speed > 2.5) {
        const hx = tx2 - playerObj.position.x, hz = tz2 - playerObj.position.z;
        if (hx * hx + hz * hz < 3.1 * 3.1
            && performance.now() > (window.__carHitCool || 0)) {
          window.__carHitCool = performance.now() + 1400;
          playerHit(1);
          popText('Hit by a car', '#ff8fa0');
        }
      }
    }
    // CROWD LOD (2026-08-06): a skinned walker costs a skeleton update and
    // a mixer tick every frame whether or not it is on screen. Positions
    // keep integrating for everyone so the crowd stays coherent when you
    // turn round; only the expensive half is distance-gated.
    const _pcam = playerObj.position;
    // ── STRUCK BY A CAR (2026-08-07) ──────────────────────────────────
    // A city where cars pass through people is a diorama. Every car with
    // real speed on it — yours or the traffic's — knocks a pedestrian down,
    // throws them along its heading, and they lie there before picking
    // themselves up. Cheap: a downed walker stops its mixer, so a pile-up
    // costs LESS per frame than the crowd walking.
    {
      const _hits = [];
      if (DRIVING && heldCar) {
        // The car you are driving is PARENTED TO THE PLAYER, so its rig
        // position is a local offset near zero — reading it as a world point
        // put every strike test at the origin, which is why traffic mowed
        // people down and your own bonnet went straight through them. The
        // kinematic body IS the car while driving; use that and modelYaw.
        const cv = Math.hypot(carVX, carVZ);
        if (cv > 2.2) {
          const bp7 = body.translation();
          _hits.push([{ x: bp7.x, z: bp7.z }, cv, modelYaw]);
        }
      }
      for (const tc of window.__traffic || []) {
        if (tc.speed > 2.2) _hits.push([tc.obj.position, tc.speed, tc.obj.rotation.y]);
      }
      if (_hits.length) {
        for (const nn of npcs) {
          if (nn.dead || nn.dormant || nn.down > 0) continue;
          for (const [cpos, cspd, cyaw] of _hits) {
            const dxn = nn.obj.position.x - cpos.x, dzn = nn.obj.position.z - cpos.z;
            if (dxn * dxn + dzn * dzn > 6.25) continue;
            nn.down = 2.6 + Math.random() * 1.4;
            nn.kx = Math.sin(cyaw) * Math.min(cspd * 0.55, 9);
            nn.kz = Math.cos(cyaw) * Math.min(cspd * 0.55, 9);
            // a guard bowled over loses you — being run down is exactly
            // when a chase should break
            if (nn.behavior === 'guard') { nn.mode = 'patrol'; nn.alert = 0; nn.lostT = 0; }
            sfx('hit');
            break;
          }
        }
        for (const pd of window.__peds || []) {
          if (pd.down > 0) continue;
          for (const [cpos, cspd, cyaw] of _hits) {
            const dx4 = pd.obj.position.x - cpos.x, dz4 = pd.obj.position.z - cpos.z;
            if (dx4 * dx4 + dz4 * dz4 > 6.25) continue;      // 2.5m strike radius
            pd.down = 2.6 + Math.random() * 1.6;
            // thrown along the CAR's heading, not away from its centre: a
            // glancing hit should still carry you down the road
            pd.kx = Math.sin(cyaw) * Math.min(cspd * 0.55, 9);
            pd.kz = Math.cos(cyaw) * Math.min(cspd * 0.55, 9);
            pd.spin = (Math.random() - 0.5) * 5;
            if (pd.mixer) pd.mixer.stopAllAction();
            sfx('hit');
            break;
          }
        }
      }
    }
    for (const pd of window.__peds || []) {
      // DOWNED: fly back, tumble flat, lie still, then get up. The walk
      // path is frozen meanwhile so they resume where they were hit rather
      // than snapping back onto the pavement mid-air.
      if (pd.down > 0) {
        pd.down -= dt;
        const k2 = Math.min(1, dt * 3.2);
        pd.obj.position.x += pd.kx * dt;
        pd.obj.position.z += pd.kz * dt;
        pd.kx -= pd.kx * k2; pd.kz -= pd.kz * k2;
        pd.obj.position.y = hAt(pd.obj.position.x, pd.obj.position.z);
        // tip flat over ~0.35s, hold, then stand back up in the last 0.6s
        const tgt = pd.down > 0.6 ? Math.PI / 2 : 0;
        pd.obj.rotation.x += (tgt - pd.obj.rotation.x) * Math.min(1, dt * 7);
        pd.obj.rotation.y += pd.spin * dt;
        pd.spin -= pd.spin * k2;
        if (pd.down <= 0) {
          pd.down = 0; pd.obj.rotation.x = 0;
          if (pd.mixer && pd._act) pd._act.reset().play();
        }
        continue;
      }
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
      const _pd2 = (pd.obj.position.x - _pcam.x) ** 2 + (pd.obj.position.z - _pcam.z) ** 2;
      const _vis = _pd2 < 95 * 95;
      if (pd.obj.visible !== _vis) pd.obj.visible = _vis;
      if (pd.mixer && _vis && _pd2 < 62 * 62) pd.mixer.update(dt);
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
        if (!(n.behavior === 'hostile' || n.behavior === 'flee' || n.behavior === 'guard') || n.dead) continue;
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
            juicePunch = FEEL.punch;
            juiceSlow = Math.max(juiceSlow, 0.09 * FEEL.slow);
            if (HAS_GUARDS) {
              // LOOT HAS VALUE (heist kit): every piece is worth a different
              // amount, so a burglar chooses what to risk reaching for
              // instead of vacuuming up identical tokens. The take is
              // tallied and shown on the win screen — that's the score.
              const val = 200 + ((c.phase * 977) | 0) % 1800;
              window.__take = (window.__take || 0) + val;
              popText(`💎 ${st.label || 'loot'}  +$${val.toLocaleString()}`
                      + `  ·  ${st._got}/${st.count}`, '#ffd54a');
              // grabbing it makes noise — a nearby guard comes to look
              for (const n of npcs) {
                if (n.behavior !== 'guard' || n.dead || n.dormant) continue;
                if (Math.hypot(n.obj.position.x - nt.x, n.obj.position.z - nt.z) < 13
                    && n.mode !== 'chase') {
                  n.alert = Math.min(0.95, (n.alert || 0) + 0.45);
                  n.beat = [[nt.x, nt.z]].concat(n.beat || []);
                  n.wp = 0;
                  break;
                }
              }
            } else {
              popText(`+1 ${st.label || ''}  ·  ${st._got}/${st.count}`, '#ffd54a');
            }
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
      yaw += dyaw * Math.min(1, ((DRIVE || DRIVING) ? 3.0 : 1.8) * dt);
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
      // LOW-HERO FRAMING (2026-08-05): camera lift scaled off camera.height_m
      // alone, so a cat (0.4 m tall) put the eye at tail height — the tail
      // filled the frame and you couldn't read the room ahead. Floor the
      // lift so short heroes are looked DOWN at, like every third-person
      // game with a small character.
      const _lift = Math.max(SPEC.camera.height_m, 1.5);
      _camWant.set(fX + Math.sin(modelYaw) * lookAhead,
                   fY + _lift * 0.5,
                   fZ + Math.cos(modelYaw) * lookAhead);
      if (camTarget.lengthSq() === 0) camTarget.copy(_camWant);
      camTarget.lerp(_camWant, 1 - Math.exp(-7 * dt));
      camera.up.set(0, 1, 0);              // never let lookAt roll-flip
      // camDistMul eases 1 -> 1.75 on entering a car: a walking-distance
      // camera sat on the roof at 19 m/s. Damped, so it reads as the camera
      // pulling back with you rather than a cut.
      const cd = SPEC.camera.distance_m * camZoom * camDistMul * (inspectOn ? 1.5 : 1);
      let cx = fX + Math.sin(yaw) * Math.cos(pitch) * cd;     // camera BEHIND
      let cz = fZ + Math.cos(yaw) * Math.cos(pitch) * cd;     // (W walks away)
      let cy = fY + Math.sin(pitch) * cd + _lift * 0.55;
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
    // PERF GATE (2026-08-05): renderer.info resets on every render call, and
    // the composer's last fullscreen pass is a render — so reading the counter
    // after the frame reports 1 draw call for any scene. Freeze autoReset and
    // reset once per frame so the number covers scene + passes together.
    // ── JUICE CAMERA, last write before render ──────────────────────
    if (juiceFly >= 0 && won) {
      // slow orbit around where the run ended — the world takes a bow
      juiceFly += rdt;
      const fp = playerObj.position;
      const fa = juiceFly * 0.55;
      const fr = SPEC.camera.distance_m * 1.6 + juiceFly * 1.2;
      camera.position.lerp(new THREE.Vector3(
        fp.x + Math.sin(fa) * fr, fp.y + 3.2 + juiceFly * 0.7,
        fp.z + Math.cos(fa) * fr), 1 - Math.exp(-4 * rdt));
      camera.lookAt(fp.x, fp.y + 1.0, fp.z);
    } else if (juicePOV) {
      // the escortee turns and looks back at the one who got him here
      juicePOV.t += rdt;
      camera.position.lerp(new THREE.Vector3(juicePOV.x, juicePOV.y, juicePOV.z),
                           1 - Math.exp(-10 * rdt));
      camera.lookAt(juicePOV.lx, juicePOV.ly, juicePOV.lz);
      if (juicePOV.t > 1.6) juicePOV = null;
    }
    if (juicePunch > 0.001) {
      camera.fov = SPEC.camera.fov_deg * (1 - 0.16 * juicePunch);
      camera.updateProjectionMatrix();
      juicePunch = Math.max(0, juicePunch - rdt * 4.2);
    } else if (camera.fov !== SPEC.camera.fov_deg) {
      camera.fov = SPEC.camera.fov_deg;
      camera.updateProjectionMatrix();
    }
    renderer.info.autoReset = false;
    renderer.info.reset();
    composer.render();
    window.__frameCalls = renderer.info.render.calls;
    window.__frameTris = renderer.info.render.triangles;
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
