# Crystal Works / Voxel Forge — roadmap

Working notes on the five differentiators from the Voxel Forge brief, ordered
by *value per unit of risk* rather than by the order they were written. Each
one is judged on the same two questions: does it make a five-second video
someone stops scrolling for, and can it be built without destabilising what
already works.

Nothing here is a promise. Where I think an idea is weaker than it sounds, it
says so.

---

## Shipped

| | what it proves |
|---|---|
| grid + tick + belts | the loop: mine, move, deliver |
| first person | standing in a factory beats arranging one |
| smelter | belts solve "these must meet", not just "that is far" |
| splitter | routing becomes a decision, not a drawing |
| upgrades | the number climbs, and spending it makes it climb faster |
| **built by the studio** | a prompt produces this game, not a hand-run file |
| **multi-sided gravity grid** | the differentiator: belts and gravity wrap a cube |
| **prestige meltdown** | the factory is thrown into the sky for a permanent core |
| **three minerals + forge** | an alloy no single face can make: a reason to cross |
| **filter tile** | routing by ore type, configured from the crosshair |
| **market ticker** | the hub pays a live price, so what to make is a decision |
| **chronos rift** | borrowed ore on a clock, and a storm if you miss it |
| **studio inspect** | the factory answers the studio's picking bridge |
| **demo is generated** | the standalone build IS the studio's output |
| **save / load** | a factory survives closing the tab |
| **collision + fair mergers** | machines are solid; a merge stopped eating items |
| **progression frame** | goals unlock machines in the order that teaches them |
| **art pass** | conveyors that convey, icons in the bar, a sky to float in |
| **lighting pass** | bloom, a graded composite, particles, a lit silhouette |
| **grounding pass** | real cast shadows, contact shadows, curved belt corners |
| **material pass** | an environment to reflect, baked occlusion, rim light, detail |
| **UI pass** | tool icons that ARE the machines, rendered at boot |
| **presence pass** | a tool in your hands, jams that read, seams that flex, one HUD |
| **depletion** | seams thin under a rig and grow back, so placement is a decision |
| **the reveal** | the worldlet shown before control is handed over; again on arrival |
| **weather** | ash on Ember, snow on Frostline, spores on Verdant, dust at home |
| **sound** | six synthesised layers, no assets; wakes on the first click, M mutes |
| **the panel** | read by shape: a hero number, a sparkline, icon chips, bars, pips |
| **the world, finished** | the meltdown pulls to orbit; hubs carry the price board; each world has its own ground |
| **refinements** | prices read from a 1.0 baseline; belts belong to their world; a title with weight; idle motion |
| **the prompt's mood** | world zero reads its own words when no palette was committed; unlocks are the families home is not |
| **unlockable worlds** | four places to put the factory, bought with cores |
| **the chain, twelve deep** | rates are HELD, not reached; rewards are machines, caps, or capabilities, derived from the tier on load |
| **capabilities** | Frostline needs the heated drill, Verdant the spore scrubber, the Drift the whole chain; cores only buy the trip |
| **creative** | chosen at world creation (`?creative=1`, or "new world"); its own save; all open, free, nothing runs out |
| **spores** | Verdant's pressure: an unfiltered belt clogs every few seconds; a filter within 3 tiles shields the belts around it |
| **the machine skin** | one shared panel map (seams, rivets, wear) on every machine; glow moved to the lamps; the sun made the key |
| **the companion** | a planet or moon in every sky, cratered or banded by hash noise, lit from the sun's side, drawn in the sky shader |
| **lanes** | every fifth grid line is a lit strip in the world's edge colour, one instanced mesh for six faces |
| **seams are lights** | each seam owns its glow: a dark-glass body, an additive core and a pool on the ground that all follow its richness |
| **items** | ore is a two-crystal chunk that spins; a refined product is a chamfered, stamped, metallic bar lying flat along its belt; the glow follows the instance colour |
| **particles** | smoke has a seeded lobed edge and dims as it swells; sparks carry a gravity along their face, arc, and cool white to red |
| **frames, finished** | the forge, splitter and filter get the cap, posts, bands and lips the smelter, rig and hub got |
| **the ghost is the machine** | the placement preview is the machine's own silhouette with a lit edge, green where it can go and red where it cannot |
| **lamps light the ground** | every lit lamp pools its light on the deck: orange under a cooking smelter, pink under a forge, gold breathing under a hub, the ore's colour under an open rift |
| **worlds show their sky** | each world row carries a swatch of its sky and edge colour; locked rows are dimmer places |
| **the grade** | a lift / gamma / gain curve and a saturation per mood in the composite, so the same furnace reads as a different object on each world |
| **the handover** | the reveal eases position and orientation into the first-person pose over its last fifth instead of cutting |
| **sound for the light** | a rig ticks per crystal pitched by the ore, a smelter clanks as an ingot leaves, a spore strike thuds; all throttled |
| **shadows that reach** | the contact ramp holds to a tile out and the decals are a fifth wider, so an unlit face grounds its machines at any grid size |
| **a palette that agrees** | a committed palette's sky and fog win only when they belong to the prompt's own family; the mood's win otherwise |
| **weight** | the body lags the intent: the camera leans into starts and out of stops, dips on a landing by how hard it was, and rolls an edge crossing with weight |
| **ambience** | a second layer in the air per family: motes in the light at home, embers off the cinder, breath on the ice, fireflies over the green |
| **a character is solid** | a generated body arrives with alphaMode BLEND and a nearly-solid alpha channel, so the camera saw through the odd patch of cheek into the inside of the head; every character is made opaque on the way out |
| **normals from the shape** | generated meshes ship normals that disagree with their own triangles, and each one caught the light as a bright speck that the derived relief map then baked in twice; every vertex normal is recomputed from the triangles, welded across the UV seams |
| **gutters filled** | an atlas is islands with bare black between them, and every mip level averaged that black into each island's edge; the empty band around each island is flooded with its colour before the relief map is derived from it |
| **the surface is kept** | a rebuilt hull cost a face at any voxel size that could bridge a collar, so a body whose island already carries it keeps its own geometry and the exact UVs the reference produced; loose scraps, the layers underneath, and the small patches that are the wrong colour for where they sit are cut away instead |
| **the overhead** | TAB opens over the face you stand on with your heading up the screen; the tread glows and every machine pools its colour, a city at night |
| **a title in each voice** | the reveal card's face, tracking, glow and rules follow the world's family: heavy and hot on the cinder, light and wide on the ice, italic serif on the green |
| **the projector reacts** | recoils on a place with a white flash, red on an erase, spins the new hologram up from small on a switch |
| **the crossing's ceremony** | an edge widens the view for a beat, bites the vignette, lands a low whoomp, and captions the face and the ore it grows |
| **reduced motion** | the system preference, `?motion=0`, or the panel toggle stills bob, lean, dip, pulses and the title's settle, and plays the reveal as a card over your own view |
| **ores by shape** | crystal octahedra, ember blocks, salt plates, in the seam and on the belt; a clogged belt keeps puffing so a clog and a jam differ by motion |
| **the tier** | `?q=ultra/balanced/performance` scales pixel ratio, shadows, the post's resolution and the particle budget together; steps down once on its own if frames drop |
| **the meltdown's ceremony** | a white flash that decays, a shockwave across the face from where the factory stood, shake on the shot, a bass thump, the core counter pops |
| **a floor under dark plating** | the bounce scales with how dark a world's plate is, soot is a shade lighter, the contact ramp holds longer; the warm underside grounds at 11 where it read 2 |
| **icons through the grade** | the tool bar's renders take the world's lift, gamma, gain and saturation, and are re-rendered when you travel |
| **photo mode** | P hides the chrome and leaves you free to frame; Enter saves a PNG named for the world and tells the studio; P restores |
| **the studio's first run** | a factory job opens under a card naming the world, the mode and the six things to know, once per job; the latest saved frame shows as a chip under the frame |
| **the fill is the world's** | the far-quadrant fill takes a lifted edge colour and the same floor as the bounce, so a red soot plate reflects it; `?world=k` lets a gate measure any world's light |
| **ice** | on a cold world an unheated seam freezes over every few seconds and its rig scrapes at half the floor; a smelter or forge within 3 tiles is heat and melts what it reaches three times faster; the heated drill ignores ice |
| **the Long Drift's rule** | seams do not grow back there and a meltdown pays double: the last place is finite and it is where the cores are |
| **a link that carries a factory** | "share link" copies a URL with the whole save in it; opening it starts that factory and drops the parameter; the studio is told |
| **shared factories in the studio** | a share link arrives with a thumbnail, world, mode, machines, value and rank; the studio keeps them per game as cards under the frame: open, copy, remove |
| **the foreman** | a new world opens one step at a time: look, walk to the hub, build a rig on the ringed seam, run a belt from it, finish the line, read the panel; each clears on the thing done, the step puts the tool in your hand, skippable and remembered |
| **the guide, movable** | Enter is the next step and G skips, named on the card; a restored step starts properly; "the guide" in the panel replays it |
| **credits** | the number is credits, earned by hubs selling to the market and spent on upgrades, in every place a player reads it |
| **the second act** | when the forge unlocks the foreman comes back for six steps: a rig on another face, an alloy, a filter, the overhead, a contract, a stamped blueprint; each clears on the thing itself |
| **hubs are rare** | a hub takes two items a tick and the belts feeding it back up amber past that; the first hub is free, then 200, 500, 1200, doubling, so a face has to be brought to one place; the blueprint leaves hubs out |
| **the assembler** | key Q, earned at tier seven: an alloy bar and an ingot of any kind in, one component out, worth more than both; it trades on the board and contracts ask for it |
| **far ore is worth more** | a hub pays 1.35 times for an ingot of an ore its own face does not grow, so bringing the far face home is the best trade on the board; the label says so and the first premium explains itself |
| **the overhead frees the mouse** | TAB releases the pointer lock and opens wide enough to show the whole face; the ghost follows the cursor there; caught by a played session with real input, which is now a gate |
| **the words** | a factory prompt's nouns over the same dynamics: the extractor names the resource, its kinds, the refined, combined and finished forms, the currency and each machine, and every string on screen passes through the swap; a bakery reads as a bakery and a mining outpost keeps its own words |
| **the kit** | the presentation layer as a package every runtime links: the three faces, the title card's four voices, the toast, the caption, the look label, the end card and the foreman, so a drift-racing build and a bakery arrive in the same hand |
| **three prompts, one system** | the reveal reads the sentence that made the world, in quotes; the demo ships the moon, the frost refinery and the bakery as the studio's own exports and lists them on the title card, each under its own save |
| **the sky's weather** | a nebula in every sky, filaments and dark lanes from warped ridged noise in the family's two colours, drifting so slowly you only see it standing still; the cold worlds add an aurora, a curtain on one side that is green at the foot and violet at the crown and ripples; all in the one sky draw call |
| **the music bed** | generative room tone from the kit, no assets: four pad voices through one lowpass and one echo, a progression on a slow clock, a sparse bell line over it; the void is lydian, the warm worlds dorian and low, the cold ones shimmer in fourths, the green sit in a pentatonic; it changes key when you cross to a new family, and the adventure runtime plays the same bed in the family its prompt chose |
| **the arc closes on a card** | when the works' reveal comes down the kit's end card stands: the sentence the world was made from, credits banked, contracts kept, the longest order, worlds seen, and three things to do with it: copy a share link, step into photo mode, or play on; the backdrop is play on too |
| **a nudge toward the edge** | between the foreman's acts, a player who has stayed three minutes on the face they started on is told once, in a toast, that the other five faces grow other ores and an ore from far away sells for more back home |
| **a city with no map** | a city prompt gets a district whether or not a map can be fetched: a jittered grid of avenues and streets, blocks cut into lots on both long sides, a tall core falling to low edges, plazas, and an 800 m race loop from spawn, in the same shape the real map arrives in so facades, districts, night glow and the minimap work unchanged; neon reads as light, not a pixel filter; a city's ground dressing is lamps and a few trees, not a forest floor |
| **paint, chassis, trim** | every machine in three tones instead of one: the structure is gunmetal, the panels carry the machine's colour, the parts a hand would touch are brass, baked into the vertex colours so it is still one material and one draw call; the smelter gains grilles and a band under its cap; the rim light follows the paint, so a dark chassis takes a faint grey rim and a coloured panel its own |
| **relief** | the plating and the machine skin get a normal map derived from the canvases the runtime already draws (luminance as height, a Sobel pair for slope, grain left out), so the sun rakes across seams and rivets instead of sliding over a print of them; a second pass of ground detail on its own random clock, so every layout stays what it was |
| **light from the machines** | four point lights, always in the scene so nothing recompiles, handed every quarter second to the four nearest machines at work: furnace orange from a cooking smelter, pink from a forge, gold from a hub as a sale lands, a faint wash of ore colour from a rig on a rich seam; embers drift out of a cooking smelter's door; belt rails and rollers go dark under the world's tint with stanchions at each end |
| **the starter outpost** | a place at spawn: the crew's habitat with a dome, a lit door and an aerial, two lamp masts and a stack of crates, beside the hub on the far side of the line, in the machines' own paint; scenery that blocks building and walking, sells nothing, is never saved or blueprinted, and stands by whatever hub the save has |
| **money you can see** | every sale lifts its number from the hub in the hub's gold, rising and fading over a second and a half; sales on the same hub within half a second add into one tag, so a busy hub reads one honest sum; the far-ore premium and a rival's bid are in the number |
| **the hints step back** | the five lines of key hints fade after forty-five seconds of play and H brings them back for a moment; the foreman teaches the same keys, so the play area is the scene and not a legend |
| **the supply drone** | every half minute a small quad lifts off the habitat's dome with a crate, banks over to the hub, hovers while the beacon breathes, and comes home empty; rotors spin and the running lights blink; nothing in the game reads it, it is the outpost breathing |
| **ambient occlusion** | N8AO (MIT, shared with the adventure runtime) renders the scene with a true depth-and-normal occlusion pass before the bloom and the grade, so corners darken, belts sit on the plating, machines have weight at their skirts and the crates stack; half resolution; ?ao=0 turns it off |
| **the first sale** | the first time anything sells in a world the hub's pulse goes wide, the credit tag is twice its size, and a toast says what happened and what the number in the corner is; once per world, and a save remembers it |
| **the idle cue** | ninety seconds without building or erasing, with the foreman gone, and the goal card pulses while a ring lands on the nearest free seam; a toast says the card is the plan and the ring is a place; once a minute after that while the stillness lasts |
| **the crossing lights the face** | walking over an edge already flashes and names the face; now its seams pulse one after another, nearest first, so the new face reads as a set of places to go before the caption fades |
| **the adventure arrives in the same hand** | START plays the kit's reveal, the title in the display face with the sentence that made the world under it, then the race counts down; a win or a loss closes on the kit's end card with the medal, the time and the best as stats and play again as a button; every em dash in the adventure's player-facing lines is gone |
| **the race beside the demo** | `flagship_build.py --adv N` copies a studio-built adventure into flagship/drift and the title card lists it as a fifth pick that opens that build; the folder is 60 MB and stays out of the repository, and the runtime hides the pick when nothing answers for it, so a clone shows four picks and a packaged download five; an adventure build ships only the textures it loads |
| **one download** | `flagship_pack.py --adv N` rebuilds the demo, writes its licence manifest (three.js MIT, N8AO CC0 with its text vendored, the three faces under the OFL) and zips the folder with the race inside; 53 MB, 147 files, and the unzipped copy passes fworlds |
| **the adventure's own foreman** | after the reveal the kit's Foreman runs a first act in the player's mode: a race teaches look, throttle, steer and boost, a walk teaches look, walk, run and jump, flight and swimming their own four; each step clears by doing it, Enter steps, G skips, the last step hands over to the objective card, and a guided game stays guided |
| **a second world that is not a factory** | a moonlit forest walk stands beside the race on the title card, shipped with `--ship JOB:SLUG` like the drift; getting there fixed three studio rules: a night-light prompt no longer gets a paper look that paints daylight over its sky, storybook no longer binds to an overhead camera and inks softer, horror keeps a floor so a night moor is a moor and not a black field of grain, and a count of one reads as "the woodcutter's stash" |
| **three sounds from the same synth** | the first sale is a rising triad with a sparkle on top, the idle cue a soft double chime, and the drone carries a hum that swells as it passes and fades with distance, a continuous layer like the belts and the furnace; nothing is loaded |
| **buildings for building prompts** | an exterior world that names a structure used to get a glowing door standing in a field; now a body from the facade kit stands around every door, its front wall facing the spawn, four wall colliders with a gap at the door, half its windows lit at night; six kits join the brownstones (manor, cottage, inn, keep, chapel, tower) and forty words map to a kind and a kit; night skies get lighting floors and a moon bounce, and the fill's sky colour never drops to black |
| **the hero is dressed for the prompt** | a generic human in a photoreal world is recast from the prompt's own words to a dressed character from the roster (a detective for a haunting, a ranger for a moor, a scientist for a lab, a knight for a castle, an explorer otherwise); a named character keeps its name |
| **the studio's notes read as sentences** | every em dash in the notes, stage lines, brief check and licence manifest is gone |
| **flat looks get flat walls** | under an illustrated look the facade kit's walls take a flat tone with no photo and no relief, drawn in the same language as the world around them |
| **windows, not slabs** | a window is a metre and a half of glass in the upper part of the bay with a stone sill under it and a lintel over it, so a facade reads as rooms behind a wall; lit ones at night are warm squares |
| **a haunting has ghosts** | the extractor cast four wolves for a haunted manor; a prompt that reads as a haunting turns unnamed animal hostiles into ghosts, and a ghost is drawn as a translucent cold figure that hovers, flickers and drifts slowly, whatever mesh plays it |
| **three ghosts, a porch lamp, a spawn that faces the door** | spectral counts are capped at three; a lamp over the door and two eave lights at the front corners give the body its edge at night; the player spawns facing the landmark's door, or the goal when there is none, the way the factory spawns facing its line |
| **the crossing washes in** | walking over an edge already widens the view, bites the vignette, names the face and lights its seams one after another; now the new face's ore colour washes over the frame for a second, strongest in the shadows, so the first crossing reads as arriving somewhere |
| **the beacon sweeps** | a hub's beacon throws a slow beam, a long soft cone of its own gold turning once every twelve seconds and brightening as a sale lands, so a hub can be found from any face by its sweep, the way a lighthouse is; one mesh per hub, no light |
| **the light moves** | the key light swings about the worldlet, twenty-four degrees each way over seven minutes, and the disc and the sky follow it: shadows lengthen and swing across the plating, a lit face goes into shade and comes back, and a long session has a day in it; reduced motion holds the sun still |
| **a machine lands** | placing a machine used to put it there between one frame and the next; now it arrives at eight-tenths scale and overshoots to one over a third of a second, and a ring of dust in the plate's colour puffs from its skirt; the machines a new world opens with are already down |
| **a sweep feeds a machine** | dragging belts across a smelter used to lay a belt where the smelter stood; the tile before it already points into the machine, and the sweep now steps over it, so a line can be swept into a furnace without losing the furnace |
| **ore carries its rock** | what rode the belts was two crystals grown together, a gem; a chunk now sits on a dark flattened lump of matrix in the wall's grey and a dim wash of its own ore colour, the ember chunk in a cinder crust and the salt on a pale slab; still one instanced draw call per ore |
| **the overhead is a planning screen** | TAB gave a view from above and nothing to read in it; now the tile under the cursor carries a readout at the cursor, its face and coordinates and what the look label would say on the ground, and every hub wears its sales in the last minute, projected over it while the view is up |
| **the works are a moment in the world** | for a minute after the works play the world celebrates: every hub's sweep races and burns bright, sparks burst from a hub every half second in its gold, the seams pulse in waves across every face, the nebula swells and the drone flies at once; then it settles and the run carries on |
| **every face its own ground** | the plating changes with the mineral of the face: the ember faces sooted and warmed with cinders in the cracks, the salt faces paler with rime grown along their seams, the underside darker and more worn, the top the world's plate as authored; crossing an edge changes the ground under you and not only the sky |
| **a save you can name** | RUNS in the panel: name the factory you are standing in and keep it, with a picture of the frame, what it had banked and its machine count; open a kept run and the factory comes back as it was, forget one with a second click; eight per world, the autosave underneath unchanged |
| **measured on the card players have** | perfpass.mjs runs six phases of a session on the real GPU with the frame-rate limit off and writes PERF.md: fps, median and 95th-percentile frame times, worst frame, draw calls, triangles; the overhead is the heaviest view at 178 fps, the occlusion pass costs 0.7 ms a frame, the worst frames are one-off hitches |
| **the warm-up** | the first sale and the first flight each cost a 300 ms frame: the d3d11 driver builds a shader's executable at its first draw and every GL command waits behind it; the warm-up draws every geometry with every material once at boot, everything visible and unculled, into an eight-pixel target under the reveal, and the stalls are gone |
| **weather on the machines** | a machine built on an ember face is sooted, one on a salt face wears rime on its upward surfaces, one on the underside is dimmer; the type's geometry is shared, so a weathered machine takes a clone with its vertex colours reworked, no new material and no new draw call |
| **seams that read** | the seam was a grey lump in daylight, the one thing on the face a player could not tell was ore; the body keeps half the colour, the emissive carries the hue and follows the richness, the core and the pool are larger, and a seam is half again the size: a landmark from across the face |
| **outcrops** | small rock-and-crystal clusters in the face's own ore gather around each seam and thin out across the face, one instanced draw per ore; scenery only, a tile with one is still a build site and the outcrop steps aside under anything built |
| **the opening frame has a landmark** | the companion sits twenty-eight degrees right of the first heading and four up, just over the face's far edge in the frame the player first sees, the nebula a third of a turn round from it |
| **more words reach a mood** | a chocolate factory and a bakery named none of the four families' words and got the void; heat, brass and the oven now read as warm, grain, the orchard and the island as green, and the words of a place are asked before the words of a machine, so a bakery on a floating island is a green place with an oven in it |
| **the arc, toured** | tourarc.mjs plays the whole arc through the runtime's own placement (exported for harnesses): a four-line factory, the second act, the overhead, a meltdown, Ember Reach, Frostline, the works and the end card, shot beat by beat |
| **a prompt the library has never seen** | "a lighthouse keeper on a stormy island" generated its own keeper end to end: the reference judged for paint splashes before the mesh, TRELLIS.2, the remeshed body with the head's own map, a rig facing the right way, good at 0.82 on the first seed; the roster grows by itself and a role it already holds plays itself |
| **the weather outranks the look** | a stormy island asked for overcast and rain and got paper daylight over an orange desert; a paper look now yields to the sentence's night, dusk, overcast, rain or snow the way it already yielded to night |
| **empty hands for a search** | a keeper looking for a lantern walked out holding a blade, the weapon table's fallback; a role the table does not name carries nothing unless the world has hostiles |
| **the foreman stays behind** | his card about the factory just left rode along to Frostline and sat over the arrival, and over the empty face after a meltdown; a step still open when the player travels or melts down is closed, and the second act counts as done |
| **nothing that swims on dry land** | a stormy island cast a fish and, with no water anywhere, laid it on the soil at the player's feet; a swimmer in a waterless world is dropped and the note says to name a lake or a coast |
| **rain darkens the ground** | the ground colour is chosen from the world's words and the weather separately, so a storm fell on desert orange; wet earth is a quarter darker and less saturated, and the rule is applied to whatever colour was picked |
| **the studio sees the kept runs** | the runtime tells the studio its kept runs at boot and on every change; the studio shows them under the frame as cards with their pictures, opens or forgets one by message, and can keep the run the frame is in |
| **the demo is one game** | the title card lists no other builds: Crystal Works, pushed as far as it can go, is the demo; the studio is what turns any prompt into a game of that standard, and its range is shown in the studio, where every job is its own game |
| **the walk has weight** | the body eases up to speed over a sixth of a second and eases down a little quicker, and a sprint widens the view by five degrees; the lean, the nod, the landing dip and the bob were already there, and this is what they were missing |
| **the panel says what it is** | value banked, a minute to your hubs, a word under every chip, headers on market and upgrades, each upgrade's effect in a line |
| **the look label** | point at anything within reach and a line under the crosshair names it and says what it is doing |
| **the bar fits the screen** | eleven tools with their descriptions ran off the right edge of a 1280, 1366 or 1440 screen, the blueprint chip first; the descriptions step out below 1640 px, a locked tool shrinks to its icon below 1480, every tool does below 1180, and a gate checks five common widths |
| **a tower defence the studio can make** | "goblins march down a road and I build archer towers" came out as a ten-second survive timer with the player cast as a goblin; it is now a defend step: a keep with a health bar at the end of the level's road, waves that walk the road and only fight you when you stand in their way, gold for every kill, and towers raised with T that pick their own targets; the fallen rejoin the pool for the next wave |
| **a platformer the studio can make** | "a 2D platformer where a fox jumps between floating islands" came out as a third-person walk over flat grass; it plays side-on now, over floating islands spaced inside the hero's own jump with the pickups on top of them, a platformer's pace instead of an anatomical ceiling, and a camera framed on the hero |
| **you are the ship** | "sail a pirate ship across the ocean" cast a pirate on foot; a sentence whose verb is sailing puts the player in the vessel it names, and "pirate ship" is a ship because a noun phrase names its thing last |
| **you fly the craft** | "fly a fighter through an asteroid field" read "fighter" as a person, and "space fighter" came back from the classifier as a car on the ground; a sentence whose verb is flying makes the craft the player in fly mode, under a space sky when the sentence is in space, and a noun phrase ending in an aircraft flies |
| **an archipelago's sea is at zero** | the sailing game's default eight-metre sea drowned every island of an archipelago shaped around sea level, and the ship sailed over a pale cyan nothing |
| **a sea has an earthly sky** | a dolphin on a coral reef was given a space sky; water under space or Mars needs the sentence to name another world |
| **every stage of a chain is a different thing** | a farm came back turnip, turnip, turnip, turnip for resource, refined, combined and product; a stage that repeats an earlier one is named as that stage of it, and the extractor is told why |
| **a farm looks like one** | the factory read its mood from the title and world name, and "Turnip Harvest" in "countryside" named no family, so a cozy farm opened on the void's navy plating under a planet; the prompt itself is read now, and the fields' words belong to green |
| **a two-word product fits the market** | "turnip crate" and "turnip stew" wrapped out of the market's 64 px box and into the upgrades header; every name has a two-line slot and the bars stay on one baseline |
| **a hull draws a little water** | the waterline held the body's centre, so a six-metre ship sat three metres down with only its masts above the sea; the keel sits a draft under the line, an eighth of the height and never more than 0.8 m |
| **the seabed is not a meadow** | a coral reef was a flooded field with grass and parked carts under the water; grass does not grow below the sea, and a land prop that could only stand under it is left out |
| **space has no sea** | an asteroid field read as an archipelago and the fighter flew top-down over an ocean; under a space sky the ground is dark rock unless the sentence put water there |
| **the weapon has the hero's name** | an archer's first slot said Blade, a spaceship's said Bow, a dolphin's said Blade; a bowman draws a bow, a craft fires guns, an animal bites |
| **the prompt's own nouns are cast** | "score three goals against a robot goalkeeper" skipped the goalkeeper as imagined, because the planner wrote it robot_goalkeeper; and the robot cast an engineer as the striker; a football sentence casts the soccer player |
| **a guide is someone you walk up to** | a sailing game put a guide standing in the open sea beside the ship; the guide is added only when the player is on foot |
| **the bridge answers the right caller** | a Blender request that timed out finished later, and its reply was read by the next caller as its own; from then on every call got the answer to the one before, a build's asset steps failed in turn and generated meshes were registered raw; a reply that is not the caller's is a leftover and is skipped, and a forced timeout now leaves the calls after it answered correctly |
| **a print never fails a build** | started with its output going to a file, the server wrote in the Windows code page, and the first progress line carrying an arrow failed a character's generation; the server writes UTF-8 however it is launched |
| **a look is asked for** | of eleven games, eight came out pixel, low-poly, cartoon, noir or horror when their sentences asked for no look, and pixel and noir moved the camera too; a game is photoreal unless its sentence names or implies a style, and the note says what the planner had suggested |
| **one thing, whole, lying level** | "a gem" came back as a wallpaper of forty grey gems and meshed into a slab, and a dolphin leapt on a diagonal and swam standing on its tail; a prop's or animal's reference is judged for being one subject and rerolled when it is a sheet or a scatter, and a swimmer's long axis is laid level before it is saved |
| **a machine is played by a machine** | enemy drones in an asteroid field were played by dragons; a drone, jet, UFO or gunship stands in as the space fighter, a warship as the pirate ship, a raft as the sailboat, matched on whole words so a combat drone is not a bat; a creature the sentence named is made in the background, so the next build casts the real one |
| **a controller plays the flagship** | the standard mapping walks, looks, builds with RT and drags, erases with LT, changes tool on the bumpers, and drives a cursor in the overhead; one set of functions builds for the mouse and the pad, so they cannot drift apart |
| **pause and settings** | Esc or Start stops time, not just input: nothing moves and nothing is earned; volume, look speed and invert look are set there and kept between visits |
| **a mystery the studio can make** | "a detective mystery in a manor, find three clues and name the killer" came out as orbs and a beacon; now suspects stand apart with their names over their heads, E questions them and shows what you notice (hand, shoes, smell, coat), each clue says one of those things about the killer, J opens the casebook, and Y names someone; the case is dealt from the seed so exactly one suspect fits every clue and each clue rules someone out, a wrong name loses and says who it was |
| **clues are evidence markers** | the library's clue was a dark card the quality gate refuses; a mystery's clues are the yellow numbered tents a crime scene is dressed with, standing on the ground |
| **everyone is dressed** | the light walker every guide, guard and villager wore was the base body in its underwear; background people take the clothed walkers in turn (never the player's own), crowds draw only from the dressed ones, and a mystery's suspects are cast from clothed bodies (the library's "driver" is a car) |
| **no ghost the sentence did not ask for** | a foggy manor came with white ghosts wandering the lawn; a ghost or a spectral flag without a haunting in the prompt is left out, and a whodunit sheds bystanders who would be mistaken for suspects |
| **a city the studio can make** | "a city builder where I lay roads, zone houses and grow the population to 500" was a quarry with its words swapped; the worldlet builds a town under a day sky: a town hall with a street, roads that serve only when they reach the hall (across edges too), homes that grow when there is work, shops when there are people, works that keep the homes beside them small, parks that let them grow into flats, money from everyone living and working there, and the sentence's population as the goal; the market, seams, foreman and contracts stand down |
| **the kit props have their colours** | 486 props from five CC0 Kenney kits (fantasy town, graveyard, survival, castle, pirate) pointed at a colormap atlas that was never vendored, so every noir, cartoon, claymation or survival world was dressed in plain white models and logged a stream of 404s; each kit's atlas is embedded in its own props (every prop's UVs were checked against the kit first, 486 of 486 identical), with the kits' licences beside them |
| **a desktop game** | `flagship_pack.py --desktop` builds Crystal Works into one executable (flagship-desktop, Tauri 2, the studio shell's crates, offline from the cache): the packed game embedded, WebView2's crash blocklist switched off, F11 fullscreen kept between launches, and a pause menu that saves and quits to the desktop |
| **no step the sentence did not ask for** | "a horror game in a graveyard, find the three lanterns" opened on "collect the abandoned camp's supplies": a quest-chain rule prepended a scout step to any one-objective prompt with "find" in it, and the planner could invent steps of its own; the quest chain is off (the point of interest stays as a place to find), and a collect or defeat step with no word of the prompt in its label is dropped, unless that would leave nothing to play |
| **one clean coat** | the fox and the guide were mottled in colour and in light: a generated atlas is about 1,300 islands, most a few texels across, with an embossed normal map made from it; every animated character in the library (50) now carries its colour on its vertices instead, rebuilt on the surface from the atlas (each face's median, flecks voted out by the surface around them, the atlas's confetti filled from the fur or cloth around it), with each material read from its own sheet, smooth normals from the geometry and one roughness; the rig and every clip are untouched, files are 3 to 6 times smaller, and new characters get the coat as they are baked (FS_COAT=0 turns it off) |
| **achievements** | the first sale, goal tiers 3, 6 and all, the first meltdown core, a new world, the works, and a grown town are achievements, kept with the save and handed to the desktop build's steam_achieve command (again at every launch, so a run played while Steam was closed still counts) |
| **eight animals had lost their coats** | the tiger, cheetah, ice wolf, gazelle, elk, dog, moose and grizzly played as black silhouettes: their rig bakes had written near-black sheets while the models they were rigged from kept full coats; the coat now reads the source model's surface (aligned by the axis turn under which the two coincide) whenever the rig's own sheet is far darker, so the tiger is orange and striped again |
| **the horse stands up** | the horse and its source lay upside down with legs in the air (and the pony, mule, donkey, zebra and camel it stands in for with it); it was flipped, then regenerated through TRELLIS.2; its pitted flank and upright mane sheets come from the quadruped rig bake and are the next thing to fix there |
| **no lines, no holes** | the black lines standing over the horse were its mane's fringe, sheets the generator hides with its texture's transparency; the rig bake dropped the transparency and the coat painted them solid, so the coat now removes every face the texture shows as clear (read from the source model when the rig's sheet has none); the holes in the moose's flank came from a clean-up that hunts a shirt under a coat, which on one layer of fur cut the body itself, so animals keep their whole surface and lose only loose scraps; every animal was rebaked, and the three whose models were wrong from the start (a monkey on its back, snow weasels sitting up, a gorilla in a T-pose) were made again: a monkey on all fours, a weasel, a gorilla on its knuckles; a generation that finds the Blender bridge still waking now waits for it instead of rigging the raw half-million-face mesh |
| **forests to the horizon** | a nature world's trees were a cylinder under a few spheres, three hundred at most, and an "ancient pine forest" could build with none at all; trees are now grown in code (trunk and limbs on bending paths, leaf, needle and frond cards drawn for the world, wind, a crown that shades itself and lights through when the sun is behind it), the land goes on past the playfield to mountains at the horizon, and up to 420,000 trees stand on it: near ones as geometry, far ones as pictures of themselves taken under the world's own sun, dissolving into each other with no pop, at 60 frames a second |
| **one sun, not three** | since 2026-09-22 a frame counter ticked twice a frame, so the step that sets every material up for cascaded shadows never ran: every world bigger than 120 m was lit by all three cascade lights at full strength, which is much of why distant ground and mountains washed out; counted once, patched before the first frame, and rebuilt when patched |
| **cars that are cars** | the city's cars were a profile pushed sideways with a glass box and a lid on top; they are now lofted, one skin from nose to tail with a shoulder crease, flush glass, painted roof and pillars, rounded ends, turned tyres and spoked rims |
| **a frame of its own** | every game opened on the same dark glass in the same face; nine skins now (parchment, terminal, noir case file, comic, horror, racing, storybook, frost, glass), chosen from the game's own words, change the panels, the type and how a message arrives: a scroll unrolls, a console types, a case file is stamped, a comic panel pops, a racing banner slides in on a slant |
| **users own what they make** | the studio's licence now says so: every output is the user's to sell, with no attribution owed, and the engine copied into each game is MIT; the studio itself stays the owner's to sell, a subscription included |
| **the forest's detail, for every world** | the grown forest is now every world's growth: a desert carries cacti, scrub and stone to the horizon, a canyon red mesas and boulders, the moon and Mars rock fields under their own skies, a snowfield frosted spruce with snow settled on every upward face, a beach palms, a swamp dead wood, a meadow scattered oaks; stone is sculpted from noise with facets cut in, textured by where it is rather than by UVs, and photographed for the distance only once its texture has arrived |
| **every fight is not the same fight** | hostiles walked up and bit for one heart, and the hero could only swing back; now a dodge (R, or B on a pad) is untouchable for a third of a second, a hit grants a moment before the next can land, and enemies come as kinds that each ask a different answer: a brute winds up a slam you can see on the ground and step out of, a skirmisher is quick and frail, a spitter keeps its distance and lobs shots you can out-dodge; where the sentence asks for a fight, the one furthest out is a boss with a bar that turns enraged at half health and starts to volley |
| **the weapon in your hand** | choosing the pistol in a sword game still swung the sword: the attack read the build's setting, not the chosen weapon; it reads the weapon now |
| **somewhere to grow** | three upgrade cards were the whole tree; eleven now (vampire, keen edge, quick feet, thorns, second wind, long arm, mending, prospector and the three old ones), three offered at a time; kills and chests pay coins, hidden caches lie off the path, and a shrine sells an upgrade for an offering that rises each time |
| **a fall is not the start again** | running out of hearts offered only a reload; the card now offers to go on from the last objective reached, for a quarter of the coins |
| **a face for every skin** | the nine skins speak in their own type: Cinzel and IM Fell for parchment, Share Tech Mono for the terminal, Bebas and a typewriter for noir, Bangers and Fredoka for comics, Creepster for horror, Russo One for racing, Lora for storybook, Josefin for frost (all free to ship and sell) |
| **trees on the avenue** | a city's street trees were blobs of spheres; they are grown broadleaves now, the same as a forest's, trunks still solid |
| **a woman and an owl** | a guide written as a woman was played by a man, and an owl by a firefly, because the library had neither; both were made through TRELLIS.2 |
| **reefs, beaches and swamps** | the biomes reached the sea and the shore: underwater a seabed of kelp, coral and stone, a beach of palms whose fronds now face the sun instead of standing edge-on and invisible, a swamp of dead wood and reeds, a meadow of oaks and birch |
| **the sea goes to the horizon** | a reef's water was a square the size of the level, floating in haze over a void, with kelp standing up through it; the surface now runs to the edge of sight over a deep bed, kelp is grown to the depth it stands in, and low sculpted islands sit on the horizon |
| **an island is an island** | "a castaway on a tropical beach island" stood in a palm savanna that ran on to snowy ranges; an island, beach or coast now ends at a wandering sand shore, the sea runs on past it with palm-topped islands in the distance, and a beach's ground is sand, not lawn |
| **a body, not a bust** | the castaway was generated while the classifier still called it an object, so the picture was a portrait and the mesh a head and shoulders, which a later build rigged as the hero; a character mesh that is not far taller than it is deep is now retired and generated again as a whole body |
| **grass that grows like the forest** | a meadow was 38,000 three-blade tufts scattered once over a 70 m square, sparse at your feet and gone past it; on a photoreal green world the grass is now a field drawn on the GPU that travels with the camera: well over a hundred blades a square metre at your feet, thinning blade by blade to the edge of the near view, laid on the terrain, kept off paths, water, floors, rock and sand, grown in clumps and bare patches, lit through like the forest's leaves, swaying in gusts and parted by the hero |
| **cars with a face** | the lofted cars read the wheelbase from the nose instead of the middle, which gave every car a parade float's overhangs; the axles now sit where a car's do, the wheels are open spokes with a barrel, disc and caliper behind them, the doors, bonnet and boot have shut lines and handles, the mirrors sit on the doors, and the lamps, a slatted grille and the plates are laid on the actual nose and tail instead of sinking inside them |
| **a neon city is lit** | "a Tokyo drift through neon streets" had a few signs on shop buildings and dark towers; a neon district now hangs signs on every building, in Japanese where the city is Japanese, blades and plates at street level and storeys up, and its towers wear light lines up their corners and round their crowns; every sign is painted into one atlas and drawn in one call |
| **streets, not dried mud** | the road photo was a crazed, cracked surface whose cracks repeated every five metres; asphalt is now drawn as fine aggregate with soft repairs. A glass tower stood on a storey-high rubble plinth that read from the street as a stone fence along the kerb; towers stand on a low granite base now and trim is dressed stone. Wilderness points of interest no longer appear in cities |
| **start cards that fit** | "driftwood" chose the racing skin because it contains "drift"; the skin words are whole words now, and a beach, castaway or lagoon reads as storybook. An intro cut at 280 characters ended mid-word; it ends on a whole sentence |
| **ranges, not cones** | the horizon was ringed with cones; with a forest to the edge it is now ringed with sculpted ranges, ridged and creased, rock on the steeps, a snowline that follows the weather, and on green worlds the forest climbs their lower slopes to a treeline |
| **a sunset that is a sunset** | a photographed sunset sky came out as white fog over the whole picture: the sun-shaft pass took the entire bright sky as the sun; shafts now come from the sun's disc and fade away from it, so the forest under a sunset stays crisp |
| **a castaway is a person** | "a castaway on a tropical beach" built a statue: the casting guessed from a cached answer; a role whose last word names a person (castaway, nomad, courier and many more) is now always a walking character |
| **a bridge that answers** | a headless Blender that had stopped answering still accepted the connection, so every bake after it hung; the studio now pings it, and one that does not answer is closed and relaunched |
| **the worldlet, grown over** | Crystal Works' outcrops were faceted dodecahedra; they are sculpted stone now, from the same module as the forests' rocks, and a green worldlet carries moss and grass tufts across its open ground (thousands, in one draw) |
| **machines with edges** | every machine on the worldlet was built of perfectly sharp boxes, which reads as a placeholder however it is painted; each part thick enough to carry one now has a rounded edge that catches a line of light, and the rivets read as domes |
| **TRELLIS.2 stopped falling back** | every generation quietly fell back to TripoSR: the checkpoints loaded while the disk was 99% full and the paging file could not grow (os error 1455), and Hugging Face began answering lookups with a redirect the hub client does not follow; TRELLIS.2 now loads only the models its pipeline runs, from the cache when cached, and the parent process hands back SDXL's and the judge's memory before it starts |
| **sellable, checked** | a licence audit found four non-commercial parts in the generation chain: nvdiffrast in every TRELLIS.2 texture bake (replaced by an own PyTorch rasteriser, matched against it on a real atlas), TripoSG's RMBG-1.4 and diso (TripoSG left the chain), and InstantMesh (the cinematic tier uses TRELLIS.2); the Sketchfab and Objaverse fetchers take CC0 only; every exported game's LICENSES.md lists what shipped with the credit lines owed (CMU, OpenStreetMap, community authors); kits carry licence files; desktop builds carry the Rust crates' notices |
| **the sentence's own steps and cast** | "searching a rainy city for a stolen painting" collected three clues: the object a sentence seeks now becomes the step when the planner's is not the prompt's; a samurai in a bamboo forest was cast as a ranger (a known character with a working rig is never recast); a swamp had no water, so its crocodiles were dropped (a wetland floods its low third); snakes, frogs and turtles counted as fish and left dry worlds (only water animals do) |
| **Steamworks in the desktop build** | `flagship_pack.py --steam --app-id N` links the Steamworks client (steamworks-rs 0.13, MIT/Apache-2.0) and ships Valve's steam_api64.dll beside the game; achievements are set and stored the moment they are earned, the pause menu names the player and opens the overlay's achievements page, and without Steam the game plays the same; `--steam-selftest` proved it against a running Steam (app 480 answered, the player known, a stats call reached Steam and refused a name no app has) |
| **one type system** | Bricolage Grotesque for what is named (a variable face whose width and optical size set the three title voices from one file), Instrument Sans for what is read, DM Mono for what is counted; all SIL OFL, shipped in vendor/fonts |
| **copy that tells you** | every toast, tip, unlock line, tool label and the hint says what happened, what it means and what to do, in sentences, with no em dashes |
| **contracts** | every seventy seconds the market posts one sized to the current rate; deliveries of its item count at the hub; filled pays a bonus and a shard, lapsed comes again |
| **shards and rank** | three shards make a core without a meltdown; every meltdown raises the rank, which pays contracts more and gilds the worldlet's edge |
| **standing orders** | three contracts kept in a row earn one: a rate to hold, paid every minute it holds and a shard every third; it closes after ten seconds short and says how long it held |
| **a rival buyer** | every couple of minutes, once the filter exists, one product pays 1.8 times for sixty seconds; the board and the card mark it; the buyer leaves saying what it took and what the premium came to |
| **the blueprint** | key 0, earned with the forge: drag a box over a line to copy it with headings and filter settings, click to stamp it on any face, R turns it; rigs land only on seams and the toast says what did not fit |
| **rank perks** | rank I Deep Bits (a rig on a seam over 80% yields every tick), II Twin Furnace (a tick off every cook), III Broker (two shards a contract); derived from the rank, named under it |
| **the works** | when the chain, three cores, three worlds and a five-minute order are all done, the reveal plays once more with the run's numbers under the name, the edge goes gold for good, and the run carries on |
| **machine skin** | one shared panel map (seams, rivets, a lip, wear) on every machine; glow moved from the paint to the lamps; sun made the key (3.1 over 0.95 hemi / 0.85 fill); a frame on the smelter |
| **the companion** | a planet or moon low in every world's sky, shaded from the sun's side with a terminator and an atmosphere rim, drawn in the sky shader; one fixed direction so it is a landmark |
| **lanes** | every fifth grid line is a faint lit strip in the world's edge colour; the far plane widened to 1400 so the sky dome no longer clips from orbit |
| **the starter line always exists** | seedLine grows a seam at the head of the first clear run when the scatter left none; `?grid=` and `?seed=` debug overrides let a gate prove it by size |
| **factory reads as factory** | the pipeline holds prompts that name a production system to the factory genre, deterministically, before the 25-minute hero path can start |

Measured on a prompt-built export: 40x40x6 grid, 40 nodes, 180 value/min,
9 ingots in 12s, 18 draw calls, no console errors. The player walks top ->
south with up [0,0,-1] and never leaves the surface; a crystal on a belt at
the top face's edge arrives on the next face. 19/19 cube-grid properties pass
against an extract of the shipping template, not against the library copy.

---

## ~~1. Multi-sided gravity grid~~ — SHIPPED 2026-09-07

Walk over the edge of a floating cube and the world rotates under you; belts
wrap around the corner and keep running.

**Why it is first on merit:** it is the only item on the list that is both
genuinely novel in this genre AND immediately legible in a silent five-second
video. Satisfactory and Foundry are flat-ground games. Shapez is a detached
top-down board. A first-person camera tumbling around the underside of a
planetoid is the whole viral funnel in one shot.

**Why it is expensive:** the simulation is currently a 2D array. Faces need
their own coordinate frames, `getAdjacentTile` has to resolve across an edge
into a different frame with a different up-vector, and every belt matrix needs
re-basing. This is not a feature bolted on; it replaces the spatial core.

**Sequencing:** build it against the *existing* mechanics before adding more.
Porting one face's worth of belts and smelters is a week; porting five
mechanics' worth afterwards is a month.

**What it actually cost:** the simulation no longer knows the shape of the
world — it asks `stepTile` what is next to a tile, and that is the only place
an edge exists. Everything that stands on the surface goes through one seating
rule, so a belt arrow, a smelter and the build ghost cannot disagree about
which way is up. Three bugs, none of which threw an error: a two-pass edge
loop that crossed and immediately crossed back (the re-seat has to happen
*inside* the loop), a spawn offset the wrong way along the face's v axis that
pinned the player to the clamp so W did nothing at all, and a Tab orbit framed
for a flat island that sat *inside* the worldlet.

## ~~2. Prestige meltdown~~ — SHIPPED 2026-09-07

Pause the sim, convert every instance matrix into a particle with outward
velocity and gravity, collapse the factory, award tokens.

We already have the two hard parts: everything is in `InstancedMesh` (so the
transforms are already in one buffer) and the engine side of this project has
shipped physics-driven destruction before. Mostly a render-mode switch. High
spectacle, low structural risk. Good candidate to do *alongside* item 1.

**As built:** machines are not deleted, they are thrown — each build group is
detached, given an outward velocity and a tumble, and pulled back by the
worldlet so it arcs rather than simply leaving. Cores multiply everything the
hub banks by 45% each, which has to be steep enough that melting a good
factory beats keeping it or the prestige is a button nobody presses twice.
Two timing bugs worth remembering: the first pass threw debris at 9-25 m/s and
the whole factory left the frame inside 300ms, and re-seeding the starter line
inside `meltdown()` meant the collapse and the rebuild were the same frame, so
neither read. The replacement line now arrives when the old one has landed.

## ~~3. Galactic market ticker~~ — SHIPPED 2026-09-07

A random-walk price per product, and a launch pad that sells at the live rate.

Small to build. Its real value is not the spectacle — it is that it gives the
player a *reason to choose what to produce*, which is the thing a one-recipe
factory currently lacks. Pairs naturally with more recipes.

**As built:** four traded goods (three ingots and the alloy) on a mean-reverting
random walk between 0.55 and 1.85, and the hub pays the live rate. Mean
reversion matters more than it sounds: without it a long session parks every
price against a rail and the market quietly switches itself off. Raw ore always
sells at base, so the market rewards refining rather than hoarding.

The three mechanics now close a loop: the market says which good is worth
making, the filter is how you re-route production to make it, and the forge
means the best-paying good may need ore from a face you have not built on yet.

## ~~4. Scriptable logic belts~~ — SHIPPED 2026-09-07, as a filter tile

Route items by rule: `if (item.purity > 80) OUTPUT_A else OUTPUT_B`.

The brief's market read is right — there is a real gap for a logic/programming
factory game, and Shapez players are exactly that audience. But shipping a
`eval`-style script box first is a mistake:

- an arbitrary-code text field is a security and save-corruption problem the
  moment anyone shares a factory blueprint
- typing JavaScript into a first-person game breaks the immersion this build
  just spent its time earning
- most players bounce off a blank text box

Better shape: a **filter/condition tile** the player configures from a short
menu (by item type, then later by a property). Same decision space, no parser,
no immersion break. A raw script mode can come later for the audience that
wants it, once there are properties worth branching on.

**As built:** point at a filter, press F, and the gate on it changes colour to
whichever ore now passes — the setting is readable from across the face rather
than from a tooltip. Matching ore carries straight on, everything else leaves
out of the side. It deliberately does NOT fall back to the other output when
the chosen one is full: an item that takes the wrong exit because the right one
was busy is a filter that has silently stopped filtering, and the player would
have no way to see it happen. Shipped after the minerals, not before, because
a filter with one item type to sort is a belt.

Also fixed on the way: items sitting on a splitter were never drawn at all, so
a backed-up splitter looked empty.

## ~~5. Chronos paradox loop~~ — SHIPPED 2026-09-07, as a debt with a clock

Buffer 10s of item history, replay it as ghosts, and storm if the player
cannot repay the exact items in time.

The most complex item on the list and the least legible. It needs several
systems that do not exist yet (item identity over time, a debt ledger, a
failure state with area effects) and its appeal is hard to read in a video —
"ghost ore you must repay" takes a paragraph to explain, which is the opposite
of the funnel.

Not a bad idea; a bad *early* idea. Revisit once there are properties, filters
and a market, because it needs all three to mean anything.

**As built, once those three existed:** the debt is the good idea; the ghosts
are the part that takes a paragraph to explain, which is the opposite of the
funnel. So a rift lends you six of whichever ore the market currently pays most
for, pays the loan out onto your belts one tile at a time like a miner, and
puts the amount and the deadline on the HUD. Feed it back through the same ring
and it settles at a premium. Miss the deadline and it throws every machine
within three tiles into the sky — the meltdown's debris path, aimed at you
rather than chosen by you. It only accepts back exactly what it lent, which is
what makes the filter tile the instrument for repaying one.

One fairness bug worth remembering: the countdown originally started when the
rift opened, so a rift whose output belt was blocked demanded repayment of ore
it had never handed over, then blew up the factory for not returning it. The
clock starts when the loan lands.

---

## Suggested order

1. ~~Multi-sided gravity grid~~ — shipped
2. ~~Prestige meltdown~~ — shipped
3. ~~Filter tile~~ and ~~more recipes~~ — shipped
4. ~~Market ticker~~ — shipped
5. ~~Chronos~~ — shipped, as a debt with a clock rather than replayed ghosts

All five differentiators from the brief are in, and the factory now saves.
The Tauri/Steam packaging path shipped 2026-09-29: `flagship_pack.py --desktop` builds one executable (see README, One download).

## Worlds

Cores were a multiplier and nothing else, so prestige was a number going up. A
world is the other half of the trade — melt the factory down enough times and
somewhere new opens, which gives the meltdown a destination.

| world | cores | needs |
|---|---|---|
| whatever the prompt asked for | 0 | — |
| the first family home is not | 2 | — (warm) / heated drill (cold) / spore scrubber (green) |
| the second | 5 | same rule, by family |
| The Long Drift (void) | 3 | the whole chain walked — seams never grow back, a meltdown pays double |

The three unlockables are the families the home world is not, so a warm prompt
offers frost, verdant and the drift. Cores buy the trip; the capability makes
it survivable, and the chain hands the capabilities out.

Deliberately DATA: a world is a row of sky, fog, ground, grid, stars and a
price, so adding one is an edit to that table and nothing else. Ore colours are
excluded on purpose — they are how a belt is read at a glance, and re-learning
them per world would be a tax on travelling.

The progression chain, for reference — ordered so each unlock lands when the
previous one has made it mean something, and so that finding the cube is a
goal rather than a hope:

| tier | goal | reward |
|---|---|---|
| 1 | bank 40 value | SPLITTER |
| 2 | hold 400 a minute for 20s | OVERCLOCK cap 8 |
| 3 | stand on a second face | FORGE |
| 4 | forge one alloy | FILTER |
| 5 | run three rigs on three seams | RICH SEAMS cap 8 |
| 6 | hold 1200 a minute for 30s | CHRONOS RIFT |
| 7 | sell an alloy above 1.20 | HOT FURNACE cap 6 |
| 8 | bank 400 value | MELTDOWN |
| 9 | earn a core | HEATED DRILL (Frostline opens) |
| 10 | hold 3000 a minute for 30s | SPORE SCRUBBER (Verdant opens) |
| 11 | repay a rift | STABLE RIFT (cores worth a quarter more) |
| 12 | reach three cores | THE LONG DRIFT opens |

A rate goal's timer runs only while the rate is at or over the target and
resets the instant it is not: the starter line alone earns ~210/min at level
zero, so 120 would have been a total wearing a costume. Rewards are never
saved — `applyRewards()` re-derives caps and capabilities from the tier index
on every load, so an old save cannot carry a stale cap.

## Checking both at once

The demo is generated from the studio runtime, so they can only disagree if the
generator was not re-run. One command checks that and then runs all four gates
against each:

    cd flagship && python -m http.server 8790     # serve the demo
    python backend/tools/factory_check.py --job <id>

### Materials

Three things that are not more polygons and matter more than polygons:

- **An environment to reflect.** metalness with no environment map makes a
  surface DARKER, not shinier — raising it on the ground plating turned the
  floor black. A PMREM built from a two-stop gradient (an HDRI would be a
  megabyte of asset for a look three colours wide) fixed that and turned out to
  be the single biggest lighting upgrade available: every standard material
  gets a soft directional bounce instead of flat lambert. Tinted per world, so
  a red planet does not have neutral grey machines standing on it.
- **Baked occlusion.** Machines are merged into one geometry at boot, which is
  the moment to write an occlusion ramp into their vertex colours — dark where
  they meet the ground and under downward faces. Plus a per-part tint, so one
  material carries a recessed door, a plinth and a panel without a second draw
  call.
- **A rim light**, a fresnel pushed into emissive so the bloom outlines every
  machine. Use `normal`, never `vNormal`: a flatShading material has no vNormal
  varying, so referencing it fails to compile on exactly the materials most
  likely to be flat shaded.

### Rendering

The post pipeline is written by hand rather than pulled from three's addons —
the standalone demo vendors exactly one file and keeping it that way means the
demo cannot break in a way the studio build does not. Scene into a target,
bright pass, two blur pairs, then a composite that adds the bloom in linear
light, tone maps, tints the shadows toward the world's own fog colour and
closes a vignette.

The second trap, in the same family: a directional light's shadow camera sits
AT the light looking at its target, so anything farther from the target than
the light is behind the camera and casts nothing. The sun was 58 units out on a
world whose corners are at 69 — measured, ground luminance across a smelter's
base read 109/110/110/110/106, perfectly flat. Every distance in the light rig
is a multiple of HALF now.

Even fixed, one directional light only shadows three of six faces, so every
machine also carries a contact shadow of its own. It is tuned against the real
one: the first version darkened a quarter as much, which left a machine on the
underside floating next to an identical machine on top that did not.

The first trap: three applies tone mapping and sRGB encoding **only
when rendering to the canvas**. Render into a target and you get raw linear
values, and compositing those straight to the screen produces a nearly black
world that looks exactly like a lighting bug and is not one. The art gate now
reads a floor pixel and asserts it is lit.

Twelve gates, run against each — the three newest cover depletion, the
reveal/weather/sound beat, and grounding.

The bug this file keeps producing, so it is written down: a `const` or `let`
declared after a hoisted function that touches it AT BOOT. `scatterSpots`,
`AUDIO`, and the intro clock all threw a temporal-dead-zone error the first
time — each because something that runs during the starter-line seed or the
first render reached forward. Everything a boot-time path touches now lives in
one block near the top, next to the scene handles.

Nine gates, run against each: the core loop and cube walk, the rift, the studio
inspect bridge, save/load, collision and merge losslessness, the goal chain, the
art (icons, instancing, a scrolling tread, a drawn sky), a draw-call budget for
a 250-machine factory, and world unlocking.

## Also outstanding

- Art uplift — placeholder boxes; the Kenney space kit (already vendored in
  `backend/assets/props`, CC0) is the right visual language for this
- Levels / progression frame: goals, unlocks, a reason to expand
- Steam: create the app's achievements (the CW_ names in the README) and a depot; the overlay over WebView2 is best effort
