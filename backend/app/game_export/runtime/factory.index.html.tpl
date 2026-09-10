<!doctype html>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;background:#0a0a12;
            font:13px/1.45 ui-monospace,Menlo,Consolas,monospace;color:#dfe3ee}
  /* ONE LANGUAGE. The tool bar became chips with rendered icons and a sans face
     while this panel stayed a stack of monospace boxes, and the two together
     read as two different products. Same cards, same gradients, same faces —
     numbers stay monospace, because numbers should line up. */
  /* ONE TYPE SYSTEM, SHIPPED. Three faces under the SIL Open Font License,
     in vendor/fonts with the game, so it looks the same on every machine and
     needs no network. Condensed for what is named, Barlow for what is read,
     Plex Mono for what is counted. */
  @font-face{font-family:"Bricolage Grotesque";font-weight:200 800;font-stretch:75% 100%;font-display:swap;src:url(vendor/fonts/BricolageGrotesque-Variable.ttf) format("truetype")}
  @font-face{font-family:"Instrument Sans";font-weight:400 700;font-stretch:75% 100%;font-display:swap;src:url(vendor/fonts/InstrumentSans-Variable.ttf) format("truetype")}
  @font-face{font-family:"DM Mono";font-weight:300;font-display:swap;src:url(vendor/fonts/DMMono-Light.ttf) format("truetype")}
  @font-face{font-family:"DM Mono";font-weight:400;font-display:swap;src:url(vendor/fonts/DMMono-Regular.ttf) format("truetype")}
  @font-face{font-family:"DM Mono";font-weight:500;font-display:swap;src:url(vendor/fonts/DMMono-Medium.ttf) format("truetype")}
  :root{--f-head:"Bricolage Grotesque","Instrument Sans",system-ui,sans-serif;
        --f-ui:"Instrument Sans",system-ui,sans-serif;
        --f-mono:"DM Mono",ui-monospace,monospace}
  body{font-family:var(--f-ui)}
  #hud{position:fixed;left:14px;top:12px;z-index:5;
       background:linear-gradient(180deg,rgba(18,23,42,.90),rgba(8,10,20,.90));
       border:1px solid rgba(120,200,255,.16);border-radius:14px;padding:12px 14px;
       min-width:224px;backdrop-filter:blur(8px);
       max-height:calc(100vh - 110px);overflow-y:auto;scrollbar-width:none;
       box-shadow:0 6px 24px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.05)}
  #hud::-webkit-scrollbar{display:none}
  /* the panel says what it is */
  .st small{display:block;font-family:var(--f-ui);font-size:8px;letter-spacing:.04em;color:#6d7590;line-height:1;margin-top:1px}
  .sec{margin:10px 0 4px;font-family:var(--f-head);font-size:10px;font-weight:700;letter-spacing:.08em;color:#8d95b3}
  .sec span{font-family:var(--f-ui);font-weight:400;letter-spacing:0;color:#5d6480;margin-left:6px;font-size:9.5px}
  .up em{display:block;font-style:normal;font-family:var(--f-ui);font-size:8.5px;color:#7b86a6;margin-top:3px;line-height:1.2}
  /* the look label: whatever is under the crosshair, named */
  #look{position:fixed;left:50%;top:55%;transform:translateX(-50%);z-index:6;pointer-events:none;
        font-family:var(--f-mono);font-size:11px;letter-spacing:.06em;color:#dfe8ff;white-space:nowrap;
        padding:4px 10px;border-radius:6px;background:rgba(10,12,22,.62);border:1px solid rgba(255,255,255,.08);
        opacity:0;transition:opacity .15s}
  #look.on{opacity:1}
  /* the foreman: one step at a time, at the top, with the reason */
  #tutor{position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:8;width:min(560px,80vw);
         padding:12px 16px 12px;border-radius:12px;border:1px solid rgba(255,212,121,.45);
         background:linear-gradient(180deg,rgba(28,24,14,.96),rgba(12,10,8,.96));box-shadow:0 8px 30px rgba(0,0,0,.5);
         opacity:0;pointer-events:none;transform:translate(-50%,-8px);transition:opacity .25s,transform .25s}
  #tutor.on{opacity:1;pointer-events:auto;transform:translate(-50%,0)}
  #tutor em{display:block;font-style:normal;font-family:var(--f-mono);font-size:9px;letter-spacing:.16em;color:#a0865a;margin-bottom:4px}
  #tutor b{display:block;font-family:var(--f-head);font-size:18px;font-weight:700;letter-spacing:.02em;color:#ffd479}
  #tutor small{display:block;font-family:var(--f-ui);font-size:12.5px;color:#f1e6c8;margin-top:4px;line-height:1.35}
  #tutor p{margin:6px 0 0;font-family:var(--f-ui);font-size:11px;color:#a89a72;line-height:1.35}
  #tutor .skip{position:absolute;right:14px;top:10px;font-family:var(--f-mono);font-size:9px;letter-spacing:.12em;color:#8d7f5c;cursor:pointer}
  #tutor .skip:hover{color:#ffd479}
  /* the tool a step wants pulses in the bar */
  .tool.hint{border-color:#ffd479;animation:hint 1.1s ease-in-out infinite}
  @keyframes hint{0%,100%{box-shadow:0 0 0 0 rgba(255,212,121,0)}50%{box-shadow:0 0 0 5px rgba(255,212,121,.35)}}
  body:has(#title.on) #tutor,body:has(#title.on) #look{opacity:0 !important}
  #hud h1{margin:0 0 7px;font-size:15px;letter-spacing:.08em;color:#8ff3dd;
          font-weight:700;font-variation-settings:"opsz" 24;
          font-family:var(--f-head)}
  .k{font-family:var(--f-ui);font-weight:500;
     letter-spacing:.02em}
  .row{display:flex;justify-content:space-between;gap:14px;padding:1px 0}
  .k{color:#7d86a3}
  .v{color:#ffd479;font-variant-numeric:tabular-nums;font-family:var(--f-mono)}
  /* seven tools no longer fit at the old size: the bar wrapped onto two lines
     and ran into the hint text in the corner */
  #tools{position:fixed;left:50%;transform:translateX(-50%);bottom:16px;z-index:5;
         display:flex;gap:7px;white-space:nowrap;max-width:calc(100vw - 24px)}
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
  .tool{display:grid;grid-template-columns:34px auto;align-items:center;
        column-gap:9px;position:relative;padding:8px 12px 8px 9px;
        border-radius:11px;
        background:linear-gradient(180deg,rgba(24,30,52,.92),rgba(10,13,26,.94));
        border:1px solid rgba(120,200,255,.16);
        box-shadow:0 2px 10px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.05);
        transition:transform .12s,border-color .12s,box-shadow .12s}
  .tool:hover{transform:translateY(-2px);border-color:rgba(120,200,255,.4)}
  .tool svg,.tool .ico{width:34px;height:34px;grid-row:1 / span 2;
        display:block;color:#5ce0d0}
  .tool .ico{filter:drop-shadow(0 2px 3px rgba(0,0,0,.55))}
  .tool b,.tool small{grid-column:2}
  .tool b{font-family:var(--f-head);
          font-size:12.5px;font-weight:700;letter-spacing:.05em;color:#dfe6f5}
  .tool small{font-family:var(--f-ui);
              font-size:9.5px;letter-spacing:0;color:#7b86a6}
  /* nine tools have to fit: the descriptions step out below 1360px and the
     names carry the bar on their own */
  @media (max-width:1360px){.tool small{display:none}.tool b{grid-row:1 / span 2}}
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
  .up{border:1px solid rgba(120,200,255,.13);border-radius:10px;padding:7px 9px;
      background:linear-gradient(180deg,rgba(255,255,255,.03),rgba(0,0,0,.12));
      cursor:not-allowed;opacity:.5}
  .up b{display:block;font-size:11.5px;letter-spacing:.05em;color:#c9d2e8;
        font-family:var(--f-head);
        font-weight:700}
  .up b span{color:#5d67a0}
  .up small{display:block;color:#7b86a6;font-size:10px;
            font-family:var(--f-ui)}
  .up i{font-style:normal;color:#ffd479;font-size:10px}
  .up.can{opacity:1;cursor:pointer;border-color:rgba(92,224,208,.45);
          background:rgba(92,224,208,.07)}
  .up.can:hover{background:rgba(92,224,208,.14)}
  .up.maxed{opacity:.42;border-color:rgba(120,200,255,.09)}
  .up.maxed i{color:#5ce0d0}
  /* the meltdown is the loudest thing in the panel because it is the loudest
     thing in the game: it destroys the factory you just spent an hour on */
  #melt{margin-top:9px;border:1px solid rgba(255,120,90,.5);border-radius:10px;
        padding:8px 10px;cursor:pointer;display:none;text-align:center;
        background:linear-gradient(180deg,rgba(255,110,80,.18),rgba(255,110,80,.06));
        font-family:var(--f-ui)}
  #melt.on{display:block}
  #melt b{display:block;font-size:13px;letter-spacing:.06em;color:#ff9f7a;font-family:var(--f-head);font-weight:700}
  #melt small{display:block;color:#8a7a86;font-size:10px}
  #melt:hover{background:rgba(255,110,80,.18)}
  /* a debt with a clock on it belongs where the counters are, not in a corner */
  #rift{margin-top:9px;border:1px solid rgba(140,110,255,.5);border-radius:10px;
        padding:8px 10px;display:none;text-align:center;
        background:linear-gradient(180deg,rgba(110,80,255,.18),rgba(110,80,255,.06));
        font-family:var(--f-ui)}
  #rift.on{display:block}
  #rift b{display:block;font-size:13px;letter-spacing:.06em;color:#b39cff;font-family:var(--f-head);font-weight:700}
  #rift small{display:block;color:#8f88b8;font-size:10px}
  /* the factory saves itself; this is the only way back to an empty one */
  #wipe{margin-top:8px;text-align:center;font-size:10px;color:#5d6480;
        cursor:pointer;user-select:none;letter-spacing:.05em}
  #wipe:hover{color:#e8697d}
  #motion{margin-top:4px;text-align:center;font-size:10px;color:#5d6480;cursor:pointer;letter-spacing:.06em}
  #motion:hover{color:#9fd6ff}
  #share{margin-top:4px;text-align:center;font-size:10px;color:#5d6480;cursor:pointer;letter-spacing:.06em}
  #share:hover{color:#5cffc9}
  /* reduced motion: nothing settles, slides or pulses in the chrome either */
  body.reduced #title b{transition:none;transform:none}
  body.reduced #facecap,body.reduced #toast,body.reduced .tool{transition:none}
  /* the core counter pops when a meltdown pays */
  @keyframes won{0%{transform:scale(1)}30%{transform:scale(1.7);color:#fff3c4}100%{transform:scale(1)}}
  #tok.won{display:inline-block;animation:won .9s cubic-bezier(.2,.8,.2,1)}
  body.reduced #tok.won{animation:none}
  /* photo mode: the chrome steps out of the frame */
  body.photo #hud,body.photo #tools,body.photo #hint,body.photo #toast,body.photo #cross{opacity:0;pointer-events:none;transition:opacity .25s}
  #wipe span{display:inline-block;margin:0 5px;padding:3px 9px;border-radius:6px;
             border:1px solid rgba(255,255,255,.14);color:#d7dcec;letter-spacing:.08em}
  #wipe span:hover{border-color:#5cffc9;color:#5cffc9}
  #wipe span[data-mode="creative"]:hover{border-color:#ffd479;color:#ffd479}
  #wipe small{display:block;margin-top:5px;color:#5d6480;font-size:9px}
  /* a creative world says so, on every frame, so a screenshot cannot pass for
     a survival run */
  #hud h1::after{content:"CREATIVE";display:none;margin-left:10px;padding:2px 7px;border-radius:5px;
                 font-size:9px;letter-spacing:.14em;vertical-align:middle;
                 color:#1a1408;background:#ffd479}
  body.creative #hud h1::after{display:inline-block}
  /* the ticker sits under the counters: it is a reason to change what you are
     making, so it has to be visible while you are looking at production */
  #tick{margin-top:9px;border-top:1px solid rgba(120,200,255,.14);padding-top:8px}
  #tick .tr{display:flex;justify-content:space-between;gap:14px;font-size:11px;
            line-height:1.55}
  #tick .u{color:#5ce0a0}
  #tick .d{color:#e8697d}
  /* the objective sits directly under the counters it is asking you to move */
  #goal{margin-top:9px;border:1px solid rgba(255,212,121,.34);border-radius:10px;
        padding:8px 10px;
        background:linear-gradient(180deg,rgba(255,212,121,.12),rgba(255,212,121,.04))}
  #goal b{display:block;font-size:14px;letter-spacing:.09em;color:#ffd479;font-family:var(--f-head);font-weight:600;
          font-family:var(--f-ui);
          font-weight:700}
  #goal small{display:block;color:#a89a72;font-size:10px;
              font-family:var(--f-ui)}
  /* where you are, and where you could go. Locked rows stay visible with their
     price on them: a destination you cannot afford yet is the reason to melt
     the factory down again. */
  #world{margin-top:9px;border-top:1px solid rgba(120,200,255,.14);padding-top:8px}
  #world b{font-family:var(--f-head);display:block;font-size:11px;letter-spacing:.08em;color:#9fd6ff;
           font-family:var(--f-ui);
           font-weight:700}
  #world small{display:block;color:#6d7590;font-size:10px;margin-bottom:5px}
  #world .wr{display:flex;justify-content:space-between;gap:10px;font-size:10px;
             color:#5d6480;padding:2px 0;
             font-family:var(--f-ui)}
  #world .wr b{font-weight:normal;display:inline-flex;align-items:center;gap:6px}
  #world .wr:not(.can) b{opacity:.6}   /* a locked world is a dimmer place */
  #world .wr .sw{width:11px;height:11px;border-radius:3px;flex:none;
                 box-shadow:inset 0 0 0 1px rgba(255,255,255,.18),0 0 6px rgba(0,0,0,.4)}
  #world .wr span{color:#4e5674}
  #world .wr.can{color:#9fd6ff;cursor:pointer}
  #world .wr.can span{color:#5ce0d0}
  #world .wr.can:hover{color:#5ce0d0}
  .tool.locked{opacity:.3}
  .tool.locked b{color:#6b7590}
  .tool.deny{border-color:#e8697d;background:rgba(232,105,125,.16)}
  /* an unlock is worth a beat of the screen; it is the only reward here that
     is not a number going up */
  #toast{position:fixed;left:50%;transform:translateX(-50%);bottom:104px;z-index:6;
         background:linear-gradient(180deg,rgba(18,23,42,.96),rgba(8,10,20,.96));
         border:1px solid rgba(92,224,208,.5);
         border-radius:11px;padding:10px 18px;color:#8ff3dd;letter-spacing:.06em;
         font-family:var(--f-ui);
         font-weight:650;box-shadow:0 6px 24px rgba(0,0,0,.5);
         opacity:0;transition:opacity .25s;pointer-events:none}
  #toast.on{opacity:1}
  /* the name of the place, over the reveal. Large, centred, and gone the
     moment the player does anything — a title that lingers over play is a
     watermark. */
  #title{position:fixed;left:0;right:0;top:34%;z-index:7;text-align:center;
         pointer-events:none;opacity:0;transition:opacity .6s}
  #title.on{opacity:1}
  /* A NAME WITH WEIGHT. A display face — system ones, since the demo ships no
     fonts — a rule above and below, and a settle in scale so the name ARRIVES
     rather than appears. The rules are what make it a title card and not a
     caption. */
  #title b{display:block;font-size:56px;line-height:1;letter-spacing:.12em;color:#f4f8ff;
           padding:0 .2em 0 .3em;
           font-family:var(--f-head);font-variation-settings:"opsz" 96;
           font-weight:700;text-transform:uppercase;
           text-shadow:0 0 34px rgba(92,224,208,.55),0 6px 22px rgba(0,0,0,.85);
           transform:scale(1.05);transition:transform 1.8s cubic-bezier(.2,.7,.2,1)}
  #title.on b{transform:scale(1)}
  #title b::before,#title b::after{content:"";display:block;height:1px;margin:0 auto 14px;
           width:min(46vw,520px);
           background:linear-gradient(90deg,transparent,rgba(159,214,255,.8),transparent)}
  #title b::after{margin:14px auto 0}
  /* EACH WORLD IN ITS OWN VOICE: the family picks the face, the tracking, the
     glow and the rule colour. The void keeps the clean face above. */
  #title{--tcol:#f4f8ff;--tglow:rgba(92,224,208,.55);--rule:rgba(159,214,255,.8);--sub:#9fd6ff}
  #title[data-mood="warm"]{--tcol:#ffe1c2;--tglow:rgba(255,122,50,.65);--rule:rgba(255,154,92,.85);--sub:#ffb27a}
  #title[data-mood="cold"]{--tcol:#f2f8ff;--tglow:rgba(160,210,255,.6);--rule:rgba(207,232,255,.85);--sub:#cfe8ff}
  #title[data-mood="green"]{--tcol:#e2ffe6;--tglow:rgba(120,230,150,.55);--rule:rgba(143,230,160,.85);--sub:#a8f0b6}
  #title b{color:var(--tcol);text-shadow:0 0 34px var(--tglow),0 6px 22px rgba(0,0,0,.85)}
  #title b::before,#title b::after{background:linear-gradient(90deg,transparent,var(--rule),transparent)}
  #title[data-mood="warm"] b{font-family:var(--f-head);font-stretch:78%;
           font-weight:800;letter-spacing:.03em;font-size:68px}
  #title[data-mood="cold"] b{font-family:var(--f-head);
           font-weight:300;letter-spacing:.42em;font-size:46px}
  #title[data-mood="green"] b{font-family:var(--f-head);
           font-weight:500;text-transform:none;letter-spacing:.08em;font-size:58px}
  /* the face caption after a crossing */
  /* high, above the placement ghost, and big enough to read in the beat it is up */
  #facecap{position:fixed;left:0;right:0;top:12%;text-align:center;z-index:6;pointer-events:none;
           font-family:var(--f-mono);font-size:13px;letter-spacing:.42em;
           color:#eef4ff;text-shadow:0 0 18px rgba(92,224,208,.6),0 2px 12px rgba(0,0,0,.95);opacity:0;transform:translateY(6px);
           transition:opacity .35s,transform .35s}
  #facecap.on{opacity:.9;transform:translateY(0)}
  #title small{display:block;margin-top:14px;font-size:12px;letter-spacing:.3em;font-family:var(--f-mono);
           text-transform:uppercase;color:var(--sub);
           font-family:var(--f-ui);
           text-shadow:0 2px 10px rgba(0,0,0,.8)}
  /* the HUD steps back while the card is up; it is not the subject yet */
  body:has(#title.on) #hud,body:has(#title.on) #tools,body:has(#title.on) #hint{opacity:.12}
  /* THE PANEL KEEPS GROWING (2026-09-08). Counters, then a ticker, then a goal,
     then a world list — it now runs off the bottom of the screen and collides
     with the tool bar. Capped and scrollable, so the next feature to land in
     here does not push something off the screen instead. */
  #hud{pointer-events:auto;max-height:calc(100vh - 128px);overflow-y:auto;
       scrollbar-width:thin;scrollbar-color:rgba(120,200,255,.28) transparent}
  #hud::-webkit-scrollbar{width:6px}
  #hud::-webkit-scrollbar-thumb{background:rgba(120,200,255,.28);border-radius:3px}
  /* ── the redesigned panel ──────────────────────────────────────────────── */
  #hud{min-width:236px;width:236px;padding:12px 12px 10px}
  .hero{position:relative;padding:2px 0 4px}
  .hero .big{display:flex;align-items:baseline;gap:8px}
  .hero .big span{font-family:var(--f-mono);font-size:34px;font-weight:500;letter-spacing:-.03em;color:#ffd479;
                  font-variant-numeric:tabular-nums;line-height:1;
                  text-shadow:0 0 18px rgba(255,212,121,.35)}
  .hero .big small{font-family:var(--f-head);font-size:12px;color:#8d8564;letter-spacing:.16em;text-transform:uppercase;
                   font-family:var(--f-ui)}
  .hero .rate{margin-top:4px;font-size:12px;color:#8ff3dd;display:flex;align-items:baseline;gap:5px}
  .hero .rate b{font-variant-numeric:tabular-nums;font-weight:500;font-family:var(--f-mono)}
  .hero .rate small{color:#5d6480;font-family:var(--f-ui)}
  #spark{display:block;width:100%;height:38px;margin-top:6px;border-radius:6px;
         background:rgba(0,0,0,.18)}
  .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin-top:9px}
  .st{display:flex;align-items:center;gap:5px;padding:4px 6px;border-radius:8px;
      background:linear-gradient(180deg,rgba(255,255,255,.035),rgba(0,0,0,.14));
      border:1px solid rgba(120,200,255,.10)}
  .st i{width:20px;height:20px;flex:0 0 20px;border-radius:5px;display:block;
        background-size:contain;background-repeat:no-repeat;background-position:center}
  .st b{font-size:12px;color:#dfe6f5;font-variant-numeric:tabular-nums}
  .st.core{grid-column:span 2;border-color:rgba(255,212,121,.35);
           background:linear-gradient(180deg,rgba(255,212,121,.12),rgba(255,212,121,.03))}
  .st.core b{color:#ffd479}
  /* the goal shows how far along it is */
  #goal em{float:right;font-style:normal;font-size:10px;letter-spacing:.12em;color:#8d7f5c;font-family:var(--f-mono)}
  #goal .held{display:block;margin-top:4px;font-size:10px;letter-spacing:.06em;color:#c9b27a;font-variant-numeric:tabular-nums;font-family:var(--f-mono)}
  /* a contract is a clock: it sits under the goal in the market's violet, with
     its own bar and its own countdown */
  #contract{display:none;margin-top:8px;border:1px solid rgba(140,110,255,.4);border-radius:10px;padding:8px 10px;
            background:linear-gradient(180deg,rgba(110,80,255,.14),rgba(110,80,255,.04))}
  #contract.on{display:block}
  #contract b{display:block;font-family:var(--f-head);font-size:13px;letter-spacing:.05em;color:#c9b8ff;font-weight:700}
  #contract small{display:block;color:#8f88b8;font-size:10px;margin-top:2px}
  #contract .bar{height:4px;margin-top:7px;border-radius:2px;background:rgba(140,110,255,.16);overflow:hidden}
  #contract .bar i{display:block;height:100%;background:linear-gradient(90deg,#b39cff,#5ce0d0);transition:width .3s}
  #contract .left{display:block;margin-top:4px;font-family:var(--f-mono);font-size:10px;letter-spacing:.06em;color:#b39cff}
  /* a standing order is the contract card in gold: a rate to be held */
  #standing{display:none;margin-top:8px;border:1px solid rgba(255,212,121,.45);border-radius:10px;padding:8px 10px;
            background:linear-gradient(180deg,rgba(255,212,121,.14),rgba(255,212,121,.04))}
  #standing.on{display:block}
  #standing.short{border-color:rgba(255,120,90,.7)}
  #standing b{display:block;font-family:var(--f-head);font-size:13px;letter-spacing:.05em;color:#ffd479;font-weight:700}
  #standing small{display:block;color:#a89a72;font-size:10px;margin-top:2px}
  #standing .bar{height:4px;margin-top:7px;border-radius:2px;background:rgba(255,212,121,.16);overflow:hidden}
  #standing .bar i{display:block;height:100%;background:linear-gradient(90deg,#ffd479,#5ce0d0);transition:width .3s}
  #standing.short .bar i{background:linear-gradient(90deg,#ff9f7a,#ffd479)}
  #standing .left{display:block;margin-top:4px;font-family:var(--f-mono);font-size:10px;letter-spacing:.06em;color:#c9b27a}
  /* the rival buyer: white, because it is not ours, and it drains left to right */
  #rival{display:none;margin-top:8px;border:1px solid rgba(255,255,255,.35);border-radius:10px;padding:8px 10px;
         background:linear-gradient(180deg,rgba(255,255,255,.10),rgba(255,255,255,.03))}
  #rival.on{display:block}
  #rival b{display:block;font-family:var(--f-head);font-size:13px;letter-spacing:.05em;color:#f4f8ff;font-weight:700}
  #rival small{display:block;color:#9aa3bf;font-size:10px;margin-top:2px}
  #rival .bar{height:4px;margin-top:7px;border-radius:2px;background:rgba(255,255,255,.12);overflow:hidden}
  #rival .bar i{display:block;height:100%;background:linear-gradient(90deg,#ffffff,#9fd6ff);transition:width .4s linear}
  #tick .mk.hot .px{color:#fff;text-shadow:0 0 8px rgba(255,255,255,.8)}
  #tick .mk.hot .nm{color:#fff}
  /* rank and shards, under the rate */
  #rank{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;margin-top:3px;font-size:10px;letter-spacing:.14em}
  #rank i{display:block;width:100%;font-style:normal;font-family:var(--f-mono);font-size:8.5px;letter-spacing:.1em;color:#8d7f5c;margin-top:2px}
  #rank b{font-family:var(--f-head);font-weight:600;color:#8d8564}
  #rank span{font-family:var(--f-mono);color:#ffd479;letter-spacing:.1em}
  #goal .bar{height:4px;margin-top:7px;border-radius:2px;background:rgba(255,212,121,.14);overflow:hidden}
  #goal .bar i{display:block;height:100%;background:linear-gradient(90deg,#ffd479,#ff9a5c);
               border-radius:2px;transition:width .4s;box-shadow:0 0 8px rgba(255,212,121,.6)}
  /* the market is four bars, not four numbers */
  #tick{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;align-items:end;height:64px}
  #tick .mk{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;
            height:100%;gap:3px;font-size:9.5px;
            font-family:var(--f-ui)}
  /* each bar rises from, or hangs below, a baseline at 1.0 */
  #tick .mk .pole{position:relative;width:100%;height:38px}
  #tick .mk .pole::before{content:"";position:absolute;left:0;right:0;top:19px;height:1px;
                          background:rgba(200,220,255,.28)}
  #tick .mk .bar{position:absolute;left:0;right:0;border-radius:3px;min-height:2px;
                 transition:height .5s;box-shadow:inset 0 1px 0 rgba(255,255,255,.18)}
  #tick .mk .bar.pos{bottom:19px}
  #tick .mk .bar.neg{top:20px;opacity:.7}
  #tick .mk .px{font-family:var(--f-mono);font-variant-numeric:tabular-nums;
                font-size:10px;color:#c9d2e8}
  #tick .mk .nm{color:#6d7590;letter-spacing:.04em}
  #tick .mk.u .px{color:#5ce0a0}
  #tick .mk.d .px{color:#e8697d}
  /* upgrades are a row of three; level is pips */
  #ups{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:9px;
       border-top:1px solid rgba(120,200,255,.14);padding-top:9px}
  .up{padding:7px 6px 6px;text-align:center;cursor:default}
  .up b{font-size:9.5px;letter-spacing:.06em}
  .up b span{display:none}
  .up small{display:none}
  .up i{display:block;margin-top:5px;font-size:9.5px}
  .up .pips{display:flex;justify-content:center;gap:2px;margin-top:5px}
  .up .pips s{display:block;width:8px;height:4px;border-radius:2px;background:rgba(120,200,255,.14);
              text-decoration:none}
  .up .pips s.on{background:#5ce0d0;box-shadow:0 0 5px rgba(92,224,208,.7)}
  .up.can{cursor:pointer}
  .up.can:hover{transform:translateY(-1px)}
  /* above the bar, not beside it — at seven tools there is no room beside it */
  /* centred above the bar: at bottom-right it sat on top of the held tool's hologram */
  #hint{font-family:var(--f-mono);position:fixed;left:50%;transform:translateX(-50%);bottom:84px;z-index:5;color:#6d7590;text-align:center;white-space:nowrap}
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
  <div class="hero">
    <div class="big" title="Value is what your hubs have banked. Upgrades are bought with it."><span id="ore">0</span><small>value banked</small></div>
    <div class="rate" title="What your hubs sell in a minute. Rate goals ask you to hold this."><b id="rate">0</b><small>a minute, to your hubs</small></div>
    <div id="rank"><b>UNRANKED</b><span>◇◇◇</span></div>
    <canvas id="spark" width="216" height="38"></canvas>
  </div>
  <div class="stats">
    <div class="st" data-ico="miner"   title="Rigs standing on seams. Each one pulls ore out of its seam."><i></i><b id="nmine">0</b><small>rigs</small></div>
    <div class="st" data-ico="belt"    title="Belt tiles laid. Belts carry ore between machines."><i></i><b id="nbelt">0</b><small>belts</small></div>
    <div class="st" data-ico="smelter" title="Smelters and forges. Two ore in, one ingot out."><i></i><b id="nsmelt">0</b><small>furnaces</small></div>
    <div class="st" data-ico="item"    title="Items riding belts right now."><i></i><b id="nitem">0</b><small>in transit</small></div>
    <div class="st" data-ico="ingot"   title="Ingots sold this run."><i></i><b id="ingot">0</b><small>ingots</small></div>
    <div class="st" data-ico="alloy"   title="Alloys sold this run. A forge makes them from two different ores."><i></i><b id="alloy">0</b><small>alloys</small></div>
    <div class="st core" data-ico="core" title="Cores are permanent. A meltdown or three shards earns one; they buy the trip to other worlds and multiply every yield."><i></i><b id="tok">0</b><small>cores</small></div>
  </div>
  <div id="goal"></div>
  <div id="contract"><b></b><small></small><div class="bar"><i style="width:0%"></i></div><span class="left"></span></div>
  <div id="standing"><b></b><small></small><div class="bar"><i style="width:0%"></i></div><span class="left"></span></div>
  <div id="rival"><b></b><small></small><div class="bar"><i style="width:100%"></i></div></div>
  <div class="sec" title="The board moves on its own. A price over 1.00 pays more than base; a rival buyer bids one product up for a minute.">MARKET <span>what a hub pays per unit; 1.00 is base</span></div>
  <div id="tick"></div>
  <div class="sec" title="Bought with banked value. Each has a cap, and the chain raises some caps.">UPGRADES <span>bought with value; click one to buy</span></div>
  <div id="ups"></div>
  <div id="world"></div>
  <div id="rift"></div>
  <div id="melt"><b>MELTDOWN</b><small>throw the whole factory to the sky for a permanent core</small></div>
  <div id="wipe">new world</div>
  <div id="motion">motion: full</div>
  <div id="share">share link</div>
</div>
<div id="tools">
  <div class="tool on" data-tool="miner"><svg viewBox="0 0 24 24"><path d="M4 20h16M6 20V9M18 20V9M6 9h12M8 9V6M16 9V6M8 6h8" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round"/><path d="M12 20v-6l-2-3h4l-2 3" fill="currentColor"/></svg><i class="key">1</i><b>MINER</b><small>on a seam</small></div>
  <div class="tool" data-tool="belt"><svg viewBox="0 0 24 24"><rect x="2.5" y="9" width="19" height="6" rx="3" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="6" cy="12" r="1.6" fill="currentColor"/><circle cx="18" cy="12" r="1.6" fill="currentColor"/><path d="M10 9.5l2 2.5-2 2.5M13.5 9.5l2 2.5-2 2.5" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg><i class="key">2</i><b>BELT</b><small>drag to draw</small></div>
  <div class="tool" data-tool="smelter"><svg viewBox="0 0 24 24"><path d="M5 20V9h14v11z" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M4 9h16" stroke="currentColor" stroke-width="1.7"/><path d="M15 9V4h3v5" stroke="currentColor" stroke-width="1.7" fill="none"/><rect x="9" y="13" width="6" height="5" fill="currentColor"/></svg><i class="key">3</i><b>SMELTER</b><small>two ore, one ingot</small></div>
  <div class="tool" data-tool="splitter"><svg viewBox="0 0 24 24"><path d="M12 3v18M3 12h18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="12" r="3.6" stroke="currentColor" stroke-width="1.7" fill="none"/></svg><i class="key">4</i><b>SPLITTER</b><small>feeds two lines</small></div>
  <div class="tool" data-tool="hub"><svg viewBox="0 0 24 24"><ellipse cx="12" cy="17" rx="9" ry="4" stroke="currentColor" stroke-width="1.7" fill="none"/><ellipse cx="12" cy="17" rx="4.5" ry="2" stroke="currentColor" stroke-width="1.4" fill="none"/><path d="M12 15V5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="12" cy="4" r="2" fill="currentColor"/></svg><i class="key">5</i><b>HUB</b><small>sells what arrives</small></div>
  <div class="tool" data-tool="forge"><svg viewBox="0 0 24 24"><path d="M6 20V8h12v12z" stroke="currentColor" stroke-width="1.7" fill="none"/><ellipse cx="12" cy="8" rx="6" ry="2.4" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M9 4l1.5 3M15 4l-1.5 3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="12" cy="15" r="2.6" fill="currentColor"/></svg><i class="key">6</i><b>FORGE</b><small>two ores, one alloy</small></div>
  <div class="tool" data-tool="filter"><svg viewBox="0 0 24 24"><path d="M3 5h18l-7 8v6l-4 2v-8z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/></svg><i class="key">7</i><b>FILTER</b><small>sorts an ore, F picks</small></div>
  <div class="tool" data-tool="rift"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="12" cy="12" r="3.4" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M12 4v3M12 17v3M4 12h3M17 12h3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg><i class="key">8</i><b>RIFT</b><small>lends ore, on a clock</small></div>
  <div class="tool" data-tool="erase"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><i class="key">9</i><b>ERASE</b><small>remove</small></div>
  <div class="tool" data-tool="blueprint"><svg viewBox="0 0 24 24"><rect x="4" y="4" width="10" height="10" rx="1.5" stroke="currentColor" stroke-width="1.7" fill="none" stroke-dasharray="3 2"/><rect x="10" y="10" width="10" height="10" rx="1.5" stroke="currentColor" stroke-width="1.7" fill="none"/></svg><i class="key">0</i><b>BLUEPRINT</b><small>copy a line, stamp it</small></div>
</div>
<div id="toast"></div>
<div id="title"><b></b><small></small></div>
<div id="facecap"></div>
<div id="look"></div>
<div id="tutor"><em></em><b></b><small></small><p></p><span class="skip">skip the guide</span></div>
<div id="cross"></div>
<div id="hint">WASD to walk, Shift to run, Space to jump, click to look around.<br>Hold the left button and sweep to draw belts. TAB opens the overhead view.<br>Point at a filter and press F to change which ore it passes.<br>Walk over any edge: each side of the world grows a different ore.<br>Your factory saves itself.</div>
<script type="importmap">{"imports":{"three":"./vendor/three.module.js"}}</script>
<script type="module" src="./game.js"></script>
