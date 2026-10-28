<div align="center">

<img src=".github/assets/logo.png" alt="Fantasy Studio" width="160"/>

# Fantasy Studio

### The AI game engine that runs on your own computer.

**Type a sentence. Play the game it describes, in about a minute. Then keep shaping it by pointing at the world.**

<a href="https://github.com/bgrut/fantasy-studio/releases/latest"><img src="https://img.shields.io/badge/Download%20for%20Windows-FantasyStudio--Setup.exe-8b5cf6?style=for-the-badge&logo=windows&logoColor=white" alt="Download Fantasy Studio for Windows"/></a>

*Windows 10/11 · Run the installer, open Fantasy Studio, pick **Game mode** · No graphics card needed · Nothing to install first*

<sub>Every download is checked against published SHA-256 checksums · installs for your user only, no admin prompt · [Is it safe?](#is-it-safe) · Developers: [install from source](#install-from-source)</sub>

<br/>

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/bgrut/fantasy-studio?label=release)](https://github.com/bgrut/fantasy-studio/releases/latest)
[![TikTok](https://img.shields.io/badge/TikTok-%40Fantasylab.ai-000000?logo=tiktok&logoColor=white)](https://www.tiktok.com/@fantasylab.ai)
[![YouTube](https://img.shields.io/badge/YouTube-%40Fantasy__lab__ai-FF0000?logo=youtube&logoColor=white)](https://youtube.com/@Fantasy_lab_ai)
[![GitHub stars](https://img.shields.io/github/stars/bgrut/fantasy-studio?style=social)](https://github.com/bgrut/fantasy-studio)

[What it makes](#what-it-makes-real-builds-unedited) · [The engine](#whats-inside-the-engine) · [Get started](#get-started) · [Install guide](INSTALL.md) · [Roadmap](ROADMAP.md) · [Changelog](CHANGELOG.md)

</div>

---

<div align="center">
<img src=".github/assets/games/v17/hero-collage.jpg" alt="Six games made by Fantasy Studio from one sentence each" width="900"/>

<sub>Six games, six sentences: a knight in a red cape in a castle courtyard · a ringmaster under the big top · a monk at a rope bridge over a misty gorge · a sumo tournament at a Tokyo shrine · a weather balloon launch from an Antarctic station · a tea picker on Darjeeling's hills. In-game captures of real builds, HUD hidden.</sub>

<br/>

<img src=".github/assets/games/v13/hero-collage.jpg" alt="Six more games made by Fantasy Studio from one sentence each" width="900"/>

<sub>Six more: a tiny ant in a giant kitchen · surf breaking on a Hawaiian beach · a dragon rider's islands above the clouds · a steam train through snowy passes · a dog in a sunny park · a snowball fight in a snowy backyard.</sub>

<br/>

<img src=".github/assets/games/classics/classics-collage.jpg" alt="Twelve more games made by Fantasy Studio, one sentence each" width="900"/>

<sub>Twelve more: neon Tokyo street racing · a samurai's shrine under cherry blossom · a gladiator in the Colosseum · the pyramids of Giza at sunrise · a Himalayan monastery · a frontier town at high noon · a kawaii candy land · a smoking volcano · a glowing crystal cave · Venice's canals by gondola · a Scottish lighthouse in a storm · a medieval joust. [See them all with their sentences.](#more-games)</sub>
</div>

---

## What is Fantasy Studio?

Fantasy Studio is a desktop app that turns a plain sentence into a **playable 3D game**: the world the sentence names, the hero it is about, the things to do in it, the weather and the hour, built and running locally in about a minute. No code, no cloud, no account, no per-game fee.

*"a tiny ant explores a giant kitchen to carry a sugar cube home"* builds a kitchen seen from the floor, with table legs like towers and a tipped sugar bowl. *"a surfer rides huge waves off a hawaiian beach at sunset"* rolls swells in that break white in the shallows and carry your board to the sand. *"a train driver takes a steam train through snowy mountain passes"* puts you on the footplate of a locomotive on its line. Every game is its own: its own maker's typefaces, minimap and title card, so a thousand games do not look like one.

A local AI (Gemma 3 via Ollama) reads the sentence and plans the game; the engine builds what it plans, and when a character the library has never had is needed, local image-to-3D (SDXL → Microsoft TRELLIS.2) makes it once, rigs it, and keeps it for every game after. Nothing you make leaves your machine unless you publish it.

The same studio still renders **cinematic video** in Blender (see [Video mode](#video-mode)), but the game engine is the heart of it now.

---

## What it makes (real builds, unedited)

Every picture below is an unedited in-game capture of a build made from the sentence under it, on one machine, with the HUD hidden.

### Newest builds

Characters with cloth that moves, water you wade through, things that break, bridges that sag under you, and a place built for each sentence.

<div align="center">

| | |
|---|---|
| <img src=".github/assets/games/v17/knight-cape.jpg" width="430"/><br/><sub>*"a knight in a red cape smashes barrels in a castle courtyard looking for the hidden key"*<br/>The cape is cloth: it streams behind a run and swings round a turn. Barrels and crates break into real pieces, and one of them holds the key.</sub> | <img src=".github/assets/games/v17/castle-courtyard.jpg" width="430"/><br/><sub>Same game, the courtyard: curtain walls with a wall-walk, round towers, the keep and its steps, stables, a smithy, a well, banners moving in the wind.</sub> |
| <img src=".github/assets/games/v17/rope-bridge.jpg" width="430"/><br/><sub>*"a monk crosses a swaying rope bridge over a misty gorge to reach a cliff temple"*<br/>The bridge hangs like rope: it sags where you stand, bounces with each step and sways in the wind. Mist lies in the gorge below.</sub> | <img src=".github/assets/games/v17/creek-wading.jpg" width="430"/><br/><sub>*"a kid splashes through a shallow creek catching frogs on a summer afternoon"*<br/>The water slows the walk and rings round your legs; stepping stones, reeds, lily pads, and frogs that hop away if you rush them.</sub> |
| <img src=".github/assets/games/v17/sumo.jpg" width="430"/><br/><sub>*"a sumo wrestler pushes rivals out of the ring at a tokyo tournament"*<br/>A shrine tournament: the clay ring under its hanging roof, a packed crowd, banners. A bout is a real pushing match; whoever leaves the straw loses.</sub> | <img src=".github/assets/games/v17/can-alley.jpg" width="430"/><br/><sub>*"a kid knocks down tin cans at a fairground stall to win a giant teddy bear"*<br/>Throw real balls at pyramids of real cans. Clear three stands and the giant bear is yours to carry.</sub> |
| <img src=".github/assets/games/v17/big-top.jpg" width="430"/><br/><sub>*"a ringmaster opening the show under a striped circus big top"*<br/>Sawdust ring, packed stands, trapeze and fairy lights; take the star and the spotlight finds you.</sub> | <img src=".github/assets/games/v17/clock-tower.jpg" width="430"/><br/><sub>*"a clockmaker climbing inside a great clock tower to mend the gears before midnight"*<br/>A stair up the inside of the tower past the swinging pendulum to the gears and the backlit dials.</sub> |
| <img src=".github/assets/games/v17/treehouses.jpg" width="430"/><br/><sub>*"a girl crossing rope bridges between treehouses in a rainforest canopy"*<br/>Thatched decks round kapok giants a dozen metres up, rope bridges between them.</sub> | <img src=".github/assets/games/v17/polar-station.jpg" width="430"/><br/><sub>*"a scientist launching a weather balloon from an Antarctic research station"*<br/>A base on the ice under the aurora; fill the balloon and watch it climb away.</sub> |
| <img src=".github/assets/games/v17/tea-estate.jpg" width="430"/><br/><sub>*"a tea picker on misty terraced hills in Darjeeling at dawn"*<br/>Clipped tea hedges on every contour, a red road up to the factory on the crest.</sub> | <img src=".github/assets/games/v17/sawmill.jpg" width="430"/><br/><sub>*"a lumberjack fells pine trees in a snowy forest and hauls the logs to the sawmill"*<br/>Trees fall as trees fall and land in the snow; the logs ride a sled to the mill with its saw and steam engine.</sub> |

</div>

### Earlier this season

<div align="center">

| | |
|---|---|
| <img src=".github/assets/games/v13/ant-kitchen.jpg" width="430"/><br/><sub>*"a tiny ant explores a giant kitchen to carry a sugar cube home"*<br/>The room is built at the hero's scale: chair legs tower, crumbs are boulders, the sugar cube sits by a tipped bowl.</sub> | <img src=".github/assets/games/v13/surf.jpg" width="430"/><br/><sub>*"a surfer rides huge waves off a hawaiian beach at sunset"*<br/>Swells roll in, steepen and break; a board on the water rides them in. Goal: ride five waves.</sub> |
| <img src=".github/assets/games/v13/sky-islands.jpg" width="430"/><br/><sub>*"a dragon rider flies between floating islands above the clouds"*<br/>You fly the dragon; a chain of turf-and-rock islands hangs over a sea of cloud, waterfalls spilling off them.</sub> | <img src=".github/assets/games/v13/steam-train.jpg" width="430"/><br/><sub>*"a train driver takes a steam train through snowy mountain passes"*<br/>The locomotive and its carriages on their line; the line does the steering.</sub> |
| <img src=".github/assets/games/v13/balloon.jpg" width="430"/><br/><sub>*"a hot air balloon pilot floats over cappadocia at sunrise"*<br/>Burner to climb, vent to sink, the wind carries you over fairy chimneys, the sky full of other balloons.</sub> | <img src=".github/assets/games/v13/sea-floor.jpg" width="430"/><br/><sub>*"a glowing jellyfish drifts through an underwater cave collecting pearls"*<br/>The sea floor under caustic light: corals, kelp, pearls to gather.</sub> |
| <img src=".github/assets/games/v13/backyard-snow.jpg" width="430"/><br/><sub>*"two kids have a snowball fight in a snowy backyard"*<br/>The back of the house, the deck, a fenced yard with a shed, a swing set and a snowman; you throw snowballs.</sub> | <img src=".github/assets/games/v13/park.jpg" width="430"/><br/><sub>*"a dog fetches a frisbee in a sunny park"*<br/>Gravel walks round a fountain, benches and lamps, a playground and a duck pond on mown lawns.</sub> |
| <img src=".github/assets/games/v13/lighthouse-hurricane.jpg" width="430"/><br/><sub>*"a lighthouse keeper keeps the light burning through a hurricane"*<br/>Driving rain, a storm sea breaking on the rocks, the light lit at the end of the path.</sub> | <img src=".github/assets/games/v13/spacewalk.jpg" width="430"/><br/><sub>*"an astronaut repairs a broken satellite in orbit above the earth"*<br/>A spacewalk: you float beside the station, the planet below.</sub> |
| <img src=".github/assets/games/v13/giant-robot.jpg" width="430"/><br/><sub>*"a giant robot stomps through tokyo at night fighting a sea monster"*<br/>A ten-metre hero in a neon street grid; the cars at its feet.</sub> | <img src=".github/assets/games/v13/mars-rover.jpg" width="430"/><br/><sub>*"a mars rover drives across red dunes looking for signs of water"*<br/>A six-wheeled rover on a rocker-bogie, built in code and driven nose first.</sub> |

</div>

### More games

Earlier builds, rebuilt on today's engine and captured the same way.

<div align="center">

| | | |
|---|---|---|
| <img src=".github/assets/games/classics/tokyo-drift.jpg" width="290"/><br/><sub>*"a tokyo drift racing game through neon streets at night"*<br/>Wet asphalt, neon fronts and a pack of rivals; the car slides when you throw it.</sub> | <img src=".github/assets/games/classics/samurai-shrine.jpg" width="290"/><br/><sub>*"a samurai walks through a bamboo forest to a mountain shrine as the sun sets over the cherry blossoms"*<br/>Blossom over the path, wildflowers in the grass, a torii gate at the climb.</sub> | <img src=".github/assets/games/classics/colosseum.jpg" width="290"/><br/><sub>*"a gladiator fights three opponents in the colosseum"*<br/>The arena floor inside tiers of a packed crowd; three opponents to beat.</sub> |
| <img src=".github/assets/games/classics/giza.jpg" width="290"/><br/><sub>*"an explorer reaches the pyramids of giza at sunrise"*<br/>Limestone pyramids course by course over the dunes, the goal at their feet.</sub> | <img src=".github/assets/games/classics/monastery.jpg" width="290"/><br/><sub>*"a monk climbs a himalayan monastery at dawn"*<br/>Chortens, prayer flags and stone stairs up a red mountain ridge.</sub> | <img src=".github/assets/games/classics/frontier-town.jpg" width="290"/><br/><sub>*"a sheriff hunts three outlaws in a wild west frontier town at high noon"*<br/>A boardwalk main street, false fronts and a telegraph office in the desert.</sub> |
| <img src=".github/assets/games/classics/candy-land.jpg" width="290"/><br/><sub>*"a kawaii candy land: hop across giant cupcakes and collect 20 sweets"*<br/>Frosting ground, sprinkles, donuts and lollipops, cupcakes to hop across.</sub> | <img src=".github/assets/games/classics/volcano.jpg" width="290"/><br/><sub>*"climb a smoking volcano and escape the lava flows"*<br/>Lava channels glow across the route to a smoking cone.</sub> | <img src=".github/assets/games/classics/crystal-cave.jpg" width="290"/><br/><sub>*"explore a glowing crystal cave deep underground"*<br/>Crystal clusters light a cavern far underground.</sub> |
| <img src=".github/assets/games/classics/venice.jpg" width="290"/><br/><sub>*"a gondolier delivers letters through the canals of venice"*<br/>Canals between palazzi, gondolas at their moorings, letters to deliver.</sub> | <img src=".github/assets/games/classics/scottish-lighthouse.jpg" width="290"/><br/><sub>*"a lighthouse keeper crosses a stormy scottish island at dusk"*<br/>Heather, rain and a storm sea on the rocks; the light at the end of the island.</sub> | <img src=".github/assets/games/classics/joust.jpg" width="290"/><br/><sub>*"a knight jousts at a medieval tournament in front of the castle"*<br/>The lists, striped pavilions and pennants before the castle.</sub> |

</div>

And the studio's flagship, **Crystal Works**, a factory-building game made in Fantasy Studio and developed alongside it ([`flagship/`](flagship/)):

<div align="center">
<img src=".github/assets/games/v17/cw-orbit.jpg" width="430"/> <img src=".github/assets/games/v17/cw-low.jpg" width="430"/>

<sub>A worldlet you can walk all the way round, each face its own country with its own ore: a blue-green meadow with brooks and wildflowers, a heath split by glowing fissures, a salt marsh crusted white, a mossy shade side. Build lines of rigs, belts, smelters and hubs across it, under a violet nebula.</sub>
</div>

---

## What's inside the engine

**Worlds built to the sentence.** A general open world (terrain, forests that grow by biome, rivers, lakes and seas with real shorelines, caves, volcanoes, fjords) plus purpose-built places for the things people actually ask for:
giant rooms seen by a tiny hero · the sea floor · islands in the sky · surfing beaches · backyards · parks · harbours and fishing villages · frontier towns · villages · monasteries on their mountains · gorges with rope bridges · creeks with stepping stones · graveyards · castles with curtain walls, and their courtyards · jungle temples · sunken cities · Venice's canals · a Colosseum · jousting lists · sumo rings · circus big tops · fairground stalls · treehouse villages in the canopy · tea estates · vineyards · polar research stations · sawmills · football pitches · skateparks · railway lines · candy lands · Cappadocia · space stations in orbit, the Moon and Mars · and real cities from OpenStreetMap (name New York, Tokyo or London and you drive its actual streets).
Interiors are generated as real rooms you walk into: manors, malls, hospitals, prisons, libraries, restaurants, castle halls, attics, the inside of a clock tower.

**Heroes and casts.** The sentence's subject is the hero. People and animals are generated once (SDXL reference → TRELLIS.2 mesh), auto-rigged, and moved by motion matching over real motion capture (CMU and 100STYLE); four-legged animals get measured walk, trot and gallop gaits; insects stand on six legs. Vehicles are built in code with real proportions: cars, go-karts, a planetary rover, a steam locomotive, sailing ships, hot-air balloons, boards (snowboard, skis, surfboard, skateboard, sled). Riders ride their mounts; flyers fly; swimmers swim; boats float. Supporting characters wear the period and the place (Vikings' villagers are fishermen and shepherds, not men in hoodies), and drawn styles get drawn characters.

**Games, not just walks.** Objectives combine freely: collect · defeat · reach · race · survive · hunt · capture · escort · defend · eliminate · score · serve · repair · deliver · ride · accuse. A sentence that names a genre gets that genre: tower defence, side-scrolling platformer, murder mystery with suspects and a casebook, sea battles, snowball fights, ghost hunts (or playing the ghost), city builder, and a full factory game on a living worldlet.

**Weather, light and physics.** Rain that splashes, snowstorms, fog that swallows the distance, hurricanes, mist in the hollows; any hour from dawn to night; real-time shadows, ambient occlusion and 4× multisampling; 2K photo-scanned ground and building materials (Poly Haven, CC0). Rapier physics: collisions, climbing, swimming, buoyancy, ragdolls, and more that you can feel:
- capes, cloaks, banners and flags are cloth that hangs, swings and catches the wind;
- water slows you as you wade, rings round your legs and splashes at every step;
- barrels, crates and pots smash into real pieces;
- rope bridges sag under you and sway;
- felled trees topple and crash;
- thrown balls knock real cans off their stands;
- a sumo bout is an actual pushing match.

**Every game has its own maker.** Each build is given a maker's voice: one of 95 open-licence typeface families for its title and text, its own colour scheme and frame, its own minimap style (radar, paper map, chart, blueprint, neon, pixel and more), a maker's mark on its title card, and an opening written for that game by the narrator. Two games from similar sentences still look and read differently.

**Styles and views you pick.** Photoreal, cartoon, anime, horror, noir, watercolour, storybook, pixel, low-poly and more; third-person 3D, top-down, or side-on.

---

## Shape it after it's built

- **Inspect mode: point at the world and change it.** Hover anything to identify it (`wolf · hostile · speed 3`), click a spot, type: *"place a campfire here," "put a sign that says stay near the fire," "fence off this pass."* It appears in seconds, and the rules are real: a campfire marked safe is a place hostiles will not enter.
- **Edit in words.** *"Make it night," "make it harder," "add two wolves."* The same seed keeps the same world; only what you asked for changes.
- **The Truth Table.** One panel lists every rule the game actually enforces, read from the live game.
- **Levels and projects.** Stack levels into one game and export it with a hub menu.

## Share it

Every game is a self-contained web build (three.js and Rapier vendored, no CDN, runs offline):

- **Community Marketplace (in-app):** publish to your own free Cloudflare worker and anyone can play from a link, on a phone too. Shared work is CC-BY-4.0 ([privacy & sharing](PRIVACY.md)).
- **Zip it** for itch.io or any static host.
- **Export to Godot 4:** a real Godot project that plays on F5, with a `STEAM_GUIDE.md` for the road to a store release.

---

## Get started

1. **[Download the installer](https://github.com/bgrut/fantasy-studio/releases/latest)** (`FantasyStudio-Setup-<version>.exe`, about 2 MB) and run it.
2. Open **Fantasy Studio** from the Start menu and pick **Game mode** (no graphics card needed) or **Full studio** (adds image and 3D generation on an NVIDIA card).
3. The first start sets everything up with a progress bar: its own Python, the engine, the 3D model library and Ollama with its local model (about 10 GB in Game mode). After that it opens straight into the studio.

Then type a sentence. Some to try:

- *a tiny mouse sneaks through an old library at night to steal a piece of cheese*
- *a kid flies a red kite on a windy hill above the sea*
- *a ghost haunts a victorian mansion scaring the guests at midnight*
- *a skier races down a steep black run through the trees*
- *a knight explores a redwood forest to find a hidden shrine at night*

### Is it safe?

The installer and everything it downloads are built from this repository at the release's tag, and every file carries a published SHA-256 checksum that the setup verifies before using it (Ollama's installer runs only if its digital signature is valid). Check the installer yourself with `Get-FileHash .\FantasyStudio-Setup-1.3.0.exe` against the release's `SHA256SUMS.txt`. Until code signing is in place, Windows may show "Windows protected your PC": choose **More info → Run anyway**.

### Install from source

For developers, or to run from a clone (needs Git, Python 3.11+, Node 20+ and Ollama):

```powershell
git clone https://github.com/bgrut/fantasy-studio
cd fantasy-studio
.\bootstrap.ps1             # read it first: it sets up the venv, npm packages, models and skies
.\desktop\launch.ps1        # opens the native Fantasy Studio desktop app
```

A clone does not download the 3D model library from Git LFS; `bootstrap.ps1` (or `python backend/tools/fetch_assets.py`) fills it in from the newest `assets-*` release. Full prerequisites and troubleshooting: **[INSTALL.md](INSTALL.md)**.

- 🕹️ **Game mode needs no GPU.** Building and playing work on any recent laptop; a graphics card makes worlds smoother.
- 🧬 **New characters need an NVIDIA GPU** (8 GB+) the first time a noun appears; after that they are cached in your library and cost nothing.
- 🎲 **Every build is a new world.** The seed is shown in the app; reuse it to rebuild a favourite.

---

## How it works

```mermaid
flowchart TB
    A["Your sentence"] --> B["Local planner<br/>Gemma 3 via Ollama"]
    B --> D["Design + spec<br/>hero · world · places · objectives · weather · maker"]
    D --> R["Readers that hold it to the sentence<br/>(the subject is the hero, a beach has a sea, a ski run is snow…)"]
    R --> C{"Cast"}
    C -->|in the library| L["Cached model"]
    C -->|new noun| G["SDXL → TRELLIS.2 → rig<br/>(once, then cached)"]
    L --> E["three.js + Rapier runtime<br/>world builders · motion matching · weather · post"]
    G --> E
    E --> P["Play · Inspect & edit · share link · Godot export"]
```

The planner proposes; the engine decides. A sentence's own words outrank the AI's guesses (a snowboarder's run is snow, a hurricane rains, a train driver drives the train), and every world type that the generic open world cannot express has a builder of its own. Same sentence and seed, same world.

Deep dives: [docs/USER_GUIDE.md](docs/USER_GUIDE.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [backend/LOCOMOTION.md](backend/LOCOMOTION.md) (the biomechanics the characters are held to) · [CHANGELOG.md](CHANGELOG.md).

---

## Video mode

The same studio renders **cinematic video** in Blender: real frames, no diffusion. The local planner picks cast, camera, light and mood; characters come from the same library; you get an MP4 plus the `.blend` file to re-light and re-render forever, from a 30-second Eevee preview up to a 4K Cycles final. Story Director turns one prompt into a multi-scene film. Video mode wants an NVIDIA GPU. See [docs/PIPELINE_V2.md](docs/PIPELINE_V2.md) and the [render gallery](docs/GALLERY.md).

---

## Honest state of things

Fantasy Studio is built in public, solo, and measured rather than hoped about.

- **How close is the first build?** A benchmark builds 24 everyday sentences, plays each, and has a local vision model judge it against its sentence (strictly). Recent runs average about **3 of 5 for matching the sentence** and **2.2 of 5 for looks**, with 12 to 30 percent of games passing every check. Familiar settings land close; a sentence that asks for a kind of place, vehicle or scale the engine has no builder for yet comes out plausible but wrong, and each of those becomes a builder (the giant kitchen, the surf and the sky islands above were all fixed that way this month).
- **Characters** generated for the first time vary in quality; a character check scores each one and retries poor ones, but faces and hands can still be soft.
- **Performance:** the first time a new world loads it can freeze for several seconds, occasionally much longer, while the graphics driver compiles its shaders. After that it holds 60 fps on the development machine (an RTX 5070 Ti).
- **Code signing** for the installer is being set up.

Detail: **[ROADMAP.md](ROADMAP.md)** and **[CHANGELOG.md](CHANGELOG.md)**.

## How it compares

| | Fantasy Studio | Cloud AI game makers | Diffusion video (Sora, Runway…) |
|---|---|---|---|
| Playable 3D games | ✅ from a sentence, editable live | ✅ (varies) | ❌ |
| Runs locally | ✅ fully, no account | ⚠️ mostly cloud | ❌ cloud |
| Edit after generating | ✅ point at the world, type | ⚠️ limited | ❌ new roll |
| Same prompt, same result | ✅ seeded | ⚠️ partly | ❌ |
| Export to a real engine | ✅ Godot 4 project | ⚠️ varies | ❌ |
| You own the output | ✅ | ⚠️ per terms | ⚠️ per terms |
| Cost | $0 after install | credits or subscription | $10–$95 a month |

---

## FAQ

**Do I need to know how to code?** No. You describe the game and edit it by pointing and typing. If you do code, export to Godot and take it anywhere.

**Do I need a graphics card?** Not for Game mode. A new character (a noun the library has never had) needs an NVIDIA GPU the first time it is generated; after that it is cached.

**Can I sell what I make?** Every model and tool the pipeline calls is listed in [backend/PIPELINE_LICENSES.md](backend/PIPELINE_LICENSES.md), and every one in use allows it. The app itself is BSL 1.1 (below).

**Is it really local?** Yes. No API keys, no cloud, no telemetry. Nothing leaves your machine unless you press Publish.

**Mac or Linux?** Windows 10/11 is the only supported platform today.

---

## License

**Business Source License 1.1**: free for personal and non-commercial use, source visible, converts to Apache 2.0 four years after first commit. Commercial licensing from FantasyLab AI. Full terms in **[LICENSE](LICENSE)**.

## Acknowledgments

- [**three.js**](https://threejs.org) (MIT) and [**Rapier**](https://rapier.rs) (Apache-2.0): the game runtime
- [**Ollama**](https://ollama.com) and [**Google Gemma**](https://ai.google.dev/gemma): the local planner
- [**Microsoft TRELLIS.2**](https://github.com/microsoft/TRELLIS) (MIT) and SDXL: image-to-3D characters (DINOv3 inside TRELLIS.2 under its own licence)
- [**CMU Motion Capture Database**](http://mocap.cs.cmu.edu) and [**100STYLE**](https://www.ianxmason.com/100style/): real motion
- [**Poly Haven**](https://polyhaven.com) (CC0): ground, building and sky scans
- [**Kenney**](https://kenney.nl) (CC0): stylised asset kits
- The open-licence type designers behind the 95 font families (SIL OFL)
- [**OpenStreetMap**](https://www.openstreetmap.org) contributors: real cities
- [**Godot**](https://godotengine.org) (MIT): the export target · [**Blender**](https://blender.org): video mode

---

<div align="center">

⭐ **If this looks interesting, star the repo to follow the build.**

Built by **Brandon Grutkowski** · [FantasyLab AI](https://fantasylab.ai) · 2026

[TikTok](https://www.tiktok.com/@fantasylab.ai) · [YouTube](https://youtube.com/@Fantasy_lab_ai) · [Waitlist](https://fantasylab.ai)

</div>
