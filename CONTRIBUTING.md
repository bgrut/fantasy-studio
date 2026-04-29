# Contributing to Fantasy Studio

Hi — thanks for considering it.

Fantasy Studio is a **solo-dev project in pre-launch** (public V1.0 lands Mid-May 2026). It's open source under BSL 1.1 with a 4-year Apache conversion. I'm shipping it because the diffusion-video bet seems wrong and the world deserves a real-tools alternative — and because building in public is more fun than building in a basement.

Contributions are genuinely welcome. The notes below set realistic expectations on response times and scope so we don't waste each other's day.

---

## Project status

- **Solo maintainer**: Brandon Grutkowski ([@bgrut](https://github.com/bgrut))
- **Stage**: pre-launch / early access
- **Response time**: best-effort. Aim is < 5 days for triage, but launch-month chaos is real
- **Communication**: GitHub Issues for bugs/features, GitHub Discussions for design questions, **Discord (coming soon)** for live chat
- **License**: BSL 1.1, see [LICENSE](LICENSE)

---

## Ways to contribute

### Highest-impact

- 🐛 **Bug reports** with a reproducible prompt + log. The pipeline trace log (`outputs/<render>/pipeline_trace.log`) makes most bugs trivially diagnosable
- 🍎 **macOS / Linux platform support** — V1 is Windows-only and tested. We need eyes on Blender path detection, separator handling, Ollama service install, the asset cache directory layout
- 🎬 **Recipe contributions** — JSON-only, no Python required (see below)
- 🎨 **Asset contributions** — curated heroes / environments / props that pass the V1.2 healer
- 📚 **Documentation** — typo fixes, screenshot updates, missing TROUBLESHOOTING entries
- 🧪 **Renderer backend prototypes** — Unreal, Godot, anything that consumes our recipe JSON

### Also valuable

- ✨ **Feature requests** that align to the [ROADMAP](ROADMAP.md). Off-roadmap requests get triaged but will land slowly
- 💬 **Prompt patterns** that work surprisingly well — open a Discussion, we'll add the best to [docs/PROMPTING.md](docs/PROMPTING.md)
- 🎓 **Tutorials and demo videos** — credit/link in your README is great

### Not currently in scope

- Multi-subject scene composition (V2 — see ROADMAP)
- Diffusion-based texture generation
- Cloud render orchestration (V1.5+)
- Marketplace integration (V2)

---

## Bug reports

Open a GitHub Issue using the **Bug Report** template. The minimum information that lets a bug get diagnosed without a 10-message back-and-forth:

- **Prompt** that triggered it (verbatim)
- **OS / GPU / RAM / Blender version / Ollama model**
- **App version** (top-right of the frontend)
- **Pipeline trace log** — paste the section from `[MAIN_START]` to `[RENDER_COMPLETE]` (or the abort line). It lives next to the render output: `outputs/blender_render_<timestamp>/pipeline_trace.log`
- **Expected vs. actual** — what should have happened, what did
- **Render output** — MP4 or screenshot, if relevant

Bugs without a log get a "please attach the trace log" comment and stall there. Bugs *with* a log usually get a fix or a workaround in 1–3 days.

---

## Feature requests

Open an Issue using the **Feature Request** template. Three things to include:

1. **What problem does this solve?** Not the solution — the problem.
2. **Where on the [ROADMAP](ROADMAP.md) does this fit?** Now / Next / Soon / Future / off-roadmap.
3. **Alternatives you considered** — even if you rejected them.

Off-roadmap requests aren't rejected, but they go to the bottom of the queue. The roadmap is short and intentional.

---

## Contributing recipes

Recipes are pure JSON. A recipe lives at `app/templates_v2/recipes/<name>.json` and references layers from sibling directories (`environments/`, `compositions/`, `lighting/`, `animations/`, `ambient/`, `post/`).

A typical recipe is ~30 lines. The dispatcher scores recipes against the prompt's scene plan; the highest scorer drives the render.

**Authoring guide**: `docs/AUTHORING_RECIPES.md` *(not yet written — flagged for post-launch)*. In the meantime, copy `app/templates_v2/recipes/vehicle_desert_hero.json` as a template and adjust the `template`, `subject_type`, `dispatch_keywords`, and layer references.

When you submit a recipe PR:
- Include 3–5 example prompts that should hit your recipe
- Show before/after screenshots
- Document any new layers your recipe needs (and consider whether a generic existing layer would do)

---

## Contributing assets

The 316-asset launch library is curated by hand and run through the V1.2 healer at ingest. If you want to contribute assets:

1. Drop a `.glb`, `.gltf`, or `.blend` into your local `Downloads/` and let `tools/downloads_ingestor.py watch` heal + register it
2. Render a couple of prompts that use it; verify HERO_VERIFY passes
3. Open a PR with the file, the registered `library.json` entry, and a thumbnail

Asset PRs will move into a **Marketplace** (V2 roadmap) where contributors get revenue share. For now, contributed assets are credited in `credits.txt` next to every render that uses them.

**Authoring guide**: `docs/AUTHORING_ASSETS.md` *(not yet written — flagged for post-launch)*.

---

## Development setup

Same as [INSTALL.md](INSTALL.md), plus:

- Backend hot-reload: `python -m app.main --reload`
- Frontend hot-reload: `npm run dev` (already enabled by Vite)
- Linting: `npm run lint` in the frontend; `ruff check .` in the backend
- Tests: `pytest` in the backend (selective; full Blender-render tests are manual)

Backups while iterating: the project uses a `*.bak_<tag>` convention. When you make a risky edit, copy the original to `<file>.bak_<short_tag>` first. Examples in the codebase: `*.bak_v141_dedup_regression`, `*.bak_v137_matcher`, `*.bak_v136_polish`. Backups are gitignored.

---

## Code style

### Python (backend)

- **PEP 8**, line length 100
- **`ruff` + `black`** in the pipeline; format before commit
- **`[CATEGORY]` log marker pattern** — every meaningful operation prints a log line prefixed with a bracketed uppercase category (`[GLB_IMPORT]`, `[FORCED_HERO_TAG]`, `[LOD_CLEANUP]`, `[HERO_VERIFY]`, …). This is non-negotiable; the pipeline is debugged by grepping for these
- **`traceback.format_exc()` in every `except`** — silent failures are the architectural enemy. If you catch, log the trace
- **`flush=True` on every `print`** — Blender subprocesses buffer stdout; without `flush` you'll lose log lines on crashes

### TypeScript / React (frontend)

- **Prettier** for formatting, **ESLint** for lint rules
- **Tailwind** for styles; no inline `style={}` except for dynamic values
- **Component file = component name** (PascalCase)
- **Server state** via `@tanstack/react-query`; no manual fetch+useState

### Commit messages

Conventional-ish, but pragmatic:

```
fix(matcher): elephant prompt no longer returns rhinoceros (V1.3.7)
feat(lod): signature-based dedup hides LOD twins post-FORCED_HERO_TAG
docs(readme): add comparison table
chore(deps): bump react-three/fiber 9.4 → 9.5
```

Tag PRs that affect rendering with a render log delta in the PR body.

---

## Pull request process

1. **Fork** the relevant repo (`fantasy-studio`, `blender-studio-backend`, or `blender-studio`)
2. **Branch** off `main`: `git checkout -b feat/your-thing`
3. **Make the change** with tests where applicable
4. **Run lint + tests** locally before pushing
5. **Open a PR** using the template — fill in the testing checklist and attach a before/after if visual or a log delta if behavioral
6. **Wait for review** — best-effort, usually 1–7 days
7. **Address feedback** — push more commits to the same branch; we'll squash on merge

PRs that change rendering behavior should include a regression matrix run against at least the canary set:
- `a ferrari racing at sunset`
- `a polar bear in the arctic`
- `a horse in the desert`
- `a bmw racing in the desert` *(LOD twin canary)*

Paste the `[PIPELINE]`, `[HERO_VERIFY]`, and `[LOD_CLEANUP]` (if applicable) lines in the PR body.

---

## License clarification

Contributions are licensed under **BSL 1.1** under the same terms as the project (see [LICENSE](LICENSE)). You retain copyright in your contributions; you grant FantasyLab AI and downstream users the BSL 1.1 license to use them.

When BSL 1.1 auto-converts to Apache 2.0 four years after the first commit, your contributions convert with it.

If you're contributing on behalf of an employer, make sure your employer's IP policy allows it.

---

## Code of Conduct

Fantasy Studio is governed by the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). Be kind, be technical, be patient with people learning. The project is a tool to help creative people make things — bring that energy.

Reports go to **conduct@fantasylab.ai** *(email being set up; for now, DM Brandon on [@Fantasylab.ai TikTok](https://www.tiktok.com/@fantasylab.ai) or open a private GitHub Discussion).*

---

## Questions

- **GitHub Discussions** — design questions, prompt-pattern shares, "is this a bug?" before filing
- **Discord** — coming soon for launch
- **TikTok / YouTube** — public roadmap and progress updates

Thanks for reading this far. Now go render something.

— Brandon
