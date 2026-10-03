# LOCOMOTION: reference numbers for animators and procedural-animation code

Numbers marked "typical" are ranges from published normal-adult or normal-animal data, not fixed constants. Sources are linked inline.

## 1. The human walk and run

**Gait cycle.** One stride = heel strike to the next heel strike of the same foot. Stance is about 60% and swing 40%; stance splits into initial double support (10%), single support (40%) and terminal double support (10%), so both feet are down for 20% of every stride ([Wikipedia](https://en.wikipedia.org/wiki/Bipedal_gait_cycle)); Perry gives 62/38 at 82 m/min ([Hersco](https://hersco.com/education-center/gait-cycle-1/)). Sub-phases: loading 0-12%, midstance 12-31%, terminal stance 31-50%, pre-swing 50-62% (toe-off about 60%), then initial, mid and terminal swing at 62-75, 75-87, 87-100% ([ProtoKinetics](https://protokinetics.com/understanding-phases-of-the-gait-cycle/)).

**Cadence, speed, step length.** Normal cadence 100-115 steps/min, comfortable speed about 80 m/min (1.33 m/s) ([Wikipedia](https://en.wikipedia.org/wiki/Bipedal_gait_cycle)); derived step length 0.70-0.75 m, stride 1.4-1.5 m, cycle 1.05-1.2 s. Animators walk "on 12s", one step per 12 frames at 24 fps, or 120 steps/min ([AnimSchool](https://blog.animschool.edu/2024/03/14/walk-cycle-animation-tips/); Williams, *The Animator's Survival Kit*).

**Centre of mass.** Vertical excursion rises with speed from 2.7 cm (slow) to 4.8 cm (fast); lateral falls from 7.0 cm to 3.9 cm ([Orendurff et al. 2004](https://pubmed.ncbi.nlm.nih.gov/15685471/)). Vertical is twice per stride (lowest at double support, highest at midstance); lateral once per stride toward the stance leg.

**Pelvis and trunk.** The pelvis rotates about 4 degrees forward on the swing side and 4 back on the stance side (8 total) and drops about 5 degrees on the swing side; the stance knee flexes 15-20 degrees at foot flat ([Podiapaedia](https://podiapaedia.org/wiki/biomechanics/gait/determinants-of-gait/)). The thorax counter-rotates: thorax-pelvis relative phase is about -20 degrees at 1 km/h and about -150 degrees (nearly opposite) at 5.4 km/h, with axial amplitudes of only 3-8 degrees ([Sci Rep 2019](https://www.nature.com/articles/s41598-018-37549-9); [Gait & Posture](https://www.sciencedirect.com/science/article/abs/pii/S0966636201001461)).

**Arm swing.** Each arm swings opposite its own leg, in phase with the other leg; arm-to-step frequency is 1:1 above about 0.8 m/s, 2:1 below ([Wikipedia](https://en.wikipedia.org/wiki/Arm_swing_in_human_locomotion)). Holding the arms still costs 12% more energy; wrong-phase swing costs 26% more ([Collins, Adamczyk, Kuo 2009](https://pubmed.ncbi.nlm.nih.gov/19640879/)). At 1.11 m/s young adults sweep the shoulder about 56 degrees total (roughly +/-28), abduct-adduct only about 20 degrees total (arms hang against the torso), and flex-extend the elbow about 30 degrees ([Kim et al. 2023](https://www.cisejournal.org/journal/view.php?doi=10.5397%2Fcise.2023.00101)); older adults sweep less, about 21 degrees extension and 11 flexion ([PMC10648336](https://pmc.ncbi.nlm.nih.gov/articles/PMC10648336/)). Typical: +/-20 to 30 degrees at the shoulder, extension larger than flexion, elbow always bent 20-45 degrees and flexing more on the forward swing; amplitude grows with speed ([Hejrati et al. 2016](https://www.sciencedirect.com/science/article/abs/pii/S016794571630077X)).

**Head.** Up to 1.2 m/s the head barely pitches in space; vertical head oscillation runs 1.4-2.5 Hz over 0.6-2.2 m/s, and acceleration is attenuated pelvis to sternum to head ([Hirasaki et al. 1999](https://pubmed.ncbi.nlm.nih.gov/10442403/); [Kavanagh et al.](https://link.springer.com/article/10.1007/s00421-005-1328-1)). Keep the head level and let the body move under it.

**Feet.** Heel strikes first; the foot rolls to toe-off near 60%. Minimum toe clearance at 40-50% of swing is only 1-2.5 cm ([Sci Rep 2017](https://www.nature.com/articles/s41598-017-02189-y)), about 5.5 cm with a toe marker ([J Gerontol 2024](https://academic.oup.com/biomedgerontology/article/79/7/glae109/7658560)). Feet track slightly toed-out on a narrow base.

**Run.** Stance alternates with flight; running has no double support ([Wikipedia, Running](https://en.wikipedia.org/wiki/Running)). Cadence is 150-170 steps/min for recreational runners, about 180 for elites, rarely above 200 short of sprinting ([E3 Rehab](https://e3rehab.com/running-cadence/)). Elbows about 90 degrees or less, hands from hip to mid-chest, opposite leg ([Wikipedia](https://en.wikipedia.org/wiki/Running)); sprinters open the elbow to 150-170 degrees on the down-stroke and close it to about 40 at the top ([SpeedEndurance](https://speedendurance.com/2015/06/16/elbow-action-in-sprinting-myth-vs-reality/)). About 6 degrees of trunk lean is most economical; 8 degrees costs 8% more ([PMC11135760](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11135760/)).

**Common mistakes.** Arms held out from the body (abduction beyond 10 degrees); locked elbows; arm swinging with the same-side leg; no thorax-pelvis counter-rotation; head bobbing with the pelvis; stance foot sliding (it must be pinned); missing heel strike and toe-off; both feet airborne in a walk.

## 2. Quadruped gaits

Notation: LH left hind, LF left fore, RH, RF. Duty factor > 50% is a walk, < 50% a run ([Wikipedia, Gait](https://en.wikipedia.org/wiki/Gait)).

**Walk (four-beat, lateral sequence).** LH, LF, RH, RF, evenly spaced, two or three feet always down ([Wikipedia, Horse gait](https://en.wikipedia.org/wiki/Horse_gait)); arboreal primates use diagonal sequence (LH, RF, RH, LF) ([Wikipedia, Gait](https://en.wikipedia.org/wiki/Gait)). Horse walk about 7 km/h; dogs walk up to 0.9-1.2 m/s ([Blaszczyk 2001](https://pubmed.ncbi.nlm.nih.gov/11721550/)); cats 0.5-0.75 m/s with stance 58-62% ([Frontiers Vet Sci](https://www.frontiersin.org/journals/veterinary-science/articles/10.3389/fvets.2026.1816089/full)).

**Trot (two-beat, diagonal).** LH+RF then RH+LF, brief suspension in dogs. Horse trot about 13 km/h, 1.13 strides/s ([IFCE](https://equipedia.ifce.fr/en/equipedia-the-universe-of-the-horse-ifce/equestrian-instruction-and-teaching/didactics-and-equestrian-techniques/interdisciplinary-principles/the-horses-gaits-definitions-and-figures)). Cats trot near 2.1 m/s; dogs gallop from 1.5-2.6 m/s ([Blaszczyk 2001](https://pubmed.ncbi.nlm.nih.gov/11721550/)).

**Pace (two-beat, lateral).** LH+LF then RH+RF; the body rocks side to side. Camels, giraffes, Standardbred pacers, occasionally bears ([Animator Notebook](https://www.animatornotebook.com/learn/quadrupeds-gaits)).

**Canter (three-beat plus suspension).** Right lead: LH, then RH+LF, then RF, then suspension; 16-27 km/h, stride 0.65 s; the body rocks back to front once per stride ([Wikipedia](https://en.wikipedia.org/wiki/Canter_and_gallop)).

**Gallop (four-beat, asymmetric).** Transverse (horses, most ungulates): LH, RH, LF, RF, one gathered suspension; 40-48 km/h, racing Thoroughbreds 10-18 m/s at 2.3-3.0 strides/s with 6.9-7.6 m strides ([Arioneo](https://training.arioneo.com/en/blog-specific-locomototion-characteristics-of-the-racehorse/); [PubMed 18310119](https://pubmed.ncbi.nlm.nih.gov/18310119/)). Rotary (dogs, cats, cheetah): LH, RH, suspension, RF, LF, suspension, two flight phases, gathered and extended ([Animator Notebook](https://www.animatornotebook.com/learn/quadrupeds-gaits)). Muybridge's 1887 plates first showed the gathered suspension ([Penn archives](https://archives.upenn.edu/exhibits/penn-history/muybridge/)).

**Spine.** Cheetahs at 15-18 m/s flex and extend the spine about 27 degrees per stride (0.47 rad, model fitted to measured runs) with only 5.7 cm vertical COM travel and 11.5 degrees of pitch ([Frontiers 2022](https://www.frontiersin.org/journals/bioengineering-and-biotechnology/articles/10.3389/fbioe.2022.825638/full)); greyhounds do likewise to about 70 km/h. Horse backs stay comparatively stiff; the gallop lives in limbs and neck, not a folding spine.

**Head and tail.** The horse head bobs twice per stride at walk (12-15 cm) and trot (9 cm), once per stride at canter (22-23 cm); neck angle rises from -4 degrees at walk to 23 at canter ([Dunbar et al. 2008](https://journals.biologists.com/jeb/article/211/24/3889/18018/)). Sound dogs show a slight symmetric head movement; an asymmetric nod means lameness ([Today's Vet Nurse](https://todaysveterinarynurse.com/rehabilitation/key-components-of-canine-gait-analysis-in-the-rehabilitation-exam/)). The cheetah tail swings opposite a turn as a counterbalance; the kangaroo tail counterbalances hops ([PMC4126630](https://pmc.ncbi.nlm.nih.gov/articles/PMC4126630/)).

**Limb posture.** Forelimbs hang vertically under the shoulder as a second pair of legs, never held out like arms. Plantigrade (bears, humans) walk on the sole; digitigrade (cats, dogs, birds) on the toes with the heel raised; unguligrade (horses, cattle) on hoof tips. The "backward knee" of a dog, cat, horse or bird is the ankle (hock); the true knee sits up near the body ([Wikipedia, Digitigrade](https://en.wikipedia.org/wiki/Digitigrade)). Stride frequency scales with mass^-0.15 and gait-transition speed with mass^0.2, so small animals step faster and change gait sooner ([Heglund & Taylor 1988](https://journals.biologists.com/jeb/article/138/1/301/5532/)).

## 3. Other body classes

**Birds.** Pigeons, chickens and herons bob when walking: a fast thrust, then a hold with the head fixed in space while the body catches up, one bob per step; ducks, geese and penguins do not ([Necker 2007](https://pubmed.ncbi.nlm.nih.gov/17987297/); [Bird Spot](https://www.birdspot.co.uk/bird-brain/why-do-birds-bob-their-heads-when-they-walk)). Wingbeats: pigeon about 5.5 Hz cruising ([PLOS Biol](https://journals.plos.org/plosbiology/article?id=10.1371%2Fjournal.pbio.3000299)), barn swallow 6-7 Hz, zebra finch about 27 Hz, hummingbird about 80 Hz ([JEB](https://journals.biologists.com/jeb/article/221/20/jeb178228/19706/)).

**Fish.** Body-caudal-fin swimmers: speed is about tail-beat frequency times body length (V = fL above 5 Hz, tail amplitude about one fifth of body length) ([Bainbridge 1958](https://journals.biologists.com/jeb/article/35/1/109/13233/)); a broader fit is U ~ 0.7 L f, with 0.1 to over 20 Hz and up to about 10 body lengths/s for a 1 m fish ([Nature Comms 2023](https://www.nature.com/articles/s41467-023-41368-6)).

**Snakes.** Lateral undulation: S-waves travel head to tail, every body point follows the same path, pushing off contact points; speed rises with wave frequency. Black mamba peaks at 15-20 km/h; concertina is about 0.1 body lengths/s; sidewinding superimposes two body waves 90 degrees out of phase ([Discover Wildlife](https://www.discoverwildlife.com/animal-facts/reptiles/whats-the-worlds-fastest-snake); [PNAS 2015](https://www.pnas.org/doi/10.1073/pnas.1418965112)).

**Large heavy animals.** Grizzlies walk at 1.1-2.0 m/s, running-walk at 2.0-3.0 m/s and canter above 3 m/s; they never trot and pace occasionally ([Shine et al. 2015](https://journals.biologists.com/jeb/article/218/19/3102/14189/)). Elephants keep the walking footfall order at all speeds, never leave the ground, and reach 6.8 m/s (25 km/h) with the hind limbs bouncing while the fore limbs walk ([Hutchinson et al. 2003](https://www.nature.com/articles/422493a); [Schmitt et al. 2006](https://journals.biologists.com/jeb/article/209/11/2042/16164/)).

## 4. What the engine should enforce

| Body class | Rule | Range (typical) |
|---|---|---|
| Human walk | stance / swing / double support | 60 / 40 / 2 x 10% of cycle |
| Human walk | cadence, speed, step | 100-115 steps/min, 1.2-1.4 m/s, 0.65-0.75 m |
| Human walk | shoulder swing, opposite same-side leg | +/-20 to 30 deg sagittal |
| Human walk | shoulder abduction | <= 10 deg (arms against torso) |
| Human walk | elbow flexion | 20-45 deg, never 0 |
| Human walk | pelvic rotation / list | +/-4 deg / 5 deg drop on swing side |
| Human walk | thorax vs pelvis | counter-rotate, 3-8 deg amplitude |
| Human walk | COM vertical / lateral | 3-5 cm (2 per stride) / 4-7 cm (1 per stride) |
| Human walk | head pitch, foot clearance | near 0 deg; 1-3 cm at mid-swing; stance foot pinned |
| Human run | flight phase, cadence, elbow, lean | 2 per stride; 150-190 steps/min; ~90 deg; 5-8 deg |
| Quadruped walk | footfall order | LH, LF, RH, RF, evenly spaced, 2-3 feet down |
| Quadruped trot | diagonal pairs | LH+RF, RH+LF, 2 beats |
| Quadruped pace | lateral pairs (camel, giraffe) | LH+LF, RH+RF, 2 beats |
| Canter | 3 beats + 1 suspension | hind, diagonal pair, lead fore |
| Gallop, ungulate | transverse, 1 gathered suspension | 2.3-3.0 strides/s at speed, stiff spine |
| Gallop, carnivore | rotary, 2 suspensions | spine flex/extend ~25-30 deg |
| Quadruped limbs | forelimbs vertical under shoulder; hock = ankle | knee near body |
| Bird walk | head thrust then hold, 1 per step | head fixed in space during hold |
| Fish | tail beat vs speed | V ~ 0.7-1.0 x L x f, amplitude ~0.2 L |
| Elephant | no aerial phase, walk order at all speeds | <= 6.8 m/s |
| Bear | plantigrade, walk / running walk / canter, no trot | transitions 2.0 and 3.0 m/s |

## 5. How the runtime applies this (proc/gait.js, 2026-10-02)

| Problem found by filming | What the gait engine does |
|---|---|
| a baked clip holds 1.7 cycles, so the loop pops mid-stride | autocorrelates the thighs' left-minus-right swing to find the true period and plays one whole cycle |
| walk and run blended on separate clocks | one gait phase drives both, aligned on left-foot contact (a sync group) |
| speed matched by play rate alone | play rate takes the square root of the speed ratio, clamped to 0.72-1.45; stride warping (two-bone leg IK along travel) takes the rest, up to 1.95 |
| a walk clip used at jogging speed | the clip follows speed: past 1.2x the walk's natural pace the body breaks into the jog |
| arms swing only behind the body | each upper arm aimed in the sagittal plane at the opposite thigh's angle, abduction capped near 10 degrees, elbow 20-45 deg walking and ~90 running; a hand holding something swings at 40% |
| trunk reclined in the jog clip | the trunk's lean is measured (head over hips, averaged ~0.5 s) and corrected to 1.5-6 degrees forward; the head is counter-rotated to stay level |
| a rig whose legs walk against its travel | the clip's forward is read from the planted foot's motion; a body carried against it for a third of a second turns round once |

Measure with `tools/shotgate/gaitlab.mjs` (J=<job> OUT=<dir>): planted-foot slide as a share of body speed (healthy under ~0.3), pelvis ride, trunk lean, stop glide.

## 6. Retarget by rotation, and let the mocap carry the body (2026-10-03)

The owner's verdict on section 5: too much lean, the knight's arms inverted,
still robotic. Research into how shipped games do it (Clavet/Zadziuk GDC 2016
motion matching, UE5 Pose Search and stride warping, Holden's MIT
Motion-Matching reference, Bollo's inertialization) agreed on one point: good
mocap carries the arms, trunk and head itself, and procedural layers only add
what a looping clip cannot know. The overrides in section 5 existed because
the old retarget lost that motion. What changed:

| Problem | Fix |
|---|---|
| the aim retarget pointed each bone at the source joint and lost the bone's twist and the body's carriage | `retarget_rot.py`: rotation transfer. Each target bone's world rotation is the source's, re-expressed through the minimal arc between their rest directions: W_t = W_s (C R_s)^-1 R_t. Bone directions match the source exactly and the twist is kept. Now the default; `FS_RETARGET=aim` restores the old path |
| the knight's legs were 49 cm long with his ankles at knee height | `retopo.py` restored the mesh from a copy taken before the object's scale was applied, so any retry (here the solidify path) brought the body back at import size: 58% tall, centred on the waist, and rigged that way. The copy now takes the same transform. The knight was never facing backward: the shrunken body fooled the toe test |
| a rig facing the wrong way walks its clips backwards (knees and elbows bend the wrong way round) | the retarget turns the source onto the mesh's own front: the rigger's toe-against-heel reading about the shank centre when it is clear (ratio over 1.5), the toe reach about the ankle otherwise |
| the idle (CMU 140_06) is a crouch, knees 57 deg and trunk 33 deg, which the aim retarget hid by never driving legs or spine | the idle is 100STYLE Neutral_ID (CC BY 4.0), its still standing stretch (knees 2 deg, trunk 1 deg), 5 s with the first half-second crossfaded from the frames after the slice so it loops without a pop |
| the pelvis was held at standing height (+-8 cm), so the sneak floated 30 cm off the floor | the source pelvis height above its planted ankles sets ours, then the lowest ankle is placed exactly where the source's is above its ground: walk, idle and sneak plant at rest foot height, the run keeps its flight |
| 'too much lean', 'robotic' | gait.js no longer corrects the trunk, levels the head or drives the arms. It adds a lean into acceleration and a bank into turns, each 0.4*atan(a/g), a few degrees at most |
| stride warp up to 1.95 turned a walk into a different, wrong gait | warp limited to 0.8-1.4; cadence takes up to 1.5x on a run; past both, the foot lock holds the planted foot |

Measured on the ranger (rotation transfer): walk knees 14-72 deg over the
cycle, trunk 3-5 deg; idle knees 2-6 deg, trunk 1-3 deg; sneak pelvis
0.68-0.74 m against 0.875 standing, lowest ankle at rest height throughout.
Tools: `tools/shotgate/cliplab.html` (a rig's clips as frame strips) and
`tools/shotgate/clipmeasure.mjs` (knee angles, trunk tilt, foot contact per clip).

Next: motion matching over the 100STYLE Neutral takes (forward, backward and
sidestep walks and runs, which include curved paths) so turns, starts and
stops come from real motion rather than one looping cycle, with inertialized
transitions instead of crossfades.

## 7. Motion matching (2026-10-03)

The hero no longer plays one walk loop and one run loop. `runtime/proc/mm.js`
plays real captured locomotion out of one shared database and chooses where
to play from ten times a second, the method Clavet and Zadziuk introduced at
GDC 2016 and Fortnite and The Last of Us ship; the implementation follows
Daniel Holden's MIT reference (orangeduck/Motion-Matching).

**The database** (`tools/mmdb.py` -> `assets/mocap/mm/mm_db.bin`, 5.7 MB,
26,638 frames = 14.8 minutes at 30 fps with every take mirrored): 117 takes
from CMU (163 downloaded into `assets/mocap/_cmu_src`, ignored by git) and
100STYLE: straight runs, jogs and sprints up to 7.8 m/s (subjects 9, 16, 35,
127, 141, 143), running turns and veers, starts and stops (16, 104, 127, 128,
131, 133, 134, 143), walking turns and turning on the spot (16, 36, 69, 83),
backpedal and sidestep, the 100STYLE standing idle, walk, jog, backward and
sidestep. Per frame: 19 bone rotations against one canonical T-pose (so
skeletons from different capture rigs share one rest pose), the hips over the
root, and Holden's 27 features (both ankles' positions and velocities, the
hips' velocity, the root's position and facing 1/3, 2/3 and 1 s ahead).

**The runtime:** the controller's velocity eases as a vector (so a change of
direction is an arc a person could run) and its future is predicted with the
same spring; the query is the playing frame's pose features plus that future;
a brute-force search over all frames takes under 1 ms. A jump needs a clear
margin (cost under 0.85 x the current) and is inertialized: the difference
between the last pose shown and the new one decays with a 0.1 s half-life.
The pose goes onto each rig by rotation transfer, calibrated once per rig from
its bind pose. gait.js keeps the foot locks and slope IK on top; its lean and
bank are off while motion matching drives (the capture already leans). An
attack clip takes the bones with a blend in and out; sneak, swim, fly and
drive keep the clip blend. `?mm=0` turns it off; `window.__mm()` reports the
take playing, its rate, jumps and search time.

**Lessons:**
- CMU takes are 1 to 2 s long. A future clamped at a take's last frame reads
  as a stop, so short sprints never matched running on; the builder carries
  the root past the end at its last velocity instead.
- A capture skeleton's rest is a T-pose, not a stance: CMU's upper spine
  rests ~10 degrees behind a natural back (a walk read 9-17 degrees of chest
  pitch), its collarbones 16-38 degrees up (an 18 degree shrug), 100STYLE's
  neck bent back (a relaxed head read 25-38 degrees down). The torso bones
  (hips to head, collarbones) are re-referenced to each ACTOR's own average
  standing pose (the dataset's where an actor never stood still), so only
  the lean away from standing transfers: standing -2, walking ~2, a 6.4 m/s
  run 7-8 degrees (the 5-8 a run should have). CMU 133's stooped walk is
  left out.
- Holden's character is carried by its animation, so the playing frame's hip
  velocity is the body's; here the game carries the body, and the query's
  hip velocity must be the body's real velocity, or a run start's pace
  persists while the hero strolls.
- The hero accelerated at ~8 m/s^2 (a sprint start), so jog-offs matched
  sprint starts leaning 30 degrees; the walk eases at 7/s up, 10/s down.
- Measure at the rig's true size: a lab rig built 1 m tall moving at a
  human's 2.4 m/s is, for its legs, running at 4.5 m/s.
- Pops are measured relative to the body (`mmlab.html`): the largest per-frame
  limb turn in each phase stays within that motion's own range.

Measured in the game (ranger, gaitlab): planted-foot slide 0.04-0.06 of body
speed at a 6.4 m/s run (was 0.06-0.31 with the clip loops). Tools:
`tools/shotgate/mmlab.html` (a scripted session through the matcher, frames
and numbers) and `tools/mmdb.py --list`.
