# img2threejs pilot verdict — classic white roadster (2026-08-30)

One reference image (our own SDXL render, seed 77) through the full
img2threejs staged pipeline: intake → suitability → detail inventory →
strict-validated ObjectSculptSpec (26 components, 8 evidence-backed
materials) → sculpted three.js module → screenshot-review loop → credited
blockout pass. Every gate ran through the skill's own forge tooling with our
venv Python; no cloud calls anywhere.

## The four questions the pilot existed to answer

**1. Does it need a cloud LLM?** No. The "intelligence loop" IS the coding
agent — the repo is a methodology (staged gates, deterministic validators,
a state machine) around agent vision and agent-written code. Apache-2.0,
stdlib-only tooling. Fits the hard constraint exactly.

**2. Does the quality discipline transfer?** Yes, and it is the real prize.
The strict validator encodes three.js at the shader level — it caught that
sheen without sheenColor multiplies by black, computed the 5.8% sheen
energy-compensation darkening and demanded the base color be pre-brightened
1.062x, and refused a blockout without a map-stripped unlit render. The
review ledger refused "looks good" without a comparison sheet and per-layer
scores. This is the verification culture this project already believes in,
mechanized.

**3. Can it produce articulated vehicles?** Yes — the deliverable proves it.
`roadster.js` exposes named `wheel-FL-steer` / `wheel-FR-steer` yaw pivots
and per-wheel spin groups plus a `userData.drive` API; the steered capture
shows the front wheel turned against a straight rear. This is the contract
our buildCar() never had, and it is what "wheels that actually steer" costs:
a hierarchy decision at sculpt time, not a retrofit.

**4. What does one asset cost?** ~2.5 hours of agent loop for spec + gates +
five correction renders, on top of one 28s SDXL reference. The correction
loop converged fast because every failure was VISIBLE: black chrome (no env
map), buried lamps, out-of-plane spoke fans, nose-at-lens camera. Renders
p1→p6 in evidence/ tell the whole story.

## Honest state

- Blockout pass CREDITED in the pipeline (fidelity 0.72, layer scores in the
  ledger). Seven refinement passes remain unrun — deliberate pilot cutoff,
  not a blocker; each is the same loop with a tighter bar.
- Known deviations, all declared: inferred rear fascia, simplified
  windscreen, soft-top rear extrude seam, chrome surround under-reads.
- Upstream patch required (img2threejs_material_physics.patch): strict mode
  had an unsatisfiable triangle for family=fabric (fabric requires sheen ->
  sheen requires sheenColor -> the pair always warns). Our checkout drops
  the wrong pair-rule and honors a sheenEnergyCompensated declaration. PR
  candidate for the upstream repo.
- Tooling footguns hit: append_review silently discards without --in-place;
  next.py/state.py disagree briefly after batch marks; validator layer-score
  keys are undocumented until they fail. All survivable.

## Integration plan (next sessions)

1. Runtime loader for sculpted modules: a `proc:` asset scheme in the spec
   (`asset: "proc:roadster"`) that imports the module instead of a GLB, and
   drives `userData.drive.setSteer/spin` from the existing vSpeed/steer
   state. The engine finally gets rolling, steering wheels on the hero car.
2. Quality bar adoption independent of img2threejs: map-stripped renders and
   comparison sheets belong in shotgate for OUR generated assets too.
3. Hero-vehicle lane: one sculpted vehicle per style family (taxi, muscle,
   van) replacing the generated GLB for close-camera use; the GLB fleet
   stays for traffic.

View: open viewer.html beside a vendor/ copied from any built game's dist
(same importmap pattern as carlab), or run shot.mjs for headless captures.
