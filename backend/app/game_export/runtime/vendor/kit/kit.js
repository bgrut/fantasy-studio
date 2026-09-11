// ═══════════════════════════════════════════════════════════════════════════
// THE KIT — the studio's presentation layer, shared by every runtime.
//
// What the factory game learned about presenting itself, with the ore taken
// out: a title card that arrives in a voice, a toast that says what happened
// and why, a caption for a beat, a label for what you point at, a foreman
// that teaches one step at a time, and a house style for the words. Pure
// DOM; no renderer, no three.js. A runtime imports what it wants:
//
//   import { title, toast, caption, look, Foreman, voice } from './vendor/kit/kit.js';
//
// Every element the kit makes carries an fs- class from kit.css and is created
// on first use, so a runtime that never toasts pays nothing for the toast.
// ═══════════════════════════════════════════════════════════════════════════

const el = (id, cls, html) => {
  let e = document.getElementById(id);
  if (!e) { e = document.createElement('div'); e.id = id; e.className = cls; e.innerHTML = html || ''; document.body.appendChild(e); }
  return e;
};

// ── THE VOICE. The rules the copy follows, as functions, so a runtime cannot
// drift back to "CONTRACT — deliver 4 x in 90s". Sentences. No em dashes. Say
// what happened, what it means, what to do. ────────────────────────────────
export const voice = {
  // "SPORES. A belt has clogged. A filter within 3 tiles keeps it clean."
  event: (label, what, why, todo) => [label ? label.toUpperCase() + '.' : '', what, why, todo].filter(Boolean).map(s => s.trim().replace(/[.!]?$/, '.')).join(' '),
  // "Splitter unlocked. One line can now feed two machines."
  unlock: (thing, means) => voice.event(null, thing + ' unlocked', means),
  // "That tool is locked until you bank 40 credits."
  locked: (until) => 'That tool is locked until you ' + until.replace(/[.!]?$/, '') + '.',
  // 1 contract kept / 2 contracts kept
  count: (n, one, many) => n + ' ' + (n === 1 ? one : (many || one + 's')),
  // 2:05
  clock: (secs) => Math.floor(secs / 60) + ':' + String(Math.floor(secs % 60)).padStart(2, '0'),
  // strip the one thing the house style forbids, in case a spec's own text carries it
  clean: (s) => String(s || '').replace(/\s*—\s*/g, ': ').replace(/\s*–\s*/g, ', '),
};

// ── THE TITLE CARD. show(name, sub, {mood, secs}); hide() on any input. ────
let titleT = null;
export const title = {
  show(name, sub, opts = {}) {
    const t = el('fs-title', 'fs-title', '<b></b><small></small>');
    t.querySelector('b').textContent = name || '';
    t.querySelector('small').textContent = voice.clean(sub || '');
    if (opts.mood) t.dataset.mood = opts.mood; else delete t.dataset.mood;
    // force the transition to restart when the same card is shown twice
    t.classList.remove('on'); void t.offsetWidth; t.classList.add('on');
    clearTimeout(titleT);
    if (opts.secs) titleT = setTimeout(() => title.hide(), opts.secs * 1000);
    return t;
  },
  hide() { const t = document.getElementById('fs-title'); if (t) t.classList.remove('on'); clearTimeout(titleT); },
  get up() { const t = document.getElementById('fs-title'); return !!t && t.classList.contains('on'); },
};

// ── THE TOAST. toast(text, secs). One at a time; a new one replaces the old. ─
let toastT = null;
export function toast(text, secs = 4) {
  const t = el('fs-toast', 'fs-toast');
  t.textContent = voice.clean(text);
  t.classList.add('on');
  clearTimeout(toastT);
  toastT = setTimeout(() => t.classList.remove('on'), secs * 1000);
  return t;
}
toast.hide = () => { const t = document.getElementById('fs-toast'); if (t) t.classList.remove('on'); };

