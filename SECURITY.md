# Security Policy

Fantasy Studio is a local-first desktop app — no cloud surface, no user accounts at this stage, no payment processing. The relevant attack surface is mostly: malicious assets, malicious prompts, and the API server bound to localhost.

That said: if you find a vulnerability, please tell us before telling the internet.

---

## Reporting a vulnerability

Email: **security@fantasylab.ai**

> *Email being set up. Until it's live, send a private GitHub Security Advisory via the repo's "Security" tab, or DM Brandon on the project's social channels.*

In your report, please include:

- A description of the issue and its impact
- Steps to reproduce (prompt, log excerpt, asset file if relevant)
- Affected version(s)
- A suggested fix if you have one
- Whether you'd like to be credited publicly

**We aim to respond within 72 hours** with an acknowledgment, an initial assessment, and a target fix window.

---

## Disclosure policy

Coordinated disclosure. We'll work with you on a fix and credit you in the [CHANGELOG](CHANGELOG.md) and the Hall of Fame below — unless you prefer anonymity, which is also fine.

We aim to ship fixes for confirmed vulnerabilities within:

- **Critical** (RCE, arbitrary file write, credential leak): 7 days
- **High** (sandbox escape, privilege escalation): 30 days
- **Medium** (DoS, information disclosure): 60 days
- **Low** (best-practice deviations): next release cycle

Please don't disclose publicly until a fix has shipped or 90 days have passed (whichever is sooner).

---

## Scope

### In scope
- Code in this repository
- Code in `backend/` (the Python pipeline)
- Code in `frontend/` (the React UI)
- The render pipeline's handling of user-provided prompts and assets
- The local API server (`localhost:8000`) endpoints
- The `tools/downloads_ingestor.py` watcher and its archive extraction (zip-slip etc.)

### Out of scope (report upstream)
- **Blender** itself — report to <https://developer.blender.org>
- **Ollama** runtime — report to <https://github.com/ollama/ollama/security>
- **Gemma** model output behavior — report to Google AI
- **Objaverse** / **Sketchfab** / **Poly Haven** content moderation — report to those services
- Issues in user-uploaded asset files (we treat them as untrusted; if our handling is unsafe, that *is* in scope, but the file content itself isn't)
- Social engineering of users (e.g. a malicious asset bundle with a misleading filename)
- Physical security
- Self-DOS by misconfiguring local resource limits
- Vulnerabilities in third-party dependencies (please report to the dep upstream and let us know so we can pin)

---

## Hall of Fame

Researchers who responsibly disclose vulnerabilities will be credited here.

*(Empty — be the first.)*

---

## Hardening notes for self-hosters

If you're running Fantasy Studio on a shared workstation or planning to expose the API beyond localhost, a few notes:

- **Never expose the API to the public internet without auth.** It's designed for `127.0.0.1` only. There's no auth layer in V1
- **Don't run with elevated privileges.** The render pipeline writes to `outputs/` and `assets/cache/`; both should be user-writable, nothing else
- **Asset cache is treated as trusted.** The healer ingests `.glb`/`.blend` files from `Downloads/` and stores them in `assets/cache/`. Files in the cache run through Blender's import. Blender's import has historically had a few CVEs around malformed files; keep Blender up to date
- **The watcher quarantines unsafe ZIP archive members** (zip-slip / `..` paths) but extracted files still go through Blender. Don't ingest archives from untrusted sources

---

Thanks for helping keep Fantasy Studio safe.
