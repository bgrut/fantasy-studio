# Fantasy Studio Share Worker — real links for published games

One small Cloudflare Worker + R2 bucket = `https://<your-worker>/g/<id>/`
links anyone can tap and play. Free tier covers a LOT of games (R2: 10 GB
storage; Workers: 100k requests/day).

## Deploy (one time, ~10 minutes, needs your Cloudflare account)

```powershell
npm install -g wrangler
cd fantasy-studio/infra/share-worker
wrangler login                                  # opens browser
wrangler r2 bucket create fantasy-studio-games
wrangler secret put PUBLISH_TOKEN               # paste any long random string
wrangler deploy                                 # prints your worker URL
```

## Publish a game manually (until the app button lands)

```powershell
$W = "https://fantasy-studio-share.<you>.workers.dev"
$T = "Bearer <your PUBLISH_TOKEN>"
$id = (Invoke-RestMethod -Method Post -Uri "$W/api/games" -Headers @{Authorization=$T}).id
Get-ChildItem -Recurse -File .\dist | ForEach-Object {
  $rel = $_.FullName.Substring((Resolve-Path .\dist).Path.Length + 1) -replace '\\','/'
  Invoke-RestMethod -Method Put -Uri "$W/api/games/$id/files/$rel" `
    -Headers @{Authorization=$T} -InFile $_.FullName
}
Invoke-RestMethod -Method Post -Uri "$W/api/games/$id/publish" `
  -Headers @{Authorization=$T} -ContentType "application/json" `
  -Body '{"title":"Winterfang","author":"you"}'
# -> { url: "https://<worker>/g/<id>/" }  ← the shareable link
```

## What travels with the link
Everything is baked into the exported files: sound, pause/settings menu,
medals, personal bests (stored in each PLAYER'S browser localStorage —
per-visitor records work on any host), and the Made-with-Fantasy-Studio
stamp. No server round-trips at play time.

## Next (app integration)
A "Publish → get link" button in the desktop app: backend zips nothing —
it PUTs the dist files straight to this worker using FS_SHARE_URL +
FS_SHARE_TOKEN env vars. Community feed = list manifests. Both land with
the marketplace round.
