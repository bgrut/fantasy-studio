<!--
Thanks for opening a PR. Quick reminders:
- Solo dev project; reviews are best-effort, usually 1–7 days
- Render-affecting changes need a regression matrix (see below)
- Match the existing [CATEGORY] log marker style
-->

## Summary

<!-- One paragraph describing what this PR changes and why. -->

## Related issue(s)

<!-- Closes #123, refs #456 -->

## Type of change

- [ ] 🐛 Bug fix (non-breaking, fixes broken behavior)
- [ ] ✨ New feature (non-breaking, adds capability)
- [ ] ⚠️ Breaking change (existing behavior changes)
- [ ] 📚 Documentation only
- [ ] 🧹 Refactor / cleanup (no behavior change)
- [ ] ⚡ Performance improvement
- [ ] 🎬 New recipe / layer
- [ ] 🎨 New asset(s)

## Testing performed

- [ ] Linter passes (`npm run lint` / `ruff check .`)
- [ ] Unit tests added/updated where applicable
- [ ] Real render performed end-to-end on at least one prompt
- [ ] Pipeline trace log reviewed for regressions
- [ ] Regression matrix run (see below) — required for render-affecting changes

### Regression matrix (render-affecting changes only)

Run the canary set and confirm no regressions. Paste relevant log lines.

| Prompt | Result | Notes |
|---|---|---|
| `a ferrari racing at sunset` | ✅ / ❌ | |
| `a polar bear in the arctic` | ✅ / ❌ | |
| `a horse in the desert` | ✅ / ❌ | |
| `a bmw racing in the desert` *(LOD twin canary)* | ✅ / ❌ | |

## Screenshots / before-after

<!-- For visual changes (frontend, render output, framing). Side-by-side ideal. -->

## Log output

<!--
For behavioral changes, paste the relevant pipeline_trace.log delta:
[PIPELINE], [MATCHER], [HERO_VERIFY], [LOD_CLEANUP], etc.
-->

```
<paste relevant log section>
```

## Checklist

- [ ] Code follows the project style (Black + ruff for Python, Prettier + ESLint for TS)
- [ ] `[CATEGORY]` log markers used for new diagnostic output
- [ ] `traceback.format_exc()` in every new `except` block
- [ ] `flush=True` on every new `print` in render-side code
- [ ] Tests pass locally
- [ ] Documentation updated (README, docs/, inline)
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] No breaking changes — or breaking changes are clearly documented in the PR description
- [ ] Backups committed for risky edits (`<file>.bak_<short_tag>` then gitignored)

---

<!-- Anything else reviewers should know? -->
