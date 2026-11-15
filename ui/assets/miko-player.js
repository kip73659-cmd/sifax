/*! miko-player.js - the integrated Miko video player.
 *
 * Parts of the design come from MikoGo (https://github.com/MzeroMiko/mikoGo, MIT License,
 * Copyright (c) 2021 MzeroMiko): the SliderBar (progress/volume bar), the MediaPlayer playlist and
 * play-order logic (ascend / random / loop), the keyboard shortcuts and the auto-hiding control bar of
 * VideoPlayer. They were rewritten here for Miko: pointer-drag seeking, a real-position bug fix,
 * YouTube/Vimeo/... embeds, a download-library playlist, graceful fallbacks, and low idle CPU use.
 * See THIRD_PARTY_LICENSES/MikoGo-MIT.txt.
 *
 * Usage:  var p = new MikoPlayer(element, {onChange, openExternal, download, resolve, openLocal});
 *         p.setResults([{title, href, thumb, uploader, duration}, ...]); p.play(0);
 * No dependencies. No timers or animation frames run while nothing is playing.
 */
(function (global) {
  "use strict";

  /* ------------------------------------------------------------------ link classification */
  function secs(t) {                       // "90", "1m30s", "1h2m3s" -> seconds
    if (!t) return 0;
    if (/^\d+$/.test(t)) return +t;
    var m = /^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$/i.exec(t);
    return m ? (+m[1] || 0) * 3600 + (+m[2] || 0) * 60 + (+m[3] || 0) : 0;
  }
  var ID_YT = /^[\w-]{11}$/;
  function classify(item) {
    /* -> {type:'local'|'direct'|'youtube'|'vimeo'|'dailymotion'|'bilibili'|'twitch'|'page'|'bad', ...} */
    if (item && item.path) return { type: "local", src: "/media?p=" + encodeURIComponent(item.path) };
    var raw = item && (item.href || item.url) || "";
    var u;
    try { u = new URL(raw); } catch (e) { return { type: "bad" }; }
    if (u.protocol !== "https:" && u.protocol !== "http:") return { type: "bad" };
    var h = u.hostname.replace(/^(www|m|music)\./, "").toLowerCase(), p = u.pathname, q = u.searchParams, id = "", m;
    if (h === "youtube.com" || h === "youtube-nocookie.com" || h === "youtu.be") {
      if (h === "youtu.be") id = p.slice(1).split("/")[0];
      else if (p === "/watch") id = q.get("v") || "";
      else if ((m = /^\/(?:shorts|embed|live|v)\/([\w-]{11})/.exec(p))) id = m[1];
      if (ID_YT.test(id)) return { type: "youtube", id: id, start: secs(q.get("t") || q.get("start") || "") };
      return { type: "page" };
    }
    if (h === "vimeo.com" && (m = /^\/(?:.*\/)?(\d{6,12})(?:\/|$)/.exec(p))) return { type: "vimeo", id: m[1] };
    if ((h === "dailymotion.com" || h === "dai.ly") && (m = /(?:\/video\/|^\/)([a-z0-9]{5,10})(?:[_/?]|$)/i.exec(p))) return { type: "dailymotion", id: m[1] };
    if (h === "bilibili.com" && (m = /\/video\/(BV[\w]{10})/.exec(p))) return { type: "bilibili", id: m[1] };
    if (h === "twitch.tv" && (m = /^\/videos\/(\d{5,12})/.exec(p))) return { type: "twitch", id: "v" + m[1] };
    if (/\.(mp4|m4v|webm|ogv|mov)$/i.test(p)) return { type: "direct", src: u.href };
    return { type: "page" };
  }
  function embedUrl(c) {
    var o = encodeURIComponent(location.origin);
    switch (c.type) {
      case "youtube": return "https://www.youtube-nocookie.com/embed/" + c.id + "?enablejsapi=1&playsinline=1&rel=0&autoplay=1&origin=" + o + (c.start ? "&start=" + c.start : "");
      case "vimeo": return "https://player.vimeo.com/video/" + c.id + "?autoplay=1";
      case "dailymotion": return "https://www.dailymotion.com/embed/video/" + c.id + "?autoplay=1";
      case "bilibili": return "https://player.bilibili.com/player.html?bvid=" + c.id + "&autoplay=1&high_quality=1";
      case "twitch": return "https://player.twitch.tv/?video=" + c.id + "&autoplay=true&parent=" + encodeURIComponent(location.hostname);
    }
    return "";
  }
  var PROVIDER_NAME = { youtube: "YouTube", vimeo: "Vimeo", dailymotion: "Dailymotion", bilibili: "Bilibili", twitch: "Twitch" };

  /* ------------------------------------------------------------------ small helpers */
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function fmt(t) {
    if (!isFinite(t) || t < 0) t = 0;
    var h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = Math.floor(t % 60);
    return (h ? h + ":" + (m < 10 ? "0" : "") : "") + m + ":" + (s < 10 ? "0" : "") + s;
  }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { } return null; }
  function svg(d) { return '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="' + d + '"/></svg>'; }
  var IC = {
    play: svg("M8 5v14l11-7z"), pause: svg("M6 5h4v14H6zM14 5h4v14h-4z"),
    prev: svg("M6 6h2v12H6zm3.5 6 8.5 6V6z"), next: svg("M16 6h2v12h-2zM6 18l8.5-6L6 6z"),
    back: svg("M11 18V6l-8.5 6zm.5-6 8.5 6V6z"), fwd: svg("M4 18l8.5-6L4 6zm9-12v12l8.5-6z"),
    vol: svg("M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"),
    mute: svg("M16.5 12A4.5 4.5 0 0 0 14 7.97v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51A8.8 8.8 0 0 0 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3 3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06a8.99 8.99 0 0 0 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4 9.91 6.09 12 8.18V4z"),
    full: svg("M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"),
    unfull: svg("M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"),
    seq: svg("M3 5h12v2H3zm0 6h12v2H3zm0 6h8v2H3zm14-1.2V8l5 3.9z"),
    loop: svg("M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z"),
    one: svg("M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4zm-4-2V9h-1l-2 1v1h1.5v4h1.5z"),
    shuf: svg("M10.59 9.17 5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"),
    open: svg("M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"),
    pip: svg("M19 11h-8v6h8v-6zm4 8V4.98C23 3.88 22.1 3 21 3H3c-1.1 0-2 .88-2 1.98V19c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2zm-2 .02H3V4.97h18v14.05z"),
    dl: svg("M5 20h14v-2H5v2zM19 9h-4V3H9v6H5l7 7 7-7z"),
    warn: svg("M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z")
  };

  var CSS = '\
.mp{--p:#ddb7ff;--pc:#b76dff;--bg:#0f0c1d;--bar:#1c192b;--hi:#2b283a;--tx:#e6dff8;--mu:#cfc2d6;--s:#ffb0cd;--t:#7bd0ff;\
 color:var(--tx);font:500 13px/1.3 "Plus Jakarta Sans","Segoe UI",system-ui,sans-serif;border-radius:16px;overflow:hidden;background:var(--bar);outline:none;user-select:none}\
.mp{container-type:inline-size}.mp *{box-sizing:border-box}\
@container (max-width:430px){.mp .mp-back,.mp .mp-fwd,.mp .mp-ext{display:none}.mp .mp-vol{width:48px}}\
.mp button{font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer}\
.mp-stage{position:relative;aspect-ratio:16/9;background:#000;overflow:hidden}\
.mp-stage video,.mp-stage iframe{position:absolute;inset:0;width:100%;height:100%;border:0;background:#000}\
.mp-stage video{object-fit:contain}\
.mp-cue,.mp-msg,.mp-idle{position:absolute;inset:0;display:none;align-items:center;justify-content:center;text-align:center}\
.mp-cue{background:#000 center/cover no-repeat;cursor:pointer}\
.mp-cue:before{content:"";position:absolute;inset:0;background:linear-gradient(0deg,rgba(0,0,0,.75),rgba(0,0,0,.15) 55%,rgba(0,0,0,.45))}\
.mp-big{position:relative;width:62px;height:62px;border-radius:50%;background:rgba(15,12,29,.82);color:var(--p);display:flex;align-items:center;justify-content:center;box-shadow:0 0 22px rgba(183,109,255,.5);transition:transform .15s}\
.mp-big svg{width:34px;height:34px}.mp-cue:hover .mp-big{transform:scale(1.08);background:var(--p);color:#2c0051}\
.mp-cap{position:absolute;left:12px;right:12px;bottom:10px;text-align:left;font-weight:600;text-shadow:0 1px 4px #000;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}\
.mp-idle{color:var(--mu);flex-direction:column;gap:6px;padding:16px;background:radial-gradient(ellipse at 50% 40%,#2b283a,#0f0c1d)}\
.mp-idle b{color:var(--p);font-size:15px}\
.mp-msg{background:rgba(15,12,29,.96);flex-direction:column;gap:10px;padding:14px 18px;overflow:auto}\
.mp-msg svg{color:var(--s);width:30px;height:30px}.mp-msg p{margin:0;max-width:34em;color:var(--tx)}.mp-msg small{color:var(--mu)}\
.mp-acts{display:flex;flex-wrap:wrap;gap:6px;justify-content:center}\
.mp-acts button{background:var(--hi);padding:6px 12px;border-radius:999px;font-weight:600;font-size:12px;display:flex;gap:6px;align-items:center}\
.mp-acts button svg{width:15px;height:15px}.mp-acts button:hover{background:var(--pc);color:#fff}\
.mp-spin{position:absolute;left:50%;top:50%;width:34px;height:34px;margin:-17px;border:3px solid rgba(255,255,255,.2);border-top-color:var(--p);border-radius:50%;display:none;animation:mpspin .8s linear infinite;pointer-events:none}\
@keyframes mpspin{to{transform:rotate(360deg)}}\
.mp-bar{padding:6px 10px 8px;background:var(--bg)}\
.mp-row{display:flex;align-items:center;gap:2px}\
.mp-seek{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--mu);font-variant-numeric:tabular-nums}\
.mp-seek .mp-sl{flex:1}\
.mp-btn{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:var(--tx);flex:none}\
.mp-btn:hover:not(:disabled){background:var(--hi);color:var(--p)}.mp-btn:disabled{opacity:.35;cursor:default}\
.mp-btn.on{color:var(--s)}\
.mp-play{background:var(--pc);color:#fff}.mp-play:hover:not(:disabled){background:var(--p)!important;color:#2c0051!important}\
.mp-sp{flex:1}\
.mp-vol{width:70px;flex:none}\
.mp-sl{position:relative;height:18px;cursor:pointer;touch-action:none;display:flex;align-items:center}\
.mp-sl i{position:absolute;left:0;right:0;height:4px;border-radius:2px;background:#4d4354}\
.mp-sl .b{right:auto;background:#6b5f73}.mp-sl .f{right:auto;background:linear-gradient(90deg,var(--pc),var(--p))}\
.mp-sl u{position:absolute;width:12px;height:12px;margin-left:-6px;border-radius:50%;background:var(--p);box-shadow:0 0 6px rgba(221,183,255,.7);transform:scale(0);transition:transform .12s}\
.mp-sl:hover u,.mp-sl.drag u,.mp-sl:focus-visible u{transform:scale(1)}\
.mp-sl[aria-disabled=true]{opacity:.35;pointer-events:none}\
.mp-tabs{display:flex;gap:4px;padding:6px 10px 0;background:var(--bar)}\
.mp-tabs button{padding:5px 12px;border-radius:999px;font-size:12px;font-weight:700;color:var(--mu)}\
.mp-tabs button.on{background:var(--pc);color:#fff}.mp-tabs button:hover:not(.on){background:var(--hi)}\
.mp-list{max-height:210px;overflow-y:auto;padding:6px 8px 8px;background:var(--bar);scrollbar-width:thin;scrollbar-color:#4d4354 transparent}\
.mp-list::-webkit-scrollbar{display:block;width:6px}.mp-list::-webkit-scrollbar-thumb{background:#4d4354;border-radius:3px}\
.mp-it{display:flex;gap:8px;align-items:center;padding:4px;border-radius:10px;cursor:pointer}\
.mp-it:hover{background:var(--hi)}.mp-it.cur{background:rgba(183,109,255,.22);box-shadow:inset 3px 0 0 var(--p)}\
.mp-th{width:64px;height:36px;border-radius:6px;background:#0f0c1d center/cover no-repeat;flex:none;display:flex;align-items:center;justify-content:center;color:var(--mu);font-size:10px}\
.mp-meta{min-width:0;flex:1}.mp-meta b{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-weight:600;font-size:12px}\
.mp-meta span{color:var(--mu);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block}\
.mp-empty{padding:14px 8px;color:var(--mu);text-align:center;font-size:12px}\
.mp:fullscreen,.mp.fs{display:flex;flex-direction:column;background:#000;border-radius:0}\
.mp:fullscreen .mp-stage,.mp.fs .mp-stage{flex:1;aspect-ratio:auto}\
.mp:fullscreen .mp-tabs,.mp:fullscreen .mp-list,.mp.fs .mp-tabs,.mp.fs .mp-list{display:none}\
.mp:fullscreen .mp-bar{transition:opacity .3s}.mp.hide-ui:fullscreen .mp-bar{opacity:0}.mp.hide-ui:fullscreen{cursor:none}';

  function injectCss() {
    if (document.getElementById("mp-css")) return;
    var s = el("style"); s.id = "mp-css"; s.textContent = CSS; document.head.appendChild(s);
  }

  /* ------------------------------------------------------------------ SliderBar (from MikoGo, rebuilt) */
  function Slider(box, onSeek, onDrag, label) {
    box.className += " mp-sl"; box.tabIndex = 0;
    box.setAttribute("role", "slider"); box.setAttribute("aria-label", label || "slider");
    box.innerHTML = "<i></i><i class='b'></i><i class='f'></i><u></u>";
    var b = box.querySelector(".b"), f = box.querySelector(".f"), k = box.querySelector("u"), dragging = false;
    function rate(e) { var r = box.getBoundingClientRect(); return r.width ? Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) : 0; }
    box.addEventListener("pointerdown", function (e) {
      if (box.getAttribute("aria-disabled") === "true") return;
      dragging = true; box.classList.add("drag"); box.setPointerCapture(e.pointerId);
      set(rate(e)); if (onDrag) onDrag(rate(e), true);
    });
    box.addEventListener("pointermove", function (e) { if (dragging) { set(rate(e)); if (onDrag) onDrag(rate(e), true); } });
    function up(e) { if (!dragging) return; dragging = false; box.classList.remove("drag"); onSeek(rate(e)); }
    box.addEventListener("pointerup", up); box.addEventListener("pointercancel", function () { dragging = false; box.classList.remove("drag"); });
    box.addEventListener("keydown", function (e) {
      var d = e.key === "ArrowRight" || e.key === "ArrowUp" ? 0.05 : e.key === "ArrowLeft" || e.key === "ArrowDown" ? -0.05 : 0;
      if (!d) return; e.preventDefault(); e.stopPropagation();
      var cur = parseFloat(box.getAttribute("aria-valuenow") || "0") / 100; onSeek(Math.min(1, Math.max(0, cur + d)));
    });
    function set(x) { x = Math.min(1, Math.max(0, +x || 0)); f.style.width = k.style.left = x * 100 + "%"; box.setAttribute("aria-valuenow", Math.round(x * 100)); }
    return {
      set: function (x) { if (!dragging) set(x); },
      buffer: function (x) { b.style.width = Math.min(1, Math.max(0, +x || 0)) * 100 + "%"; },
      enable: function (on) { box.setAttribute("aria-disabled", on ? "false" : "true"); },
      el: box
    };
  }

  /* ------------------------------------------------------------------ the player */
  function MikoPlayer(host, opts) {
    injectCss();
    opts = opts || {};
    var self = this;
    var root = el("div", "mp"); root.tabIndex = 0;
    host.innerHTML = ""; host.appendChild(root);
    root.innerHTML =
      '<div class="mp-stage">' +
      '<video preload="metadata" playsinline referrerpolicy="no-referrer"></video>' +
      '<div class="mp-embed"></div>' +
      '<div class="mp-idle"><b>Miko Player</b><span>Pick a video from the results to watch it here.</span></div>' +
      '<div class="mp-cue"><div class="mp-big">' + IC.play + '</div><div class="mp-cap"></div></div>' +
      '<div class="mp-msg"></div><div class="mp-spin"></div>' +
      '</div>' +
      '<div class="mp-bar">' +
      '<div class="mp-seek"><span class="mp-cur">0:00</span><div class="mp-seekbar"></div><span class="mp-dur">0:00</span></div>' +
      '<div class="mp-row">' +
      '<button class="mp-btn mp-prev" title="Previous (P)" aria-label="Previous">' + IC.prev + '</button>' +
      '<button class="mp-btn mp-back" title="Back 10 s (Left)" aria-label="Back 10 seconds">' + IC.back + '</button>' +
      '<button class="mp-btn mp-play" title="Play / Pause (Space)" aria-label="Play">' + IC.play + '</button>' +
      '<button class="mp-btn mp-fwd" title="Forward 10 s (Right)" aria-label="Forward 10 seconds">' + IC.fwd + '</button>' +
      '<button class="mp-btn mp-next" title="Next (N)" aria-label="Next">' + IC.next + '</button>' +
      '<button class="mp-btn mp-mute" title="Mute (M)" aria-label="Mute">' + IC.vol + '</button>' +
      '<div class="mp-vol"></div><span class="mp-sp"></span>' +
      '<button class="mp-btn mp-order" title="Play order: in sequence" aria-label="Play order">' + IC.seq + '</button>' +
      '<button class="mp-btn mp-pip" title="Picture in picture" aria-label="Picture in picture">' + IC.pip + '</button>' +
      '<button class="mp-btn mp-ext" title="Open original page in your browser" aria-label="Open original">' + IC.open + '</button>' +
      '<button class="mp-btn mp-full" title="Fullscreen (F or double-click)" aria-label="Fullscreen">' + IC.full + '</button>' +
      '</div></div>' +
      '<div class="mp-tabs"><button class="mp-tab on" data-l="results">Up next</button><button class="mp-tab" data-l="downloads">Downloaded</button></div>' +
      '<div class="mp-list"></div>';
    function q(s) { return root.querySelector(s); }
    var stage = q(".mp-stage"), video = q("video"), embedBox = q(".mp-embed"), idle = q(".mp-idle"), cue = q(".mp-cue"),
      cap = q(".mp-cap"), msg = q(".mp-msg"), spin = q(".mp-spin"), curEl = q(".mp-cur"), durEl = q(".mp-dur"),
      bPlay = q(".mp-play"), bMute = q(".mp-mute"), bOrder = q(".mp-order"), bFull = q(".mp-full"), bPip = q(".mp-pip"),
      bPrev = q(".mp-prev"), bNext = q(".mp-next"), bBack = q(".mp-back"), bFwd = q(".mp-fwd"), bExt = q(".mp-ext"),
      listEl = q(".mp-list");

    /* ---------------- state */
    var lists = { results: [], downloads: [] }, active = "results", idx = -1, item = null, mode = "idle"; // idle|cue|native|embed|msg
    var order = store("miko.player.order") || "seq", history = [], iframe = null, ytAlive = false, ytOrigin = "", cls = null;
    var vol = parseFloat(store("miko.player.vol")); if (!isFinite(vol)) vol = 0.8;
    var muted = store("miko.player.muted") === "1";
    var T = null;                      // transport of the current mode
    var lastUi = 0, hideTimer = 0, loadToken = 0;
    var ORDERS = ["seq", "loop", "one", "shuffle"], ORDER_TIP = { seq: "in sequence", loop: "repeat all", one: "repeat one", shuffle: "shuffle" };

    var seek = Slider(q(".mp-seekbar"), function (r) { if (T && T.seek && T.dur() > 0) T.seek(r * T.dur()); }, function (r) { if (T && T.dur() > 0) curEl.textContent = fmt(r * T.dur()); }, "Seek");
    var volume = Slider(q(".mp-vol"), function (r) { setVol(r); }, function (r) { setVol(r, true); }, "Volume");
    seek.enable(false); volume.set(muted ? 0 : vol);

    /* ---------------- ui helpers */
    function show(what) {                       // what: idle|cue|native|embed|msg|loading
      idle.style.display = what === "idle" ? "flex" : "none";
      cue.style.display = what === "cue" ? "flex" : "none";
      msg.style.display = what === "msg" ? "flex" : "none";
      video.style.display = what === "native" ? "block" : "none";
      embedBox.style.display = what === "embed" ? "block" : "none";
    }
    function setPlayIcon(playing) { bPlay.innerHTML = playing ? IC.pause : IC.play; bPlay.setAttribute("aria-label", playing ? "Pause" : "Play"); }
    function loading(on) { spin.style.display = on ? "block" : "none"; }
    function setCaps(c) {                       // what the current mode can do
      bBack.disabled = bFwd.disabled = !c.seek; seek.enable(!!c.seek); bPlay.disabled = !c.play;
      bMute.disabled = !c.vol; volume.enable(!!c.vol); bPip.style.display = c.pip ? "" : "none";
      bExt.disabled = !(item && (item.href || item.url));
      if (!c.seek) { seek.set(0); seek.buffer(0); curEl.textContent = "0:00"; durEl.textContent = c.live || "0:00"; }
    }
    function updateNav() { var n = lists[active].length; bPrev.disabled = n < 2 && order !== "one" && !history.length; bNext.disabled = n < 2 && order !== "loop" && order !== "one"; }
    function paintOrder() { bOrder.innerHTML = IC[order === "seq" ? "seq" : order === "loop" ? "loop" : order === "one" ? "one" : "shuf"]; bOrder.title = "Play order: " + ORDER_TIP[order] + " (click to change)"; bOrder.classList.toggle("on", order !== "seq"); }
    paintOrder();
    function tick(cur, dur, buf) {              // throttled UI refresh (max twice a second, never while hidden)
      var now = Date.now(); if (now - lastUi < 450 || document.hidden) return; lastUi = now;
      curEl.textContent = fmt(cur); durEl.textContent = dur > 0 ? fmt(dur) : "0:00";
      seek.set(dur > 0 ? cur / dur : 0); if (buf != null && dur > 0) seek.buffer(buf / dur);
    }
    function setVol(v, noSave) {
      vol = Math.min(1, Math.max(0, v)); muted = vol === 0;
      if (T && T.vol) T.vol(vol, muted);
      volume.set(vol); bMute.innerHTML = muted ? IC.mute : IC.vol;
      if (!noSave) { store("miko.player.vol", String(vol || 0.8)); store("miko.player.muted", muted ? "1" : "0"); }
    }
    function toggleMute() {
      muted = !muted; if (!muted && vol === 0) vol = 0.5;
      if (T && T.vol) T.vol(vol, muted); volume.set(muted ? 0 : vol); bMute.innerHTML = muted ? IC.mute : IC.vol;
      store("miko.player.muted", muted ? "1" : "0");
    }

    /* ---------------- list rendering */
    function renderList() {
      var L = lists[active];
      root.querySelectorAll(".mp-tab").forEach(function (t) {
        var n = lists[t.getAttribute("data-l")].length; var base = t.getAttribute("data-l") === "results" ? "Up next" : "Downloaded";
        t.textContent = base + (n ? " (" + n + ")" : ""); t.classList.toggle("on", t.getAttribute("data-l") === active);
      });
      if (!L.length) { listEl.innerHTML = '<div class="mp-empty">' + (active === "results" ? "Search for videos and they will queue up here." : "Videos you download with Miko appear here.") + "</div>"; return; }
      var html = "";
      L.forEach(function (it, i) {
        var sub = it.path ? (it.ext || "").replace(".", "").toUpperCase() + (it.playable === false ? " • may not play here" : "") : (it.uploader || it.publisher || host_of(it.href));
        html += '<div class="mp-it' + (i === idx ? " cur" : "") + '" data-i="' + i + '" role="button" tabindex="-1">' +
          '<div class="mp-th" style="' + (it.thumb ? "background-image:url(&quot;" + esc(it.thumb) + "&quot;)" : "") + '">' + (it.thumb ? "" : (it.kind === "audio" ? "MP3" : "VIDEO")) + "</div>" +
          '<div class="mp-meta"><b>' + esc(it.title || it.name || "Untitled") + "</b><span>" + esc(sub) + (it.duration ? " • " + esc(it.duration) : "") + "</span></div></div>";
      });
      listEl.innerHTML = html;
      var c = listEl.querySelector(".cur"); if (c && c.scrollIntoView) c.scrollIntoView({ block: "nearest" });
    }
    function host_of(u) { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return ""; } }
    listEl.addEventListener("click", function (e) {
      var r = e.target.closest(".mp-it"); if (!r) return; var i = +r.getAttribute("data-i"); history = [];
      self.play(i, { list: active, user: true });
    });
    root.querySelectorAll(".mp-tab").forEach(function (t) { t.onclick = function () { active = t.getAttribute("data-l"); if (active === "downloads" && opts.onLibraryOpen) opts.onLibraryOpen(); renderList(); updateNav(); }; });

    /* ---------------- teardown of the current source (frees the decoder and any iframe) */
    function teardown() {
      loadToken++;
      if (opts.detach) { try { opts.detach(); } catch (e) { } }
      try { video.pause(); } catch (e) { }
      if (video.getAttribute("src") !== null) { video.removeAttribute("src"); try { video.load(); } catch (e) { } }
      if (iframe) { try { iframe.src = "about:blank"; } catch (e) { } iframe.remove(); iframe = null; }
      embedBox.innerHTML = ""; ytAlive = false; T = null; loading(false); setPlayIcon(false);
      lastUi = 0; seek.set(0); seek.buffer(0); curEl.textContent = "0:00"; durEl.textContent = "0:00";
    }

    /* ---------------- fallback card */
    function fail(title, text, why, extra) {
      teardown(); mode = "msg"; show("msg"); setCaps({});
      var href = item && (item.href || item.url) || "";
      var b = "";
      if (href) {
        b += '<button data-a="ext">' + IC.open + "Open in my browser</button>";
        b += '<button data-a="pop">' + IC.pip + "Open in small window</button>";
      }
      if (item && item.path) b += '<button data-a="local">' + IC.play + "Open with Windows player</button>";
      if (extra && extra.stream) b += '<button data-a="stream">' + IC.play + "Try direct stream</button>";
      if (href && opts.download) b += '<button data-a="dl">' + IC.dl + "Download it</button>";
      b += '<button data-a="skip">' + IC.next + "Next video</button>";
      msg.innerHTML = IC.warn + "<p><b>" + esc(title) + "</b><br>" + esc(text) + "</p>" + (why ? "<small>" + esc(why) + "</small>" : "") + '<div class="mp-acts">' + b + "</div>";
      msg.querySelectorAll("button").forEach(function (bt) {
        bt.onclick = function () {
          var a = bt.getAttribute("data-a");
          if (a === "ext" && opts.openExternal) opts.openExternal(href, false);
          if (a === "pop" && opts.openExternal) opts.openExternal(href, true);
          if (a === "local" && opts.openLocal) opts.openLocal(item.path);
          if (a === "dl" && opts.download) opts.download(item);
          if (a === "skip") self.next(true);
          if (a === "stream") streamFallback();
        };
      });
      if (opts.onState) opts.onState("failed", item);
    }

    /* ---------------- native <video> */
    function applyVol() { video.volume = vol; video.muted = muted; }
    function mountNative(src, token) {
      mode = "native"; show("native"); loading(true); applyVol();
      T = {
        toggle: function () { video.paused ? video.play().catch(function () { }) : video.pause(); },
        pause: function () { video.pause(); }, play: function () { return video.play(); },
        seek: function (t) { video.currentTime = Math.max(0, Math.min(t, video.duration || t)); },
        rel: function (d) { if (isFinite(video.duration)) video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + d)); },
        time: function () { return video.currentTime; }, dur: function () { return isFinite(video.duration) ? video.duration : 0; },
        vol: function (v, m) { video.volume = v; video.muted = m; }, playing: function () { return !video.paused && !video.ended; }
      };
      setCaps({ seek: true, play: true, vol: true, pip: !!document.pictureInPictureEnabled && item.kind !== "audio" });
      if (!(opts.attach && opts.attach(video, src, token))) video.src = src;      // optional hook (Anime Room: HLS)
      var p = video.play(); if (p && p.catch) p.catch(function (err) { if (token === loadToken && err && err.name === "NotAllowedError") { loading(false); setPlayIcon(false); } });
    }
    video.addEventListener("loadedmetadata", function () { if (mode === "native") { durEl.textContent = fmt(video.duration); } });
    video.addEventListener("playing", function () { if (mode === "native") { loading(false); setPlayIcon(true); } });
    video.addEventListener("waiting", function () { if (mode === "native" && !video.paused) loading(true); });
    video.addEventListener("canplay", function () { if (mode === "native") loading(false); });
    video.addEventListener("pause", function () { if (mode === "native") setPlayIcon(false); });
    video.addEventListener("play", function () { if (mode === "native") setPlayIcon(true); });
    video.addEventListener("timeupdate", function () {
      if (mode !== "native") return;
      var buf = 0; try { if (video.buffered.length) buf = video.buffered.end(video.buffered.length - 1); } catch (e) { }
      tick(video.currentTime, video.duration, buf);
    });
    video.addEventListener("ended", function () { if (mode === "native") { setPlayIcon(false); self.next(false); } });
    video.addEventListener("error", function () {
      if (mode !== "native" || !video.getAttribute("src")) return;
      var code = video.error ? video.error.code : 0, local = item && item.path;
      var why = code === 4 ? "The built-in player cannot decode this file or link (format/codec not supported, e.g. MKV, HEVC or HLS)."
        : code === 2 ? "The network connection to the video was interrupted."
          : code === 3 ? "The video data could not be decoded." : "The video could not be loaded.";
      var stream = !local && !!opts.resolve && !(cls && cls.resolved);
      fail("This video cannot play inside Miko", local ? "Try opening it with your normal Windows video player." : "The site may block playback outside its own page.", why, { stream: stream });
    });
    video.addEventListener("click", function () { if (T && T.toggle) T.toggle(); });

    /* ---------------- embedded players (YouTube has a real two-way link, others are view-only) */
    function mountEmbed(c, token) {
      mode = "embed"; show("embed"); loading(true);
      var url = embedUrl(c); if (!url) return fail("Cannot embed this link", "", "");
      iframe = document.createElement("iframe");
      iframe.setAttribute("allow", "autoplay; fullscreen; picture-in-picture; encrypted-media");
      iframe.setAttribute("allowfullscreen", ""); iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      iframe.setAttribute("title", item.title || "Video");
      iframe.src = url; ytOrigin = new URL(url).origin; ytAlive = false;
      var state = { cur: 0, dur: 0, playing: false };
      var isYT = c.type === "youtube";
      function post(func, args) { if (iframe && iframe.contentWindow) iframe.contentWindow.postMessage(JSON.stringify({ event: "command", func: func, args: args || [] }), ytOrigin); }
      T = isYT ? {
        toggle: function () { post(state.playing ? "pauseVideo" : "playVideo"); }, pause: function () { post("pauseVideo"); }, play: function () { post("playVideo"); },
        seek: function (t) { post("seekTo", [t, true]); state.cur = t; }, rel: function (d) { post("seekTo", [Math.max(0, state.cur + d), true]); },
        time: function () { return state.cur; }, dur: function () { return state.dur; },
        vol: function (v, m) { post("setVolume", [Math.round(v * 100)]); post(m ? "mute" : "unMute"); }, playing: function () { return state.playing; }
      } : { toggle: function () { }, pause: function () { }, play: function () { }, time: function () { return 0; }, dur: function () { return 0; }, playing: function () { return false; } };
      setCaps(isYT ? { seek: false, play: false, vol: false } : { live: PROVIDER_NAME[c.type] });
      iframe.addEventListener("load", function () {
        loading(false);
        if (isYT && token === loadToken) {          // open the YouTube two-way message channel
          iframe.contentWindow.postMessage(JSON.stringify({ event: "listening", id: 1, channel: "widget" }), ytOrigin);
          setTimeout(function () { if (token === loadToken && iframe && !ytAlive) iframe.contentWindow.postMessage(JSON.stringify({ event: "listening", id: 1, channel: "widget" }), ytOrigin); }, 1500);
        }
      });
      embedBox.appendChild(iframe);
      if (!isYT) return;
      mountEmbed.onMsg = function (d) {
        if (d.event === "onReady" || d.event === "initialDelivery" || d.event === "infoDelivery" || d.event === "onStateChange") {
          if (!ytAlive) { ytAlive = true; setCaps({ seek: true, play: true, vol: true }); post("setVolume", [Math.round(vol * 100)]); post(muted ? "mute" : "unMute"); loading(false); }
        }
        var info = d.info || {};
        if (d.event === "infoDelivery" || d.event === "initialDelivery") {
          if (typeof info.currentTime === "number") state.cur = info.currentTime;
          if (typeof info.duration === "number" && info.duration > 0) state.dur = info.duration;
          if (typeof info.playerState === "number") { state.playing = info.playerState === 1 || info.playerState === 3; setPlayIcon(info.playerState === 1); }
          tick(state.cur, state.dur, state.dur * (info.videoLoadedFraction || 0));
        }
        if (d.event === "onStateChange" && typeof d.info === "number") {
          state.playing = d.info === 1 || d.info === 3; setPlayIcon(d.info === 1); loading(d.info === 3);
          if (d.info === 0) { setPlayIcon(false); self.next(false); }
        }
        if (d.event === "onError") {
          var codes = { 2: "The video link is invalid.", 5: "YouTube could not play this video in an embedded player.", 100: "This video was removed or is private.",
            101: "The owner of this video does not allow it to be played outside YouTube.", 150: "The owner of this video does not allow it to be played outside YouTube.",
            153: "YouTube refused to play this video in an embedded player." };
          fail("This YouTube video cannot be played inside Miko", "You can still watch it on YouTube or download it.", codes[d.info] || "YouTube error " + d.info, { stream: !!opts.resolve });
        }
      };
    }
    window.addEventListener("message", function (e) {
      if (!iframe || !ytOrigin || e.origin !== ytOrigin || e.source !== iframe.contentWindow) return;
      var d; try { d = typeof e.data === "string" ? JSON.parse(e.data) : e.data; } catch (x) { return; }
      if (d && mountEmbed.onMsg) mountEmbed.onMsg(d);
    });

    /* ---------------- unknown page link: try a direct stream (yt-dlp) or fall back */
    function mountPage(token, forced) {
      var href = item.href || item.url;
      if (!opts.resolve) return fail("This site cannot be embedded", "Open it in your browser instead.", "Websites like this block playback inside other apps.");
      mode = "native"; show("native"); loading(true); setCaps({});
      opts.resolve(href).then(function (r) {
        if (token !== loadToken) return;
        if (r && r.ok && r.url) { cls = { type: "direct", resolved: true }; mountNative(r.url, token); }
        else fail("This site cannot be embedded", "Open it in your browser or download it instead.", (r && r.error) || "Websites like this block playback inside other apps.");
      }, function () { if (token === loadToken) fail("This site cannot be embedded", "Open it in your browser instead.", "Could not ask Miko's helper to resolve the link."); });
    }
    function streamFallback() {
      var token = ++loadToken, href = item && (item.href || item.url); if (!href || !opts.resolve) return;
      var keep = item; teardown(); loadToken = token; mode = "native"; show("native"); loading(true); setCaps({});
      opts.resolve(href).then(function (r) {
        if (token !== loadToken || item !== keep) return;
        if (r && r.ok && r.url) { cls = { type: "direct", resolved: true }; mountNative(r.url, token); }
        else fail("No direct stream available", "This video can only be watched on its own site.", (r && r.error) || "");
      }, function () { if (token === loadToken) fail("No direct stream available", "", "Could not reach Miko's helper."); });
    }

    /* ---------------- public: loading and playing items */
    function load(it, autoplay) {
      teardown(); item = it; cls = classify(it);
      bExt.disabled = !(it.href || it.url);
      cap.textContent = it.title || "";
      if (!autoplay) {                           // "cue": show a poster only; nothing is downloaded or decoded
        mode = "cue"; show("cue"); cue.style.backgroundImage = it.thumb ? 'url("' + String(it.thumb).replace(/["\\\n]/g, "") + '")' : "";
        setCaps({}); if (opts.onState) opts.onState("cued", it); return;
      }
      var token = ++loadToken;
      if (opts.onState) opts.onState("loading", it);
      switch (cls.type) {
        case "local": case "direct": return mountNative(cls.src, token);
        case "youtube": case "vimeo": case "dailymotion": case "bilibili": case "twitch": return mountEmbed(cls, token);
        case "page": return mountPage(token);
        default: return fail("Unsupported link", "This result does not have a playable address.", "");
      }
    }
    cue.addEventListener("click", function () { if (item) load(item, true); });

    this.setResults = function (arr) {
      var curHref = item && (item.href || item.path);
      lists.results = (arr || []).slice();
      if (active === "results") { idx = -1; for (var i = 0; i < lists.results.length; i++) if (lists.results[i].href === curHref) { idx = i; break; } }
      renderList(); updateNav();
    };
    this.setLibrary = function (arr) {
      var curP = item && item.path;
      lists.downloads = (arr || []).slice();
      if (active === "downloads") { idx = -1; for (var i = 0; i < lists.downloads.length; i++) if (lists.downloads[i].path === curP) { idx = i; break; } }
      renderList(); updateNav();
    };
    this.play = function (i, o) {
      o = o || {}; var name = o.list || active, L = lists[name];
      if (i < 0 || i >= L.length) return;
      if (name !== active) { active = name; }
      if (o.history !== false && idx >= 0 && idx !== i && active === name) { history.push(idx); if (history.length > 100) history.shift(); }
      idx = i; renderList(); updateNav();
      load(L[i], o.user !== false && !o.cue);
      if (opts.onChange) opts.onChange(L[i], i, name, !!o.cue);
    };
    this.cue = function (i, name) { this.play(i, { list: name, cue: true, history: false }); };
    this.next = function (manual) {
      var L = lists[active], n = L.length; if (!n) return;
      if (!manual && order === "one") return load(item, true);
      var i;
      if (order === "shuffle" && n > 1) { do { i = Math.floor(Math.random() * n); } while (i === idx); }
      else { i = idx + 1; if (i >= n) { if (order === "loop" || manual) i = 0; else { teardown(); mode = "cue"; load(item, false); if (opts.onState) opts.onState("ended", item); return; } } }
      self.play(i, { list: active });
    };
    this.prev = function () {
      var L = lists[active]; if (!L.length) return;
      if (T && T.time && T.time() > 5) return T.seek && T.seek(0);   // like most players: restart first
      var i = history.length ? history.pop() : (idx <= 0 ? L.length - 1 : idx - 1);
      self.play(i, { list: active, history: false });
    };
    this.pause = function () { if (T && T.pause) T.pause(); };
    this.toggle = function () { if (mode === "cue" && item) return load(item, true); if (T && T.toggle) T.toggle(); };
    this.pip = function () {
      if (mode !== "native" || !document.pictureInPictureEnabled || !video.requestPictureInPicture) return false;
      (document.pictureInPictureElement ? document.exitPictureInPicture() : video.requestPictureInPicture()).catch(function () { }); return true;
    };
    this.fullscreen = toggleFull;
    this.current = function () { return item; };
    this.mode = function () { return mode; };
    this.destroy = function () { teardown(); host.innerHTML = ""; };

    /* ---------------- controls */
    bPlay.onclick = function () { self.toggle(); };
    bBack.onclick = function () { if (T && T.rel) T.rel(-10); };
    bFwd.onclick = function () { if (T && T.rel) T.rel(10); };
    bPrev.onclick = function () { self.prev(); };
    bNext.onclick = function () { self.next(true); };
    bMute.onclick = toggleMute;
    bOrder.onclick = function () { order = ORDERS[(ORDERS.indexOf(order) + 1) % ORDERS.length]; store("miko.player.order", order); paintOrder(); updateNav(); };
    bPip.onclick = function () { self.pip(); };
    bExt.onclick = function () { var h = item && (item.href || item.url); if (h && opts.openExternal) opts.openExternal(h, false); };
    bFull.onclick = toggleFull;
    function fsEl() { return document.fullscreenElement || document.webkitFullscreenElement || null; }
    function toggleFull() {
      if (fsEl()) { (document.exitFullscreen || document.webkitExitFullscreen).call(document); return; }
      var t = root; if (t.requestFullscreen) t.requestFullscreen().catch(function () { root.classList.toggle("fs"); paintFull(); }); else if (t.webkitRequestFullscreen) t.webkitRequestFullscreen();
    }
    function paintFull() { var on = fsEl() === root || root.classList.contains("fs"); bFull.innerHTML = on ? IC.unfull : IC.full; bFull.setAttribute("aria-label", on ? "Exit fullscreen" : "Fullscreen"); }
    document.addEventListener("fullscreenchange", function () { paintFull(); if (fsEl() !== root) root.classList.remove("hide-ui"); });
    stage.addEventListener("dblclick", function (e) { if (e.target.closest("iframe")) return; toggleFull(); });
    // hide the control bar after 3 s of no mouse movement while fullscreen (MikoGo behaviour)
    root.addEventListener("mousemove", function () {
      if (fsEl() !== root) return; root.classList.remove("hide-ui"); clearTimeout(hideTimer);
      hideTimer = setTimeout(function () { if (mode === "native" && T && T.playing()) root.classList.add("hide-ui"); }, 3000);
    });
    root.addEventListener("keydown", function (e) {
      if (e.target.closest && e.target.closest(".mp-sl")) { if (e.key !== " ") return; }
      var k = e.key, used = true;
      if (k === " " || k === "k") self.toggle();
      else if (k === "ArrowLeft") { if (T && T.rel) T.rel(-10); else used = false; }
      else if (k === "ArrowRight") { if (T && T.rel) T.rel(10); else used = false; }
      else if (k === "ArrowUp") setVol(Math.min(1, (muted ? 0 : vol) + 0.05));
      else if (k === "ArrowDown") setVol(Math.max(0, vol - 0.05));
      else if (k === "m" || k === "M") toggleMute();
      else if (k === "f" || k === "F") toggleFull();
      else if (k === "n" || k === "N") self.next(true);
      else if (k === "p" || k === "P") self.prev();
      else used = false;
      if (used) e.preventDefault();
    });
    setCaps({}); show("idle"); renderList(); updateNav(); bMute.innerHTML = muted ? IC.mute : IC.vol;
  }

  MikoPlayer.classify = classify;
  MikoPlayer.embedUrl = embedUrl;
  global.MikoPlayer = MikoPlayer;
})(window);
