---
name: Bug report
about: Something rendered wrong, the pipeline crashed, or the frontend misbehaved
title: "[BUG] "
labels: bug, triage
assignees: ''
---

<!--
Thanks for filing a bug. The single biggest accelerator for getting it fixed
is the pipeline trace log — see Backend log section below.
-->

## Bug summary

<!-- One sentence describing what's wrong. -->

## Steps to reproduce

1.
2.
3.

## Expected behavior

<!-- What should have happened? -->

## Actual behavior

<!-- What did happen? -->

## Render output

<!--
If the bug shows up in the render itself (wrong asset, dual hero, weird
framing, broken lighting), attach the MP4 or a screenshot. GIFs are great too.
-->

## Backend log

<!--
Paste the relevant section of pipeline_trace.log. It lives at:
    outputs/blender_render_<timestamp>/pipeline_trace.log

A good slice is from [MAIN_START] through [RENDER_COMPLETE] (or the abort
line). If the file is huge, the most useful sections are:
  - [PIPELINE] markers
  - [MATCHER], [HERO_RESOLVE], [ASSET_AGENT]
  - [BLEND_DEDUP], [GLB_DEDUP], [FORCED_HERO_TAG], [LOD_CLEANUP]
  - [HERO_VERIFY] (especially if it failed)
  - any [ERROR] / [WARN] / traceback
-->

```
<paste log here>
```

## Environment

- **OS**: <!-- Windows 11 22H2 / macOS 14.x / Ubuntu 22.04 -->
- **CPU**:
- **GPU**: <!-- e.g. RTX 4070 12GB -->
- **RAM**:
- **Blender version**: <!-- e.g. 5.1.0 -->
- **Ollama model**: <!-- e.g. gemma3:12b -->
- **Fantasy Studio version**: <!-- visible top-right of the frontend -->
- **Browser** (if frontend issue):

## Additional context

<!-- Anything else that might help. Links to related issues, recent prompt
patterns that worked, screenshots of the cast panel, etc. -->
