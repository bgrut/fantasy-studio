# Privacy & Sharing Policy

Fantasy Studio is a **local-first** application. This document explains what
stays on your machine (almost everything), what leaves it (only what you
explicitly publish), and the terms that apply to community sharing.

## The local-first promise

- **Generation is local.** Prompts, extracted game specs, rendered videos,
  generated 3D characters, and built games are produced and stored on your own
  computer (under `backend/renders/` and `backend/assets/`). No prompt or
  output is sent to Fantasy Studio's authors or any third-party AI service.
- **The AI is local.** Language extraction runs on your own Ollama install;
  image and 3D generation run on your own hardware (SDXL, TripoSR/TRELLIS).
- **No telemetry.** The app collects no analytics, no crash reports, and no
  usage data. The only database is a local SQLite file used for your own
  render history.
- **Network access the app makes on its own:** downloading open-source model
  weights on first install, and OpenStreetMap map data when a prompt names a
  real city (subject to the [OSM privacy policy](https://wiki.osmfoundation.org/wiki/Privacy_Policy)).
  Nothing about you is included in those requests beyond a normal HTTP fetch.

## What "Publish" does (Community Marketplace)

Publishing is **always explicit** — a button you press, behind a consent
checkbox. When you publish:

- **A game**: the exported game files (HTML/JS/GLB assets of your project)
  are uploaded to **your own Cloudflare Worker + R2 bucket** and listed on the
  community feed served by that worker. Anyone with the link (or reading the
  feed) can play and download those files.
- **A character**: the character's 3D model files (GLB) are uploaded and
  listed the same way. Anyone can install it into their own library.
- **What is attached**: the title/description you provide, the display name
  you chose in Marketplace → Setup, and a timestamp. Choose your display name
  accordingly — use a pseudonym if you prefer.
- **What is never attached**: your prompts, edit history, file paths, system
  information, or anything else from your machine.

Your worker URL and publish token are stored locally in
`backend/renders/share_config.json` (a gitignored path) and are only ever sent
to *your* worker.

## Terms of community sharing

By pressing Publish you agree that:

1. **You own it or have the right to share it.** Don't publish content you
   don't have rights to, and don't publish content that includes other
   people's personal data.
2. **License**: everything published to the community feed is shared under
   **[CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/)** — anyone may
   play, download, remix, and reuse it (including in their own games), with
   attribution to your display name.
3. **No unlawful or harmful content.** No content that is illegal, infringing,
   hateful, or sexualizes minors. Keep it something you'd show at a game jam.
4. **Hosting is yours.** The feed and files live on the Cloudflare account of
   whoever runs the worker. If that's you, Cloudflare's
   [privacy policy](https://www.cloudflare.com/privacypolicy/) applies to the
   hosting layer. The worker keeps no logs beyond Cloudflare's defaults.
5. **Removal**: the worker operator can unpublish any item
   (`DELETE /api/items/:id`). To request removal of content from a feed you
   don't operate, contact its operator; for anything related to this
   repository, open a GitHub issue on the project repo.

## Third-party components & attribution

Fantasy Studio ships only free, commercially-safe components. Generated games
embed their own attribution footer (three.js — MIT, Rapier — Apache-2.0,
CMU Motion Capture Database, © OpenStreetMap contributors where map data is
used). Do not remove these notices from published games.

## Children

Fantasy Studio is a developer tool and is not directed at children under 13.
Community feeds are unmoderated by default — operators are responsible for
what their feed hosts.

## Changes

This policy travels with the repository; changes are visible in git history
and noted in `CHANGELOG.md`.

*Last updated: 2026-07-08*