// ── THE CAPTION. caption('SOUTH FACE  ·  salt', 2.2) ─────────────────────
let capT = null;
export function caption(text, secs = 2.2) {
  const c = el('fs-caption', 'fs-caption');
  c.textContent = text;
  c.classList.add('on');
  clearTimeout(capT);
  capT = setTimeout(() => c.classList.remove('on'), secs * 1000);
  return c;
}

// ── THE LOOK LABEL. look.set('SMELTER  ·  cooking') / look.clear() ──────────
export const look = {
  set(text) { const l = el('fs-look', 'fs-look'); if (text) { l.textContent = text; l.classList.add('on'); } else l.classList.remove('on'); },
  clear() { look.set(''); },
};

// ── THE END CARD. end.show({ title, text, stats: [...], mood, links: [{text, href}], onAgain }) ──
export const end = {
  show(o = {}) {
    const e = el('fs-end', 'fs-end', '<div class="card"><h2></h2><p></p><div class="stats"></div><div class="acts"></div></div>');
    if (o.mood) e.dataset.mood = o.mood;
    e.querySelector('h2').textContent = o.title || '';
    e.querySelector('p').textContent = voice.clean(o.text || '');
    e.querySelector('.stats').innerHTML = (o.stats || []).map(s => '<span class="stat"></span>').join('');
    [...e.querySelectorAll('.stat')].forEach((s, k) => { s.textContent = o.stats[k]; });
    const acts = e.querySelector('.acts'); acts.innerHTML = '';
    for (const l of (o.links || [])) { const a = document.createElement('a'); a.textContent = l.text; a.href = l.href; acts.appendChild(a); }
    if (o.onAgain) { const b = document.createElement('button'); b.textContent = o.again || 'play again'; b.addEventListener('click', o.onAgain); acts.appendChild(b); }
    e.classList.add('on');
    return e;
  },
  hide() { const e = document.getElementById('fs-end'); if (e) e.classList.remove('on'); },
};

// ── THE FOREMAN. One step at a time; each clears on the thing itself. ───────
//
//   const f = new Foreman([
//     { title: 'Look around', text: 'Move the mouse to look. W, A, S and D walk.',
//       why: 'This is the whole track.', check: () => moved > 3, mark: () => tilePos },
//     ...
//   ], { name: 'the foreman', onStep: (k, step) => {}, onDone: () => {},
//        onMark: (pos|null) => {} /* draw a ring where the step means */,
//        save: (k) => {}, load: () => k });
//   f.start(k = 0);  f.tick(dt) every frame;  Enter -> f.next(), G -> f.skip()
//
// The card says what to do, why, and the keys. A step with `gotit: true`
// waits for Enter or the card's own control rather than a check.
export class Foreman {
  constructor(steps, opts = {}) {
    this.steps = steps; this.opts = opts; this.k = -1; this.clock = 0; this.done = false;
    this.name = opts.name || 'the foreman';
    this._keys = (e) => {
      if (!this.active) return;
      if (e.code === 'Enter') { e.preventDefault(); this.next(); }
      else if (e.code === 'KeyG') { this.skip(); }
    };
    addEventListener('keydown', this._keys);
  }
  get active() { return this.k >= 0 && this.k < this.steps.length && !this.done; }
  get step() { return this.active ? this.steps[this.k] : null; }
  start(k = 0) {
    this.done = false; this.k = Math.max(0, Math.min(this.steps.length - 1, k)); this.clock = 0;
    if (this.opts.onStep) this.opts.onStep(this.k, this.steps[this.k]);
    if (this.opts.save) this.opts.save(this.k);
    this.render();
  }
  next() { if (!this.active) return; this.k++; if (this.k >= this.steps.length) return this.finish(); this.clock = 0;
           if (this.opts.onStep) this.opts.onStep(this.k, this.steps[this.k]); if (this.opts.save) this.opts.save(this.k); this.render(); }
  skip() { if (!this.active) return; this.finish(true); }
  finish(skipped) {
    this.done = true; this.k = this.steps.length;
    const c = document.getElementById('fs-card'); if (c) c.classList.remove('on');
    if (this.opts.onMark) this.opts.onMark(null);
    if (this.opts.save) this.opts.save(this.k);
    if (this.opts.onDone) this.opts.onDone(!!skipped);
  }
  tick(dt) {
    if (!this.active) return;
    this.clock += dt;
    if (this.clock < 0.25) return;
    this.clock = 0;
    const s = this.steps[this.k];
    if (this.opts.onMark) this.opts.onMark(s.mark ? s.mark() : null);
    if (!s.gotit && s.check && s.check()) this.next();
  }
  render() {
    const s = this.step; if (!s) return;
    const c = el('fs-card', 'fs-card', '<em></em><b></b><small></small><p></p><span class="next">next step</span><span class="skip">skip the guide</span><i class="keys"></i>');
    c.querySelector('em').textContent = this.name + '  ·  ' + (this.k + 1) + ' / ' + this.steps.length;
    c.querySelector('b').textContent = s.title;
    c.querySelector('small').textContent = voice.clean(s.text);
    c.querySelector('p').textContent = voice.clean(s.why || '');
    c.querySelector('.keys').textContent = 'Enter: next step  ·  G: skip the guide' + (s.keys ? '  ·  ' + s.keys : '');
    c.querySelector('.next').onclick = (e) => { e.stopPropagation(); this.next(); };
    c.querySelector('.skip').onclick = (e) => { e.stopPropagation(); this.skip(); };
    c.classList.add('on');
  }
}

