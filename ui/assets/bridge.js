
(function(){
  /* Miko bridge: injected into every Stitch screen by the server.
     1) makes the top tabs / settings gear really navigate
     2) exposes window.miko.api(...) so buttons can call the Python backend */
  var map = {"web-search":1,"image-gallery":1,"video-vault":1,"news-feed":1,
             "research-intel":1,"downloads":1,"settings":1,"overlay":1,"audio":1,"anime-room":1};
  /* Anime Room tab: copied from the Downloads tab so it matches every screen's look */
  function addAnimeTab(){
    var nav = document.querySelector("nav[data-active-classes]");
    if(!nav || nav.querySelector('[data-path="anime-room"]')) return;
    var ref = nav.querySelector('[data-path="downloads"]');
    if(!ref) return;
    var a = ref.cloneNode(true);
    a.setAttribute("data-path","anime-room"); a.removeAttribute("aria-current"); a.textContent = "Anime";
    nav.insertBefore(a, ref);
  }
  if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", addAnimeTab); else addAnimeTab();
  document.addEventListener("click", function(e){
    var a = e.target.closest && e.target.closest("[data-path]");
    if(a && map[a.getAttribute("data-path")]){
      e.preventDefault();
      parent.postMessage({type:"miko-nav", route:a.getAttribute("data-path")}, "*");
    }
  }, true);
  window.miko = {
    api: function(path, body){
      return fetch("/api/" + path, {
        method: body === undefined ? "GET" : "POST",
        headers: {"Content-Type": "application/json"},
        body: body === undefined ? undefined : JSON.stringify(body)
      }).then(function(r){ return r.json(); });
    }
  };
  /* window controls in the Stitch title bar */
  document.addEventListener("click", function(e){
    var b = e.target.closest && e.target.closest("button[aria-label]");
    if(!b) return;
    var l = b.getAttribute("aria-label");
    if(l === "Close") window.miko.api("window", {action:"close"});
    if(l === "Minimize") window.miko.api("window", {action:"minimize"});
  }, true);
})();


/* ---------- Miko companion chat wiring ---------- */
(function(){
  function $(s,r){return (r||document).querySelector(s);}
  function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));}

  // The companion speech bubble: the <p> right after the "Companion Dialogue" label.
  function bubble(){
    if(window.miko && window.miko.bubbleEl) return window.miko.bubbleEl;
    var lab = $$("span").filter(function(x){return x.textContent.trim()==="Companion Dialogue";})[0];
    return lab ? lab.closest("div").parentElement.querySelector("p") : null;
  }
  // The follow-up input: any text input whose placeholder / label mentions Miko or follow-up.
  function chatInput(){
    return $$("input[type=text],input:not([type])").filter(function(i){
      var t=((i.placeholder||"")+" "+(i.getAttribute("aria-label")||"")).toLowerCase();
      return t.indexOf("miko")>-1 || t.indexOf("follow-up")>-1 || t.indexOf("verify")>-1 || t.indexOf("copilot")>-1;
    })[0] || $("#copilot-query-input");
  }
  function sendBtnFor(inp){
    if(!inp) return null;
    var box = inp.parentElement;
    for(var i=0;i<4 && box;i++, box=box.parentElement){
      var b = $$("button",box).filter(function(x){
        var t=(x.textContent||"").trim(); return t==="send" || t==="arrow_upward" || (x.getAttribute("aria-label")||"").toLowerCase().indexOf("send")>-1;
      })[0];
      if(b) return b;
    }
    return null;
  }

  var busy=false;
  async function ask(text, context){
    var p = bubble();
    if(!text || !text.trim() || !p || busy) return;
    busy=true; p.textContent="…"; p.style.opacity=".7";
    try{
      var r = await fetch("/stream/chat",{method:"POST",headers:{"Content-Type":"application/json"},
                          body:JSON.stringify({text:text,context:context||""})});
      var reader = r.body.getReader(), dec = new TextDecoder(), out="";
      for(;;){
        var c = await reader.read(); if(c.done) break;
        out += dec.decode(c.value,{stream:true});
        p.textContent = out.split("\u0000")[0]; p.style.opacity="1";
      }
      var parts = out.split("\u0000"); out = parts[0]; p.textContent = out;
      if(parts[1]){ try{ var act=JSON.parse(parts[1]); parent.postMessage({type:"miko-action", action:act}, "*"); }catch(e){} }
      window.miko.lastReply = out;
      if(window.miko.cfg && window.miko.cfg.speak_replies && out) window.miko.speak(out);
    }catch(e){ p.textContent="I lost connection to my brain. Is Miko running?"; }
    busy=false; p.style.opacity="1";
  }
  window.miko.ask = ask;
  window.miko.showBubble = function(t){ var p = bubble(); if(p){ p.textContent = t; p.style.opacity = "1"; } };

  function wire(){
    var inp = chatInput(), btn = sendBtnFor(inp);
    if(inp){
      var go = function(){ var v=inp.value; inp.value=""; ask(v, window.miko.pageContext ? window.miko.pageContext() : ""); };
      inp.addEventListener("keydown", function(e){ if(e.key==="Enter"){ e.preventDefault(); go(); }});
      if(btn) btn.addEventListener("click", function(e){ e.preventDefault(); go(); });
    }
    // Suggested-inquiry chips send their own text as a question.
    var head = $$("span").filter(function(x){return x.textContent.trim().toLowerCase()==="suggested inquiries";})[0];
    if(head){
      $$("button", head.parentElement).forEach(function(b){
        b.addEventListener("click", function(e){ e.preventDefault(); ask(b.textContent.trim(), ""); });
      });
    }
    // Clear Session: wipe chat history and reset the bubble.
    $$("button").forEach(function(b){
      if(b.textContent.indexOf("Clear Session")>-1){
        b.addEventListener("click", function(e){
          e.preventDefault();
          window.miko.api("chat/clear",{}).then(function(){
            var p=bubble(); if(p) p.textContent="Fresh start! What shall we look up?";
            var i=chatInput(); if(i) i.value="";
          });
        });
      }
    });
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded", wire); else wire();
})();


