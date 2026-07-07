// Fantasy Studio share worker — marketplace step 2, the "real link" service.
// Publish a game's dist/ files, get https://<worker>/g/<id>/ that anyone can
// tap and play. Games are static three.js bundles, so serving is pure R2
// reads — no compute, no cold starts that matter, free-tier friendly.
//
// API (Bearer PUBLISH_TOKEN required for writes):
//   POST /api/games                     -> { id }             create a game id
//   PUT  /api/games/:id/files/<path>    (body = file bytes)   upload one file
//   POST /api/games/:id/publish         -> { url }            finalize
//   GET  /g/:id/                        serve index.html
//   GET  /g/:id/<path>                  serve any game file
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

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const parts = url.pathname.split("/").filter(Boolean);

    // ── play routes (public) ────────────────────────────────────────────────
    if (parts[0] === "g" && parts[1]) {
      const id = parts[1];
      const rest = parts.slice(2).join("/") || "index.html";
      const obj = await env.GAMES.get(`games/${id}/${rest}`);
      if (!obj) return new Response("game not found", { status: 404 });
      return new Response(obj.body, {
        headers: {
          "content-type": ctype(rest),
          "cache-control": rest.endsWith(".html") ? "no-cache" : "public, max-age=31536000, immutable",
        },
      });
    }

    // ── api routes ──────────────────────────────────────────────────────────
    if (parts[0] === "api" && parts[1] === "games") {
      // public manifest read
      if (req.method === "GET" && parts[2] && parts.length === 3) {
        const m = await env.GAMES.get(`games/${parts[2]}/manifest.json`);
        return m ? new Response(m.body, { headers: { "content-type": "application/json" } })
                 : json({ error: "not found" }, 404);
      }
      if (!authed(req, env)) return json({ error: "unauthorized" }, 401);

      // create id
      if (req.method === "POST" && parts.length === 2) {
        const id = crypto.randomUUID().slice(0, 8);
        return json({ id });
      }
      // upload one file
      if (req.method === "PUT" && parts[2] && parts[3] === "files") {
        const path = decodeURIComponent(parts.slice(4).join("/"));
        if (!path || path.includes("..")) return json({ error: "bad path" }, 400);
        await env.GAMES.put(`games/${parts[2]}/${path}`, req.body);
        return json({ ok: true, path });
      }
      // publish (write manifest)
      if (req.method === "POST" && parts[2] && parts[3] === "publish") {
        const body = await req.json().catch(() => ({}));
        const manifest = {
          id: parts[2],
          title: body.title || "Fantasy Studio Game",
          author: body.author || "anonymous",
          created: new Date().toISOString(),
          engine: "fantasy-studio",
        };
        await env.GAMES.put(`games/${parts[2]}/manifest.json`, JSON.stringify(manifest));
        return json({ ok: true, url: `${url.origin}/g/${parts[2]}/` });
      }
    }

    return json({ service: "fantasy-studio-share", ok: true });
  },
};
