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
  #tools{position:fixed;left:50%;transform:translateX(-50%);bottom:16px;z-index:5;
         display:flex;gap:9px;white-space:nowrap}
  .tool{cursor:pointer;user-select:none;color:#aeb6cd;white-space:nowrap}
  .tool.on{border-color:#5ce0d0;
           background:linear-gradient(180deg,rgba(26,66,62,.95),rgba(10,24,26,.95));
           box-shadow:0 2px 14px rgba(92,224,208,.28),inset 0 1px 0 rgba(255,255,255,.07)}
  .tool.on b{color:#a8f6e6}
  .tool b{display:block;font-size:11px;letter-spacing:.05em}
  .tool small{color:#6b7590}
  /* THE ICON IS THE LABEL. A row of nine identical boxes reading MINER BELT
     SMELTER is a menu you have to parse every time; a drill, a conveyor and a
     furnace are recognised without reading. Each one is drawn as its machine
     is drawn in the world, in the machine's own colour, so the bar and the
     worldlet agree about what a thing looks like. */
  /* A BAR, NOT A LIST OF COMMANDS. Monospace labels with "1 · MINER" in them
     read as a terminal; a game's build bar is a row of things you recognise by
     picture, with the key as a small badge rather than part of the name. The
     icon is a render of the actual machine — see buildToolIcons(). */
  .tool{display:grid;grid-template-columns:38px auto;align-items:center;
        column-gap:9px;position:relative;padding:8px 12px 8px 9px;
        border-radius:11px;
        background:linear-gradient(180deg,rgba(24,30,52,.92),rgba(10,13,26,.94));
        border:1px solid rgba(120,200,255,.16);
        box-shadow:0 2px 10px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.05);
        transition:transform .12s,border-color .12s,box-shadow .12s}
  .tool:hover{transform:translateY(-2px);border-color:rgba(120,200,255,.4)}
  .tool svg,.tool .ico{width:38px;height:38px;grid-row:1 / span 2;
        display:block;color:#5ce0d0}
  .tool .ico{filter:drop-shadow(0 2px 3px rgba(0,0,0,.55))}
  .tool b,.tool small{grid-column:2}
  .tool b{font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
          font-size:11.5px;font-weight:650;letter-spacing:.07em;color:#dfe6f5}
  .tool small{font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
              font-size:10px;letter-spacing:.01em;color:#7b86a6}
  /* the shortcut is a badge in the corner, not part of the machine's name */
  .tool .key{position:absolute;top:-6px;left:-6px;width:17px;height:17px;
             border-radius:6px;background:#1b2340;border:1px solid rgba(120,200,255,.3);
             color:#8fa3cc;font-style:normal;font-size:10px;line-height:15px;
             text-align:center;font-variant-numeric:tabular-nums}
  .tool.on .key{background:#12463f;border-color:#5ce0d0;color:#8ff3dd}
  .tool[data-tool="miner"] svg{color:#ff5d73}
  .tool[data-tool="belt"] svg{color:#3ad39a}
  .tool[data-tool="smelter"] svg{color:#8c6bff}
  .tool[data-tool="splitter"] svg{color:#4bb5ff}
  .tool[data-tool="hub"] svg{color:#ffc75a}
  .tool[data-tool="forge"] svg{color:#d94fb0}
  .tool[data-tool="filter"] svg{color:#2fd6b0}
  .tool[data-tool="rift"] svg{color:#9b7cff}
  .tool[data-tool="erase"] svg{color:#e8697d}
  .tool.locked svg{color:#5b6480}
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
  /* the objective sits directly under the counters it is asking you to move */
  #goal{margin-top:9px;border:1px solid rgba(255,212,121,.34);border-radius:7px;
        padding:6px 8px;background:rgba(255,212,121,.07)}
  #goal b{display:block;font-size:11px;letter-spacing:.07em;color:#ffd479}
  #goal small{display:block;color:#8d8564;font-size:10px}
  /* where you are, and where you could go. Locked rows stay visible with their
     price on them: a destination you cannot afford yet is the reason to melt
     the factory down again. */
  #world{margin-top:9px;border-top:1px solid rgba(120,200,255,.14);padding-top:8px}
  #world b{display:block;font-size:11px;letter-spacing:.06em;color:#9fd6ff}
  #world small{display:block;color:#6d7590;font-size:10px;margin-bottom:5px}
  #world .wr{display:flex;justify-content:space-between;gap:10px;font-size:10px;
             color:#5d6480;padding:2px 0}
  #world .wr span{color:#4e5674}
  #world .wr.can{color:#9fd6ff;cursor:pointer}
  #world .wr.can span{color:#5ce0d0}
  #world .wr.can:hover{color:#5ce0d0}
  .tool.locked{opacity:.3}
  .tool.locked b{color:#6b7590}
  .tool.deny{border-color:#e8697d;background:rgba(232,105,125,.16)}
  /* an unlock is worth a beat of the screen; it is the only reward here that
     is not a number going up */
  #toast{position:fixed;left:50%;transform:translateX(-50%);bottom:96px;z-index:6;
         background:rgba(8,10,20,.92);border:1px solid rgba(92,224,208,.5);
         border-radius:9px;padding:9px 16px;color:#5ce0d0;letter-spacing:.05em;
         opacity:0;transition:opacity .25s;pointer-events:none}
  #toast.on{opacity:1}
  /* THE PANEL KEEPS GROWING (2026-09-08). Counters, then a ticker, then a goal,
     then a world list — it now runs off the bottom of the screen and collides
     with the tool bar. Capped and scrollable, so the next feature to land in
     here does not push something off the screen instead. */
  #hud{pointer-events:auto;max-height:calc(100vh - 128px);overflow-y:auto;
       scrollbar-width:thin;scrollbar-color:rgba(120,200,255,.28) transparent}
  #hud::-webkit-scrollbar{width:6px}
  #hud::-webkit-scrollbar-thumb{background:rgba(120,200,255,.28);border-radius:3px}
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
  <div id="world"></div>
  <div id="goal"></div>
  <div id="tick"></div>
  <div id="ups"></div>
  <div id="rift"></div>
  <div id="melt"><b>MELTDOWN</b><small>collapse it all for cores</small></div>
  <div id="wipe">new world</div>
</div>
<div id="tools">
  <div class="tool on" data-tool="miner"><svg viewBox="0 0 24 24"><path d="M4 20h16M6 20V9M18 20V9M6 9h12M8 9V6M16 9V6M8 6h8" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round"/><path d="M12 20v-6l-2-3h4l-2 3" fill="currentColor"/></svg><i class="key">1</i><b>MINER</b><small>on a node</small></div>
  <div class="tool" data-tool="belt"><svg viewBox="0 0 24 24"><rect x="2.5" y="9" width="19" height="6" rx="3" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="6" cy="12" r="1.6" fill="currentColor"/><circle cx="18" cy="12" r="1.6" fill="currentColor"/><path d="M10 9.5l2 2.5-2 2.5M13.5 9.5l2 2.5-2 2.5" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg><i class="key">2</i><b>BELT</b><small>drag to draw</small></div>
  <div class="tool" data-tool="smelter"><svg viewBox="0 0 24 24"><path d="M5 20V9h14v11z" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M4 9h16" stroke="currentColor" stroke-width="1.7"/><path d="M15 9V4h3v5" stroke="currentColor" stroke-width="1.7" fill="none"/><rect x="9" y="13" width="6" height="5" fill="currentColor"/></svg><i class="key">3</i><b>SMELTER</b><small>2 ore &rarr; 1 ingot</small></div>
  <div class="tool" data-tool="splitter"><svg viewBox="0 0 24 24"><path d="M12 3v18M3 12h18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="12" r="3.6" stroke="currentColor" stroke-width="1.7" fill="none"/></svg><i class="key">4</i><b>SPLITTER</b><small>feeds both ways</small></div>
  <div class="tool" data-tool="hub"><svg viewBox="0 0 24 24"><ellipse cx="12" cy="17" rx="9" ry="4" stroke="currentColor" stroke-width="1.7" fill="none"/><ellipse cx="12" cy="17" rx="4.5" ry="2" stroke="currentColor" stroke-width="1.4" fill="none"/><path d="M12 15V5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="12" cy="4" r="2" fill="currentColor"/></svg><i class="key">5</i><b>HUB</b><small>delivers</small></div>
  <div class="tool" data-tool="forge"><svg viewBox="0 0 24 24"><path d="M6 20V8h12v12z" stroke="currentColor" stroke-width="1.7" fill="none"/><ellipse cx="12" cy="8" rx="6" ry="2.4" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M9 4l1.5 3M15 4l-1.5 3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="12" cy="15" r="2.6" fill="currentColor"/></svg><i class="key">6</i><b>FORGE</b><small>2 different ores</small></div>
  <div class="tool" data-tool="filter"><svg viewBox="0 0 24 24"><path d="M3 5h18l-7 8v6l-4 2v-8z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/></svg><i class="key">7</i><b>FILTER</b><small>F to set ore</small></div>
  <div class="tool" data-tool="rift"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="12" cy="12" r="3.4" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M12 4v3M12 17v3M4 12h3M17 12h3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg><i class="key">8</i><b>RIFT</b><small>ore now, pay later</small></div>
  <div class="tool" data-tool="erase"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><i class="key">9</i><b>ERASE</b><small>&nbsp;</small></div>
</div>
<div id="toast"></div>
<div id="cross"></div>
<div id="hint">WASD walk · Shift run · Space jump · click to look<br>hold LMB and sweep to draw belts · TAB overhead<br>point at a filter and press F to change what passes<br>walk over an edge — each side of the world grows a different ore<br>your factory saves itself</div>
<script type="importmap">{"imports":{"three":"./vendor/three.module.js"}}</script>
<script type="module" src="./game.js"></script>
