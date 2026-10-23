# Gallery

Games and renders from Fantasy Studio, each made locally from a one-line prompt: no diffusion, no cloud, no per-game fee. The games come first; the video renders follow, each with the recipe the dispatcher chose.

Want to contribute a render? Open a PR — see [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Games (October 2026)

Unedited in-game captures of games built from the sentence under each, HUD hidden.

<table>
<tr>
<td width="50%"><img src="../.github/assets/games/v13/ant-kitchen.jpg" width="100%"/><br/><em>"a tiny ant explores a giant kitchen to carry a sugar cube home"</em></td>
<td width="50%"><img src="../.github/assets/games/v13/surf.jpg" width="100%"/><br/><em>"a surfer rides huge waves off a hawaiian beach at sunset"</em></td>
</tr>
<tr>
<td><img src="../.github/assets/games/v13/sky-islands.jpg" width="100%"/><br/><em>"a dragon rider flies between floating islands above the clouds"</em></td>
<td><img src="../.github/assets/games/v13/balloon.jpg" width="100%"/><br/><em>"a hot air balloon pilot floats over cappadocia at sunrise"</em></td>
</tr>
<tr>
<td><img src="../.github/assets/games/v13/steam-train.jpg" width="100%"/><br/><em>"a train driver takes a steam train through snowy mountain passes"</em></td>
<td><img src="../.github/assets/games/v13/skier.jpg" width="100%"/><br/><em>"a skier races down a steep black run through the trees"</em></td>
</tr>
<tr>
<td><img src="../.github/assets/games/v13/park-wide.jpg" width="100%"/><br/><em>"a dog fetches a frisbee in a sunny park"</em></td>
<td><img src="../.github/assets/games/v13/backyard-snow.jpg" width="100%"/><br/><em>"two kids have a snowball fight in a snowy backyard"</em></td>
</tr>
<tr>
<td><img src="../.github/assets/games/v13/sea-floor.jpg" width="100%"/><br/><em>"a glowing jellyfish drifts through an underwater cave collecting pearls"</em></td>
<td><img src="../.github/assets/games/v13/lighthouse-hurricane.jpg" width="100%"/><br/><em>"a lighthouse keeper keeps the light burning through a hurricane"</em></td>
</tr>
<tr>
<td><img src="../.github/assets/games/v13/spacewalk.jpg" width="100%"/><br/><em>"an astronaut repairs a broken satellite in orbit above the earth"</em></td>
<td><img src="../.github/assets/games/v13/giant-robot.jpg" width="100%"/><br/><em>"a giant robot stomps through tokyo at night fighting a sea monster"</em></td>
</tr>
<tr>
<td><img src="../.github/assets/games/v13/mars-rover.jpg" width="100%"/><br/><em>"a mars rover drives across red dunes looking for signs of water"</em></td>
<td><img src="../.github/assets/games/v13/kite.jpg" width="100%"/><br/><em>"a kid flies a red kite on a windy hill above the sea"</em></td>
</tr>
</table>

### More games

Earlier builds, rebuilt on the October engine and captured the same way.

<table>
<tr>
<td width="50%"><img src="../.github/assets/games/classics/tokyo-drift.jpg" width="100%"/><br/><em>"a tokyo drift racing game through neon streets at night"</em></td>
<td width="50%"><img src="../.github/assets/games/classics/samurai-shrine.jpg" width="100%"/><br/><em>"a samurai walks through a bamboo forest to a mountain shrine as the sun sets over the cherry blossoms"</em></td>
</tr>
<tr>
<td width="50%"><img src="../.github/assets/games/classics/colosseum.jpg" width="100%"/><br/><em>"a gladiator fights three opponents in the colosseum"</em></td>
<td width="50%"><img src="../.github/assets/games/classics/giza.jpg" width="100%"/><br/><em>"an explorer reaches the pyramids of giza at sunrise"</em></td>
</tr>
<tr>
<td width="50%"><img src="../.github/assets/games/classics/monastery.jpg" width="100%"/><br/><em>"a monk climbs a himalayan monastery at dawn"</em></td>
<td width="50%"><img src="../.github/assets/games/classics/frontier-town.jpg" width="100%"/><br/><em>"a sheriff hunts three outlaws in a wild west frontier town at high noon"</em></td>
</tr>
<tr>
<td width="50%"><img src="../.github/assets/games/classics/candy-land.jpg" width="100%"/><br/><em>"a kawaii candy land: hop across giant cupcakes and collect 20 sweets"</em></td>
<td width="50%"><img src="../.github/assets/games/classics/volcano.jpg" width="100%"/><br/><em>"climb a smoking volcano and escape the lava flows"</em></td>
</tr>
<tr>
<td width="50%"><img src="../.github/assets/games/classics/crystal-cave.jpg" width="100%"/><br/><em>"explore a glowing crystal cave deep underground"</em></td>
<td width="50%"><img src="../.github/assets/games/classics/venice.jpg" width="100%"/><br/><em>"a gondolier delivers letters through the canals of venice"</em></td>
</tr>
<tr>
<td width="50%"><img src="../.github/assets/games/classics/scottish-lighthouse.jpg" width="100%"/><br/><em>"a lighthouse keeper crosses a stormy scottish island at dusk"</em></td>
<td width="50%"><img src="../.github/assets/games/classics/joust.jpg" width="100%"/><br/><em>"a knight jousts at a medieval tournament in front of the castle"</em></td>
</tr>
</table>

---

## Cinematic Wildlife

<table>
<tr>
<td width="50%">
<img src="../.github/assets/gallery-polar-bear-arctic.gif" alt="Polar bear in the arctic" width="100%"/>

**Prompt**: *"a polar bear in the arctic at sunset"*<br/>
**Recipe**: `hero_ocean_horizon`<br/>
**Tier**: Polished

The launch hero shot. Sunset light skating across snow, the bear walking the ridge with the horizon doing all the work. This is what V1 ships to do — single subject, real environment, locally rendered, cinematic.
</td>
<td width="50%">
<img src="../.github/assets/gallery-horse-mountain.gif" alt="Horse galloping in the mountains" width="100%"/>

**Prompt**: *"a horse galloping through mountain pass at golden hour"*<br/>
**Recipe**: `animal_mountain_walk`<br/>
**Tier**: Polished

Golden-hour rim light on a moving subject is one of the harder things to nail with diffusion. With a real renderer it just works — the sun is a sun, the rocks cast real shadows, the gallop cycle reads cleanly at every frame.
</td>
</tr>
<tr>
<td>
<img src="../.github/assets/gallery-rhino-desert.gif" alt="Rhinoceros in the desert" width="100%"/>

**Prompt**: *"a rhinoceros in the desert"*<br/>
**Recipe**: `hero_desert_epic`<br/>
**Tier**: High Quality

The matcher fix from V1.3.7 in action — the alias map now correctly handles `rhinoceros` / `rhinos` / `rhino` as the same subject and refuses to fall through to nearest-tag matches like *elephant*.
</td>
<td>
<img src="../.github/assets/showcase-deer.gif" alt="Deer in environment" width="100%"/>

**Prompt**: *"a deer in the forest at dawn"*<br/>
**Recipe**: `animal_forest_intimate`<br/>
**Tier**: Polished

A quieter shot — soft fill, intimate framing, the camera holding still while the subject does. Counter-programming for the high-energy chase / racing renders.
</td>
</tr>
</table>

---

## Vehicles

<table>
<tr>
<td width="50%">
<img src="../.github/assets/gallery-ferrari-sunset.gif" alt="Ferrari at sunset" width="100%"/>

**Prompt**: *"a ferrari racing at sunset"*<br/>
**Recipe**: `vehicle_desert_hero`<br/>
**Tier**: High Quality

The canary prompt. Cycles, 128 samples, real light bounces, real specular on real paint. The thing diffusion video can't reproduce twice.
</td>
<td width="50%">
<img src="../.github/assets/gallery-porsche-desert.gif" alt="Porsche in the desert" width="100%"/>

**Prompt**: *"a porsche in the desert"*<br/>
**Recipe**: `vehicle_desert_hero`<br/>
**Tier**: Polished

Same recipe, different cast — same scene assembly, same lighting language, different car. The director routes both prompts through the same dispatcher score and gets two coherent shots out the other end.
</td>
</tr>
</table>

---

## Atmospheric / Experimental

<table>
<tr>
<td width="50%">
<img src="../.github/assets/gallery-cat-canyon.gif" alt="Cat in canyon" width="100%"/>

**Prompt**: *"a cat sitting on a rock in the canyon at golden hour"*<br/>
**Recipe**: `cat_canyon_cinematic`<br/>
**Tier**: Polished

This recipe is named after this exact shot. We hit it once during the V1.3 sprint, said "that's the look," and locked the layer composition. It's now its own dispatcher entry — small subject, big landscape, shallow DOF.
</td>
<td width="50%">

</td>
</tr>
</table>

---

## More renders coming with V1.1

The launch gallery is six shots deep on purpose — every one ran through the public pipeline, every one is a real render Brandon can re-open in Blender. As the launch library expands and the recipe set grows in V1.1, this gallery grows with it.

Submit your own renders via PR. We'll add the best to a community section after launch.

---

## Built in public

For more renders + behind-the-scenes:

- **TikTok**: [@Fantasylab.ai](https://www.tiktok.com/@fantasylab.ai)
- **YouTube**: [@Fantasy_lab_ai](https://youtube.com/@Fantasy_lab_ai)
- **Discord**: Coming soon
- **Waitlist**: [fantasylab.ai](https://fantasylab.ai)
