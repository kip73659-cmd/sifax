/* Miko Anime Room (screen script).
   Uses: window.miko (bridge.js), MikoPlayer (miko-player.js, unchanged except two optional hooks), /api/anime/* (miko_anime.py).
   Reader-mode browsing, search by name, watch in Miko's own player, downloads through Miko's download manager, library, voice/AI commands. */
(function () {
  "use strict";
  function boot() {
    if (!window.miko || !window.miko.api || !document.getElementById("ar-root")) { return setTimeout(boot, 25); }
    init();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();

  function init() {
    var $ = function (s, r) { return (r || document).querySelector(s); };
    var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
    var root = $("#ar-root"), BTN = root.dataset.btn, BTNP = root.dataset.btnp;
    var CARD = "rounded-DEFAULT bg-surface-container-low/80 backdrop-blur-xl shadow-[0_6px_24px_rgba(0,0,0,0.35)]";
    var API = function (p, b) { return window.miko.api("anime/" + p, b || {}); };
    function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
    function say(t) { try { window.miko.showBubble(t); } catch (e) { } }
    function status(t) { var s = $("#ar-status"); if (s) s.textContent = t || ""; }
    function host(u) { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return ""; } }
    function toks(s) { return String(s || "").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").match(/[a-z0-9]+/g) || []; }
    function overlap(q, t) { var a = toks(q), b = toks(t); if (!a.length || !b.length) return 0; var set = {}; b.forEach(function (x) { set[x] = 1; }); return a.filter(function (x) { return set[x]; }).length / a.length; }
    function fmtB(n) { n = +n || 0; return n < 1e6 ? (n / 1e3).toFixed(0) + " KB" : n < 1e9 ? (n / 1e6).toFixed(1) + " MB" : (n / 1e9).toFixed(2) + " GB"; }
    function img(it, cls) {
      var src = it.thumb || it.poster || "", alt = it.thumb_p || it.poster_p || "";
      if (!src && !alt) return '<div class="' + cls + ' bg-surface-container-lowest flex items-center justify-center text-outline"><span class="material-symbols-outlined">movie</span></div>';
      return '<img class="' + cls + ' object-cover bg-surface-container-lowest" referrerpolicy="no-referrer" loading="lazy" src="' + esc(src || alt) + '" data-alt="' + esc(alt) + '" alt="' + esc(it.title || "") + '"/>';
    }
    document.addEventListener("error", function (e) {
      var t = e.target;
      if (t && t.tagName === "IMG" && t.dataset && t.dataset.alt && t.getAttribute("src") !== t.dataset.alt) t.src = t.dataset.alt;
    }, true);

    /* ------------------------------------------------------------------ state */
    var S = {
      sites: [], library: [], jobs: [], siteMsg: {}, chips: {}, tab: "search", series: null, sel: {}, lastSearch: null, hist: [], cur: null,
      pendingDl: null, autoNext: null, ytdlp: true, ffmpeg: false, bs4: true, playing: null, pendingSeek: 0, tries: {}, lastProg: 0
    };

    /* ------------------------------------------------------------------ tabs */
    function showTab(name) {
      S.tab = name;
      $$(".ar-pane").forEach(function (p) { p.style.display = (p.id === "pane-" + name) ? "" : "none"; });
      $$(".ar-tab").forEach(function (b) {
        var on = b.getAttribute("data-tab") === name;
        b.classList.toggle("bg-primary-container", on); b.classList.toggle("text-on-primary-container", on);
        b.classList.toggle("bg-surface-container", !on);
      });
      if (name === "library") renderLibrary();
      if (name === "sites") renderSites();
      if (name === "dl") renderDownloads();
      if (name === "browse" && !$("#br-body").children.length) renderBrowseHome();
    }
    $("#ar-tabs").addEventListener("click", function (e) { var b = e.target.closest(".ar-tab"); if (b) showTab(b.getAttribute("data-tab")); });

    /* ------------------------------------------------------------------ player (the existing Miko player) */
    var player = null, hls = null, hlsLib = null;
    function loadHls(cb) {
      if (window.Hls) return cb(window.Hls);
      if (hlsLib === "failed") return cb(null);
      var urls = ["/assets/hls.min.js", "https://cdnjs.cloudflare.com/ajax/libs/hls.js/1.5.13/hls.min.js"], i = 0;
      (function next() {
        if (i >= urls.length) { hlsLib = "failed"; return cb(null); }
        var s = document.createElement("script"); s.src = urls[i++];
        s.onload = function () { cb(window.Hls || null); }; s.onerror = function () { s.remove(); next(); };
        document.head.appendChild(s);
      })();
    }
    function detachHls() { if (hls) { try { hls.destroy(); } catch (e) { } hls = null; } }
    function attach(video, src) {                       // hook from miko-player.js: return true when we take over loading
      detachHls();
      if (!/\.m3u8(\?|$)/i.test(src)) return false;
      video.autoplay = true;
      loadHls(function (Hls) {
        if (Hls && Hls.isSupported()) {
          hls = new Hls({ maxBufferLength: 40, enableWorker: true });
          var retried = false;
          hls.on(Hls.Events.ERROR, function (ev, d) {
            if (!d.fatal) return;
            if (d.type === Hls.ErrorTypes.NETWORK_ERROR && !retried) { retried = true; try { hls.startLoad(); } catch (e) { } return; }
            if (d.type === Hls.ErrorTypes.MEDIA_ERROR && !retried) { retried = true; try { hls.recoverMediaError(); } catch (e) { } return; }
            video.dispatchEvent(new Event("error"));
          });
          hls.on(Hls.Events.MANIFEST_PARSED, function () { var p = video.play(); if (p && p.catch) p.catch(function () { }); });
          hls.loadSource(src); hls.attachMedia(video);
        } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
          video.src = src;
        } else {
          video.src = src;                              // will raise the player's normal "cannot play" card
        }
      });
      return true;
    }
    function setupPlayer() {
      var hostEl = $("#miko-player-card");
      if (!hostEl || !window.MikoPlayer) { hostEl && (hostEl.innerHTML = '<div class="p-space-lg text-on-surface-variant">The video player could not be loaded.</div>'); return; }
      player = new window.MikoPlayer(hostEl, {
        attach: attach, detach: detachHls,
        openExternal: function (url, popup) { window.miko.api("open", { url: url, popup: !!popup }); },
        openLocal: function (p) { window.miko.api("download/open", { path: p }); },
        download: function (it) { if (it && it._ep) downloadEpisodes([it._ep]); },
        resolve: function (url) {                       // used for every episode page; "Try direct stream" cycles to the next source
          var n = S.tries[url] || 0; S.tries[url] = n + 1;
          return API("resolve", { url: url, index: n, force: n > 0 }).then(function (r) { if (r && r.ok) status("Source " + (r.index + 1) + " of " + r.count + " (" + r.via + ")"); return r; });
        },
        onLibraryOpen: refreshPlayerLibrary,
        onChange: function (it, i, list, cued) {
          if (list !== "results" || !it) return;
          saveProgress(true);
          S.playing = it; S.tries[it.href] = 0; S.pendingSeek = (!cued && it._ep && it._ep.pos > 15 && (!it._ep.dur || it._ep.pos < it._ep.dur - 40)) ? it._ep.pos : 0;
          nowPlaying(it);
          markPlayingRow(it._ep && it._ep.n);
        },
        onState: function (st, it) { if (st === "ended" && S.playing && S.playing._ep) { markWatched(S.playing._ep.n, true); } }
      });
      var v = player && $("video", hostEl);
      if (v) {
        v.addEventListener("loadedmetadata", function () { if (S.pendingSeek > 0 && v.duration > S.pendingSeek + 20) { try { v.currentTime = S.pendingSeek; } catch (e) { } } S.pendingSeek = 0; });
        v.addEventListener("ended", function () { if (S.playing && S.playing._ep) markWatched(S.playing._ep.n, true); });
      }
      setInterval(function () { if (v && !v.paused && !document.hidden) saveProgress(false); }, 15000);
      window.addEventListener("pagehide", function () { saveProgress(true); });
    }
    function videoEl() { return $("#miko-player-card video"); }
    function saveProgress(force) {
      var v = videoEl(), p = S.playing;
      if (!v || !p || !p._ep || !S.series || !S.series.library_id || !isFinite(v.duration) || v.duration < 30) return;
      if (!force && Date.now() - S.lastProg < 10000) return;
      S.lastProg = Date.now();
      if (v.currentTime < 5 && !force) return;
      p._ep.pos = v.currentTime; p._ep.dur = v.duration;
      API("progress", { id: S.series.library_id, n: p._ep.n, pos: v.currentTime, dur: v.duration });
      if (v.currentTime >= 0.9 * v.duration) { p._ep.watched = true; paintEpisodes(); }
    }
    function markWatched(n, flag) {
      var ep = S.series && S.series.episodes.filter(function (e) { return e.n === n; })[0];
      if (ep) ep.watched = flag;
      if (S.series && S.series.library_id) API("progress", { id: S.series.library_id, n: n, watched: flag }).then(loadState);
      paintEpisodes();
    }
    function refreshPlayerLibrary() { window.miko.api("video/library", {}).then(function (r) { if (r && r.ok && player) player.setLibrary(r.items || []); }).catch(function () { }); }
    function nowPlaying(it) {
      var ep = it._ep;
      $("#ar-now").innerHTML = '<div class="flex items-center gap-space-sm">' + img(S.series || {}, "w-12 h-16 rounded-md flex-shrink-0") +
        '<div class="min-w-0"><div class="font-title-sm text-title-sm text-on-surface truncate">' + esc(S.series ? S.series.title : it.title) + '</div>' +
        '<div class="text-primary">' + (ep ? "Episode " + esc(ep.n) : "") + (it.path ? " &bull; from your downloads" : "") + '</div>' +
        '<div class="font-label-sm truncate">' + esc(host(it.href || "")) + ' <span id="ar-src"></span></div></div></div>';
    }

    /* ------------------------------------------------------------------ state loading */
    function loadState() {
      return API("state").then(function (r) {
        if (!r || !r.ok) return;
        S.sites = r.sites; S.library = r.library; S.jobs = r.jobs; S.ytdlp = r.ytdlp; S.ffmpeg = r.ffmpeg; S.bs4 = r.bs4; S.folder = r.folder;
        renderChips(); renderBrowseSites();
        if (S.tab === "library") renderLibrary(); if (S.tab === "sites") renderSites(); if (S.tab === "dl") renderDownloads();
        badge();
        window.miko.pageContext = pageContext;
      });
    }
    function badge() {
      var act = S.jobs.filter(function (j) { return j.status === "queued" || j.status === "downloading"; }).length, b = $("#ar-dl-badge");
      b.textContent = act; b.classList.toggle("hidden", !act);
    }
    function pageContext() {
      var c = "The user is in Miko's Anime Room. Saved sites: " + (S.sites.map(function (s) { return s.name; }).join(", ") || "none") + ". ";
      if (S.series) c += "Open series: " + S.series.title + " (" + S.series.episodes.length + " episodes found). ";
      if (S.playing && S.playing._ep) c += "Now playing episode " + S.playing._ep.n + ". ";
      if (S.library.length) c += "Library: " + S.library.slice(0, 8).map(function (l) { return l.title + " (" + l.watched + "/" + l.total + " watched)"; }).join("; ") + ".";
      return c;
    }

    /* ------------------------------------------------------------------ site chips (which sites to search) */
    function renderChips() {
      var box = $("#ar-chips");
      if (!S.sites.length) { box.innerHTML = '<button data-addsite class="' + BTNP + '"><span class="material-symbols-outlined text-[16px]">add</span>Add your first anime website</button>'; return; }
      box.innerHTML = S.sites.map(function (s) {
        var on = S.chips[s.id] !== false && s.enabled;
        return '<button data-chip="' + esc(s.id) + '" class="' + BTN + (on ? " bg-primary-container text-on-primary-container" : "") + '" title="' + esc(s.url) + '">' + esc(s.name) + '</button>';
      }).join("");
    }
    $("#ar-chips").addEventListener("click", function (e) {
      if (e.target.closest("[data-addsite]")) return showTab("sites");
      var b = e.target.closest("[data-chip]"); if (!b) return;
      var id = b.getAttribute("data-chip"); S.chips[id] = S.chips[id] === false; renderChips();
    });
    function activeSiteIds() { return S.sites.filter(function (s) { return s.enabled && S.chips[s.id] !== false; }).map(function (s) { return s.id; }); }

    /* ------------------------------------------------------------------ search by name */
    function isUrl(t) { return /^(https?:\/\/|www\.)\S+$/i.test(t) || /^[a-z0-9-]+(\.[a-z0-9-]+)+\/\S*$/i.test(t); }
    function runSearch(q) {
      q = (q || $("#ar-q").value || "").trim(); if (!q) return Promise.resolve(null);
      $("#ar-q").value = q; window.miko.setQuery && window.miko.setQuery(q);
      if (isUrl(q)) { return openPage(/^https?:/i.test(q) ? q : "https://" + q.replace(/^www\./i, "www.")); }
      showTab("search");
      if (!S.sites.length) { $("#pane-search").innerHTML = emptyBox("Add an anime website first, then I can search it for you.", '<button data-goto="sites" class="' + BTNP + '">Add a website</button>'); return Promise.resolve(null); }
      $("#pane-search").innerHTML = emptyBox("Searching " + esc(q) + " on your sites…");
      status("Searching…");
      return API("search", { q: q, sites: activeSiteIds() }).then(function (r) {
        status("");
        if (!r || !r.ok) { $("#pane-search").innerHTML = emptyBox(esc((r && r.error) || "Search failed.")); return null; }
        S.lastSearch = r; renderSearch(r); return r;
      });
    }
    function emptyBox(msg, extra) { return '<div class="' + CARD + ' p-space-lg text-on-surface-variant font-body-md text-center flex flex-col items-center gap-space-sm"><div>' + msg + '</div>' + (extra || "") + '</div>'; }
    function renderSearch(r) {
      var h = "";
      if (r.meta && r.meta.length) {
        h += '<div class="' + CARD + ' p-space-md"><div class="font-label-sm text-on-surface-variant uppercase tracking-wider mb-space-xs">Names &amp; info (AniList)</div><div class="flex gap-space-sm overflow-x-auto pb-1">' +
          r.meta.slice(0, 5).map(function (m, i) {
            return '<div data-meta="' + i + '" class="flex-shrink-0 w-48 flex gap-space-sm cursor-pointer rounded-DEFAULT bg-surface-container hover:bg-surface-container-high p-space-sm">' + img({ thumb: m.poster }, "w-12 h-16 rounded-md flex-shrink-0") +
              '<div class="min-w-0 font-body-sm text-body-sm"><div class="text-on-surface font-semibold line-clamp-2">' + esc(m.title) + '</div><div class="text-on-surface-variant">' + esc([m.format, m.year, m.episodes ? m.episodes + " eps" : ""].filter(Boolean).join(" • ")) + '</div></div></div>';
          }).join("") + '</div></div>';
      }
      (r.sites || []).forEach(function (s, si) {
        h += '<div class="' + CARD + ' p-space-md flex flex-col gap-space-sm"><div class="flex items-center justify-between"><div class="font-headline-md text-headline-md text-on-surface">' + esc(s.site) + '</div>' +
          '<div class="font-label-sm text-on-surface-variant">' + (s.ok ? (s.items.length + " result" + (s.items.length === 1 ? "" : "s")) : "") + '</div></div>';
        if (!s.ok) h += '<div class="text-error font-body-sm">' + esc(s.error) + '</div>';
        else if (!s.items.length) h += '<div class="text-on-surface-variant font-body-sm">' + esc(s.error || "No results on this site.") + '</div>';
        else h += cardGrid(s.items, si, s.site_id);
        h += '</div>';
      });
      $("#pane-search").innerHTML = h || emptyBox("Nothing found.");
    }
    function cardHtml(it, key, siteId) {
      return '<div data-card="' + key + '" data-site="' + esc(siteId || "") + '" class="group cursor-pointer rounded-DEFAULT bg-surface-container hover:bg-surface-container-high overflow-hidden transition-all">' +
        '<div class="relative">' + img(it, "w-full aspect-[3/4]") + (it.kind === "episode" ? '<span class="absolute top-1 left-1 px-2 rounded-full bg-secondary-container text-on-secondary-container font-label-sm">EP ' + esc(it.ep) + '</span>' : "") +
        (it.score >= 0.8 ? '<span class="absolute top-1 right-1 px-2 rounded-full bg-primary-container text-on-primary-container font-label-sm">match</span>' : "") + '</div>' +
        '<div class="p-space-sm font-body-sm text-body-sm text-on-surface line-clamp-2 group-hover:text-primary" title="' + esc(it.title) + '">' + esc(it.title) + '</div></div>';
    }
    function cardGrid(items, group, siteId) {
      return '<div class="grid grid-cols-2 sm:grid-cols-3 gap-space-sm">' + items.slice(0, 60).map(function (it, i) { return cardHtml(it, group + ":" + i, siteId); }).join("") + '</div>';
    }

    $("#pane-search").addEventListener("click", function (e) {
      var g = e.target.closest("[data-goto]"); if (g) return showTab(g.getAttribute("data-goto"));
      var m = e.target.closest("[data-meta]");
      if (m && S.lastSearch) { var meta = S.lastSearch.meta[+m.getAttribute("data-meta")]; $("#ar-q").value = meta.romaji || meta.title; return runSearch(); }
      var c = e.target.closest("[data-card]"); if (!c || !S.lastSearch) return;
      var k = c.getAttribute("data-card").split(":"), it = S.lastSearch.sites[+k[0]].items[+k[1]];
      openItem(it, c.getAttribute("data-site"));
    });
    function openItem(it, siteId) {
      if (it.kind === "episode") return playSingle(it, siteId);
      return openPage(it.href, siteId);
    }

    /* ------------------------------------------------------------------ browse (reader mode) */
    function renderBrowseSites() {
      $("#br-sites").innerHTML = S.sites.map(function (s) { return '<button data-home="' + esc(s.id) + '" class="' + BTN + '">' + esc(s.name) + '</button>'; }).join("") || '<span class="text-on-surface-variant font-body-sm">No sites saved yet.</span>';
    }
    function renderBrowseHome() {
      $("#br-body").innerHTML = emptyBox(S.sites.length ? "Pick one of your sites above, or type any address and press Go." : "Add an anime website in <b>My sites</b>, then browse it here.");
    }
    $("#br-sites").addEventListener("click", function (e) { var b = e.target.closest("[data-home]"); if (!b) return; var s = S.sites.filter(function (x) { return x.id === b.getAttribute("data-home"); })[0]; if (s) openPage(s.url, s.id); });
    $("#br-go").addEventListener("click", function () { var u = $("#br-url").value.trim(); if (u) runSearch(u); });
    $("#br-url").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); $("#br-go").click(); } });
    $("#br-back").addEventListener("click", function () { S.hist.pop(); var p = S.hist.pop(); if (p) openPage(p.url, p.site); });
    $("#br-ext").addEventListener("click", function () { var u = S.cur && S.cur.url || $("#br-url").value; if (u) window.miko.api("open", { url: u }); });
    $("#br-live").addEventListener("click", function () {
      var u = (S.cur && S.cur.url) || $("#br-url").value.trim(); if (!u) return;
      API("frameable", { url: u }).then(function (r) {
        if (r && r.ok && r.frameable) {
          showTab("browse");
          $("#br-body").innerHTML = '<div class="' + CARD + ' overflow-hidden"><div class="p-space-sm flex gap-space-sm items-center font-label-sm text-on-surface-variant"><span class="material-symbols-outlined text-[16px]">info</span>Live view (pop-ups are blocked). Playing from here isn\'t possible; use the reader view for that.<button id="br-live-close" class="' + BTN + ' ml-auto">Back to reader view</button></div>' +
            '<iframe sandbox="allow-scripts allow-forms allow-same-origin" referrerpolicy="no-referrer" src="' + esc(r.url) + '" style="width:100%;height:70vh;border:0;background:#fff"></iframe></div>';
          $("#br-live-close").onclick = function () { if (S.cur) renderPage(S.cur); };
        } else say("That site does not allow being shown inside other apps, so I'm using the reader view. You can still open it in your browser.");
      }).catch(function () { });
    });

    function openPage(url, siteId) {
      showTab("browse"); $("#br-url").value = url; status("Loading page…");
      $("#br-body").innerHTML = emptyBox("Loading " + esc(host(url)) + "…");
      return API("page", { url: url, site_id: siteId || null }).then(function (r) {
        status("");
        if (!r || !r.ok) {
          $("#br-body").innerHTML = emptyBox(esc((r && r.error) || "Could not open that page.") + '<br><button data-ext class="' + BTN + ' mt-2">Open in my browser</button>');
          S.cur = { url: url }; return null;
        }
        S.cur = r; S.hist.push({ url: r.url, site: r.site_id }); $("#br-url").value = r.url;
        if (r.kind === "series") { openSeries(r); return r; }
        renderPage(r); return r;
      });
    }
    $("#br-body").addEventListener("click", function (e) {
      if (e.target.closest("[data-ext]")) { var u = S.cur && S.cur.url; if (u) window.miko.api("open", { url: u }); return; }
      var n = e.target.closest("[data-next]"); if (n) return openPage(n.getAttribute("data-next"), S.cur && S.cur.site_id);
      var c = e.target.closest("[data-card]"); if (c && S.cur) { var it = S.cur.items[+c.getAttribute("data-card").split(":")[1]]; return openItem(it, S.cur.site_id); }
      if (e.target.closest("[data-play-this]")) return playSingle({ href: S.cur.url, title: S.cur.title, thumb: S.cur.poster, ep: S.cur.ep }, S.cur.site_id);
      if (e.target.closest("[data-gen]")) return generateFromTemplate();
    });
    function renderPage(r) {
      var h = "";
      if (r.kind === "episode") {
        h += '<div class="' + CARD + ' p-space-lg flex flex-col gap-space-sm"><div class="font-headline-md text-headline-md text-on-surface">' + esc(r.title) + '</div>' +
          '<div class="text-on-surface-variant font-body-sm">This looks like a single episode page.</div><div class="flex gap-space-xs flex-wrap"><button data-play-this class="' + BTNP + '"><span class="material-symbols-outlined text-[16px]">play_arrow</span>Play it here</button></div>' +
          (r.template ? '<div class="mt-space-sm pt-space-sm flex flex-col gap-space-xs"><div class="font-label-md text-on-surface">Build the whole episode list from this link</div><div class="flex gap-space-xs items-center flex-wrap">' +
            'Episodes <input id="gen-start" type="number" min="1" value="1" class="w-20 px-2 py-1 rounded-full bg-surface-container-lowest text-on-surface select-text"/> to <input id="gen-end" type="number" min="1" value="' + Math.max(12, (+r.ep || 0)) + '" class="w-20 px-2 py-1 rounded-full bg-surface-container-lowest text-on-surface select-text"/>' +
            '<button data-gen class="' + BTN + '">Build list</button></div><div class="font-label-sm text-on-surface-variant select-text">' + esc(r.template) + '</div></div>' : '') + '</div>';
      }
      if (r.items && r.items.length) {
        h += '<div class="' + CARD + ' p-space-md flex flex-col gap-space-sm"><div class="font-headline-md text-headline-md text-on-surface">' + esc(r.title || host(r.url)) + '</div>' +
          cardGrid(r.items, 0, r.site_id) + (r.next ? '<button data-next="' + esc(r.next) + '" class="' + BTN + ' self-center">Next page <span class="material-symbols-outlined text-[16px]">arrow_forward</span></button>' : "") + '</div>';
      } else if (r.kind !== "episode") {
        h += emptyBox("I couldn't find any anime cards on this page. It may load its content with scripts. Try the site's search, the Live view, or open it in your browser.");
      }
      $("#br-body").innerHTML = h;
    }
    function generateFromTemplate() {
      var a = +$("#gen-start").value || 1, b = +$("#gen-end").value || 12;
      API("episodes/template", { template: S.cur.template, start: a, end: b }).then(function (r) {
        if (!r.ok) return say(r.error);
        openSeries({ url: S.cur.url, title: S.cur.title.replace(/\s*[-–]?\s*(?:episode|ep)\s*\d+.*$/i, "") || S.cur.title, episodes: r.episodes, poster: S.cur.poster, poster_p: S.cur.poster_p, site_id: S.cur.site_id, site: S.cur.site, kind: "series", built: true });
      });
    }

    /* ------------------------------------------------------------------ series + episodes */
    function openSeries(r) {
      r.episodes = r.episodes || [];
      S.series = r; S.sel = {};
      $("#ar-series-tab").textContent = r.title.length > 24 ? r.title.slice(0, 22) + "…" : r.title;
      $(".ar-tab[data-tab=series]").style.display = "";
      renderSeries(); showTab("series"); setPlaylist();
      window.miko.pageContext = pageContext;
      if (!r.episodes.length) tryYtdlpList(r);
      afterSeriesOpen();
    }
    function tryYtdlpList(r) {
      if (!S.ytdlp) return;
      API("episodes/ytdlp", { url: r.url }).then(function (x) { if (x && x.ok && x.episodes.length && S.series === r) { r.episodes = x.episodes; renderSeries(); setPlaylist(); } });
    }
    function epItems() {
      var s = S.series; if (!s) return [];
      return s.episodes.map(function (e) {
        var it = { href: e.url, title: s.title + " \u2013 Episode " + e.n, thumb: s.poster || "", _ep: e };
        if (e.path) { it.path = e.path; it.name = e.path.split(/[\\/]/).pop(); }
        return it;
      });
    }
    function setPlaylist() { if (player) player.setResults(epItems()); }
    function epRow(e) {
      var sel = S.sel[e.n] ? "ring-2 ring-primary" : "";
      return '<div data-ep="' + esc(e.n) + '" class="ar-ep flex items-center gap-space-sm rounded-DEFAULT bg-surface-container hover:bg-surface-container-high p-space-sm ' + sel + '">' +
        '<input type="checkbox" data-pick="' + esc(e.n) + '" ' + (S.sel[e.n] ? "checked" : "") + ' class="accent-purple-500 w-4 h-4"/>' +
        '<div class="w-10 text-center font-title-sm text-title-sm text-primary">' + esc(e.n) + '</div>' +
        '<div class="flex-1 min-w-0 font-body-sm text-on-surface truncate" title="' + esc(e.title) + '">' + esc(e.title) + '</div>' +
        (e.watched ? '<span class="material-symbols-outlined text-[18px] text-tertiary" title="Watched">check_circle</span>' : (e.pos > 15 ? '<span class="font-label-sm text-on-surface-variant">' + Math.round(e.pos / 60) + ' min in</span>' : "")) +
        (e.path ? '<span class="material-symbols-outlined text-[18px] text-secondary" title="Downloaded">download_done</span>' : "") +
        '<button data-play="' + esc(e.n) + '" class="p-1.5 rounded-full bg-surface-container-highest text-primary hover:bg-primary hover:text-on-primary-fixed" title="Watch"><span class="material-symbols-outlined text-[18px]">play_arrow</span></button>' +
        '<button data-dl="' + esc(e.n) + '" class="p-1.5 rounded-full bg-surface-container-highest text-on-surface-variant hover:text-secondary" title="Download"><span class="material-symbols-outlined text-[18px]">download</span></button></div>';
    }
    function renderSeries() {
      var s = S.series, p = $("#pane-series"); if (!s) { p.innerHTML = ""; return; }
      var inLib = !!s.library_id;
      p.innerHTML =
        '<div class="' + CARD + ' p-space-md flex gap-space-md">' + img(s, "w-28 h-40 rounded-DEFAULT flex-shrink-0") +
        '<div class="min-w-0 flex flex-col gap-space-xs"><div class="font-headline-lg text-headline-lg text-on-surface">' + esc(s.title) + '</div>' +
        '<div class="font-label-sm text-on-surface-variant">' + esc((s.site || host(s.url)) + " • " + s.episodes.length + " episodes") + '</div>' +
        '<div class="font-body-sm text-on-surface-variant line-clamp-4">' + esc(s.description || "") + '</div>' +
        '<div class="flex gap-space-xs flex-wrap mt-auto">' +
        '<button data-lib class="' + (inLib ? BTN : BTNP) + '"><span class="material-symbols-outlined text-[16px]">' + (inLib ? "bookmark_added" : "bookmark_add") + '</span>' + (inLib ? "In library" : "Add to library") + '</button>' +
        '<button data-ask class="' + BTN + '"><span class="material-symbols-outlined text-[16px]">auto_awesome</span>Ask Miko</button>' +
        '<button data-ext2 class="' + BTN + '"><span class="material-symbols-outlined text-[16px]">open_in_new</span>Site</button></div></div></div>' +
        '<div id="ar-confirm"></div>' +
        (s.episodes.length ? '<div class="' + CARD + ' p-space-md flex flex-col gap-space-sm">' +
          '<div class="flex items-center gap-space-xs flex-wrap"><input id="ar-range" type="text" placeholder="e.g. 1-12, 5, 3-6,9, latest" class="flex-1 min-w-[10rem] px-space-md py-1.5 rounded-full bg-surface-container-lowest text-on-surface select-text"/>' +
          '<button data-selrange class="' + BTN + '">Select</button><button data-selall class="' + BTN + '">All</button><button data-selnone class="' + BTN + '">None</button>' +
          '<button data-selunw class="' + BTN + '">Unwatched</button></div>' +
          '<div class="flex items-center gap-space-xs flex-wrap"><span id="ar-selcount" class="font-label-md text-on-surface-variant">0 selected</span>' +
          '<button data-dlsel class="' + BTNP + ' ml-auto"><span class="material-symbols-outlined text-[16px]">download</span>Download selected</button></div>' +
          (S.ytdlp ? "" : '<div class="font-label-sm text-on-surface-variant">Tip: yt-dlp is not installed, so some streams cannot be downloaded (run install_extra_packages.bat).</div>') +
          '</div><div id="ar-eps" class="flex flex-col gap-space-xs max-h-[60vh] overflow-y-auto pr-1">' + s.episodes.map(epRow).join("") + '</div>'
          : '<div class="' + CARD + ' p-space-lg text-on-surface-variant text-center flex flex-col gap-space-sm"><div>I could not find an episode list on this page (many sites fill it in with scripts).</div>' +
            '<div class="font-body-sm">If you have one episode link, paste it in the search box and use &ldquo;Build the whole episode list&rdquo;.</div></div>');
      updateSelCount();
    }
    function paintEpisodes() {
      var box = $("#ar-eps"); if (!box || !S.series) return;
      var top = box.scrollTop; box.innerHTML = S.series.episodes.map(epRow).join(""); box.scrollTop = top; updateSelCount();
      if (S.playing && S.playing._ep) markPlayingRow(S.playing._ep.n);
    }
    function markPlayingRow(n) { $$(".ar-ep").forEach(function (r) { r.style.outline = (n != null && r.getAttribute("data-ep") === String(n)) ? "2px solid #ddb7ff" : ""; }); }
    function updateSelCount() { var n = Object.keys(S.sel).filter(function (k) { return S.sel[k]; }).length, el = $("#ar-selcount"); if (el) el.textContent = n + " selected"; }
    function selectedEpisodes() { return S.series.episodes.filter(function (e) { return S.sel[e.n]; }); }
    function rangeToSet(spec) {
      var nums = S.series.episodes.map(function (e) { return e.n; }).sort(function (a, b) { return a - b; }), out = {}; spec = (spec || "").toLowerCase().trim();
      if (!nums.length) return out;
      if (spec === "all" || spec === "") nums.forEach(function (n) { out[n] = true; });
      else if (spec === "latest" || spec === "last") out[nums[nums.length - 1]] = true;
      else if (spec === "first") out[nums[0]] = true;
      else {
        var m = /^last\s+(\d+)$/.exec(spec);
        if (m) nums.slice(-(+m[1])).forEach(function (n) { out[n] = true; });
        else spec.split(/[,\s]+/).forEach(function (part) {
          var r = /^(\d+)\s*(?:-|to)\s*(\d+)$/.exec(part);
          if (r) { var a = Math.min(+r[1], +r[2]), b = Math.max(+r[1], +r[2]); nums.forEach(function (n) { if (n >= a && n <= b) out[n] = true; }); }
          else if (/^\d+$/.test(part)) nums.forEach(function (n) { if (n === +part) out[n] = true; });
        });
      }
      return out;
    }
    function toRangeString(eps) {
      var n = eps.map(function (e) { return e.n; }).sort(function (a, b) { return a - b; }), out = [], i = 0;
      while (i < n.length) { var j = i; while (j + 1 < n.length && n[j + 1] === n[j] + 1) j++; out.push(j > i ? n[i] + "-" + n[j] : String(n[i])); i = j + 1; }
      return out.join(",");
    }
    $("#pane-series").addEventListener("click", function (e) {
      var s = S.series; if (!s) return;
      var t;
      if ((t = e.target.closest("[data-play]"))) { return playEpisodeNumber(+t.getAttribute("data-play")); }
      if ((t = e.target.closest("[data-dl]"))) { var ep = s.episodes.filter(function (x) { return String(x.n) === t.getAttribute("data-dl"); })[0]; return downloadEpisodes([ep]); }
      if (e.target.closest("[data-lib]")) return toggleLibrary();
      if (e.target.closest("[data-ask]")) return window.miko.ask("In two short, spoiler-free sentences: what is the anime \"" + s.title + "\" about, and is it worth watching?", pageContext());
      if (e.target.closest("[data-ext2]")) return window.miko.api("open", { url: s.url });
      if (e.target.closest("[data-selrange]")) { S.sel = rangeToSet($("#ar-range").value); return paintEpisodes(); }
      if (e.target.closest("[data-selall]")) { S.sel = rangeToSet("all"); return paintEpisodes(); }
      if (e.target.closest("[data-selnone]")) { S.sel = {}; return paintEpisodes(); }
      if (e.target.closest("[data-selunw]")) { S.sel = {}; s.episodes.forEach(function (x) { if (!x.watched) S.sel[x.n] = true; }); return paintEpisodes(); }
      if (e.target.closest("[data-dlsel]")) { var sel = selectedEpisodes(); if (!sel.length) return say("Select some episodes first, for example type 1-12 and press Select."); return downloadEpisodes(sel); }
      if (e.target.closest("[data-confirm]")) return confirmPending();
      if (e.target.closest("[data-cancelconf]")) { S.pendingDl = null; $("#ar-confirm").innerHTML = ""; }
    });
    $("#pane-series").addEventListener("change", function (e) {
      var c = e.target.closest("[data-pick]"); if (!c) return;
      S.sel[c.getAttribute("data-pick")] = c.checked; if (!c.checked) delete S.sel[c.getAttribute("data-pick")];
      c.closest(".ar-ep").classList.toggle("ring-2", c.checked); c.closest(".ar-ep").classList.toggle("ring-primary", c.checked); updateSelCount();
    });
    $("#pane-series").addEventListener("keydown", function (e) { if (e.target.id === "ar-range" && e.key === "Enter") { S.sel = rangeToSet(e.target.value); paintEpisodes(); } });

    function ensureLibrary() {
      var s = S.series; if (s.library_id) return Promise.resolve(s.library_id);
      return API("library/save", { url: s.url, title: s.title, poster: s.poster || "", site: s.site || "", site_id: s.site_id || "", description: s.description || "", episodes: s.episodes }).then(function (r) {
        if (r && r.ok) { s.library_id = r.id; loadState(); renderSeries(); return r.id; } throw new Error("save failed");
      });
    }
    function toggleLibrary() {
      var s = S.series;
      if (s.library_id) return API("library/remove", { id: s.library_id }).then(function () { s.library_id = null; loadState(); renderSeries(); say("Removed from your library. Downloaded files stay on disk."); });
      return ensureLibrary().then(function () { say("Saved " + s.title + " to your library."); });
    }

    /* ------------------------------------------------------------------ watching */
    function playEpisodeNumber(n) {
      var s = S.series; if (!s) return;
      var i = s.episodes.map(function (e) { return e.n; }).indexOf(n);
      if (i < 0) return say("I don't see episode " + n + " in this list.");
      setPlaylist();
      if (!s.library_id) ensureLibrary().catch(function () { });
      player.play(i, { list: "results", user: true });
      window.scrollTo({ top: 0, behavior: "smooth" });
      say("Playing " + s.title + " episode " + n + ".");
    }
    function playSingle(it, siteId) {
      var ep = { n: it.ep != null ? it.ep : 1, title: it.title, url: it.href };
      S.series = { title: (it.title || "Episode").replace(/\s*[-–]?\s*(?:episode|ep)\s*\d+.*$/i, "") || it.title, url: it.href, episodes: [ep], poster: it.thumb || "", poster_p: it.thumb_p || "", site_id: siteId, kind: "episode", single: true };
      S.sel = {}; setPlaylist(); player.play(0, { list: "results", user: true });
      $("#ar-series-tab").textContent = S.series.title.slice(0, 22); $(".ar-tab[data-tab=series]").style.display = ""; renderSeries();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    /* ------------------------------------------------------------------ downloads */
    function downloadEpisodes(eps) {
      var s = S.series; if (!s || !eps.length) return;
      var all = s.episodes;
      return API("download", { title: s.title, url: s.url, episodes: all, range: toRangeString(eps), poster: s.poster || "", site: s.site || "", site_id: s.site_id || "" }).then(function (r) {
        if (!r || !r.ok) return say("I couldn't start that: " + ((r && r.error) || "unknown error"));
        say("Queued " + r.count + " episode" + (r.count === 1 ? "" : "s") + " of " + s.title + ". They download two at a time; watch the Downloads tab.");
        S.sel = {}; paintEpisodes(); loadState(); startPolling();
      });
    }
    var pollT = null;
    function startPolling() { if (pollT) return; pollT = setInterval(poll, 1500); poll(); }
    function poll() {
      if (document.hidden) return;
      API("state").then(function (r) {
        if (!r || !r.ok) return;
        var before = S.jobs, doneNow = [];
        r.jobs.forEach(function (j) { var b = before.filter(function (x) { return x.id === j.id; })[0]; if (j.status === "done" && (!b || b.status !== "done")) doneNow.push(j); });
        S.jobs = r.jobs; S.library = r.library; badge();
        if (S.tab === "dl") renderDownloads();
        if (doneNow.length && S.series) {
          doneNow.forEach(function (j) { if (j.anime === S.series.title) { var ep = S.series.episodes.filter(function (e) { return e.n === j.ep; })[0]; if (ep) ep.path = j.path; } });
          paintEpisodes(); setPlaylist(); refreshPlayerLibrary();
        }
        if (!r.jobs.some(function (j) { return j.status === "queued" || j.status === "downloading"; })) { clearInterval(pollT); pollT = null; }
      });
    }
    function renderDownloads() {
      var p = $("#pane-dl"), jobs = S.jobs;
      var head = '<div class="' + CARD + ' p-space-md flex items-center gap-space-sm flex-wrap"><div class="font-headline-md text-headline-md text-on-surface">Anime downloads</div><div class="font-label-sm text-on-surface-variant select-text">' + esc(S.folder || "") + '</div>' +
        '<button data-opendl class="' + BTN + ' ml-auto"><span class="material-symbols-outlined text-[16px]">folder_open</span>Open folder</button><button data-dlscreen class="' + BTN + '">Full download manager</button></div>';
      if (!jobs.length) { p.innerHTML = head + emptyBox("No anime downloads yet. Open a series, pick episodes and press Download."); return; }
      p.innerHTML = head + '<div class="flex flex-col gap-space-xs">' + jobs.map(function (j) {
        var act = j.status === "queued" || j.status === "downloading";
        return '<div class="' + CARD + ' p-space-sm flex flex-col gap-1"><div class="flex items-center gap-space-sm"><div class="flex-1 min-w-0 font-body-sm text-on-surface truncate">' + esc(j.title) + '</div>' +
          '<div class="font-label-sm ' + (j.status === "error" ? "text-error" : j.status === "done" ? "text-tertiary" : "text-on-surface-variant") + '">' + esc(j.status === "downloading" ? j.progress + "%" + (j.speed ? " • " + fmtB(j.speed) + "/s" : "") : j.status) + '</div>' +
          (act ? '<button data-cancel="' + j.id + '" class="p-1 rounded-full text-on-surface-variant hover:text-error" title="Cancel"><span class="material-symbols-outlined text-[18px]">close</span></button>' : "") +
          (j.status === "done" && j.path ? '<button data-playfile="' + esc(j.path) + '" class="p-1 rounded-full text-primary" title="Play"><span class="material-symbols-outlined text-[18px]">play_arrow</span></button>' : "") + '</div>' +
          (j.status === "downloading" ? '<div class="h-1 rounded-full bg-surface-container-highest overflow-hidden"><div class="h-full bg-gradient-to-r from-tertiary to-primary-container" style="width:' + (+j.progress || 0) + '%"></div></div>' : "") +
          (j.status === "error" ? '<div class="font-label-sm text-error">' + esc(j.error) + '</div>' : "") + '</div>';
      }).join("") + '</div>';
    }
    $("#pane-dl").addEventListener("click", function (e) {
      var t;
      if ((t = e.target.closest("[data-cancel]"))) return window.miko.api("download/cancel", { id: +t.getAttribute("data-cancel") }).then(poll);
      if (e.target.closest("[data-opendl]")) return window.miko.api("download/reveal", { path: "" });
      if (e.target.closest("[data-dlscreen]")) return parent.postMessage({ type: "miko-nav", route: "downloads" }, "*");
      if ((t = e.target.closest("[data-playfile]"))) { var path = t.getAttribute("data-playfile"); refreshPlayerLibrary(); S.playing = null; player.setResults([{ path: path, title: path.split(/[\\/]/).pop(), href: "" }]); player.play(0, { list: "results", user: true }); }
    });

    /* ------------------------------------------------------------------ library */
    function renderLibrary() {
      var p = $("#pane-library"), L = S.library;
      if (!L.length) { p.innerHTML = emptyBox("Your library is empty. Open a series and press <b>Add to library</b>. Anything you download is added automatically."); return; }
      p.innerHTML = '<div class="grid grid-cols-1 sm:grid-cols-2 gap-space-sm">' + L.map(function (e) {
        return '<div class="' + CARD + ' p-space-sm flex gap-space-sm" data-lib="' + esc(e.id) + '">' + img({ thumb: e.poster }, "w-20 h-28 rounded-md flex-shrink-0") +
          '<div class="min-w-0 flex flex-col gap-1 flex-1"><div class="font-title-sm text-title-sm text-on-surface line-clamp-2">' + esc(e.title) + '</div>' +
          '<div class="font-label-sm text-on-surface-variant">' + esc(e.watched + "/" + e.total + " watched • " + e.downloaded + " downloaded • " + e.site) + '</div>' +
          '<div class="h-1 rounded-full bg-surface-container-highest overflow-hidden"><div class="h-full bg-primary" style="width:' + (e.total ? Math.round(100 * e.watched / e.total) : 0) + '%"></div></div>' +
          '<div class="flex gap-space-xs flex-wrap mt-auto">' + (e.next ? '<button data-cont="' + esc(e.id) + '" class="' + BTNP + '">Continue E' + esc(e.next.n) + '</button>' : "") +
          '<button data-open="' + esc(e.id) + '" class="' + BTN + '">Open</button><button data-refresh="' + esc(e.id) + '" class="' + BTN + '" title="Look for new episodes"><span class="material-symbols-outlined text-[16px]">refresh</span></button>' +
          '<button data-remove="' + esc(e.id) + '" class="' + BTN + '" title="Remove from library"><span class="material-symbols-outlined text-[16px]">delete</span></button></div></div></div>';
      }).join("") + '</div>';
    }
    function libEntryToSeries(id) {
      return API("library/get", { id: id }).then(function (r) {
        var e = r && r.entry; if (!e) return null;
        return { url: e.url, title: e.title, poster: e.poster || "", description: e.description || "", episodes: e.episodes, site: e.site, site_id: e.site_id, library_id: e.id, kind: "series" };
      });
    }
    $("#pane-library").addEventListener("click", function (e) {
      var t;
      if ((t = e.target.closest("[data-cont]"))) { return libEntryToSeries(t.getAttribute("data-cont")).then(function (s) { if (!s) return; openSeries(s); var n = (S.library.filter(function (l) { return l.id === s.library_id; })[0] || {}).next; playEpisodeNumber(n ? n.n : s.episodes[0].n); }); }
      if ((t = e.target.closest("[data-open]"))) { return libEntryToSeries(t.getAttribute("data-open")).then(function (s) { if (s) openSeries(s); }); }
      if ((t = e.target.closest("[data-refresh]"))) { status("Checking for new episodes…"); return API("library/refresh", { id: t.getAttribute("data-refresh") }).then(function (r) { status(""); say(r.ok ? (r.added ? r.added + " new episode(s) found." : "No new episodes yet.") : r.error); loadState(); }); }
      if ((t = e.target.closest("[data-remove]"))) { return API("library/remove", { id: t.getAttribute("data-remove") }).then(function () { if (S.series && S.series.library_id === t.getAttribute("data-remove")) S.series.library_id = null; loadState(); }); }
    });

    /* ------------------------------------------------------------------ my sites */
    function renderSites() {
      var p = $("#pane-sites");
      var h = '<div class="' + CARD + ' p-space-md flex flex-col gap-space-sm"><div class="font-headline-md text-headline-md text-on-surface">Add an anime website</div>' +
        '<div class="flex gap-space-xs flex-wrap"><input id="site-url" type="text" placeholder="https://your-anime-site.example" class="flex-1 min-w-[12rem] px-space-md py-2 rounded-full bg-surface-container-lowest text-on-surface select-text"/>' +
        '<input id="site-name" type="text" placeholder="Name (optional)" class="w-44 px-space-md py-2 rounded-full bg-surface-container-lowest text-on-surface select-text"/>' +
        '<button data-addsite2 class="' + BTNP + '"><span class="material-symbols-outlined text-[16px]">add</span>Save site</button></div>' +
        '<div class="font-label-sm text-on-surface-variant">You choose the sites. Miko reads their pages and finds the video for you; it never ships with any site list. Please only use sites and content you are allowed to access in your country.</div>' +
        (S.bs4 ? "" : '<div class="font-label-md text-error">The beautifulsoup4 package is missing. Run install_extra_packages.bat, then restart Miko.</div>') + '</div>';
      if (!S.sites.length) h += emptyBox("No sites saved yet.");
      S.sites.forEach(function (s) {
        h += '<div class="' + CARD + ' p-space-md flex flex-col gap-space-sm" data-siteid="' + esc(s.id) + '"><div class="flex items-center gap-space-sm flex-wrap">' +
          '<div class="font-title-sm text-title-sm text-on-surface">' + esc(s.name) + '</div><div class="font-label-sm text-on-surface-variant select-text">' + esc(s.url) + '</div>' +
          '<label class="ml-auto flex items-center gap-1 font-label-sm text-on-surface-variant"><input type="checkbox" data-enable ' + (s.enabled ? "checked" : "") + ' class="accent-purple-500"/>Use in search</label></div>' +
          '<div class="flex gap-space-xs flex-wrap"><button data-browse class="' + BTN + '">Browse</button><button data-test class="' + BTN + '">Test</button><button data-rm class="' + BTN + '">Remove</button><span data-result class="font-label-sm self-center ' + ((S.siteMsg[s.id] || {}).ok === false ? "text-error" : "text-tertiary") + '">' + esc((S.siteMsg[s.id] || {}).text || "") + '</span></div>' +
          '<details><summary class="cursor-pointer font-label-md text-on-surface-variant">Advanced (search address, cookie)</summary><div class="flex flex-col gap-space-xs mt-space-xs">' +
          '<input data-f="search_url" type="text" value="' + esc(s.search_url) + '" placeholder="Search address, e.g. https://site.com/?s={q}  (blank = detect automatically)" class="px-space-md py-1.5 rounded-full bg-surface-container-lowest text-on-surface select-text"/>' +
          '<input data-f="cookie" type="text" placeholder="' + (s.has_cookie ? "Cookie saved (type a new one to replace)" : "Cookie header (only for sites that need your browser login / anti-bot check)") + '" class="px-space-md py-1.5 rounded-full bg-surface-container-lowest text-on-surface select-text"/>' +
          '<div class="flex gap-space-xs"><button data-saveadv class="' + BTN + '">Save</button>' + (s.has_cookie ? '<button data-clearcookie class="' + BTN + '">Forget cookie</button>' : "") + '</div></div></details></div>';
      });
      p.innerHTML = h;
    }
    $("#pane-sites").addEventListener("click", function (e) {
      var t;
      if (e.target.closest("[data-addsite2]")) { return API("sites/add", { url: $("#site-url").value, name: $("#site-name").value }).then(function (r) { if (!r.ok) return say(r.error); say("Saved " + r.site.name + ". Testing it now…"); return loadState().then(function () { return testSite(r.site.id); }); }); }
      var card = e.target.closest("[data-siteid]"); if (!card) return; var id = card.getAttribute("data-siteid");
      var s = S.sites.filter(function (x) { return x.id === id; })[0];
      if (e.target.closest("[data-browse]")) return openPage(s.url, id);
      if (e.target.closest("[data-test]")) return testSite(id);
      if (e.target.closest("[data-rm]")) return API("sites/remove", { id: id }).then(loadState);
      if (e.target.closest("[data-saveadv]")) { var b = { id: id, search_url: $("[data-f=search_url]", card).value }; var ck = $("[data-f=cookie]", card).value.trim(); if (ck) b.cookie = ck; return API("sites/update", b).then(function (r) { say(r.ok ? "Saved." : r.error); loadState(); }); }
      if (e.target.closest("[data-clearcookie]")) return API("sites/update", { id: id, clear_cookie: true }).then(loadState);
    });
    $("#pane-sites").addEventListener("change", function (e) {
      if (!e.target.matches("[data-enable]")) return; var id = e.target.closest("[data-siteid]").getAttribute("data-siteid");
      API("sites/update", { id: id, enabled: e.target.checked }).then(loadState);
    });
    function testSite(id) {
      var card = $('[data-siteid="' + id + '"]'), out = card && $("[data-result]", card);
      S.siteMsg[id] = { text: "Testing…", ok: true }; if (out) out.textContent = "Testing…";
      return API("sites/test", { id: id }).then(function (r) {
        var m = r.ok ? ("Works \u2022 " + r.cards + " items found \u2022 search " + (r.search_url ? "detected" : "not detected (set it under Advanced)") + " \u2022 " + r.ms + " ms") : ("Problem: " + r.error);
        S.siteMsg[id] = { text: m, ok: !!r.ok };
        say(m); return loadState();
      });
    }

    /* ------------------------------------------------------------------ voice / AI commands (queued by the server) */
    function bestLibrary(q) {
      var best = null, sc = 0; S.library.forEach(function (l) { var s = overlap(q, l.title); if (s > sc) { sc = s; best = l; } }); return sc >= 0.67 ? best : null;
    }
    function epFromSpec(spec) {
      var s = S.series; if (!s || !s.episodes.length) return null; spec = String(spec || "1");
      var nums = s.episodes.map(function (e) { return e.n; });
      if (/^\d+$/.test(spec)) return +spec;
      if (spec === "latest") return nums[nums.length - 1];
      if (spec === "next") { var lib = S.library.filter(function (l) { return l.id === s.library_id; })[0]; return lib && lib.next ? lib.next.n : nums[0]; }
      return nums[0];
    }
    function afterSeriesOpen() {
      var a = S.autoNext; if (!a || !S.series) return; S.autoNext = null;
      if (a.mode === "watch") { var n = epFromSpec(a.ep); if (n != null) playEpisodeNumber(n); }
      if (a.mode === "download") { stageDownload(a.range); }
    }
    function stageDownload(range) {
      var s = S.series; if (!s) return; var set = rangeToSet(range === "all" ? "all" : range);
      var eps = s.episodes.filter(function (e) { return set[e.n]; });
      if (!eps.length) return say("I opened " + s.title + " but couldn't match episodes \"" + range + "\" to its list. Choose them below.");
      S.sel = set; paintEpisodes(); S.pendingDl = eps;
      $("#ar-confirm").innerHTML = '<div class="' + CARD + ' p-space-md flex items-center gap-space-sm flex-wrap ring-2 ring-primary"><span class="material-symbols-outlined text-primary">help</span>' +
        '<div class="flex-1 font-body-md text-on-surface">Download ' + eps.length + ' episode' + (eps.length === 1 ? "" : "s") + ' (' + esc(toRangeString(eps)) + ') of ' + esc(s.title) + '?</div>' +
        '<button data-confirm class="' + BTNP + '">Download</button><button data-cancelconf class="' + BTN + '">Cancel</button></div>';
      say("Ready: " + eps.length + " episode(s) of " + s.title + ". Press Download, or say \"confirm download\".");
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    function confirmPending() {
      if (!S.pendingDl || !S.pendingDl.length) { say("There's nothing waiting for confirmation."); return; }
      var eps = S.pendingDl; S.pendingDl = null; $("#ar-confirm") && ($("#ar-confirm").innerHTML = ""); downloadEpisodes(eps);
    }
    function findAndOpen(q, mode, spec) {
      var lib = bestLibrary(q);
      S.autoNext = { mode: mode, ep: spec, range: spec };
      if (lib) return libEntryToSeries(lib.id).then(function (s) { if (s) { say("Found " + s.title + " in your library."); openSeries(s); } });
      return runSearch(q).then(function (r) {
        if (!r) { S.autoNext = null; return; }
        var best = null;
        (r.sites || []).forEach(function (sx) { (sx.items || []).forEach(function (it) { if (it.kind === "series" && (!best || it.score > best.it.score)) best = { it: it, site: sx.site_id }; }); });
        if (best && best.it.score >= 0.8) { say("Opening " + best.it.title + "."); return openPage(best.it.href, best.site); }
        say(r.sites && r.sites.some(function (x) { return x.items && x.items.length; }) ? "I found a few matches. Pick the right one and I'll " + (mode === "watch" ? "start playing" : "set up the download") + "." : "I couldn't find that on your saved sites.");
        if (!(r.sites || []).some(function (x) { return x.items && x.items.length; })) S.autoNext = null;
      });
    }
    function handleAction(a) {
      if (!a) return;
      switch (a.do) {
        case "open": return;
        case "add_site": return API("sites/add", { url: a.url }).then(function (r) { if (!r.ok) return say(r.error); say("Added " + r.site.name + "."); loadState().then(function () { showTab("sites"); testSite(r.site.id); }); });
        case "search": $("#ar-q").value = a.q; return runSearch(a.q);
        case "watch": $("#ar-q").value = a.q; return findAndOpen(a.q, "watch", a.ep || "1");
        case "download": $("#ar-q").value = a.q; return findAndOpen(a.q, "download", a.range || "all");
        case "confirm": return confirmPending();
        case "continue":
          var e = S.library.filter(function (l) { return l.next; })[0];
          if (!e) return say("Your library has nothing to continue yet.");
          return libEntryToSeries(e.id).then(function (s) { if (!s) return; openSeries(s); playEpisodeNumber(e.next.n); });
      }
    }
    var handling = false;
    function handlePending() {
      if (handling) return; handling = true;
      return API("pending").then(function (r) {
        var acts = (r && r.actions) || [];
        return acts.reduce(function (p, a) { return p.then(function () { return handleAction(a); }); }, Promise.resolve());
      }).catch(function () { }).then(function () { handling = false; });
    }
    window.addEventListener("message", function (e) { if (e.data && e.data.type === "miko-anime") loadState().then(handlePending); });

    /* ------------------------------------------------------------------ search box + start */
    $("#ar-go").addEventListener("click", function () { runSearch(); });
    $("#ar-q").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); runSearch(); } });
    document.addEventListener("keydown", function (e) { if (e.key === "/" && document.activeElement && !/input|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); $("#ar-q").focus(); } });
    document.addEventListener("click", function (e) { var d = e.target.closest("[data-goto]"); if (d) showTab(d.getAttribute("data-goto")); });

    setupPlayer();
    showTab("search");
    $("#pane-search").innerHTML = emptyBox("Type an anime name above and I'll search all your saved sites. You can also paste any page or episode link.");
    loadState().then(function () {
      if (S.jobs.some(function (j) { return j.status === "queued" || j.status === "downloading"; })) startPolling();
      if (!S.sites.length) $("#pane-search").innerHTML = emptyBox("Welcome to the Anime Room. Start by adding an anime website you like to use.", '<button data-goto="sites" class="' + BTNP + '">Add a website</button>');
      return handlePending();
    });
    refreshPlayerLibrary();
    window.__animeRoom = { S: S, runSearch: runSearch, openPage: openPage, handleAction: handleAction };
  }
})();
