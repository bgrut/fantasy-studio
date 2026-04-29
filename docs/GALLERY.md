# Render Gallery

Real renders from Fantasy Studio. Every shot below was generated locally from a one-line prompt — no diffusion, no cloud, no per-frame fee. Each entry shows the prompt and the recipe the dispatcher chose.

Want to contribute a render? Open a PR — see [CONTRIBUTING.md](../CONTRIBUTING.md).

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
