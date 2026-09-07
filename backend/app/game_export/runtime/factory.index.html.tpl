<!doctype html>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;background:#0a0a12;
            font:13px/1.45 ui-monospace,Menlo,Consolas,monospace;color:#dfe3ee}
  #hud{position:fixed;left:14px;top:12px;z-index:5;background:rgba(8,10,20,.78);
       border:1px solid rgba(120,200,255,.18);border-radius:10px;padding:12px 14px;
       min-width:210px;backdrop-filter:blur(6px)}
  #hud h1{margin:0 0 8px;font-size:14px;letter-spacing:.06em;color:#5ce0d0;font-weight:700}
  .row{display:flex;justify-content:space-between;gap:14px;padding:1px 0}
  .k{color:#7d86a3}
  .v{color:#ffd479;font-variant-numeric:tabular-nums}
  /* seven tools no longer fit at the old size: the bar wrapped onto two lines
     and ran into the hint text in the corner */
  #tools{position:fixed;left:50%;transform:translateX(-50%);bottom:14px;z-index:5;
         display:flex;gap:6px;white-space:nowrap}
  .tool{background:rgba(8,10,20,.82);border:1px solid rgba(120,200,255,.18);
        border-radius:8px;padding:6px 8px;cursor:pointer;user-select:none;
        color:#aeb6cd;white-space:nowrap;font-size:12px}
  .tool.on{border-color:#5ce0d0;color:#5ce0d0;background:rgba(92,224,208,.10)}
  .tool b{display:block;font-size:11px;letter-spacing:.05em}
  .tool small{color:#6b7590}
  #ups{margin-top:10px;border-top:1px solid rgba(120,200,255,.14);padding-top:9px;
       display:flex;flex-direction:column;gap:5px;pointer-events:auto}
  .up{border:1px solid rgba(120,200,255,.13);border-radius:7px;padding:5px 8px;
      cursor:not-allowed;opacity:.5}
  .up b{display:block;font-size:11px;letter-spacing:.05em;color:#aeb6cd}
  .up b span{color:#5d67a0}
  .up small{display:block;color:#6d7590;font-size:10px}
  .up i{font-style:normal;color:#ffd479;font-size:10px}
  .up.can{opacity:1;cursor:pointer;border-color:rgba(92,224,208,.45);
          background:rgba(92,224,208,.07)}
  .up.can:hover{background:rgba(92,224,208,.14)}
  .up.maxed{opacity:.42;border-color:rgba(120,200,255,.09)}
  .up.maxed i{color:#5ce0d0}
  /* the meltdown is the loudest thing in the panel because it is the loudest
     thing in the game: it destroys the factory you just spent an hour on */
  #melt{margin-top:9px;border:1px solid rgba(255,120,90,.5);border-radius:7px;
        padding:6px 8px;background:rgba(255,110,80,.09);cursor:pointer;
        display:none;text-align:center}
  #melt.on{display:block}
  #melt b{display:block;font-size:11px;letter-spacing:.09em;color:#ff9f7a}
  #melt small{display:block;color:#8a7a86;font-size:10px}
  #melt:hover{background:rgba(255,110,80,.18)}
  /* a debt with a clock on it belongs where the counters are, not in a corner */
  #rift{margin-top:9px;border:1px solid rgba(140,110,255,.5);border-radius:7px;
        padding:6px 8px;background:rgba(110,80,255,.10);display:none;text-align:center}
  #rift.on{display:block}
  #rift b{display:block;font-size:11px;letter-spacing:.09em;color:#b39cff}
  #rift small{display:block;color:#8f88b8;font-size:10px}
  /* the factory saves itself; this is the only way back to an empty one */
  #wipe{margin-top:8px;text-align:center;font-size:10px;color:#5d6480;
        cursor:pointer;user-select:none;letter-spacing:.05em}
  #wipe:hover{color:#e8697d}
  /* the ticker sits under the counters: it is a reason to change what you are
     making, so it has to be visible while you are looking at production */
  #tick{margin-top:9px;border-top:1px solid rgba(120,200,255,.14);padding-top:8px}
  #tick .tr{display:flex;justify-content:space-between;gap:14px;font-size:11px;
            line-height:1.55}
  #tick .u{color:#5ce0a0}
  #tick .d{color:#e8697d}
  #hud{pointer-events:auto}
  /* above the bar, not beside it — at seven tools there is no room beside it */
  #hint{position:fixed;right:14px;bottom:74px;z-index:5;color:#6d7590;text-align:right}
  /* the crosshair IS the cursor once the pointer is locked */
  #cross{position:fixed;left:50%;top:50%;width:16px;height:16px;margin:-8px 0 0 -8px;
         z-index:4;pointer-events:none;opacity:.85}
  #cross:before,#cross:after{content:"";position:absolute;background:#8ff3dd;
         box-shadow:0 0 4px rgba(0,0,0,.9)}
  #cross:before{left:7px;top:0;width:2px;height:16px}
  #cross:after{top:7px;left:0;height:2px;width:16px}
  body.overhead #cross{display:none}
  /* while the studio is inspecting, the build bar is not what you are doing */
  body.inspect #tools,body.inspect #hint{opacity:.28;pointer-events:none}
</style>
<div id="hud">
  <h1>CRYSTAL WORKS</h1>
  <div class="row"><span class="k">value</span><span class="v" id="ore">0</span></div>
  <div class="row"><span class="k">ingots</span><span class="v" id="ingot">0</span></div>
  <div class="row"><span class="k">alloys</span><span class="v" id="alloy">0</span></div>
  <div class="row"><span class="k">per minute</span><span class="v" id="rate">0</span></div>
  <div class="row"><span class="k">miners</span><span class="v" id="nmine">0</span></div>
  <div class="row"><span class="k">belts</span><span class="v" id="nbelt">0</span></div>
  <div class="row"><span class="k">smelters</span><span class="v" id="nsmelt">0</span></div>
  <div class="row"><span class="k">on belts</span><span class="v" id="nitem">0</span></div>
  <div class="row"><span class="k">cores</span><span class="v" id="tok">0</span></div>
  <div id="tick"></div>
  <div id="ups"></div>
  <div id="rift"></div>
  <div id="melt"><b>MELTDOWN</b><small>collapse it all for cores</small></div>
  <div id="wipe">new world</div>
</div>
<div id="tools">
  <div class="tool on" data-tool="miner"><b>1 · MINER</b><small>on a node</small></div>
  <div class="tool" data-tool="belt"><b>2 · BELT</b><small>drag to draw</small></div>
  <div class="tool" data-tool="smelter"><b>3 · SMELTER</b><small>2 ore &rarr; 1 ingot</small></div>
  <div class="tool" data-tool="splitter"><b>4 · SPLITTER</b><small>feeds both ways</small></div>
  <div class="tool" data-tool="hub"><b>5 · HUB</b><small>delivers</small></div>
  <div class="tool" data-tool="forge"><b>6 · FORGE</b><small>2 different ores</small></div>
  <div class="tool" data-tool="filter"><b>7 · FILTER</b><small>F to set ore</small></div>
  <div class="tool" data-tool="rift"><b>8 · RIFT</b><small>ore now, pay later</small></div>
  <div class="tool" data-tool="erase"><b>9 · ERASE</b><small>&nbsp;</small></div>
</div>
<div id="cross"></div>
<div id="hint">WASD walk · Shift run · Space jump · click to look<br>hold LMB and sweep to draw belts · TAB overhead<br>point at a filter and press F to change what passes<br>walk over an edge — each side of the world grows a different ore<br>your factory saves itself</div>
<script type="importmap">{"imports":{"three":"./vendor/three.module.js"}}</script>
<script type="module" src="./game.js"></script>
