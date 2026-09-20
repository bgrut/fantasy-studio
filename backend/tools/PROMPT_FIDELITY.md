# Prompt fidelity

Scored on 2026-09-20 by `backend/tools/prompt_check.py`: each sentence carries what a careful reader would expect from it, and the build is scored on how many of those it delivered, read from the resolved spec the studio wrote. The studio's own off-brief notes ride along.

**36 of 39 expectations met (92%).** Pass.

| the sentence | title | genre | score | missed | off-brief |
|---|---|---|---:|---|---|
| a haunted manor on a windswept moor, find the three relics before the bell tolls | Haunted Manor | adventure | 6/7 | reach bell: none |  |
| a tokyo drift racing game through neon streets at night | Tokyo Drift Nights | adventure | 5/5 |  |  |
| a rusted mining outpost on a dead red moon | Rusted Moon Outpost | factory | 2/2 |  |  |
| an ice refinery on a frozen moon | Lunar Ice Refinery | factory | 2/2 |  |  |
| a knight defending a stone keep from wolves at dusk | Keep Defender | adventure | 5/5 |  |  |
| a samurai crossing a bamboo forest to reach a mountain temple | Bamboo Path | adventure | 4/4 |  |  |
| a detective searching a rainy city for a stolen painting | City Shadows | adventure | 4/5 | collect painting x1: clues x5 |  |
| a scientist collecting samples in a toxic swamp full of crocodiles | Swamp Samples | adventure | 3/4 | hostile crocodile: man |  |
| a moonlit forest walk to gather lost fireflies before dawn | Firefly Dawn | adventure | 3/3 |  |  |
| a bakery on a floating island where grain is milled into flour and baked into loaves | Skybound Bakery | factory | 2/2 |  |  |

## What each sentence is held to

- a haunted manor on a windswept moor, find the three relics before the bell tolls: genre adventure, sky night, style horror, landmark manor, spectral, collect ('relic', 3), reach bell
- a tokyo drift racing game through neon streets at night: genre adventure, sky night, mode drive, objective race, city
- a rusted mining outpost on a dead red moon: genre factory, mood warm
- an ice refinery on a frozen moon: genre factory, mood cold
- a knight defending a stone keep from wolves at dusk: genre adventure, hero knight, landmark keep, hostile wolf, sky dusk
- a samurai crossing a bamboo forest to reach a mountain temple: genre adventure, hero samurai, objective reach, landmark temple
- a detective searching a rainy city for a stolen painting: genre adventure, hero detective, weather rain, collect ('painting', 1), city
- a scientist collecting samples in a toxic swamp full of crocodiles: genre adventure, hero scientist, collect ('sample', None), hostile crocodile
- a moonlit forest walk to gather lost fireflies before dawn: genre adventure, sky night, collect ('firefl', None)
- a bakery on a floating island where grain is milled into flour and baked into loaves: genre factory, theme ['flour', 'loaf', 'loaves', 'grain', 'dough', 'bread']