/* ---------- Web Search screen wiring ---------- */
(function(){
  if(location.pathname.indexOf("/screen/web-search")!==0) return;
  function $(s,r){return (r||document).querySelector(s);}
  function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));}
  function txt(el,t){ if(el) el.textContent=t; }
  function domain(u){ try{ return new URL(u).hostname.replace(/^www\./,""); }catch(e){ return u||""; } }

  var section, header, pager, template, input, countEl, latEl, current = {q:"", results:[], page:1, filter:""};
  var PER_PAGE = 6;

  function init(){
    input = $("#main-search-input");
    section = $$("section").filter(function(s){ return s.querySelector("article"); })[0];
    if(!section || !input) return;
    var arts = $$("article", section);
    template = arts[0].cloneNode(true);
    // template: strip the decorative glow so clones stay clean but keep every class
    arts.forEach(function(a){ a.remove(); });
    header = section.children[0];
    pager  = section.children[section.children.length-1];
    countEl = $$("span", header)[0];
    latEl = $$("span").filter(function(s){ return /^\d+\.\d+s$/.test(s.textContent.trim()); })[0];
    wireControls();
    var q = new URLSearchParams(parent.location.search).get("q") || "";
    if(q){ input.value=q; run(); } else { setStatus("Type something and press Search."); }
  }

  function setStatus(msg){
    $$(".miko-status", section).forEach(function(n){ n.remove(); });
    var d=document.createElement("div");
    d.className="miko-status p-space-md rounded-DEFAULT bg-surface-container-low/70 text-on-surface-variant font-body-md";
    d.textContent=msg; section.insertBefore(d, pager);
  }

  function card(r, i){
    var c = template.cloneNode(true);
    var img = $("img", c);
    var host = domain(r.href);
    if(img){ img.removeAttribute("data-alt"); img.alt=r.title||"";
      img.src = "https://www.google.com/s2/favicons?sz=128&domain=" + encodeURIComponent(host);
      img.style.objectFit="contain"; img.style.padding="18px"; }
    var tag = $$("span", c).filter(function(s){ return /^(WIKI|GUIDE|REDDIT|OFFICIAL)$/i.test(s.textContent.trim()); })[0];
    txt(tag, host.split(".").slice(-2,-1)[0] ? host.split(".").slice(-2,-1)[0].toUpperCase().slice(0,10) : "WEB");
    var badge = $$("span", c).filter(function(s){ return /Match|Verified|Official|Community/.test(s.textContent); })[0];
    if(badge && badge.querySelector("span")){ badge.lastChild.textContent = " Result " + String(i+1).padStart(2,"0"); }
    var url = $$("span", c).filter(function(s){ return /^https?:\/\//.test(s.textContent.trim()); })[0];
    txt(url, r.href);
    var h2 = $("h2", c); txt(h2, r.title || host);
    h2.onclick = function(){ openUrl(r.href); };
    txt($("p", c), (r.body||"").trim() || "No description available.");
    var btns = $$("button", c);
    btns.forEach(function(b){
      var label = b.textContent.trim();
      if(/Open in Miko Browser/.test(label)) b.onclick=function(){ openUrl(r.href); };
      else if(/Extract Summary|Analyze|Replies|Calculator|Build/.test(label)) b.onclick=function(){ summarize(r, b); };
      else if(b.title==="Save to Cache" || /bookmark/.test(b.textContent)) b.onclick=function(){ save(r, b); };
    });
    // keep only the three real buttons: open, summarize, save
    var upd = $$("span", c).filter(function(s){ return /^(Updated|Official|\d)/.test(s.textContent.trim()) && !s.querySelector("span"); }).pop();
    txt(upd, host);
    return c;
  }

  function openUrl(u){ window.miko.api("open", {url:u}); }
  function summarize(r, btn){
    window.miko.ask("Summarize this search result in two short sentences. Title: " + r.title + ". Text: " + (r.body||"").slice(0,900), "");
  }
  function save(r, btn){
    window.miko.api("memory/add", {fact:"Saved link: " + r.title + " - " + r.href}).then(function(){
      var ic=$("span", btn); if(ic){ ic.textContent="bookmark_added"; }
    });
  }

  function render(){
    $$("article", section).forEach(function(a){ a.remove(); });
    $$(".miko-status", section).forEach(function(n){ n.remove(); });
    var all = current.results;
    if(!all.length){ setStatus(current.error || "No results."); }
    var start=(current.page-1)*PER_PAGE, slice=all.slice(start, start+PER_PAGE);
    slice.forEach(function(r,i){ section.insertBefore(card(r,start+i), pager); });
    txt(countEl, String(all.length));
    var pages = Math.max(1, Math.ceil(all.length/PER_PAGE));
    var nums = $$("button, span", pager).filter(function(e){ return /^\d+$/.test(e.textContent.trim()); });
    nums.forEach(function(e,i){
      e.style.display = (i<pages)?"":"none";
      e.textContent = String(i+1);
      var on = (i+1)===current.page;
      e.onclick = function(){ current.page=i+1; render(); };
      e.className = e.className.replace(/bg-primary text-on-primary|bg-surface-container hover:bg-surface-container-high text-on-surface-variant/g, on ? "bg-primary text-on-primary" : "bg-surface-container hover:bg-surface-container-high text-on-surface-variant");
    });
    var navs = $$("button", pager).filter(function(b){ return /Previous|Next/.test(b.textContent); });
    navs.forEach(function(b){
      b.onclick=function(){ var d=/Next/.test(b.textContent)?1:-1; var p=Math.min(pages,Math.max(1,current.page+d)); if(p!==current.page){ current.page=p; render(); } };
    });
    window.miko.pageContext = function(){
      return "The user is looking at web search results for '" + current.q + "': " +
        all.slice(0,6).map(function(r){ return r.title + " - " + (r.body||"").slice(0,160); }).join(" | ");
    };
  }

  async function run(){
    var q = (input.value||"").trim();
    if(!q) return;
    window.miko.setQuery(q);
    if(current.filter){ q = q + " " + current.filter; }
    setStatus("Searching the web for \u201c" + q + "\u201d\u2026");
    var t0 = performance.now();
    var res;
    try{ res = await window.miko.api("search", {kind:"web", q:q, n:12}); }
    catch(e){ res = {ok:false, results:[], error:"Could not reach Miko's search."}; }
    current = {q:q, results:res.results||[], page:1, filter:current.filter, error: res.ok ? "" : res.error};
    txt(latEl, ((performance.now()-t0)/1000).toFixed(2)+"s");
    render();
  }

  function wireControls(){
    input.addEventListener("keydown", function(e){ if(e.key==="Enter"){ e.preventDefault(); current.filter=""; run(); }});
    var go = $$("button").filter(function(b){ return b.textContent.replace(/\s+/g," ").trim()==="auto_awesome Search"; })[0];
    if(go) go.addEventListener("click", function(e){ e.preventDefault(); current.filter=""; run(); });
    var clr = $("#clear-search-btn");
    if(clr) clr.addEventListener("click", function(e){ e.preventDefault(); input.value=""; input.focus(); });
    // Filter pills: each one adds a real search hint to the query
    var hints = {"All Results":"", "Guides & Wikis":"guide wiki", "Reddit Discussions":"reddit", "Official Sites":"official site", "Build Calculators":"calculator tool"};
    $$("button").forEach(function(b){
      var label = b.textContent.replace(/\s+/g," ").trim().replace(/^[a-z_]+ /,"");
      if(label in hints){
        b.addEventListener("click", function(e){ e.preventDefault(); current.filter=hints[label]; run(); });
      }
    });
    // Voice search mic: browser speech recognition when available
    var mic = $$("button[title*='Voice']")[0];
    if(mic) mic.addEventListener("click", function(){
      setStatus("Listening\u2026 just speak (say \u201csearch for \u2026\u201d)."); window.miko.wake();
    });
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded", init); else init();
})();


/* ---------- Image Gallery screen wiring ---------- */
(function(){
  if(location.pathname.indexOf("/screen/image-gallery")!==0) return;
  function $(s,r){return (r||document).querySelector(s);}
  function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));}
  function txt(el,t){ if(el) el.textContent=t; }
  function say(html){ var s=$("#mikoSpeech"); if(s) s.innerHTML=html; }
  function esc(s){ return String(s||"").replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }

  var grid, tpl, input, selected=null, items=[], picked={}, lastFile={}, PER=12, page=1, stat, preset="";
  var PRESETS={"Wallpapers (4K/8K)":"wallpaper 4k","Concept Art":"concept art","Transparent PNGs":"transparent png","Anime Fanart":"anime fanart","Ultrawide 21:9":"ultrawide 21:9 wallpaper"};

  function init(){
    input=$("#searchInput");
    grid=$$("div").filter(function(d){ return (d.className||"").indexOf("md:grid-cols-2")>-1 && d.querySelector("article"); })[0];
    if(!grid||!input) return;
    window.miko.bubbleEl=$("#mikoSpeech"); tpl=$("article",grid).cloneNode(true); tpl.removeAttribute("onclick");
    $$("article",grid).forEach(function(a){a.remove();});
    stat=$$("span").filter(function(s){ return /Media Found/.test(s.textContent); })[0];
    wire();
    var q=new URLSearchParams(parent.location.search).get("q")||"";
    if(q){ input.value=q; search(); } else { grid.innerHTML='<div class="col-span-full p-space-md text-on-surface-variant">Type something and press Enter to search for images.</div>'; }
  }

  function card(it,idx){
    var c=tpl.cloneNode(true);
    var im=$("img",c); im.removeAttribute("data-alt"); im.alt=it.title||""; im.loading="lazy";
    im.src=it.thumb||it.image; im.onerror=function(){ if(im.src!==it.image && it.image) im.src=it.image; };
    var badges=$$("span",c).filter(function(s){ return /4K|2K|PNG|WEBP|JPG|Native|UHD|Fanart|QHD/i.test(s.textContent) && !s.querySelector("span"); });
    var dim=(it.w&&it.h)?(it.w+"\u00d7"+it.h):"";
    var fmt=((it.image||"").split("?")[0].split(".").pop()||"img").toUpperCase().slice(0,4);
    if(badges[0]) txt(badges[0], it.w>=3800?"4K UHD":(it.w>=2500?"2K QHD":(it.w?"HD":"IMG")));
    if(badges[1]) txt(badges[1], fmt);
    var dom=$$("span",c).filter(function(s){ return /\.(com|net|org|io|co)/.test(s.textContent)&&!s.querySelector("span"); })[0];
    txt(dom, (it.source||"").slice(0,24));
    txt($("h4",c), it.title||"Untitled");
    txt($("p",c), [dim, fmt, it.source].filter(Boolean).join(" \u2022 "));
    c.onclick=function(e){ if(e.target.closest("button")) return; select(it,c); };
    $$("button",c).forEach(function(b){
      var t=(b.title||"")+" "+b.textContent;
      b.onclick=function(e){ e.stopPropagation();
        if(/Download/.test(t)) download(it,b);
        else if(/Wallpaper|Desktop/.test(t)) wallpaper(it,b);
        else if(/Visual Search/.test(t)) window.miko.api("open",{url:"https://lens.google.com/uploadbyurl?url="+encodeURIComponent(it.image)});
        else if(/Source/.test(t)) window.miko.api("open",{url:it.href});
        else if(/favorite/.test(t)) fav(it,b);
      };
    });
    it._card=c; return c;
  }

  function select(it,c){
    selected=it;
    $$("article",grid).forEach(function(a){ a.style.outline=""; }); if(c) c.style.outline="2px solid #ddb7ff";
    var im=$("#inspectorImg"); if(im){ im.removeAttribute("data-alt"); im.src=it.thumb||it.image; }
    txt($("#targetResolution"), (it.w&&it.h)?(it.w+" x "+it.h):"size unknown");
    txt($("#targetFormat"), ((it.image||"").split("?")[0].split(".").pop()||"img").toUpperCase().slice(0,4));
    say("Loaded <strong>"+esc(it.title)+"</strong> from <em>"+esc(it.source||"the web")+"</em>. Want me to download it or set it as your wallpaper?");
  }

  function waitJob(id, cb){
    var t=setInterval(function(){ window.miko.api("download/list",{}).then(function(r){
      var j=(r.jobs||[]).filter(function(x){return x.id===id;})[0];
      if(!j) { clearInterval(t); return; }
      if(j.status==="done"||j.status==="error"||j.status==="cancelled"){ clearInterval(t); cb(j); }
    }); },700);
  }
  function download(it,btn){
    say("Downloading <strong>"+esc(it.title)+"</strong>\u2026");
    window.miko.api("download/start",{kind:"file",url:it.image,title:it.title}).then(function(r){
      if(!r.ok){ say("I couldn't start that download: "+esc(r.error)); return; }
      waitJob(r.id,function(j){ if(j.status==="done"){ lastFile[it.image]=j.path; say("Saved! It's in your Miko downloads folder."); } else say("That download failed: "+esc(j.error||j.status)); });
    });
  }
  function wallpaper(it,btn){
    say("Getting the picture ready\u2026");
    var go=function(path){ window.miko.api("wallpaper",{path:path}).then(function(r){ say(r.ok?"Wallpaper set! \u2661":"I couldn't set the wallpaper: "+esc(r.error)); }); };
    if(lastFile[it.image]) return go(lastFile[it.image]);
    window.miko.api("download/start",{kind:"file",url:it.image,title:it.title}).then(function(r){
      if(!r.ok){ say("Download failed: "+esc(r.error)); return; }
      waitJob(r.id,function(j){ if(j.status==="done"){ lastFile[it.image]=j.path; go(j.path); } else say("Download failed: "+esc(j.error||j.status)); });
    });
  }
  function fav(it,b){ window.miko.api("memory/add",{fact:"Liked image: "+it.title+" - "+it.href}).then(function(){ var i=$("span",b); if(i) i.style.fontVariationSettings="'FILL' 1"; }); }

  function render(){
    grid.innerHTML="";
    if(!items.length){ grid.innerHTML='<div class="col-span-full p-space-md text-on-surface-variant">'+esc(window.__imgErr||"No images found.")+'</div>'; }
    var s=(page-1)*PER; items.slice(s,s+PER).forEach(function(it,i){ grid.appendChild(card(it,s+i)); });
    txt(stat, items.length+" Media Found");
    var pages=Math.max(1,Math.ceil(items.length/PER));
    var pg=$$("button").filter(function(b){ return /^\d+$/.test(b.textContent.trim()); });
    pg.forEach(function(b,i){ b.style.display=(i<pages)?"":"none"; b.textContent=String(i+1); b.onclick=function(){ page=i+1; render(); }; });
    var sa=$$("button").filter(function(b){ return /Select All/.test(b.textContent); })[0]; if(sa) txt($("span:last-child",sa),"Select All ("+Math.min(PER,items.length)+")");
    window.miko.pageContext=function(){ return "The user is browsing image results for '"+input.value+"'."; };
  }

  async function search(){
    var q=(input.value||"").trim(); if(!q) return; window.miko.setQuery(q);
    if(preset) q=q+" "+preset;
    txt(stat,"Searching\u2026");
    var r; try{ r=await window.miko.api("search",{kind:"images",q:q,n:36}); }catch(e){ r={ok:false,results:[],error:"Could not reach Miko's image search."}; }
    window.__imgErr=r.ok?"":r.error; items=r.results||[]; picked={}; page=1; render();
    if(items.length) select(items[0], $("article",grid));
  }

  function wire(){
    input.addEventListener("keydown",function(e){ if(e.key==="Enter"){ e.preventDefault(); preset=""; search(); }});
    $$("button").forEach(function(b){
      var label=b.textContent.replace(/\s+/g," ").trim();
      var key=Object.keys(PRESETS).filter(function(k){ return label.indexOf(k)>-1; })[0];
      if(key) b.addEventListener("click",function(){ preset=PRESETS[key]; search(); });
      if(/Refine/.test(label)) b.addEventListener("click",function(){ input.focus(); input.select(); });
      if(/Miko DeepScan/.test(label)) b.addEventListener("click",function(){ if(selected) window.miko.ask("Describe what kind of image this is and suggest a better search to find similar art. Title: "+selected.title+". Source: "+selected.source,""); else say("Pick an image first."); });
      if(/Select All/.test(label)) b.addEventListener("click",function(){ items.slice((page-1)*PER,page*PER).forEach(function(it,n){ picked[(page-1)*PER+n]=it; if(it._card) it._card.style.outline="2px solid #ffb0cd"; }); say("Selected "+Object.keys(picked).length+" images."); });
      if(/Batch Download/.test(label)) b.addEventListener("click",function(){ var list=Object.keys(picked).map(function(k){return picked[k];}); if(!list.length){ say("Select some images first with Select All, or click one and use Download."); return; } list.forEach(function(it){ window.miko.api("download/start",{kind:"file",url:it.image,title:it.title}); }); say("Queued "+list.length+" downloads. Watch them in the Downloads tab."); });
      if(/Set as Windows/.test(label)) b.addEventListener("click",function(){ if(selected) wallpaper(selected,b); else say("Pick an image first."); });
      if(/Upscale to 8K|AI Backgroun/.test(label)) b.addEventListener("click",function(){ say("That one needs an upscaler model, which I haven't added yet. I can download the original for you instead."); });
    });
    var sb=$("#setWallpaperBtn"); if(sb) sb.addEventListener("click",function(){ if(selected) wallpaper(selected,sb); });
    var clr=$("#clearBtn"); if(clr) clr.addEventListener("click",function(){ input.value=""; input.focus(); });
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();


/* ---------- Video Vault screen wiring ---------- */
(function(){
  if(location.pathname.indexOf("/screen/video-vault")!==0) return;
  function $(s,r){return (r||document).querySelector(s);}
  function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));}
  function txt(el,t){ if(el) el.textContent=t; }
  function esc(s){ return String(s||"").replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }

  var input, listBox, tpl, featured, more, matches, respEl, speech, selBanner, picked=null, all=[], shown=0, STEP=6, filter="all";
  var pipeName, pipeInfo, pipeBar, player=null;

  function init(){
    input=$("#video-search-input");
    var cards=$$("div").filter(function(d){ return (d.className||"").indexOf("group relative rounded-DEFAULT")>-1 && d.querySelector("h4") && d.querySelector("img"); });
    if(!input||cards.length<2) return;
    tpl=cards[cards.length-1].cloneNode(true);            // a plain list card
    listBox=cards[cards.length-1].parentElement;
    featured=cards[0];                                    // the big featured card
    cards.forEach(function(c){ if(c!==featured) c.remove(); });
    more=$$("button").filter(function(b){ return /Load More/.test(b.textContent); })[0];
    matches=$$("span").filter(function(s){ return /Matches$/.test(s.textContent.trim()); })[0];
    respEl=$$("span").filter(function(s){ return /response$/.test(s.textContent.trim()); })[0];
    var idx=$$("span").filter(function(s){ return /Indexing:/.test(s.textContent); })[0]; if(idx) idx.parentElement.parentElement.style.display="none";
    speech=$$("p").filter(function(p){ return /analyzed video/i.test(p.textContent); })[0];
    selBanner=$$("span").filter(function(s){ return /^Selected:/.test(s.textContent.trim()); })[0];
    var pipe=$$("span").filter(function(s){ return /Active Video Pipe/.test(s.textContent); })[0];
    if(pipe){ var box=pipe.closest("div").parentElement; pipeName=$$("span.truncate",box)[0]; pipeInfo=pipeName&&pipeName.nextElementSibling; pipeBar=$$("div",box).filter(function(d){ return /bg-gradient-to-r/.test(d.className)&&!d.children.length; })[0]; txt($$("span",box).filter(function(s){return /MB\/s/.test(s.textContent);})[0],"idle"); }
    // hide the fake jump points + waveform: they were sample data, not real analysis
    $$("span").filter(function(s){ return /AI Key Jump Points/.test(s.textContent); }).forEach(function(s){ var blk=s.closest("div").parentElement; if(blk) blk.style.display="none"; });
    $$("span").filter(function(s){ return /Dynamic Audio Waveform/.test(s.textContent); }).forEach(function(s){ var blk=s.closest("div").parentElement; if(blk) blk.style.display="none"; });
    wire();
    setupPlayer();
    var q=new URLSearchParams(parent.location.search).get("q")||"";
    if(q){ input.value=q; search(); } else { say("Type what you want to watch and press Enter. I'll find the videos."); featured.style.display="none"; }
  }
  function say(t){ if(speech) speech.textContent=t; }

  function fillCard(c, v, big){
    var im=$("img",c); if(im){ im.removeAttribute("data-alt"); im.src=v.thumb||""; im.alt=v.title||""; im.loading="lazy"; }
    var dur=$$("span",c).filter(function(s){ return /^\d{1,2}:\d{2}(:\d{2})?$/.test(s.textContent.trim()); })[0];
    txt(dur, v.duration||"");
    txt($("h4,h3",c), v.title||"Untitled");
    var meta=$$("span",c).filter(function(s){ return /text-(tertiary|secondary-fixed)/.test(s.className)&&!s.querySelector("span"); })[0];
    txt(meta, v.uploader||v.publisher||"Unknown");
    var rows=$$("span",c).filter(function(s){ return /views|ago/.test(s.textContent)&&!s.querySelector("span"); });
    if(rows[0]) txt(rows[0], v.publisher||"video"); if(rows[1]) txt(rows[1], (v.published||"").slice(0,10));
    // replace the made-up quality strip with real info
    $$("span",c).filter(function(s){ return /AI Timestamps|4K Master|Verified Stats|Miko Pick/.test(s.textContent); }).forEach(function(s){ s.style.display="none"; });
    $$("span",c).filter(function(s){ return /1440p|1080p|Dolby/.test(s.textContent); }).forEach(function(s){ txt(s, hostOf(v.href)); });
    c.style.cursor="pointer"; c._v=v;
    c.onclick=function(){ select(v,c,true); };
  }
  function hostOf(u){ try{ return new URL(u).hostname.replace(/^www\./,""); }catch(e){ return ""; } }

  /* ---- integrated video player (miko-player.js) ---- */
  function setupPlayer(){
    var host=$("#miko-player-card"); if(!host||!window.MikoPlayer) return;
    try{
      player=new window.MikoPlayer(host,{
        openExternal:function(url,popup){ window.miko.api("open",{url:url,popup:!!popup}); },
        download:function(it){ if(it&&it.href) window.miko.api("download/start",{kind:"video",url:it.href,title:it.title}).then(function(r){ if(r.ok){ say("Downloading \u201c"+(it.title||"")+"\u201d. Check the progress strip below."); watchJob(r.id,it.title); } else say("I couldn't start that: "+r.error); }); },
        resolve:function(url){ return window.miko.api("video/resolve",{url:url}); },
        openLocal:function(path){ window.miko.api("download/open",{path:path}); },
        onLibraryOpen:refreshLib,
        onChange:function(it,i,list){
          if(list==="results"){ var c=cardOf(it); select(it,c,false,true); if(c&&c.scrollIntoView) c.scrollIntoView({block:"nearest"}); }
          else say("Playing from your downloads: \u201c"+(it.title||it.name||"")+"\u201d.");
        }
      });
      setTimeout(refreshLib,600);
    }catch(e){ player=null; }
  }
  function refreshLib(){ if(!player) return; window.miko.api("video/library",{}).then(function(r){ if(r&&r.ok) player.setLibrary(r.items||[]); }).catch(function(){}); }
  function cardOf(v){ if(featured&&featured._v===v) return featured; return $$("div",listBox).filter(function(d){ return d._v===v; })[0]||null; }

  function select(v,c,user,quiet){
    picked=v;
    $$("div",listBox).forEach(function(d){ d.style.outline=""; }); featured.style.outline=""; if(c) c.style.outline="2px solid #ddb7ff";
    txt(selBanner,"Selected: "+(v.title||"").slice(0,48));
    if(selBanner&&selBanner.nextElementSibling) txt(selBanner.nextElementSibling,(v.uploader||v.publisher||"")+" \u2022 "+(v.duration||""));
    var bi=selBanner&&selBanner.closest("div").parentElement.querySelector("img"); if(bi){ bi.removeAttribute("data-alt"); bi.src=v.thumb||""; }
    say(user?"Playing \u201c"+(v.title||"")+"\u201d. I can also download it, pull the audio as MP3, or summarize it for you.":"Loaded \u201c"+(v.title||"")+"\u201d. Press play, or download it, pull the audio as MP3, or ask me to summarize it.");
    if(player&&!quiet){ var i=all.indexOf(v); if(i>=0){ if(user) player.play(i,{list:"results",user:true}); else player.cue(i,"results"); } }
  }

  function renderMore(){
    var slice=all.slice(shown,shown+STEP);
    slice.forEach(function(v,i){
      if(shown===0&&i===0){ featured.style.display=""; fillCard(featured,v,true); featured._v=v; return; }
      var c=tpl.cloneNode(true); fillCard(c,v,false); listBox.appendChild(c);
    });
    shown+=slice.length;
    if(more) more.style.display=(shown<all.length)?"":"none";
    txt(matches, all.length+" Matches");
  }

  async function search(){
    var q=(input.value||"").trim(); if(!q) return; window.miko.setQuery(q);
    var qq=q; if(filter==="youtube") qq+=" youtube"; if(filter==="twitch") qq+=" twitch"; if(filter==="bilibili") qq+=" bilibili";
    if(filter==="guides") qq+=" guide tutorial full"; if(filter==="shorts") qq+=" shorts";
    say("Searching for videos\u2026"); $$("div",listBox).forEach(function(d){ if(d!==featured && d.parentElement===listBox) d.remove(); });
    var t0=performance.now(), r;
    try{ r=await window.miko.api("search",{kind:"videos",q:qq,n:36}); }catch(e){ r={ok:false,results:[],error:"Could not reach Miko's video search."}; }
    txt(respEl, ((performance.now()-t0)/1000).toFixed(2)+"s response");
    all=r.results||[];
    if(filter==="guides") all=all.filter(function(v){ return mins(v.duration)>10; });
    if(filter==="shorts") all=all.filter(function(v){ var m=mins(v.duration); return m>0&&m<=1.1; });
    shown=0; txt(matches, all.length+" Matches");
    if(player) player.setResults(all);
    if(!all.length){ featured.style.display="none"; say(r.ok?"I couldn't find any videos for that.":(r.error||"Video search failed.")); return; }
    renderMore(); select(all[0],featured);
    window.miko.pageContext=function(){ return "The user is browsing video results for '"+q+"': "+all.slice(0,6).map(function(v){return v.title;}).join(" | "); };
  }
  function mins(d){ if(!d) return 0; var p=String(d).split(":").map(Number); if(p.some(isNaN)) return 0; return p.length===3?p[0]*60+p[1]+p[2]/60:p[0]+(p[1]||0)/60; }

  function watchJob(id,name){
    txt(pipeName,name||"Downloading\u2026");
    var t=setInterval(function(){ window.miko.api("download/list",{}).then(function(r){
      var j=(r.jobs||[]).filter(function(x){return x.id===id;})[0]; if(!j){ clearInterval(t); return; }
      if(pipeBar) pipeBar.style.width=j.progress+"%"; txt(pipeInfo, j.status==="downloading"?j.progress+"%":j.status);
      if(j.status==="done"){ clearInterval(t); say("Done! Saved to your Miko downloads folder."); txt(pipeInfo,"100% \u2713"); refreshLib(); }
      if(j.status==="error"){ clearInterval(t); say("That download didn't work: "+(j.error||"unknown error")); txt(pipeInfo,"failed"); }
      if(j.status==="cancelled"){ clearInterval(t); txt(pipeInfo,"cancelled"); }
    }); },800);
  }
  function dl(kind){
    if(!picked){ say("Pick a video first."); return; }
    window.miko.api("download/start",{kind:kind,url:picked.href,title:picked.title}).then(function(r){
      if(!r.ok){ say("I couldn't start that: "+r.error); return; }
      say((kind==="audio"?"Pulling the audio":"Downloading the video")+" now. Check the progress strip below."); watchJob(r.id,picked.title);
    });
  }

  function wire(){
    input.addEventListener("keydown",function(e){ if(e.key==="Enter"){ e.preventDefault(); search(); }});
    var clr=$("#clear-search-btn"); if(clr) clr.addEventListener("click",function(e){ e.preventDefault(); input.value=""; input.focus(); });
    $$("button").forEach(function(b){
      var l=b.textContent.replace(/\s+/g," ").trim();
      if(/Analyze & Search|Analyze &amp; Search/.test(l)) b.addEventListener("click",function(e){ e.preventDefault(); search(); });
      if(/^travel_explore All Platforms/.test(l)) b.addEventListener("click",function(){ filter="all"; search(); });
      if(/ YouTube$/.test(l)) b.addEventListener("click",function(){ filter="youtube"; search(); });
      if(/Twitch VODs/.test(l)) b.addEventListener("click",function(){ filter="twitch"; search(); });
      if(/ Bilibili$/.test(l)) b.addEventListener("click",function(){ filter="bilibili"; search(); });
      if(/Guides/.test(l)&&/timer/.test(l)) b.addEventListener("click",function(){ filter="guides"; search(); });
      if(/Shorts/.test(l)) b.addEventListener("click",function(){ filter="shorts"; search(); });
      if(/Load More/.test(l)) b.addEventListener("click",function(){ renderMore(); });
      if(/Download Video/.test(l)) b.addEventListener("click",function(){ dl("video"); });
      if(/Extract MP3/.test(l)) b.addEventListener("click",function(){ dl("audio"); });
      if(/Float PiP/.test(l)) b.addEventListener("click",function(){ if(player&&player.pip()) return; if(picked) window.miko.api("open",{url:picked.href,popup:true}); else say("Pick a video first."); });
      if(/Generate AI Transcript Summary/.test(l)) b.addEventListener("click",function(){ if(picked) window.miko.ask("In two short sentences, what is this video probably about, and is it worth watching? Title: "+picked.title+". Channel: "+(picked.uploader||picked.publisher)+". Length: "+picked.duration,""); else say("Pick a video first."); });
      if(b.title==="Sort Relevance") b.addEventListener("click",function(){ all.sort(function(a,b2){ return mins(b2.duration)-mins(a.duration); }); $$("div",listBox).forEach(function(d){ if(d!==featured&&d.parentElement===listBox) d.remove(); }); shown=0; renderMore(); if(player) player.setResults(all); say("Sorted by length, longest first."); });
    });
    // double-click a card to open the video in your browser
    document.addEventListener("dblclick",function(e){ var c=e.target.closest("div.group"); if(!c||!picked) return; if(player&&player.mode()!=="idle"&&player.mode()!=="msg") player.fullscreen(); else if(picked.href) window.miko.api("open",{url:picked.href}); });
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();

/* ---------- News Feed screen wiring ---------- */
(function(){
  if(location.pathname.indexOf("/screen/news-feed")!==0) return;
  function $(s,r){return (r||document).querySelector(s);}
  function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));}
  function txt(el,t){ if(el) el.textContent=t; }
  function hide(el){ if(el) el.style.display="none"; }
  function hostOf(u){ try{ return new URL(u).hostname.replace(/^www\./,""); }catch(e){ return ""; } }
  function ago(d){
    var t=Date.parse(d); if(isNaN(t)) return "";
    var m=Math.max(0,Math.round((Date.now()-t)/60000));
    if(m<60) return m+" mins ago"; if(m<1440) return Math.round(m/60)+"h ago"; return Math.round(m/1440)+"d ago";
  }
  function sentences(s){ return (s||"").replace(/\s+/g," ").split(/(?<=[.!?])\s+/).map(function(x){return x.trim();}).filter(function(x){return x.length>25;}); }

  var input, hero, secTpl, secBox, col, statusEl, bubbleP, synced, healthEl, srcEl, sparks=[];
  var items=[], mode="news", pillName="Gaming", sortNew=false, lastQ="", speaking=false;
  var PILLS={"Trending Gaming":{q:"video game news",tag:"Gaming"},"AI & Neural Tech":{q:"artificial intelligence news",tag:"AI"},
             "Patch Notes":{q:"game patch notes update",tag:"Patch"},"Anime & Pop Culture":{q:"anime news",tag:"Anime"},
             "PC Hardware":{q:"PC hardware GPU news",tag:"Hardware"},"Saved Intel":{saved:true,tag:"Saved"}};

  function init(){
    input=$("input[placeholder^='Search news']");
    hero=$$("article").filter(function(a){ return a.querySelector("h2"); })[0];
    var secs=$$("article").filter(function(a){ return a.querySelector("h3"); });
    if(!input||!hero||!secs.length) return;
    secTpl=secs[0].cloneNode(true); secBox=secs[0].parentElement; secs.forEach(function(a){ a.remove(); });
    col=hero.parentElement;
    bubbleP=(function(){ var l=$$("span").filter(function(s){ return /60-Second Morning Debriefing/.test(s.textContent); })[0]; return l?l.closest("div").parentElement.querySelector("p"):null; })();
    window.miko.bubbleEl=bubbleP;
    synced=$$("span").filter(function(s){ return /^Synced/.test(s.textContent.trim()); })[0];
    var rss=$$("span").filter(function(s){ return /RSS \/ Webhook/.test(s.textContent); })[0];
    if(rss){ srcEl=rss; txt(rss,"DuckDuckGo News"); healthEl=rss.closest("div").parentElement.querySelector(".font-mono"); }
    // hide invented analytics: sentiment gauge from "48,910 posts" etc.
    var sent=$$("span").filter(function(s){ return /Global Community Sentiment/.test(s.textContent); })[0]; if(sent) hide(sent.closest("div").parentElement);
    wire(); load(PILLS["Trending Gaming"].q,"Gaming");
  }

  function status(msg){
    if(!statusEl){ statusEl=document.createElement("div"); statusEl.className="p-space-md rounded-DEFAULT bg-surface-container-low/70 text-on-surface-variant font-body-md"; col.insertBefore(statusEl,col.firstChild); }
    statusEl.textContent=msg; statusEl.style.display=msg?"":"none";
  }

  function fillHero(n){
    hero.style.display="";
    var im=$("img",hero); im.removeAttribute("data-alt"); im.style.display=n.image?"":"none"; if(n.image) im.src=n.image; im.onerror=function(){ im.style.display="none"; };
    $$("span",hero).forEach(function(s){
      var t=s.textContent.trim();
      if(/Headline Event/.test(t)) txt(s, mode==="saved"?"Saved":"Top Story");
      if(/Reads/.test(t)&&!s.querySelector("span")||/Hot/.test(t)&&/Reads/.test(t)) hide(s);
      if(/min read/.test(t)) hide(s.parentElement);
      if(/Verified Publisher/.test(t)){ hide(s); var p=s.previousElementSibling; if(p&&/•/.test(p.textContent)) hide(p); }
      if(/ago$/.test(t)&&s.lastChild&&s.lastChild.nodeType===3) s.lastChild.textContent=" "+(ago(n.date)||"recently");
      if(s.classList.contains("font-bold")&&s.classList.contains("text-primary")) txt(s, n.source||hostOf(n.href)||"News");
    });
    txt($("h2",hero), n.title);
    var sn=sentences(n.body); var lis=$$("ul li",hero);
    lis.forEach(function(li,i){ var sp=$$("span",li)[1]; if(sn[i]){ li.style.display=""; txt(sp,sn[i]); } else li.style.display="none"; });
    var box=$("ul",hero); if(box) box.parentElement.style.display=sn.length?"":"none";
    $$("a",hero).forEach(function(a){ if(/Read Full Article/.test(a.textContent)){ a.removeAttribute("href"); a.style.cursor="pointer"; a.onclick=function(e){ e.preventDefault(); open(n); }; } });
    $$("button",hero).forEach(function(b){ var t=(b.title||"")+" "+b.textContent;
      b.onclick=function(e){ e.preventDefault(); if(/Add to Research/.test(t)) research(n,b); else if(/Share/.test(t)) share(n,b); else if(/Bookmark/.test(t)) bookmark(n,b); }; });
    $$("button",hero).forEach(function(b){ if(/Add to Research/.test(b.textContent)){ var l=$$("span",b).pop(); txt(l,"Add to Research"); } });
    $("h2",hero).style.cursor="pointer"; $("h2",hero).onclick=function(){ open(n); };
  }

  function card(n){
    var c=secTpl.cloneNode(true);
    var im=$("img",c); im.removeAttribute("data-alt"); im.style.display=n.image?"":"none"; if(n.image) im.src=n.image; im.loading="lazy"; im.onerror=function(){ im.style.display="none"; };
    txt($("span.absolute",c), PILLS_TAG());
    var line=$("div.flex.items-center.gap-1",c); if(line){ var sp=$$("span",line); txt(sp[0], n.source||hostOf(n.href)); txt(sp[2], ago(n.date)||"recently"); }
    txt($("h3",c), n.title); txt($("p",c), (n.body||"").slice(0,200));
    $$("span",c).forEach(function(s){ if(s.querySelector(".material-symbols-outlined")&&/forum/.test(s.textContent)) hide(s); });
    $("h3",c).style.cursor="pointer"; $("h3",c).onclick=function(){ open(n); };
    $$("button",c).forEach(function(b){ b.onclick=function(e){ e.preventDefault(); open(n); }; });
    return c;
  }
  function PILLS_TAG(){ return pillName; }

  function open(n){ window.miko.api("open",{url:n.href}); }
  function research(n,b){
    window.miko.api("research/add",{type:"research",title:n.title,url:n.href,body:n.body,source:n.source,image:n.image,date:n.date}).then(function(r){
      var l=$$("span",b).pop(); if(r.ok) txt(l, r.new?"Added \u2713":"Already added"); else txt(l,"Failed");
      setTimeout(function(){ txt(l,"Add to Research"); },1800);
    });
  }
  function bookmark(n,b){
    window.miko.api("research/add",{type:"saved",title:n.title,url:n.href,body:n.body,source:n.source,image:n.image,date:n.date}).then(function(r){
      var i=$("span",b); if(i&&r.ok) i.style.fontVariationSettings="'FILL' 1";
    });
  }
  function share(n,b){
    var done=function(){ var i=$("span",b); if(i){ i.textContent="check"; setTimeout(function(){ i.textContent="share"; },1200); } };
    try{ navigator.clipboard.writeText(n.href).then(done,function(){ fallback(); }); }catch(e){ fallback(); }
    function fallback(){ var t=document.createElement("textarea"); t.value=n.href; document.body.appendChild(t); t.select(); try{ document.execCommand("copy"); }catch(e){} t.remove(); done(); }
  }

  function render(){
    $$("article",secBox).forEach(function(a){ a.remove(); });
    var list=items.slice(); if(sortNew) list.sort(function(a,b){ return (Date.parse(b.date)||0)-(Date.parse(a.date)||0); });
    if(!list.length){ hero.style.display="none"; status(window.__newsErr||(mode==="saved"?"Nothing saved yet. Tap the heart on a story to keep it here.":"No stories found.")); setSide([]); txt(synced,"0 stories"); return; }
    status(""); fillHero(list[0]);
    list.slice(1,10).forEach(function(n){ secBox.appendChild(card(n)); });
    setSide(list.slice(10,13).length?list.slice(10,13):list.slice(1,4));
    briefing(list);
    $$(".overflow-x-auto button").forEach(function(b){ var cnt=$$("span",b).filter(function(s){ return /^\d+$/.test(s.textContent.trim()); })[0]; if(cnt){ var on=/bg-primary-container/.test(b.className); cnt.style.display=on?"":"none"; if(on) txt(cnt,String(list.length)); } });
    window.miko.pageContext=function(){ return "The user is reading news. Top headlines: "+list.slice(0,6).map(function(n){ return n.title+" ("+(n.source||hostOf(n.href))+")"; }).join(" | "); };
  }

  function setSide(list){
    var lab=$$("span").filter(function(s){ return /Curated Daily Sparks/.test(s.textContent); })[0]; if(!lab) return;
    var rows=$$("div",lab.parentElement).filter(function(d){ return d.parentElement===lab.parentElement; });
    rows.forEach(function(r,i){ var n=list[i]; if(!n){ r.style.display="none"; return; }
      r.style.display=""; r.style.cursor="pointer"; txt($$("span",r).filter(function(s){ return !s.classList.contains("material-symbols-outlined"); })[0], n.title); r.onclick=function(){ open(n); }; });
  }

  function briefing(list){
    if(!bubbleP) return;
    var top=list.slice(0,3).map(function(n){ return n.title.replace(/\s+[-|\u2013].*$/,"").slice(0,90); });
    bubbleP.textContent="Here's what's making noise right now: "+top.join(". ")+". Ask me below if you want any of it checked or explained.";
  }

  async function load(q,tag){
    pillName=tag||"News"; lastQ=q; mode="news"; status("Fetching the latest stories\u2026");
    var t0=performance.now(), r;
    try{ r=await window.miko.api("search",{kind:"news",q:q,n:16}); }catch(e){ r={ok:false,results:[],error:"Could not reach Miko's news search."}; }
    window.__newsErr=r.ok?"":r.error; items=(r.results||[]).map(function(n){ return n; });
    if(healthEl){ txt(healthEl,r.ok?"OK":"FAILED"); healthEl.className=healthEl.className.replace(/text-(tertiary|error)/,r.ok?"text-tertiary":"text-error"); }
    txt(synced,"Synced "+items.length+" stories \u2022 "+((performance.now()-t0)/1000).toFixed(1)+"s");
    render();
  }
  async function loadSaved(){
    pillName="Saved"; mode="saved";
    var r=await window.miko.api("research/list",{type:"saved"});
    items=(r.items||[]).map(function(i){ return {title:i.title,href:i.url,body:i.body,source:i.source,image:i.image,date:i.date}; });
    window.__newsErr=""; txt(synced,items.length+" saved"); render();
  }

  function wire(){
    input.value="";
    input.addEventListener("keydown",function(e){ if(e.key==="Enter"){ e.preventDefault(); var q=input.value.trim(); if(q) load(q,"Search"); }});
    $$("button").forEach(function(b){
      var l=b.textContent.replace(/\s+/g," ").trim();
      if(b.title==="Clear") b.addEventListener("click",function(e){ e.preventDefault(); input.value=""; input.focus(); });
      if(/^tune Filter$|^Filter$/.test(l)||/Filter$/.test(l)&&b.closest(".absolute")) b.addEventListener("click",function(e){ e.preventDefault(); sortNew=!sortNew; b.title=sortNew?"Sorted: newest first (click for relevance)":"Sorted: relevance (click for newest)"; render(); });
      if(b.title==="Read Aloud with Voice") b.addEventListener("click",function(e){
        e.preventDefault(); if(!bubbleP) return; window.miko.speak(bubbleP.textContent);
      });
    });
    $$(".overflow-x-auto button").forEach(function(b){
      var name=$$("span",b).filter(function(s){ return !s.classList.contains("material-symbols-outlined")&&!/^\d+$/.test(s.textContent.trim()); })[0];
      var key=name?name.textContent.trim():""; var def=PILLS[key];
      if(def) b.addEventListener("click",function(){ input.value=""; if(def.saved) loadSaved(); else load(def.q,def.tag); });
    });
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();

/* ---------- Research workspace wiring ---------- */
(function(){
  if(location.pathname.indexOf("/screen/research-intel")!==0) return;
  function $(s,r){return (r||document).querySelector(s);}
  function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));}
  function txt(el,t){ if(el) el.textContent=t; }
  function hide(el){ if(el) el.style.display="none"; }
  function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }
  function hostOf(u){ try{ return new URL(u).hostname.replace(/^www\./,""); }catch(e){ return ""; } }
  function ago(ts){ var m=Math.max(0,Math.round((Date.now()/1000-ts)/60)); if(m<2) return "just now"; if(m<60) return m+" min ago"; if(m<1440) return Math.round(m/60)+"h ago"; return Math.round(m/1440)+"d ago"; }
  function store(){ try{ return JSON.parse(localStorage.getItem("miko.research")||"{}"); }catch(e){ return {}; } }
  function keep(o){ try{ var s=store(); for(var k in o) s[k]=o[k]; localStorage.setItem("miko.research",JSON.stringify(s)); }catch(e){} }

  var topicIn, runBtn, listBox, tpl, report, canvas, bubbleP, activeEl, savedEl, selEl, scratchSub, input2, send2;
  var sources=[], off={}, md="", running=false;

  function init(){
    var h1=$("h1"); runBtn=$("#rescan-btn");
    var lab=$$("span").filter(function(s){ return /^Synthesis Canvas$/.test(s.textContent.trim()); })[0];
    listBox=$$("div").filter(function(d){ return d.className.indexOf("gap-space-sm")>-1 && d.firstElementChild && /Source Item|p-space-md/.test(d.firstElementChild.className||"") && d.querySelector("input[type=checkbox]"); })[0];
    if(!h1||!runBtn||!lab||!listBox) return;
    canvas=lab.closest("div.p-space-lg");
    tpl=listBox.firstElementChild.cloneNode(true);

    // header: real labels instead of the sample report
    $$("span").forEach(function(s){
      var t=s.textContent.trim();
      if(/DEEP DIVE REPORT/.test(t)) txt(s,"RESEARCH WORKSPACE");
      if(/Synthesized by Miko Core/.test(t)&&s.lastChild&&s.lastChild.nodeType===3) s.lastChild.textContent=" Written by your local Miko AI";
      if(/^\u2022 Cross-Examined/.test(t)) hide(s);
      if(/Sources Analyzed/.test(t)){ savedEl=s; var bar=s.nextElementSibling; hide(bar); hide(bar&&bar.nextElementSibling); }
    });
    topicIn=document.createElement("input"); topicIn.type="text"; topicIn.placeholder="Type a research topic and press Enter\u2026";
    topicIn.className="w-full bg-transparent outline-none font-headline-lg text-headline-lg text-on-surface placeholder:text-on-surface-variant/50 border-b border-outline-variant/40 focus:border-primary pb-1";
    h1.replaceWith(topicIn);
    var nb=runBtn.cloneNode(false); nb.id="rescan-btn"; nb.className=runBtn.className; nb.innerHTML='<span class="material-symbols-outlined text-[16px]">travel_explore</span><span>Run Research</span>';
    runBtn.replaceWith(nb); runBtn=nb;

    // left column
    $$("span").forEach(function(s){ if(/Active$/.test(s.textContent.trim())&&/\//.test(s.textContent)) activeEl=s; });
    var pills=$$("div").filter(function(d){ return /Citation Density|Conflict Rate/.test(d.textContent)&&d.children.length===2&&d.className.indexOf("p-space-sm")>-1; });
    if(pills[0]){ txt(pills[0].children[0],"Sources saved"); savedEl=pills[0].children[1]; }
    if(pills[1]){ txt(pills[1].children[0],"Selected"); selEl=pills[1].children[1]; }
    var inj=$$("button").filter(function(b){ return /Inject Custom URL/.test(b.textContent); })[0];
    if(inj) inj.addEventListener("click",function(){ injectBox(inj); });

    // middle column: replace the sample report with a live one
    $$(":scope > *",canvas).forEach(function(c,i){ if(i>0) c.style.display="none"; });
    report=document.createElement("div"); report.className="flex flex-col gap-space-sm min-h-[260px]";
    canvas.appendChild(report);
    $$("button",canvas).forEach(function(b){
      var t=b.title||"";
      if(t==="Sync to Cloud") hide(b);
      if(t==="Export to PDF"){ b.title="Print / save as PDF"; b.addEventListener("click",pdf); }
      if(t==="Copy Markdown") b.addEventListener("click",copyMd);
      if(t==="Save to Obsidian"){ b.title="Save report as a Markdown file"; b.addEventListener("click",saveMd); }
    });
    var cp=$$("button",canvas).filter(function(b){ return b.title==="Copy Markdown"; })[0];
    if(cp){ var rw=cp.cloneNode(true); rw.title="Rewrite the report from the selected sources"; $("span",rw).textContent="autorenew"; cp.parentElement.insertBefore(rw,cp); rw.addEventListener("click",function(){ synth(); }); }

    // right column: copilot
    $$("span").forEach(function(s){ if(/Hypothesis Conflict Alert/.test(s.textContent)) txt(s,"Miko says"); if(/98% Sync/.test(s.textContent)) hide(s.parentElement); if(/Suggested Miko Actions/.test(s.textContent)) txt(s,"Quick questions"); });
    var lab2=$$("span").filter(function(s){ return /^Miko says$/.test(s.textContent.trim()); })[0];
    bubbleP=lab2?lab2.closest("div").parentElement.querySelector("p"):null;
    window.miko.bubbleEl=bubbleP;
    var oldIn=$("#copilot-query-input"), oldSend=$("#copilot-send-btn");
    input2=oldIn.cloneNode(true); oldIn.replaceWith(input2); send2=oldSend.cloneNode(true); oldSend.replaceWith(send2);
    var Q=["Summarize what my sources say in 3 bullet points.","Which of my sources disagree with each other?","Draft a simple step-by-step guide from this research."], L=["\u26a1 Summarize my sources","\u2696\ufe0f Where do they disagree?","\ud83d\udcdc Draft a guide"];
    $$(".copilot-action-chip").forEach(function(c,i){
      var n=c.cloneNode(true); c.replaceWith(n); if(L[i]){ txt($("span",n),L[i]); n.addEventListener("click",function(){ say(Q[i]); }); } else hide(n);
    });
    var go=function(){ var v=input2.value; input2.value=""; say(v); };
    send2.addEventListener("click",go); input2.addEventListener("keydown",function(e){ if(e.key==="Enter"){ e.preventDefault(); go(); }});
    var mic=$("button[title='Voice Input']"); if(mic) mic.addEventListener("click",function(){
      bub("Listening\u2026 just speak."); window.miko.wake();
    });
    var scr=$$("span").filter(function(s){ return /Neural Scratchpad/.test(s.textContent); })[0];
    if(scr){ txt(scr,"Source Library"); scratchSub=scr.nextElementSibling; var purge=scr.closest("div.p-space-md").querySelector("button"); var armed=false;
      if(purge){ purge.addEventListener("click",function(){ if(!armed){ armed=true; txt(purge,"Sure?"); setTimeout(function(){ armed=false; txt(purge,"Purge"); },2500); return; }
        window.miko.api("research/clear",{type:"research"}).then(function(){ md=""; keep({md:""}); load(); renderReport(); bub("Source library cleared."); armed=false; txt(purge,"Purge"); }); }); } }

    topicIn.addEventListener("keydown",function(e){ if(e.key==="Enter"){ e.preventDefault(); run(); }});
    runBtn.addEventListener("click",run);
    var st=store(); topicIn.value=st.topic||""; off=st.off||{}; md=st.md||"";
    renderReport(); load();
    bub("Pick a topic above and press Run Research. I'll search the web, collect sources, and write you a report. You can also ask me things below.");
  }

  function bub(t){ if(bubbleP) bubbleP.textContent=t; }
  function ctx(){
    var sel=sources.filter(function(s){ return !off[s.id]; }).slice(0,8);
    return "The user is in the research workspace. Topic: "+(topicIn.value||"none")+". Sources: "+sel.map(function(s,i){ return "["+(i+1)+"] "+s.title+": "+(s.body||"").slice(0,200); }).join(" | ")+(md?" Current report: "+md.slice(0,1200):"");
  }
  function say(t){ if(t&&t.trim()) window.miko.ask(t, ctx()); }

  function counts(){
    var sel=sources.filter(function(s){ return !off[s.id]; }).length;
    txt(activeEl, sel+" / "+sources.length+" Active"); txt(savedEl,String(sources.length)); txt(selEl,String(sel));
    txt(scratchSub, sources.length+" sources saved");
  }

  function load(){
    return window.miko.api("research/list",{type:"research"}).then(function(r){ sources=r.items||[]; drawSources(); });
  }
  function drawSources(){
    listBox.innerHTML="";
    if(!sources.length){ var e=document.createElement("div"); e.className="p-space-md rounded-DEFAULT bg-surface-container-low/70 text-on-surface-variant font-body-sm"; e.textContent="No sources yet. Run a research, add a story from News, or inject your own link below."; listBox.appendChild(e); }
    sources.forEach(function(s){
      var c=tpl.cloneNode(true);
      var ic=$(".material-symbols-outlined",c); txt(ic,"link");
      var nm=$("span.font-title-sm",c); txt(nm,(s.title||hostOf(s.url)).slice(0,60)); nm.style.cursor="pointer"; nm.onclick=function(){ window.miko.api("open",{url:s.url}); };
      var tag=$$("span",c).filter(function(x){ return /Tier 1|v1\.04|Live Build|Testing/.test(x.textContent); })[0]; txt(tag,(s.source||hostOf(s.url)).slice(0,14));
      txt($("p",c),(s.body||"").slice(0,150)||"No preview text.");
      var cred=$$("span",c).filter(function(x){ return /Credibility/.test(x.textContent); })[0]; txt(cred,"Added "+ago(s.ts));
      var cb=$("input[type=checkbox]",c); cb.checked=!off[s.id];
      cb.addEventListener("change",function(){ if(cb.checked) delete off[s.id]; else off[s.id]=1; keep({off:off}); counts(); });
      var rm=document.createElement("button"); rm.title="Remove this source"; rm.className="w-6 h-6 rounded-full flex items-center justify-center text-on-surface-variant hover:text-error";
      rm.innerHTML='<span class="material-symbols-outlined text-[14px]">close</span>';
      rm.onclick=function(){ window.miko.api("research/remove",{id:s.id}).then(load); };
      var lbl=cb.closest("label"); lbl.parentElement.insertBefore(rm,lbl);
      listBox.appendChild(c);
    });
    counts();
  }

  function injectBox(btn){
    if($("#miko-inject")){ $("#miko-inject input").focus(); return; }
    var box=document.createElement("div"); box.id="miko-inject"; box.className="flex items-center gap-space-xs";
    box.innerHTML='<input type="text" placeholder="Paste a link and press Enter" class="flex-1 min-w-0 px-3 py-2 rounded-DEFAULT bg-surface-container-lowest/80 border border-outline-variant/40 text-on-surface font-body-sm outline-none focus:border-primary"/><button class="px-3 py-2 rounded-DEFAULT bg-primary-container text-on-primary-container font-label-sm">Add</button>';
    btn.parentElement.insertBefore(box,btn);
    var inp=$("input",box), add=$("button",box);
    var doit=function(){
      var u=inp.value.trim(); if(!u) return; if(!/^https?:\/\//i.test(u)) u="https://"+u;
      add.textContent="\u2026"; 
      window.miko.api("fetch/page",{url:u}).then(function(p){
        if(!p.ok){ bub("I couldn't read that page: "+p.error); add.textContent="Add"; return; }
        return window.miko.api("research/add",{type:"research",title:p.title,url:u,body:p.text,source:hostOf(u)}).then(function(r){ box.remove(); bub(r.ok?(r.new?"Added \u201c"+p.title.slice(0,60)+"\u201d to your sources.":"That one is already in your sources."):"Couldn't add it: "+r.error); load(); });
      });
    };
    add.addEventListener("click",doit); inp.addEventListener("keydown",function(e){ if(e.key==="Enter"){ e.preventDefault(); doit(); } if(e.key==="Escape") box.remove(); }); inp.focus();
  }

  async function run(){
    if(running) return;
    var topic=topicIn.value.trim();
    if(!topic){ bub("Type a research topic in the box at the top first."); topicIn.focus(); return; }
    running=true; keep({topic:topic}); setBtn("Searching\u2026"); bub("Searching the web for \u201c"+topic+"\u201d\u2026");
    var r; try{ r=await window.miko.api("search",{kind:"web",q:topic,n:8}); }catch(e){ r={ok:false,results:[],error:"Could not reach Miko's search."}; }
    if(r.ok&&r.results.length){
      await Promise.all(r.results.slice(0,8).map(function(x){ return window.miko.api("research/add",{type:"research",title:x.title,url:x.href,body:x.body,source:hostOf(x.href)}); }));
      await load();
    } else {
      bub((r.error||"No web results.")+" I'll use the sources you already have.");
    }
    running=false; await synth();
  }
  function setBtn(t){ txt($$("span",runBtn)[1],t); runBtn.disabled=(t!=="Run Research"); }

  async function synth(){
    if(running&&false) return;
    var topic=topicIn.value.trim(); keep({topic:topic});
    if(!topic){ bub("Type a research topic first."); return; }
    var sel=sources.filter(function(s){ return !off[s.id]; }).slice(0,10).map(function(s){ return {title:s.title,url:s.url,body:s.body}; });
    if(!sel.length){ bub("No sources are switched on. Run the research or turn some on."); return; }
    setBtn("Writing\u2026"); bub("Reading "+sel.length+" sources and writing your report\u2026"); md=""; renderReport(true);
    try{
      var r=await fetch("/stream/research",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({topic:topic,sources:sel})});
      var rd=r.body.getReader(), dec=new TextDecoder(), pending=false;
      for(;;){ var c=await rd.read(); if(c.done) break; md+=dec.decode(c.value,{stream:true});
        if(!pending){ pending=true; requestAnimationFrame(function(){ pending=false; renderReport(true); }); } }
    }catch(e){ md="[I lost connection to Miko's brain.]"; }
    keep({md:md}); renderReport(); setBtn("Run Research"); bub(/^\[/.test(md)?md:"Your report is ready! You can copy it, save it, or print it as a PDF. Ask me anything about it below.");
  }

  function inline(s){ return esc(s).replace(/\*\*(.+?)\*\*/g,'<strong class="text-on-surface">$1</strong>').replace(/\[(\d+)\]/g,'<span class="text-primary font-semibold">[$1]</span>'); }
  function toHtml(m){
    var out=[], list=null, lines=String(m).split(/\r?\n/);
    function close(){ if(list){ out.push("</"+list+">"); list=null; } }
    lines.forEach(function(l){
      var t=l.trim(), h=t.match(/^#{1,4}\s+(.*)/), b=t.match(/^[-*\u2022]\s+(.*)/), n=t.match(/^\d+[.)]\s+(.*)/);
      if(h){ close(); out.push('<h3 class="font-headline-md text-headline-md text-on-surface pt-space-sm">'+inline(h[1])+"</h3>"); }
      else if(b){ if(list!=="ul"){ close(); list="ul"; out.push('<ul class="list-disc pl-5 flex flex-col gap-1 text-on-surface-variant font-body-md">'); } out.push("<li>"+inline(b[1])+"</li>"); }
      else if(n){ if(list!=="ol"){ close(); list="ol"; out.push('<ol class="list-decimal pl-5 flex flex-col gap-1 text-on-surface-variant font-body-md">'); } out.push("<li>"+inline(n[1])+"</li>"); }
      else if(t){ close(); out.push('<p class="font-body-md text-body-md text-on-surface-variant">'+inline(t)+"</p>"); }
      else close();
    });
    close(); return out.join("");
  }
  function renderReport(live){
    if(!md){ report.innerHTML='<div class="p-space-md rounded-DEFAULT bg-surface-container-low/70 text-on-surface-variant font-body-md">Your report will appear here. Enter a topic and press <strong>Run Research</strong>.</div>'; return; }
    report.innerHTML=toHtml(md)+(live?'<span class="inline-block w-2 h-4 bg-primary animate-pulse"></span>':"");
  }

  function copyMd(){
    if(!md){ bub("There's no report to copy yet."); return; }
    var done=function(){ bub("Report copied to the clipboard."); };
    try{ navigator.clipboard.writeText(md).then(done,fb); }catch(e){ fb(); }
    function fb(){ var t=document.createElement("textarea"); t.value=md; document.body.appendChild(t); t.select(); try{ document.execCommand("copy"); }catch(e){} t.remove(); done(); }
  }
  function saveMd(){
    if(!md){ bub("There's no report to save yet."); return; }
    var name=(topicIn.value||"Miko report").slice(0,60);
    window.miko.api("save/text",{name:name,text:"# "+name+"\n\n"+md}).then(function(r){
      if(!r.ok){ bub("Couldn't save: "+r.error); return; }
      bub("Saved! Opening the folder."); window.miko.api("download/reveal",{path:r.path});
    });
  }
  function pdf(){
    if(!md){ bub("There's no report to print yet."); return; }
    var w=window.open("","_blank"); if(!w){ bub("Your browser blocked the print window. Allow pop-ups for Miko and try again."); return; }
    w.document.write('<!doctype html><title>'+esc(topicIn.value||"Report")+'</title><body style="font:15px/1.6 Segoe UI,Arial,sans-serif;max-width:760px;margin:32px auto;color:#111"><h1>'+esc(topicIn.value||"Report")+"</h1>"+toHtml(md).replace(/class="[^"]*"/g,"")+"</body>");
    w.document.close(); w.focus(); setTimeout(function(){ w.print(); },300);
  }

  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();

/* ---------- Downloads manager wiring ---------- */
(function(){
  if(location.pathname.indexOf("/screen/downloads")!==0) return;
  function $(s,r){return (r||document).querySelector(s);}
  function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));}
  function txt(el,t){ if(el) el.textContent=t; }
  function hide(el){ if(el) el.style.display="none"; }
  function hostOf(u){ try{ return new URL(u).hostname.replace(/^www\./,""); }catch(e){ return ""; } }
  function fmtB(n){ n=+n||0; if(n<1000) return n+" B"; if(n<1e6) return (n/1e3).toFixed(0)+" KB"; if(n<1e9) return (n/1e6).toFixed(1)+" MB"; return (n/1e9).toFixed(2)+" GB"; }
  function fmtT(s){ s=Math.round(s); if(!isFinite(s)||s<=0) return "--"; if(s<60) return s+"s"; if(s<3600) return Math.floor(s/60)+"m "+String(s%60).padStart(2,"0")+"s"; return Math.floor(s/3600)+"h "+String(Math.floor(s%3600/60)).padStart(2,"0")+"m"; }
  function etaOf(j){
    if(j.eta){ var p=String(j.eta).split(":").map(Number); if(!p.some(isNaN)) return p.length===3?p[0]*3600+p[1]*60+p[2]:p[0]*60+(p[1]||0); }
    return (j.speed>0&&j.total>0)?(j.total-j.got)/j.speed:0;
  }
  function when(ts){
    var d=new Date(ts*1000), n=new Date(), hm=String(d.getHours()).padStart(2,"0")+":"+String(d.getMinutes()).padStart(2,"0");
    var day=Math.floor((new Date(n.getFullYear(),n.getMonth(),n.getDate())-new Date(d.getFullYear(),d.getMonth(),d.getDate()))/864e5);
    return (day===0?"Today":day===1?"Yesterday":d.toLocaleDateString())+", "+hm;
  }
  function isImg(name){ return /\.(jpe?g|png|webp|gif|bmp)$/i.test(name||""); }
  function iconFor(name,kind){ if(kind==="audio"||/\.(mp3|m4a|flac|wav|ogg)$/i.test(name)) return "music_note"; if(kind==="video"||/\.(mp4|mkv|webm|mov|avi)$/i.test(name)) return "movie"; if(/\.(zip|7z|rar)$/i.test(name)) return "folder_zip"; if(/\.pdf$/i.test(name)) return "picture_as_pdf"; return "draft"; }
  function extOf(n){ var m=/\.([A-Za-z0-9]{2,4})$/.exec(n||""); return m?m[1].toUpperCase():""; }

  var box, activeTpl, doneTpl, tab="active", data={jobs:[],history:[],disk:{},ytdlp:true}, sig="", seen={}, bubbleP, actBadge, doneBadge, urlIn, usageCount=-1;
  var activeCls, inactiveCls;

  function init(){
    box=$("#downloads-container"); if(!box) return;
    activeTpl=box.children[0].cloneNode(true); doneTpl=$(".completed-item",box).cloneNode(true);
    var ta=$("#tab-active"), tc=$("#tab-completed"); activeCls=ta.className; inactiveCls=tc.className;
    actBadge=$$("span",ta).pop(); doneBadge=$$("span",tc).pop();
    // honest labels instead of the sample "Defender" claim
    var lab=$$("span").filter(function(s){ return /Real-time Defender Status/.test(s.textContent); })[0];
    if(lab){ txt(lab,"Download status"); bubbleP=lab.closest("div").parentElement.querySelector("p"); window.miko.bubbleEl=bubbleP; }
    $$("span").forEach(function(s){ if(/^High Priority$/.test(s.textContent.trim())) hide(s); });
    window.switchDownloadTab=function(t){ tab=t; ta.className=(t==="active")?activeCls:inactiveCls; tc.className=(t==="completed")?activeCls:inactiveCls; sig=""; render(); };
    window.togglePauseAll=function(){ var anyRunning=data.jobs.some(function(j){ return j.kind==="file"&&(j.status==="downloading"||j.status==="queued"); }); window.miko.api("download/pause_all",{paused:anyRunning}).then(refresh); };
    window.clearCompletedList=function(){ window.miko.api("download/clear",{}).then(function(){ say("Cleared the list. Your files are still in the folder."); refresh(); usage(); }); };
    addLinkBar(); wireToggles(); refresh(); usage();
    setInterval(function(){ if(!document.hidden) refresh(); },1000);
  }

  function say(t){ if(bubbleP) bubbleP.textContent=t; }

  function addLinkBar(){
    var bar=document.createElement("div");
    bar.className="flex flex-wrap items-center gap-space-xs p-space-sm rounded-DEFAULT bg-surface-container/80 border border-outline-variant/30";
    bar.innerHTML='<span class="material-symbols-outlined text-primary">add_link</span>'+
      '<input id="miko-dl-url" type="text" placeholder="Paste a link to download (file, video or audio)\u2026" class="flex-1 min-w-[200px] bg-transparent outline-none text-on-surface font-body-md"/>'+
      ["file:File","video:Video","audio:MP3"].map(function(x){ var p=x.split(":"); return '<button data-k="'+p[0]+'" class="px-space-md py-1.5 rounded-DEFAULT bg-surface-container-high hover:bg-primary-container hover:text-on-primary-container text-on-surface font-label-sm transition-all">'+p[1]+'</button>'; }).join("");
    box.parentElement.insertBefore(bar,box);
    urlIn=$("#miko-dl-url",bar);
    function go(kind){
      var u=urlIn.value.trim(); if(!u){ say("Paste a link first."); return; } urlIn.value=""; if(!/^https?:\/\//i.test(u)) u="https://"+u;
      if(!kind) kind=/\.[a-z0-9]{2,4}(\?|$)/i.test(new URL(u).pathname)?"file":"video";
      window.miko.api("download/start",{kind:kind,url:u,title:""}).then(function(r){ if(r.ok){ tab==="active"||window.switchDownloadTab("active"); refresh(); } else { urlIn.value=u; say("I couldn't start that: "+r.error); } });
    }
    $$("button",bar).forEach(function(b){ b.addEventListener("click",function(){ go(b.getAttribute("data-k")); }); });
    urlIn.addEventListener("keydown",function(e){ if(e.key==="Enter"){ e.preventDefault(); go(""); }});
  }

  function wireToggles(){
    var map={"Auto-extract archives":"auto_extract","Notify on download complete":"notify_done"};
    window.miko.api("config/get").then(function(r){
      var cfg=r.config||{};
      $$("span").forEach(function(s){
        Object.keys(map).forEach(function(k){
          if(s.textContent.indexOf(k)>-1&&s.querySelector&&!s.querySelector("span.flex")){
            var cb=s.closest("div").querySelector("input[type=checkbox]"); if(!cb||cb._w) return; cb._w=1;
            cb.checked=!!cfg[map[k]];
            cb.addEventListener("change",function(){ var o={}; o[map[k]]=cb.checked; window.miko.api("config/set",o); });
          }
        });
      });
    });
  }

  function usage(){
    window.miko.api("download/usage").then(function(r){
      var u=r.usage||{}; var lab=$$("span").filter(function(s){ return /Storage Allocation/.test(s.textContent); })[0]; if(!lab) return;
      var card=lab.parentElement.parentElement, pathEl=lab.nextElementSibling;
      txt(pathEl,(data.folder||"").split(/[\\/]/).slice(-3).join("\\")||"Downloads\\Miko");
      var bar=$(".h-3",card), segs=bar?Array.prototype.slice.call(bar.children):[], tot=u.total||0;
      var vals=[u.images||0,u.media||0,u.other||0], names=["Images","Media","Other"];
      segs.forEach(function(sg,i){ var pc=tot?Math.round(vals[i]*100/tot):0; sg.style.width=pc+"%"; sg.title=names[i]+": "+fmtB(vals[i]); });
      var leg=$$(".grid-cols-3 > div span.truncate",card);
      leg.forEach(function(sp,i){ txt(sp,names[i]+" ("+(tot?Math.round(vals[i]*100/tot):0)+"%)"); });
      usageCount=data.history.length;
    });
  }

  function refresh(){
    window.miko.api("download/list").then(function(r){
      if(!r||!r.ok) return;
      // notice jobs that just finished
      r.jobs.forEach(function(j){ if(seen[j.id]&&seen[j.id]!=="done"&&j.status==="done") say("Finished: "+(j.name||j.title)+". It's in your Miko downloads folder."); seen[j.id]=j.status; });
      data=r;
      var s=JSON.stringify([tab,r.jobs.map(function(j){return [j.id,j.status,j.progress,Math.round(j.speed/1e4),j.paused];}),r.history.map(function(h){return h.id;}),r.ytdlp]);
      if(s!==sig){ sig=s; render(); }
      if(usageCount!==r.history.length) usage();
    }).catch(function(){});
  }

  function activeJobs(){ return data.jobs.filter(function(j){ return j.status==="queued"||j.status==="downloading"||j.status==="paused"||j.status==="error"; }); }

  function render(){
    var act=activeJobs(), run=act.filter(function(j){ return j.status!=="error"; });
    txt(actBadge,String(run.length)); txt(doneBadge,String(data.history.length));
    var spd=run.reduce(function(a,j){ return a+(j.status==="downloading"?j.speed:0); },0);
    var maxEta=run.reduce(function(a,j){ return Math.max(a,etaOf(j)); },0);
    var paused=run.some(function(j){ return j.paused; });
    txt($("#top-speed-indicator"), paused&&!spd?"Paused":fmtB(spd)+"/s");
    var big=$$("span.font-headline-md").filter(function(s){ return /\/s$/.test(s.textContent.trim()); })[0]; txt(big,fmtB(spd)+"/s");
    var sub=$$("span").filter(function(s){ return /^Active:/.test(s.textContent.trim()); })[0];
    txt(sub,"Active: "+run.length+" transfer"+(run.length===1?"":"s")+" \u2022 Est. completion: "+(maxEta?fmtT(maxEta):"--")+" \u2022 Throttle: Off");
    txt($("#pause-all-text"), paused?"Resume All":"Pause All"); txt($("#pause-all-icon"), paused?"play_arrow":"pause");
    var d=data.disk||{}; 
    say(run.length+" active \u2022 "+data.history.length+" finished"+(d.total?" \u2022 "+fmtB(d.free)+" free on "+(d.drive||"this drive"):"")+(data.ytdlp?"":". To download videos I need yt-dlp: run  pip install yt-dlp  once."));
    box.innerHTML="";
    if(tab==="active"){
      if(!act.length) box.appendChild(empty("Nothing downloading right now. Paste a link above, or download from the Images and Videos tabs."));
      act.forEach(function(j){ box.appendChild(activeCard(j)); });
    } else {
      if(!data.history.length) box.appendChild(empty("No finished downloads yet."));
      data.history.forEach(function(h){ box.appendChild(doneCard(h)); });
    }
  }
  function empty(t){ var e=document.createElement("div"); e.className="p-space-lg rounded-DEFAULT bg-surface-container-low/70 text-on-surface-variant font-body-md text-center"; e.textContent=t; return e; }

  function btn(c,label){ return $$("button",c).filter(function(b){ return b.getAttribute("aria-label")===label; })[0]; }

  function activeCard(j){
    var c=activeTpl.cloneNode(true), name=j.name||j.title||"download", u=j.url||"";
    var th=$(".relative.w-14",c); if(th){ th.innerHTML='<span class="material-symbols-outlined text-[28px] text-primary">'+iconFor(name,j.kind)+'</span>'; th.className=th.className+" flex items-center justify-center"; }
    txt($("h3",c),name.length>48?name.slice(0,46)+"\u2026":name);
    var pill=$$("span",c).filter(function(s){ return /^(MP4|EXE)$/.test(s.textContent.trim()); })[0]; txt(pill, j.kind==="audio"?"MP3":j.kind==="video"?"VIDEO":(extOf(name)||"FILE"));
    var col=$$("div.flex.flex-col.min-w-0",c)[0]; var line=$$(":scope > div",col)[1]; var ls=line?$$(":scope > span",line).filter(function(s){ return s.textContent.trim()!=="\u2022"; }):[];
    var st=j.status;
    txt(ls[0], j.total?fmtB(j.got)+" / "+fmtB(j.total):(j.got?fmtB(j.got):(st==="queued"?"Waiting\u2026":"Starting\u2026")));
    txt(ls[1], st==="downloading"?fmtB(j.speed)+"/s":(st==="paused"?"paused":(st==="error"?"failed":"")));
    txt(ls[2], st==="downloading"&&etaOf(j)?"ETA: "+fmtT(etaOf(j)):"");
    var bar=$(".h-full.bg-gradient-to-r",c); if(bar) bar.style.width=(j.progress||0)+"%";
    var foot=$$("span",$(".justify-between.items-center",c)); 
    txt(foot[0], st==="error"?"Download failed":(j.progress||0)+"% "+(st==="paused"?"paused":"downloaded"));
    txt(foot[1], st==="error"?(j.error||"unknown error"):hostOf(u));
    if(st==="error"&&foot[1]) foot[1].className=foot[1].className.replace(/text-(secondary|tertiary-fixed)/g,"text-error");
    var boost=btn(c,"Priority Boost"), pause=btn(c,"Pause"), cancel=btn(c,"Cancel");
    if(boost){ if(st==="error"){ $("span",boost).textContent="refresh"; boost.title="Try again"; boost.onclick=function(){ window.miko.api("download/start",{kind:j.kind,url:j.url,title:j.title}).then(function(){ window.miko.api("download/remove",{id:j.id}).then(refresh); }); }; } else hide(boost); }
    if(pause){ if(j.kind!=="file"||st==="error"){ hide(pause); } else { $("span",pause).textContent=(st==="paused")?"play_arrow":"pause"; pause.title=(st==="paused")?"Resume":"Pause"; pause.onclick=function(){ window.miko.api("download/pause",{id:j.id,paused:st!=="paused"}).then(refresh); }; } }
    if(cancel){ cancel.title=(st==="error")?"Dismiss":"Cancel"; cancel.onclick=function(){ window.miko.api(st==="error"?"download/remove":"download/cancel",{id:j.id}).then(function(){ setTimeout(refresh,300); }); }; }
    return c;
  }

  function doneCard(h){
    var c=doneTpl.cloneNode(true), name=h.name||h.title||"file";
    var th=$(".relative.w-14",c);
    if(th){
      if(isImg(name)&&!h.missing){ th.innerHTML='<img class="w-full h-full object-cover" loading="lazy" src="/dlfile?p='+encodeURIComponent(h.path)+'"/>'; }
      else { th.innerHTML='<span class="material-symbols-outlined text-[28px] text-primary">'+iconFor(name,h.kind)+'</span>'; th.className=th.className+" flex items-center justify-center"; }
    }
    txt($("h3",c),name.length>52?name.slice(0,50)+"\u2026":name);
    var line=$("div.flex.items-center.gap-space-xs",$$("div.flex.flex-col.min-w-0",c)[0]); var ls=line?$$(":scope > span",line).filter(function(s){ return s.textContent.trim()!=="\u2022"; }):[];
    if(h.missing){ if(ls[0]){ ls[0].lastChild.textContent=" File moved or deleted"; } } 
    txt(ls[1],fmtB(h.size)); txt(ls[2],when(h.ts));
    var open=$$("button",c).filter(function(b){ return /^Open$/.test(b.textContent.trim()); })[0];
    var show=btn(c,"Show in Folder"), wall=btn(c,"Set as Wallpaper");
    if(open){ if(h.missing) open.disabled=true; else open.onclick=function(){ window.miko.api("download/open",{path:h.path}); }; }
    if(show) show.onclick=function(){ window.miko.api("download/reveal",{path:h.missing?"":h.path}); };
    if(wall){ if(isImg(name)&&!h.missing) wall.onclick=function(){ window.miko.api("wallpaper",{path:h.path}).then(function(r){ say(r.ok?"Wallpaper set! \u2661":"I couldn't set the wallpaper: "+r.error); }); }; else hide(wall); }
    if(/\.zip$/i.test(name)&&!h.missing&&show){
      var ex=show.cloneNode(true); ex.setAttribute("aria-label","Extract Here"); ex.title="Extract here"; $("span",ex).textContent="unarchive";
      ex.onclick=function(){ say("Extracting\u2026"); window.miko.api("download/extract",{path:h.path}).then(function(r){ say(r.ok?"Extracted! Opening the folder.":"Couldn't extract: "+r.error); if(r.ok) window.miko.api("download/reveal",{path:r.folder+"/."}); }); };
      show.parentElement.appendChild(ex);
    }
    return c;
  }

  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();

/* ---------- Miko shared helpers (voice, speech, footer, unified query) ---------- */
(function(){
  var m = window.miko;
  m.wake = function(){ return m.api("voice/wake", {}); };
  m.setQuery = function(q){ try{ parent.postMessage({type:"miko-q", q:q}, "*"); }catch(e){} };
  var audio = null;
  m.speak = function(text){
    if(audio && !audio.paused){ audio.pause(); audio = null; return Promise.resolve(); }
    var c = m.cfg || {};
    return fetch("/stream/tts", {method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({text:String(text||"").slice(0,1500), voice:c.voice, rate:c.voice_rate, pitch:c.voice_pitch})})
      .then(function(r){ if(!r.ok) throw new Error("speech failed"); return r.blob(); })
      .then(function(b){ audio = new Audio(URL.createObjectURL(b)); return audio.play(); })
      .catch(function(){ try{ var s=window.speechSynthesis; if(s){ s.cancel(); s.speak(new SpeechSynthesisUtterance(String(text||"").slice(0,600))); } }catch(e){} });
  };
  m.api("config/get").then(function(r){ m.cfg = r.config || {}; footer(); }).catch(function(){});

  var voiceState = "off";
  function footer(){
    Array.prototype.slice.call(document.querySelectorAll("footer span")).forEach(function(s){
      var t = s.textContent.trim();
      if(/^Node:/.test(t) && s.lastChild && s.lastChild.nodeType===3) s.lastChild.textContent = " Local: 127.0.0.1:8765";
      if(/^Active Session/.test(t)) s.textContent = "Voice: " + voiceState;
      if(/Secure SSL\/TLS/.test(t)) s.textContent = "Brain: " + ((m.cfg && m.cfg.brain) || "ollama");
    });
  }
  window.addEventListener("message", function(e){
    var d = e.data || {};
    if(d.type === "miko-status" && d.voice){ voiceState = d.voice.state || "off"; footer(); if(m.onStatus) m.onStatus(d.voice); }
    if(d.type === "miko-voice" && d.ev){
      var ev = d.ev;
      if(ev.type === "heard") m.showBubble("\u201c" + ev.text + "\u201d \u2026");
      if(ev.type === "reply") m.showBubble(ev.text);
      if(ev.type === "error") m.showBubble(ev.text);
      if(m.onVoice) m.onVoice(ev);
    }
  });
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded", footer); else footer();
})();

/* ---------- Settings screen wiring ---------- */
(function(){
  if(location.pathname.indexOf("/screen/settings")!==0) return;
  function $(s,r){return (r||document).querySelector(s);}
  function $$(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));}
  function txt(el,t){ if(el) el.textContent=t; }
  function hide(el){ if(el) el.style.display="none"; }
  function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }
  function setNum(span,t){ var tn=Array.prototype.filter.call(span.childNodes,function(n){ return n.nodeType===3; })[0]; if(tn) tn.textContent=t; else span.insertBefore(document.createTextNode(t),span.firstChild); }
  function byText(sel,re){ return $$(sel).filter(function(e){ return re.test(e.textContent.trim()); })[0]; }

  var cfg={}, sec={}, bubbleP, sampleP, telem={}, poseEl, rows={}, activeCls, inactiveCls, circleOn, circleOff;
  var NAMES={tsundere:"Kawaii Tsundere",researcher:"Tactical Researcher",lofi:"Soothing Lo-Fi",hacker:"Cyberpunk Hacker",original:"Original Miko"};
  var timer={};
  function save(o){ return window.miko.api("config/set",o).then(function(r){ if(r.config){ cfg=r.config; window.miko.cfg=cfg; } return r; }); }
  function saveSoon(key,o,ms){ clearTimeout(timer[key]); timer[key]=setTimeout(function(){ save(o); },ms||350); }
  function say(t){ if(bubbleP) bubbleP.textContent=t; }

  function init(){ window.miko.api("config/get").then(function(r){ cfg=r.config||{}; window.miko.cfg=cfg; build(); }); }

  function build(){
    [["archetype",/Archetype &/],["voice",/Neural Voice Engine/],["desktop",/Companion Render/],["memory",/Vector Memory/]].forEach(function(p){
      var h=byText("h3",p[1]); sec[p[0]]=h?h.closest("div.flex-col.gap-space-md"):null; });
    right(); header(); archetypes(); sliders(); voice(); desktop(); memory(); panel(); rail();
    window.miko.onStatus=onStatus; window.miko.api("status").then(function(s){ onStatus(s.voice||{}); telemetry(s); });
  }

  /* ---- header: model picker, defaults, save ---- */
  function header(){
    var badge=byText("span",/Miko-v2\.4-Neural-Large/);
    if(badge){
      Array.prototype.slice.call(badge.childNodes).forEach(function(n){ if(n.nodeType===3) n.remove(); });
      var sel=document.createElement("select"); sel.className="bg-transparent outline-none text-on-surface font-label-sm cursor-pointer"; sel.title="Which Ollama model Miko thinks with";
      badge.appendChild(sel);
      window.miko.api("ollama/models",{}).then(function(r){
        var names=(r.models||[]).slice(); if(names.indexOf(cfg.brain)<0) names.unshift(cfg.brain);
        sel.innerHTML=names.map(function(n){ return '<option value="'+esc(n)+'"'+(n===cfg.brain?" selected":"")+'>'+esc(n)+'</option>'; }).join("");
        if(!r.ok) sel.title="Ollama is not reachable right now. Start Ollama and reopen Settings to see your models.";
      });
      sel.addEventListener("change",function(){ save({brain:sel.value}).then(function(){ say("Okay, I'll think with "+sel.value+" from now on."); }); });
    }
    var intro=byText("p",/Calibrate Miko/); txt(intro,"Choose how Miko talks and sounds. Everything saves automatically and applies to the next thing you say.");
    var defBtn=byText("button",/Defaults/); if(defBtn) defBtn.addEventListener("click",function(){
      save({archetype:"original",tone:{},voice:"en-US-AvaNeural",voice_rate:5,voice_pitch:6,speak_replies:false}).then(function(){ location.reload(); }); });
    var saveBtn=byText("button",/Save Preset/); if(saveBtn) saveBtn.addEventListener("click",function(){
      var l=$$("span",saveBtn).pop(); txt(l,"Saved \u2713"); say("Everything is already saved, and I keep it for next time."); setTimeout(function(){ txt(l,"Save Preset"); },1600); });
  }

  /* ---- archetype cards ---- */
  function archetypes(){
    var keyOf={"Kawaii Tsundere":"tsundere","Tactical Researcher":"researcher","Soothing Lo-Fi":"lofi","Cyberpunk Hacker":"hacker"};
    var cards=$$("h4").filter(function(h){ return keyOf[h.textContent.trim()]; }).map(function(h){ return h.closest("div.cursor-pointer"); }).filter(Boolean);
    activeCls=cards[0].className; inactiveCls=cards[1].className;
    var c0=$("span.w-5.h-5",cards[0]), c1=$("span.w-5.h-5",cards[1]); circleOn={cls:c0.className,html:c0.innerHTML}; circleOff={cls:c1.className,html:c1.innerHTML};
    var activeLabel=byText("span",/^Active:/);
    function paint(){
      cards.forEach(function(c){ var k=keyOf[$("h4",c).textContent.trim()], on=(cfg.archetype===k);
        c.className=on?activeCls:inactiveCls; var circ=$("span.w-5.h-5",c); circ.className=on?circleOn.cls:circleOff.cls; circ.innerHTML=on?circleOn.html:circleOff.html; });
      txt(activeLabel,"Active: "+(NAMES[cfg.archetype]||NAMES.original)+(cfg.archetype==="original"?" (your original warm friend)":""));
    }
    cards.forEach(function(c){ var k=keyOf[$("h4",c).textContent.trim()];
      c.addEventListener("click",function(){ var next=(cfg.archetype===k)?"original":k; cfg.archetype=next; paint(); save({archetype:next}).then(function(){ say(next==="original"?"Back to my original personality!":"Okay! I'll be your "+NAMES[next]+" from now on."); telemetry(); }); }); });
    paint();
  }

  /* ---- draggable bars ---- */
  function bar(bar,onSet){
    var down=false; bar.style.cursor="pointer"; bar.style.touchAction="none";
    function at(e){ var r=bar.getBoundingClientRect(); var v=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)); onSet(v); }
    bar.addEventListener("pointerdown",function(e){ down=true; try{ bar.setPointerCapture(e.pointerId); }catch(x){} at(e); });
    bar.addEventListener("pointermove",function(e){ if(down) at(e); });
    bar.addEventListener("pointerup",function(){ down=false; });
  }
  function sliders(){
    var defs=[[/Banter & Sass/,"sass"],[/Proactive Assistance/,"hide"],[/Affection & Praise/,"affection"],[/Technical Precision/,"precision"]];
    defs.forEach(function(d){
      var lab=$$("span").filter(function(s){ return d[0].test(s.textContent.replace(/&amp;/g,"&")); })[0]; if(!lab) return;
      var block=lab.closest("div.p-space-md"); if(d[1]==="hide"){ hide(block); return; }
      var valEl=lab.parentElement.children[1], b=$(".h-3",block), fill=b.firstElementChild, tone=cfg.tone||{};
      function show(v,applied){ fill.style.width=v+"%"; setNum(valEl,applied?v+"%":"Default"); }
      show(tone[d[1]]==null?50:tone[d[1]], tone[d[1]]!=null);
      bar(b,function(f){ var v=Math.round(f*100); show(v,true); cfg.tone=cfg.tone||{}; cfg.tone[d[1]]=v; saveSoon(d[1],{tone:cfg.tone}); });
    });
  }

  /* ---- voice ---- */
  function toggle(btn,on){
    var knob=$("span",btn);
    if(!btn._onCls) btn._onCls=btn.className;
    btn.className=on?btn._onCls:"w-12 h-6 rounded-full bg-surface-container-highest p-0.5 transition-all flex items-center justify-start";
    knob.className=on?"w-5 h-5 rounded-full bg-on-secondary shadow-md":"w-5 h-5 rounded-full bg-outline shadow-md";
  }
  function voice(){
    var nameEl=byText("div",/^Miko Neo-Kyoto v2\.4$/), subEl=nameEl&&nameEl.nextElementSibling;
    var playBtn=$("button[title='Play Voice Sample']"); sampleP=byText("p",/always here for you/);
    var sample="Hi! I'm Miko. This is how I sound with the voice you picked.";
    txt(sampleP,"\u201c"+sample+"\u201d"); txt(subEl,"Free Microsoft neural voice (needs internet)");
    var sel=document.createElement("select"); sel.className="w-full bg-transparent outline-none text-on-surface font-title-sm cursor-pointer"; nameEl.replaceWith(sel);
    window.miko.api("voice/voices",{}).then(function(r){
      var vs=r.voices||[]; if(!vs.some(function(v){ return v.name===cfg.voice; })) vs.unshift({name:cfg.voice,gender:"",locale:""});
      sel.innerHTML=vs.map(function(v){ return '<option value="'+esc(v.name)+'"'+(v.name===cfg.voice?" selected":"")+'>'+esc(v.name.replace(/Neural$/,""))+(v.gender?" ("+v.gender+")":"")+'</option>'; }).join("");
    });
    function play(){ var icon=playBtn&&$("span",playBtn); if(icon) icon.textContent="hourglass_top";
      window.miko.speak(sample).then(function(){ if(icon) icon.textContent="play_arrow"; },function(){ if(icon) icon.textContent="play_arrow"; }); }
    sel.addEventListener("change",function(){ save({voice:sel.value}).then(play); });
    if(playBtn) playBtn.addEventListener("click",play);

    // pitch + speed: real edge-tts values
    function slider(labelRe,key,min,max,fmt){
      var lab=byText("span",labelRe); if(!lab) return; var panel=lab.closest("div.p-space-md"), valEl=lab.parentElement.children[1], b=$(".h-2",panel), fill=b.firstElementChild;
      function show(v){ fill.style.width=Math.round((v-min)*100/(max-min))+"%"; txt(valEl,fmt(v)); }
      show(Number(cfg[key])); b.parentElement.style.paddingTop="4px"; b.style.height="10px";
      bar(b,function(f){ var v=Math.round(min+f*(max-min)); show(v); cfg[key]=v; saveSoon(key,(function(){ var o={}; o[key]=v; return o; })(),500); });
      b.addEventListener("pointerup",function(){ setTimeout(play,700); });
    }
    slider(/^Voice Pitch$/,"voice_pitch",-20,30,function(v){ return (v>=0?"+":"")+v+" Hz"; });
    slider(/^Speech Cadence$/,"voice_rate",-30,50,function(v){ return (v>=0?"+":"")+v+"% speed"; });

    // the old "Whisper" row becomes "Speak chat replies"; a clone becomes the hands-free switch
    var wt=byText("div",/^Whisper & Late-Night ASMR Mode$/); var row=wt.closest("div.p-space-md");
    var tbtn=$("button",row); var onCls=tbtn.className; tbtn._onCls=onCls; txt(wt,"Speak chat replies aloud"); txt(wt.nextElementSibling,"Miko reads her answers to your typed messages out loud, using the voice above");
    toggle(tbtn,!!cfg.speak_replies); tbtn.addEventListener("click",function(){ cfg.speak_replies=!cfg.speak_replies; toggle(tbtn,cfg.speak_replies); save({speak_replies:cfg.speak_replies}); });
    var row2=row.cloneNode(true); row.parentElement.insertBefore(row2,row);
    var t2=byText("div",/^Speak chat replies aloud$/); var all=$$("div").filter(function(d){ return d.textContent.trim()==="Speak chat replies aloud"; });
    var title2=all[0]; txt(title2,"Hands-free voice (say \u201cMiko\u201d)"); var desc2=title2.nextElementSibling; txt(desc2,"Off"); rows.handsfree={btn:$("button",row2),desc:desc2};
    rows.handsfree.btn._onCls=onCls; rows.handsfree.lock=0;
    toggle(rows.handsfree.btn,!!cfg.voice_enabled);
    rows.handsfree.btn.addEventListener("click",function(){
      var want=!(rows.handsfree.on); toggle(rows.handsfree.btn,want); rows.handsfree.on=want; rows.handsfree.lock=Date.now()+3500;
      txt(desc2,want?"Starting\u2026 loading the speech models (the first time takes a little while)":"Turning off\u2026");
      window.miko.api(want?"voice/start":"voice/stop",{}).then(function(){ cfg.voice_enabled=want; });
    });
    // microphone picker
    var mic=document.createElement("div"); mic.className=row.className.replace(/\bhover:[^\s]+/g,"");
    mic.innerHTML='<div class="flex items-center gap-space-sm"><span class="material-symbols-outlined text-primary">mic</span><div><div class="font-title-sm text-title-sm text-on-surface">Microphone</div><div class="font-body-sm text-body-sm text-on-surface-variant">The input Miko listens on for her wake word</div></div></div><select class="bg-transparent outline-none text-on-surface font-label-sm cursor-pointer max-w-[220px]"></select>';
    row.parentElement.appendChild(mic); var ms=$("select",mic);
    window.miko.api("voice/mics",{}).then(function(r){
      var list=r.mics||[]; if(!list.length){ ms.innerHTML='<option>No microphone found</option>'; return; }
      ms.innerHTML=list.map(function(m){ return '<option value="'+m.index+'"'+(Number(cfg.mic_device)===m.index?" selected":"")+'>'+esc(m.name.slice(0,40))+' (#'+m.index+')</option>'; }).join("");
    });
    ms.addEventListener("change",function(){ save({mic_device:Number(ms.value)}).then(function(){ say("Microphone changed. If hands-free is on, switch it off and on again."); }); });
  }

  function onStatus(v){
    var h=rows.handsfree; if(!h) return; var st=v.state||"off", on=(st!=="off"&&st!=="error")||v.running;
    if(Date.now()>h.lock){ h.on=on; toggle(h.btn,on); }
    var msg={off:"Off",loading:"Loading the speech models\u2026 (first time takes a while)",idle:"On \u2014 listening for \u201cMiko\u201d",listening:"Listening to you now\u2026",thinking:"Thinking\u2026",speaking:"Speaking\u2026",error:"Problem: "+(v.error||"unknown")}[st]||st;
    txt(h.desc,msg);
    if(poseEl) txt(poseEl,"State: "+st+(v.game_mode?" \u2022 game mode":""));
  }

  /* ---- desktop ---- */
  function desktop(){
    ["Floating Desktop Hologram","Taskbar Tray Only"].forEach(function(n){
      var t=byText("div",new RegExp("^"+n+"$")); if(!t) return; var card=t.closest("div.cursor-pointer");
      var tag=document.createElement("span"); tag.textContent="Coming soon"; tag.className="px-2 py-0.5 rounded-full bg-secondary-container/40 text-secondary font-label-sm text-[10px] self-start"; t.parentElement.insertBefore(tag,t);
      card.addEventListener("click",function(){ say("The "+n.toLowerCase()+" is the next thing on my list. For now I live in this window!"); });
    });
    var chroma=byText("div",/^Cat-Ear Neon LED Chroma Sync$/); if(chroma) hide(chroma.closest("div.p-space-md").parentElement);
    var d=byText("p",/Always-on-top transparent avatar/); // keep wording
  }

  /* ---- memory ---- */
  function memory(){
    var s=sec.memory; if(!s) return;
    var used=byText("span",/GB Used/), barBox=$(".h-2\\.5",s), info=byText("span",/Indexed Episodic/), local=byText("span",/Zero Cloud/);
    if(barBox) hide(barBox);
    var tagsBox=$$("span",s).filter(function(x){ return /^#/.test(x.textContent.trim()); });
    var purge=byText("button",/Purge Short-term/), exp=byText("button",/Export Brain/);
    function refresh(){ window.miko.api("memory/list").then(function(r){
      var f=r.facts||[]; txt(used,f.length+" fact"+(f.length===1?"":"s")+" remembered"); txt(info,f.length?"Newest first. Say \u201cremember that \u2026\u201d to add one, or \u201cforget that\u201d to remove the last.":"Nothing saved yet. Say \u201cremember that \u2026\u201d to teach me something.");
      txt(local,"Stored on this PC only \u2022 no cloud");
      tagsBox.forEach(function(t,i){ var fact=f[f.length-1-i]; if(fact){ t.style.display=""; t.title=fact; txt(t,"# "+(fact.length>30?fact.slice(0,28)+"\u2026":fact)); } else t.style.display="none"; });
    }); }
    refresh();
    if(purge){ txt($$("span",purge).pop(),"Clear chat history"); purge.addEventListener("click",function(){ window.miko.api("chat/clear",{}).then(function(){ say("Chat history cleared. Your saved facts are untouched."); }); }); }
    if(exp){ exp.addEventListener("click",function(){ window.miko.api("brain/export",{}).then(function(r){ if(r.ok){ say("Exported "+r.facts+" facts and your settings. Opening the folder."); window.miko.api("download/reveal",{path:r.path}); } else say("Couldn't export: "+r.error); }); }); }
    if(purge){ var fa=purge.cloneNode(true); purge.parentElement.insertBefore(fa,purge); txt($$("span",fa).pop(),"Forget all facts"); $("span",fa).textContent="delete_forever"; var armed=false;
      fa.addEventListener("click",function(){ var l=$$("span",fa).pop(); if(!armed){ armed=true; txt(l,"Really forget everything?"); setTimeout(function(){ armed=false; txt(l,"Forget all facts"); },3000); return; }
        window.miko.api("memory/forget_all",{}).then(function(){ armed=false; txt(l,"Forget all facts"); refresh(); say("Okay, I forgot everything I had saved."); }); }); }
  }

  /* ---- connections & about ---- */
  function panel(){
    var host=sec.memory&&sec.memory.parentElement; if(!host) return;
    var p=document.createElement("div"); p.id="miko-about"; p.className=sec.memory.className;
    p.innerHTML='<div class="flex items-center gap-space-sm"><div class="w-8 h-8 rounded-full bg-tertiary-container/40 flex items-center justify-center text-tertiary"><span class="material-symbols-outlined">hub</span></div><div><h3 class="font-headline-md text-headline-md text-on-surface">Connections &amp; About</h3><p class="font-body-sm text-body-sm text-on-surface-variant">What Miko can use on this PC, and where her files live</p></div></div>'+
      '<div id="miko-mods" class="flex flex-wrap gap-space-xs"></div>'+
      '<div class="flex flex-wrap items-center gap-space-xs"><span class="font-title-sm text-title-sm text-on-surface">Web search key (Tavily):</span><span id="miko-key" class="font-label-md text-on-surface-variant">checking\u2026</span><input id="miko-keyin" type="password" placeholder="paste a new key" class="flex-1 min-w-[160px] px-3 py-1.5 rounded-DEFAULT bg-surface-container-lowest/80 border border-outline-variant/40 text-on-surface font-body-sm outline-none focus:border-primary"/><button id="miko-keysave" class="px-space-md py-1.5 rounded-DEFAULT bg-primary-container text-on-primary-container font-label-sm">Save key</button></div>'+
      '<div id="miko-paths" class="font-body-sm text-body-sm text-on-surface-variant flex flex-col gap-1"></div>';
    host.appendChild(p);
    window.miko.api("about",{}).then(function(a){
      $("#miko-mods").innerHTML=(a.modules||[]).map(function(m){ return '<span title="'+(m.ok?"installed":"missing \u2014 run: pip install "+esc(m.pip))+'" class="px-space-sm py-1 rounded-full font-label-sm '+(m.ok?"bg-tertiary-container/30 text-tertiary":"bg-error-container/40 text-error")+'">'+(m.ok?"\u2713 ":"\u2717 ")+esc(m.pip)+'</span>'; }).join("");
      $("#miko-paths").innerHTML=["Program folder: "+a.folder,"Memory file: "+a.memory_file,"Downloads: "+a.downloads,"Address: "+a.url,"Python "+a.python].map(function(x){ return "<span>"+esc(x)+"</span>"; }).join("");
    });
    function key(r){ txt($("#miko-key"),r.has_key?"saved ("+r.masked+")":"not set \u2014 web search needs a free key from tavily.com"); }
    window.miko.api("settings/search_key",{}).then(key);
    $("#miko-keysave").addEventListener("click",function(){ var k=$("#miko-keyin").value.trim(); if(!k) return;
      window.miko.api("settings/search_key",{key:k}).then(function(r){ if(r.ok){ $("#miko-keyin").value=""; key(r); say("Search key saved!"); } else say(r.error); }); });
    sec.about=p;
  }

  /* ---- left rail ---- */
  function rail(){
    var nav=$("#settings-nav"); if(!nav) return;
    var btns=$$("button",nav), act=btns[0].className, inact=btns[1].className;
    var target={"AI Personality & Voice":function(){ return sec.archetype; },"Neural Memory & Privacy":function(){ return sec.memory; },
                "Search & Web Scraper":function(){ return sec.about; },"Windows 11 Integration":function(){ return sec.desktop; },"About Miko Core":function(){ return sec.about; },
                "Appearance & Acrylic":function(){ say("My look comes from the Stitch design (purple acrylic). There's nothing to change here yet."); return null; }};
    btns.forEach(function(b){
      var name=$$("span",b).filter(function(s){ return !s.classList.contains("material-symbols-outlined"); })[0];
      var key=name?name.textContent.replace(/&amp;/g,"&").trim():""; 
      $$("span",b).forEach(function(s){ var t=s.textContent.trim(); if(t==="Mica"||t==="Win+M") hide(s); if(t==="v2.4") txt(s,"v1.0"); });
      b.addEventListener("click",function(){ btns.forEach(function(x){ x.className=inact; }); b.className=act; var t=target[key]&&target[key](); if(t) t.scrollIntoView({behavior:"smooth",block:"start"}); });
    });
  }

  /* ---- right column ---- */
  function right(){
    var l=byText("span",/^Miko says:$/); bubbleP=l?l.closest("div").parentElement.querySelector("p"):null; window.miko.bubbleEl=bubbleP;
    txt(bubbleP,"Change my personality or voice and I'll react right here!");
    var pose=byText("span",/^Pose:/); poseEl=pose; var sync=byText("span",/^Sync 60fps$/); hide(sync);
    $$("button").forEach(function(b){ var t=b.textContent.trim();
      if(/Poke Head/.test(t)) b.addEventListener("click",function(){ window.miko.ask("*pokes your head playfully* React in one short sentence.",""); });
      if(/Feed Snack/.test(t)) b.addEventListener("click",function(){ window.miko.ask("*hands you a tasty snack* React in one short sentence.",""); }); });
    var caps={"Smart Japanese & EN AI Assistant":"Smart AI assistant that runs locally (Ollama)","Universal Search & Scraper":"Web, image, video and news search","Multithreaded Download Vault":"Download manager with pause and history","Windows 11 Volume & App Control":"Windows volume, timers and app launching","Continuous Self-Learning Persona":"Remembers the facts you tell it"};
    $$("li span").forEach(function(s){ var k=s.textContent.replace(/&amp;/g,"&").trim(); if(caps[k]) txt(s,caps[k]); });
    var lab=byText("span",/^Sync Pipeline$/); if(lab){ telem.pipe=lab.nextElementSibling; var box=lab.closest("div.p-space-md");
      var rowsT=$$("div.flex.items-center",box); var lat=byText("span",/^Response Latency$/), emo=byText("span",/^Emotion Weight$/);
      txt(lab,"Ollama"); telem.lat=lat&&lat.nextElementSibling; telem.emo=emo&&emo.nextElementSibling; txt(lat,"Last reply took"); txt(emo,"Personality"); var gbar=$(".h-1",box); hide(gbar); }
  }
  function telemetry(s){
    if(s){ telem.last=s; } s=telem.last; if(!s) return;
    if(telem.pipe){ var ok=s.ollama_ok; telem.pipe.lastChild.textContent=ok===true?" Online":ok===false?" Not reachable":" Not used yet"; }
    txt(telem.lat,s.last_latency!=null?s.last_latency+" s":"\u2014"); txt(telem.emo,NAMES[cfg.archetype]||NAMES.original);
  }

  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();

/* ---------- Audio wave screen: follows Miko's real state ---------- */
(function(){
  if(location.pathname.indexOf("/screen/audio")!==0) return;
  function $$(s){return Array.prototype.slice.call(document.querySelectorAll(s));}
  function init(){
    var names={"tab-state-1":"1: Speaking","tab-state-2":"2: Listening","tab-state-3":"3: Thinking","tab-state-4":"4: Idle"};
    Object.keys(names).forEach(function(id){ var b=document.getElementById(id); if(!b) return; var sp=b.querySelectorAll("span"); sp[sp.length-1].textContent=names[id]; });
    $$("span").forEach(function(s){ var t=s.textContent.trim();
      if(t==="0.08ms") s.textContent="live"; if(t==="Low-Latency DSP") s.textContent="follows Miko's voice state";
      if(t==="Spotify + Neural TTS") s.textContent="Miko voice engine"; if(t==="v2.4 DSP") s.textContent="visual";
      if(/Real-time spectral/.test(t)) s.textContent="A visual preview of how Miko looks while she talks and listens"; });
    var rms=document.getElementById("rms-val"); var map={speaking:"state-1",listening:"state-2",thinking:"state-3",idle:"state-4",off:"state-4",loading:"state-4",error:"state-4"};
    var last="";
    window.miko.onStatus=function(v){ var id=map[v.state]||"state-4"; if(id!==last){ last=id; if(window.switchState) window.switchState(id); if(rms) rms.innerText=(v.state||"off"); } };
    window.miko.api("status").then(function(s){ window.miko.onStatus(s.voice||{}); });
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();