// ── THE MOOD. The same four families the factory uses, from a prompt's own
// words, so any runtime can pick a voice for its title and chrome. ─────────
export const MOODS = [
  { id: 'warm', words: /\b(red|rust|rusted|ember|cinder|lava|magma|volcan|scorch|burn|fire|ash|crimson|copper|desert|sun-?baked|inferno|forge|neon|tokyo|night ?city)\w*/i },
  { id: 'cold', words: /\b(ice|icy|frost|frozen|snow|glacier|arctic|tundra|winter|polar|blizzard|cryo|white|moon(?:lit)?)\w*/i },
  { id: 'green', words: /\b(jungle|forest|moss|verdant|overgrown|swamp|fungal|spore|garden|bloom|vine|toxic|acid|meadow)\w*/i },
];
export function moodOf(text) { return (MOODS.find(m => m.words.test(text || '')) || { id: 'void' }).id; }
export function setMood(mood) { document.body.dataset.mood = mood || 'void'; }

// ── THE MUSIC BED. Generative, per family, no assets. ───────────────────────
//
//   const bed = new Bed(ctx, masterGain);   // after the user's first gesture
//   bed.family('cold');                      // void | warm | cold | green
//   bed.step(dt);                            // every frame
//   bed.on = false;                          // fades out; true fades back
//
// A pad of four voices moving through a progression on a slow clock, and a
// sparse high line over it, through one lowpass and one feedback echo. Room
// tone, not a soundtrack: quiet enough to be missed and heard when it stops.
export const BED_KEYS = {
  //         root      mode (semitones)          progression (degrees, 4 voices)                       hold  sparkle gap  wave        cutoff level high
  void:  { root: 220.0, mode: [0, 2, 4, 6, 7, 9, 11], prog: [[0, 2, 4, 6], [3, 5, 0, 2], [4, 6, 1, 3], [1, 3, 5, 0]], hold: 11, gap: [2.2, 5.5], wave: 'triangle', cut: 900,  level: 0.11, high: 2 },
  warm:  { root: 164.8, mode: [0, 2, 3, 5, 7, 9, 10], prog: [[0, 2, 4, 6], [5, 0, 2, 4], [3, 5, 0, 2], [4, 6, 1, 3]], hold: 13, gap: [4.0, 9.0], wave: 'sawtooth', cut: 520,  level: 0.08, high: 1 },
  cold:  { root: 261.6, mode: [0, 2, 4, 5, 7, 9, 11], prog: [[0, 2, 4, 5], [3, 5, 0, 2], [1, 3, 5, 0], [4, 6, 1, 3]], hold: 12, gap: [1.6, 4.0], wave: 'sine',     cut: 1400, level: 0.10, high: 3 },
  green: { root: 196.0, mode: [0, 2, 4, 7, 9],        prog: [[0, 1, 2, 3], [1, 2, 3, 4], [2, 3, 4, 0], [3, 4, 0, 1]], hold: 10, gap: [1.2, 3.2], wave: 'triangle', cut: 1100, level: 0.10, high: 2 },
};
export function bedNote(key, deg, oct) {
  const m = key.mode, o = Math.floor(deg / m.length) + (oct || 0), d = ((deg % m.length) + m.length) % m.length;
  return key.root * Math.pow(2, o + m[d] / 12);
}
export class Bed {
  constructor(ctx, master) {
    this.ctx = ctx; this.fam = 'void'; this.chord = -1; this.next = 0; this.gap = 1.5; this._on = true;
    this.gain = ctx.createGain(); this.gain.gain.value = 0;
    this.lp = ctx.createBiquadFilter(); this.lp.type = 'lowpass'; this.lp.frequency.value = 900; this.lp.Q.value = 0.4;
    // one echo for the whole bed: a fifth of a second, feeding a third back
    this.delay = ctx.createDelay(1.0); this.delay.delayTime.value = 0.42;
    const fb = ctx.createGain(); fb.gain.value = 0.34;
    const wet = ctx.createGain(); wet.gain.value = 0.35;
    this.delay.connect(fb); fb.connect(this.delay); this.lp.connect(this.delay); this.delay.connect(wet); wet.connect(this.gain);
    this.lp.connect(this.gain); this.gain.connect(master);
    this.voices = [];
    for (let v = 0; v < 4; v++) {
      const o = ctx.createOscillator(), g = ctx.createGain(); g.gain.value = 0;
      o.type = 'triangle'; o.frequency.value = 220; o.detune.value = (v - 1.5) * 6;   // a little apart: a pad, not an organ
      o.connect(g); g.connect(this.lp); o.start();
      this.voices.push({ o, g });
    }
  }
  get key() { return BED_KEYS[this.fam] || BED_KEYS.void; }
  get on() { return this._on; }
  set on(v) { this._on = !!v; this.gain.gain.setTargetAtTime(this._on ? this.key.level : 0, this.ctx.currentTime, 1.2); }
  family(fam, slow) {
    this.fam = BED_KEYS[fam] ? fam : 'void';
    const t = this.ctx.currentTime;
    this.lp.frequency.setTargetAtTime(this.key.cut, t, 1.5);
    for (const v of this.voices) v.o.type = this.key.wave;
    this.chord = -1; this.next = 0; this.gap = 1.5;
    this.gain.gain.setTargetAtTime(this._on ? this.key.level : 0, t, slow ? 2.5 : 1.0);
  }
  step(dt) {
    const key = this.key, t = this.ctx.currentTime;
    this.next -= dt;
    if (this.next <= 0) {
      this.chord = (this.chord + 1) % key.prog.length;
      const degs = key.prog[this.chord];
      this.voices.forEach((v, i) => {
        const hz = bedNote(key, degs[i], i === 3 ? 1 : 0);
        v.g.gain.setTargetAtTime(0, t, 0.3);               // the old note falls
        v.o.frequency.setTargetAtTime(hz, t + 1.1, 0.3);   // the move happens under near silence
        v.g.gain.setTargetAtTime(0.22, t + 1.5, 1.4);      // and the new one swells
      });
      this.next = key.hold + Math.random() * 2;
    }
    this.gap -= dt;
    if (this.gap <= 0) {
      // a note of the current chord, high: a bell with a long fall through the echo
      const degs = key.prog[Math.max(0, this.chord)];
      const hz = bedNote(key, degs[Math.floor(Math.random() * degs.length)], key.high);
      const o = this.ctx.createOscillator(), g = this.ctx.createGain();
      o.type = 'sine'; o.frequency.value = hz;
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.16, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0006, t + 2.4);
      o.connect(g); g.connect(this.lp); o.start(t); o.stop(t + 2.5);
      this.gap = key.gap[0] + Math.random() * (key.gap[1] - key.gap[0]);
    }
  }
}
