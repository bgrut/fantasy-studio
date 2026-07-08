// Fantasy Studio share worker — the community marketplace backend.
// Publish a game's dist/ (or a character GLB), get a link anyone can tap,
// and a public feed the in-app Marketplace browses. Everything is static
// files in R2 — no compute, free-tier friendly.
//
// API (Bearer PUBLISH_TOKEN required for writes):
//   POST /api/games                     -> { id }             create a game id
//   PUT  /api/games/:id/files/<path>    (body = file bytes)   upload one file
//   POST /api/games/:id/publish         -> { url }            finalize + feed
//   POST /api/characters                -> { id }             create a character id
//   PUT  /api/characters/:id/files/<p>  (body = file bytes)   upload glb/thumb
//   POST /api/characters/:id/publish    -> { url }            finalize + feed
//   DELETE /api/items/:id               remove from the feed (moderation)
//   GET  /api/feed                      -> { items: [...] }   public
//   GET  /g/:id/<path>                  serve game files (public)
//   GET  /c/:id/<path>                  serve character files (public)
//   GET  /api/games/:id                 -> manifest (public)

const TYPES = {
  html: "text/html;charset=utf-8", js: "text/javascript", css: "text/css",
  json: "application/json", glb: "model/gltf-binary", png: "image/png",
  jpg: "image/jpeg", svg: "image/svg+xml", wasm: "application/wasm",
  ico: "image/x-icon",
};

function ctype(path) {
  const ext = path.split(".").pop().toLowerCase();
  return TYPES[ext] || "application/octet-stream";
}

function authed(req, env) {
  const h = req.headers.get("Authorization") || "";
  return env.PUBLISH_TOKEN && h === `Bearer ${env.PUBLISH_TOKEN}`;
}

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, POST, PUT, DELETE, OPTIONS",
  "access-control-allow-headers": "authorization, content-type",
};

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status, headers: { "content-type": "application/json", ...CORS } });

async function readFeed(env) {
  const f = await env.GAMES.get("feed/index.json");
  if (!f) return [];
  try { return JSON.parse(await f.text()); } catch { return []; }
}

async function writeFeed(env, items) {
  await env.GAMES.put("feed/index.json", JSON.stringify(items));
}

async function serveFile(env, prefix, id, rest) {
  let obj = await env.GAMES.get(`${prefix}/${id}/${rest}`);
  if (!obj && !rest.split("/").pop().includes(".")) {
    // directory-style URL (a level's dist/) → serve its index.html
    rest = rest.replace(/\/+$/, "") + "/index.html";
    obj = await env.GAMES.get(`${prefix}/${id}/${rest}`);
  }
  if (!obj) return new Response("not found", { status: 404, headers: CORS });
  return new Response(obj.body, {
    headers: {
      "content-type": ctype(rest),
      "cache-control": rest.endsWith(".html") || rest.endsWith(".json")
        ? "no-cache" : "public, max-age=31536000, immutable",
      ...CORS,
    },
  });
}

// shared create/upload/publish flow for both kinds
async function handleKind(req, env, url, parts, kind, prefix) {
  // create id
  if (req.method === "POST" && parts.length === 2) {
    return json({ id: crypto.randomUUID().slice(0, 8) });
  }
  // upload one file
  if (req.method === "PUT" && parts[2] && parts[3] === "files") {
    const path = decodeURIComponent(parts.slice(4).join("/"));
    if (!path || path.includes("..")) return json({ error: "bad path" }, 400);
    await env.GAMES.put(`${prefix}/${parts[2]}/${path}`, req.body);
    return json({ ok: true, path });
  }
  // publish: write manifest + append to the community feed
  if (req.method === "POST" && parts[2] && parts[3] === "publish") {
    const body = await req.json().catch(() => ({}));
    const id = parts[2];
    const manifest = {
      id, kind,
      title: (body.title || "Untitled").slice(0, 80),
      author: (body.author || "anonymous").slice(0, 40),
      description: (body.description || "").slice(0, 300),
      character_kind: body.character_kind || null,   // characters: library noun
      created: new Date().toISOString(),
      license: "CC-BY-4.0",                          // marketplace terms
      engine: "fantasy-studio",
    };
    await env.GAMES.put(`${prefix}/${id}/manifest.json`, JSON.stringify(manifest));
    const feed = (await readFeed(env)).filter(i => i.id !== id);
    feed.unshift({ ...manifest,
      url: `${url.origin}/${kind === "game" ? "g" : "c"}/${id}/` });
    await writeFeed(env, feed.slice(0, 500));        // feed caps at 500 items
    return json({ ok: true, url: `${url.origin}/${kind === "game" ? "g" : "c"}/${id}/` });
  }
  return json({ error: "bad request" }, 400);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const parts = url.pathname.split("/").filter(Boolean);
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });

    // ── public file serving ─────────────────────────────────────────────────
    if (parts[0] === "g" || parts[0] === "c") {
      // TRAILING-SLASH REDIRECT (2026-07-08): a directory URL served without a
      // trailing slash makes the browser resolve the hub's relative links one
      // level too high (`/g/id/levels/..` becomes `/g/levels/..` → 404, the
      // "click a level, nothing loads" bug). Redirect directories to add the
      // slash so relative links resolve correctly — standard web-server rule.
      const last = parts[parts.length - 1] || "";
      const isDir = !last.includes(".");
      if (parts[1] && isDir && !url.pathname.endsWith("/")) {
        return Response.redirect(url.origin + url.pathname + "/" + url.search, 301);
      }
    }
    if (parts[0] === "g" && parts[1]) {
      return serveFile(env, "games", parts[1], parts.slice(2).join("/") || "index.html");
    }
    if (parts[0] === "c" && parts[1]) {
      return serveFile(env, "characters", parts[1], parts.slice(2).join("/") || "manifest.json");
    }

    // ── public feed + manifests ─────────────────────────────────────────────
    if (parts[0] === "api" && parts[1] === "feed" && req.method === "GET") {
      return json({ items: await readFeed(env) });
    }
    if (parts[0] === "api" && parts[1] === "games"
        && req.method === "GET" && parts[2] && parts.length === 3) {
      const m = await env.GAMES.get(`games/${parts[2]}/manifest.json`);
      return m ? new Response(m.body, { headers: { "content-type": "application/json", ...CORS } })
               : json({ error: "not found" }, 404);
    }

    // ── authed writes ───────────────────────────────────────────────────────
    if (parts[0] === "api" && ["games", "characters", "items"].includes(parts[1])) {
      if (!authed(req, env)) return json({ error: "unauthorized" }, 401);
      if (parts[1] === "games") return handleKind(req, env, url, parts, "game", "games");
      if (parts[1] === "characters") return handleKind(req, env, url, parts, "character", "characters");
      // moderation / unpublish: drop from the feed (files become unlisted)
      if (parts[1] === "items" && req.method === "DELETE" && parts[2]) {
        await writeFeed(env, (await readFeed(env)).filter(i => i.id !== parts[2]));
        return json({ ok: true, removed: parts[2] });
      }
    }

    return json({ service: "fantasy-studio-share", ok: true });
  },
};
