<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>__TITLE__</title>
<style>
  html,body{margin:0;padding:0;height:100%;overflow:hidden;background:#0b0e12;
            font-family:system-ui,Segoe UI,Arial,sans-serif}
  #app{position:fixed;inset:0}
  #hud{position:fixed;left:12px;top:10px;color:#fff;text-shadow:0 1px 3px rgba(0,0,0,.7);
       user-select:none;pointer-events:none;z-index:5}
  #hud h1{font-size:15px;margin:0 0 2px;font-weight:600;letter-spacing:.3px}
  #hud .hint{font-size:11px;opacity:.75}
  #fps{position:fixed;right:12px;top:10px;color:#9f9;font:11px monospace;
       text-shadow:0 1px 3px rgba(0,0,0,.7);z-index:5}
  #err{position:fixed;inset:auto 12px 12px 12px;display:none;background:#3a1114;
       color:#ffd9d9;border:1px solid #a33;border-radius:8px;padding:10px 12px;
       font:12px monospace;white-space:pre-wrap;z-index:9}
  #obj{position:fixed;left:50%;top:10px;transform:translateX(-50%);color:#ffe9a8;
       font:600 14px system-ui;text-shadow:0 1px 4px rgba(0,0,0,.8);z-index:5;display:none}
  #win{position:fixed;inset:0;display:none;align-items:center;justify-content:center;
       background:rgba(4,8,14,.55);z-index:8}
  #win .card{background:#101826;border:1px solid #3a5;border-radius:14px;padding:28px 40px;
       color:#eaffe9;text-align:center;font-family:system-ui}
  #win h2{margin:0 0 6px;font-size:26px;color:#8f8}
  #stick{position:fixed;left:18px;bottom:18px;width:104px;height:104px;border-radius:50%;
         border:2px solid rgba(255,255,255,.35);display:none;z-index:6;touch-action:none}
  #nub{position:absolute;left:32px;top:32px;width:40px;height:40px;border-radius:50%;
       background:rgba(255,255,255,.45)}
  @media (pointer:coarse){ #stick{display:block} }
</style>
</head>
<body>
<div id="app"></div>
<div id="hud"><h1>__TITLE__</h1><div class="hint">WASD / arrows to move &middot; Shift to run &middot; drag to look</div></div>
<div id="fps"></div>
<div id="err"></div>
<div id="obj"></div>
<div id="win"><div class="card"><h2>You win!</h2><div id="wintext"></div>
<a id="nextlvl" style="display:none;margin-top:14px;padding:8px 22px;border-radius:10px;
background:#7c5cff;color:#fff;text-decoration:none;font-weight:600;display:none">Next level →</a>
<a id="backhub" style="display:none;margin-top:8px;color:#a78bfa;font-size:12px;text-decoration:none">↩ level select</a></div></div>
<div id="stick"><div id="nub"></div></div>
<script type="importmap">
{ "imports": { "three": "./vendor/three.module.js" } }
</script>
<script type="module" src="./game.js"></script>
</body>
</html>
