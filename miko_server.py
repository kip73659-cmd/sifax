"""Miko Stitch server (piece 1).
Standard library only. Serves the unified Stitch UI and a small JSON API.
Binds to 127.0.0.1 so nothing outside this PC can reach it.
"""
import json, os, sys, threading, time, webbrowser, hmac, hashlib, secrets, socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None:                      # started with pythonw (no console): never crash on print()
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.path.join(BASE, "miko_server.log"), "a", buffering=1)
UI = os.path.join(BASE, "ui")
# Remote access: set MIKO_REMOTE=1 (see start_miko_remote.bat) to reach Miko from phones/PCs on your network.
# Remote visitors must enter the access key stored in miko_access_key.txt. Without MIKO_REMOTE nothing changes.
REMOTE = os.environ.get("MIKO_REMOTE") == "1"
HOST, PORT = ("0.0.0.0" if REMOTE else "127.0.0.1"), 8765
LOCAL_URL = "http://127.0.0.1:%d/" % 8765
BRIDGE_TAG = '<script src="/assets/bridge.js"></script>'
SCREENS = {"web-search", "image-gallery", "video-vault", "news-feed",
           "research-intel", "downloads", "settings", "overlay", "audio", "anime-room"}
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".gif": "image/gif", ".bmp": "image/bmp", ".svg": "image/svg+xml"}

# API handlers are registered here; later pieces add chat, search, downloads...
API = {}
def api(name):
    def deco(fn):
        API[name] = fn
        return fn
    return deco

@api("ping")
def _ping(body):
    return {"ok": True, "app": "miko-stitch"}

@api("window")
def _window(body):
    action = (body or {}).get("action")
    if action == "close":
        threading.Timer(0.3, lambda: os._exit(0)).start()
        return {"ok": True}
    return {"ok": True, "note": action + " handled by the desktop window"}


import miko_chat, miko_search, miko_downloads, miko_research, miko_voice
import miko_player          # integrated video player backend (media streaming, library, stream resolver)
import miko_anime           # Anime Room backend (saved sites, search, watch, download, library)
for _n, _f in miko_anime.ENDPOINTS.items():
    API["anime/" + _n] = _f
miko_downloads.SETTINGS_GETTER = miko_chat.load_config

@api("chat/clear")
def _chat_clear(body):
    miko_chat.clear_session()
    return {"ok": True}

@api("memory/list")
def _mem_list(body):
    return {"ok": True, "facts": miko_chat.load_memory()}

@api("memory/add")
def _mem_add(body):
    fact = (body or {}).get("fact", "").strip()
    if not fact:
        return {"ok": False, "error": "empty"}
    miko_chat.save_memory(fact)
    return {"ok": True, "facts": miko_chat.load_memory()}

@api("memory/forget_last")
def _mem_last(body):
    return {"ok": miko_chat.forget_last(), "facts": miko_chat.load_memory()}

@api("memory/forget_all")
def _mem_all(body):
    miko_chat.forget_all()
    return {"ok": True, "facts": []}

@api("search")
def _search(body):
    body = body or {}
    q = (body.get("q") or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": []}
    return miko_search.run_search(body.get("kind", "web"), q, body.get("n"))

@api("open")
def _open(body):
    url = (body or {}).get("url", "")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "only http(s) links can be opened"}
    if (body or {}).get("popup"):
        import shutil, subprocess
        for exe in ("msedge", "chrome", "google-chrome", "chromium"):
            path = shutil.which(exe)
            if not path and os.name == "nt":
                for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
                    for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
                        cand = os.path.join(base, rel)
                        if os.path.exists(cand):
                            path = cand
                            break
                    if path:
                        break
            if path:
                subprocess.Popen([path, "--app=" + url, "--window-size=640,400"])
                return {"ok": True, "popup": True}
    webbrowser.open(url)
    return {"ok": True}

def _inside_downloads(path):
    try:
        root = os.path.realpath(miko_downloads.DOWNLOAD_DIR)
        return os.path.realpath(path).startswith(root + os.sep)
    except Exception:
        return False

@api("download/start")
def _dl_start(body):
    body = body or {}
    try:
        jid = miko_downloads.start(body.get("kind", "file"), body.get("url", ""), body.get("title", ""))
        return {"ok": True, "id": jid}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@api("download/list")
def _dl_list(body):
    return {"ok": True, "jobs": miko_downloads.list_jobs(), "history": miko_downloads.list_history(),
            "ytdlp": miko_downloads.ytdlp_available(), "folder": miko_downloads.DOWNLOAD_DIR,
            "disk": miko_downloads.disk()}

@api("download/usage")
def _dl_usage(body):
    return {"ok": True, "usage": miko_downloads.usage()}

@api("download/pause")
def _dl_pause(body):
    b = body or {}
    return {"ok": miko_downloads.pause(int(b.get("id", 0)), bool(b.get("paused", True)))}

@api("download/pause_all")
def _dl_pause_all(body):
    return {"ok": True, "count": miko_downloads.pause_all(bool((body or {}).get("paused", True)))}

@api("download/remove")
def _dl_remove(body):
    return {"ok": miko_downloads.remove(int((body or {}).get("id", 0)))}

@api("download/extract")
def _dl_extract(body):
    path = (body or {}).get("path", "")
    if not _inside_downloads(path):
        return {"ok": False, "error": "that file is outside the Miko downloads folder"}
    try:
        return {"ok": True, "folder": miko_downloads.extract(path)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}

@api("download/cancel")
def _dl_cancel(body):
    miko_downloads.cancel(int((body or {}).get("id", 0)))
    return {"ok": True}

@api("download/clear")
def _dl_clear(body):
    miko_downloads.clear_history()
    return {"ok": True}

@api("download/reveal")
def _dl_reveal(body):
    path = (body or {}).get("path", "")
    if path and not _inside_downloads(path):
        return {"ok": False, "error": "that file is outside the Miko downloads folder"}
    return {"ok": miko_downloads.reveal(path)}

@api("download/open")
def _dl_open(body):
    path = (body or {}).get("path", "")
    if not _inside_downloads(path):
        return {"ok": False, "error": "that file is outside the Miko downloads folder"}
    return {"ok": miko_downloads.open_path(path)}

@api("video/library")
def _vid_library(body):
    try:
        return {"ok": True, "items": miko_player.library(), "folder": miko_downloads.DOWNLOAD_DIR}
    except Exception as e:
        return {"ok": False, "items": [], "error": str(e)[:160]}

@api("video/resolve")
def _vid_resolve(body):
    return miko_player.resolve((body or {}).get("url", ""))

@api("wallpaper")
def _wallpaper(body):
    path = (body or {}).get("path", "")
    if not _inside_downloads(path):
        return {"ok": False, "error": "wallpaper must be a file Miko downloaded"}
    try:
        return {"ok": True, "path": miko_downloads.set_wallpaper(path)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}

@api("research/list")
def _r_list(body):
    return {"ok": True, "items": miko_research.list_items((body or {}).get("type"))}

@api("research/add")
def _r_add(body):
    try:
        rec, new = miko_research.add(body or {})
        return {"ok": True, "item": rec, "new": new}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@api("research/remove")
def _r_remove(body):
    return {"ok": miko_research.remove(int((body or {}).get("id", 0)))}

@api("research/update")
def _r_update(body):
    rec = miko_research.update(int((body or {}).get("id", 0)), body or {})
    return {"ok": rec is not None, "item": rec}

@api("research/clear")
def _r_clear(body):
    miko_research.clear((body or {}).get("type"))
    return {"ok": True}

@api("fetch/page")
def _fetch_page(body):
    try:
        return {"ok": True, **miko_search.page_info((body or {}).get("url", ""))}
    except Exception as e:
        return {"ok": False, "error": "could not read that page: " + str(e)[:120]}

@api("save/text")
def _save_text(body):
    import re
    body = body or {}
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(body.get("name", "report"))).strip(" .")[:80] or "report"
    folder = os.path.join(miko_downloads.DOWNLOAD_DIR, "Reports")
    os.makedirs(folder, exist_ok=True)
    path = miko_downloads._unique(os.path.join(folder, name + ".md"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(body.get("text", "")))
    return {"ok": True, "path": path}

@api("status")
def _status(body):
    cfg = miko_chat.load_config()
    v = miko_voice.ENGINE.status()
    return {"ok": True, "voice": v, "brain": cfg["brain"], "archetype": cfg["archetype"],
            "ollama_ok": miko_chat.STATS["ollama_ok"], "last_latency": miko_chat.STATS["last_latency"],
            "last_error": miko_chat.STATS["last_error"], "facts": len(miko_chat.load_memory()),
            "ytdlp": miko_downloads.ytdlp_available(), "voice_enabled": cfg["voice_enabled"]}

@api("voice/start")
def _v_start(body):
    miko_chat.save_config({"voice_enabled": True})
    miko_voice.ENGINE.start()
    return {"ok": True, "voice": miko_voice.ENGINE.status()}

@api("voice/stop")
def _v_stop(body):
    miko_chat.save_config({"voice_enabled": False})
    miko_voice.ENGINE.stop()
    return {"ok": True}

@api("voice/wake")
def _v_wake(body):
    miko_voice.ENGINE.wake()
    return {"ok": True, "voice": miko_voice.ENGINE.status()}

@api("voice/events")
def _v_events(body):
    since = int((body or {}).get("since", 0))
    return {"ok": True, "events": miko_voice.ENGINE.events_since(since), "voice": miko_voice.ENGINE.status()}

@api("voice/voices")
def _v_voices(body):
    try:
        return {"ok": True, "voices": miko_voice.list_voices(), "live": True}
    except Exception:
        return {"ok": True, "voices": miko_voice.STATIC_VOICES, "live": False}

@api("voice/mics")
def _v_mics(body):
    try:
        return {"ok": True, "mics": miko_voice.list_mics()}
    except Exception as e:
        return {"ok": False, "mics": [], "error": str(e)[:120]}

@api("ollama/models")
def _o_models(body):
    names = miko_chat.list_models()
    return {"ok": bool(names), "models": names, "brain": miko_chat.load_config()["brain"]}

@api("settings/search_key")
def _skey(body):
    import re
    p = os.path.join(BASE, "tavily_key.txt")
    body = body or {}
    if "key" in body:
        k = str(body["key"]).strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-]{10,200}", k):
            return {"ok": False, "error": "that does not look like a Tavily key"}
        with open(p, "w", encoding="utf-8") as f:
            f.write(k)
        miko_search._cache.clear()
    k = ""
    try:
        k = open(p, encoding="utf-8").read().strip()
    except Exception:
        pass
    return {"ok": True, "has_key": bool(k), "masked": (k[:5] + "..." + k[-4:]) if len(k) > 12 else ("set" if k else "")}

@api("brain/export")
def _brain_export(body):
    import json as _json
    cfg = miko_chat.load_config()
    data = {"app": "Miko", "exported": time.strftime("%Y-%m-%d %H:%M:%S"), "facts": miko_chat.load_memory(),
            "settings": {k: cfg[k] for k in ("brain", "archetype", "tone", "voice", "voice_rate", "voice_pitch")}}
    folder = os.path.join(miko_downloads.DOWNLOAD_DIR, "Reports")
    os.makedirs(folder, exist_ok=True)
    path = miko_downloads._unique(os.path.join(folder, "miko_brain.miko"))
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)
    return {"ok": True, "path": path, "facts": len(data["facts"])}

@api("about")
def _about(body):
    import platform
    cfg = miko_chat.load_config()
    import importlib.util
    mods = [("ollama", "ollama"), ("requests", "requests"), ("ddgs", "ddgs"), ("faster_whisper", "faster-whisper"),
            ("sounddevice", "sounddevice"), ("edge_tts", "edge-tts"), ("pygame", "pygame"), ("yt_dlp", "yt-dlp"),
            ("pycaw", "pycaw"), ("PIL", "pillow"), ("numpy", "numpy"), ("bs4", "beautifulsoup4")]
    modules = [{"module": m, "pip": pip, "ok": importlib.util.find_spec(m) is not None} for m, pip in mods]
    return {"ok": True, "modules": modules, "python": platform.python_version(), "os": platform.platform(),
            "folder": BASE, "memory_file": cfg["memory_file"], "downloads": miko_downloads.DOWNLOAD_DIR,
            "url": LOCAL_URL}

@api("config/get")
def _cfg_get(body):
    return {"ok": True, "config": miko_chat.load_config()}

@api("config/set")
def _cfg_set(body):
    return {"ok": True, "config": miko_chat.save_config(body or {})}


READ_ONLY = {"ping", "status", "memory/list", "config/get", "download/list", "download/usage", "research/list"}
ALLOWED_HOSTS = {"127.0.0.1:%d" % PORT, "localhost:%d" % PORT}
ALLOWED_ORIGINS = {"http://" + h for h in ALLOWED_HOSTS}
MAX_BODY = 2_000_000

KEY_FILE = os.path.join(BASE, "miko_access_key.txt")
_FAILS = {}

def _access_key():
    try:
        k = open(KEY_FILE, encoding="utf-8").read().strip()
        if len(k) >= 6:
            return k
    except Exception:
        pass
    k = secrets.token_urlsafe(9)
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(k + "\n")
    return k

def _auth_token():
    return hmac.new(_access_key().encode(), b"miko-remote-v1", hashlib.sha256).hexdigest()

def _throttled(ip):
    t = [x for x in _FAILS.get(ip, []) if time.time() - x < 60]
    _FAILS[ip] = t
    return len(t) >= 5

def _fail(ip):
    _FAILS.setdefault(ip, []).append(time.time())

def _lan_ips():
    ips = set()
    try:
        s_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s_.connect(("10.255.255.255", 1))
        ips.add(s_.getsockname()[0]); s_.close()
    except Exception:
        pass
    return sorted(ips)

class Handler(BaseHTTPRequestHandler):
    server_version = "MikoStitch/1"

    def log_message(self, *a):
        pass  # keep the console quiet and CPU use low

    def _send(self, code, data, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode("utf-8"), MIME[".json"])

    def _file(self, path):
        if not os.path.isfile(path):
            return self._send(404, b"Not found", "text/plain")
        ext = os.path.splitext(path)[1].lower()
        with open(path, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))

    def _site_ok(self):
        """Same-origin/typed-in requests are fine. A same-site GET that loads Miko inside an iframe
        (the Streamlit wrapper on another port of this same host) is allowed too; nothing else cross-site."""
        site = self.headers.get("Sec-Fetch-Site")
        if not site or site in ("same-origin", "none"):
            return True
        return (site == "same-site" and self.command == "GET"
                and self.headers.get("Sec-Fetch-Dest") == "iframe")

    def _is_local(self):
        """Opened on this PC itself (loopback client AND a localhost Host header). No key needed."""
        return (self.client_address[0] in ("127.0.0.1", "::1")
                and self.headers.get("Host", "") in ALLOWED_HOSTS)

    def _authed(self):
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "miko_auth" and hmac.compare_digest(v, _auth_token()):
                return True
        return False

    def _login(self, post):
        ip = self.client_address[0]
        if post:
            n = min(int(self.headers.get("Content-Length") or 0), 2000)
            form = parse_qs(self.rfile.read(n).decode("utf-8", "ignore"))
            attempt = (form.get("key", [""])[0]).strip()
            if _throttled(ip):
                return self._send(429, b"Too many tries. Wait a minute.", "text/plain")
            if hmac.compare_digest(attempt.encode(), _access_key().encode()):
                self.send_response(303)
                self.send_header("Set-Cookie", "miko_auth=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000" % _auth_token())
                self.send_header("Location", "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            _fail(ip)
            msg = "Wrong key."
        else:
            msg = ""
        page = ("<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
                "<body style='background:#0f0f14;color:#eee;font-family:sans-serif;display:grid;place-items:center;height:100vh;margin:0'>"
                "<form method=post action=/login style='text-align:center'><h2>Miko</h2>"
                "<input name=key type=password placeholder='Access key' autofocus style='padding:12px;font-size:16px;border-radius:8px;border:0'><br><br>"
                "<button style='padding:10px 24px;font-size:16px;border-radius:8px;border:0'>Enter</button>"
                "<p style='color:#f88'>%s</p></form></body>" % msg)
        self._send(200, page.encode("utf-8"), MIME[".html"])

    def _guard(self, post=False):
        """Local window: only Miko's own pages (blocks CSRF / DNS rebinding).
        Remote mode: everyone else needs the access key (cookie)."""
        path = urlparse(self.path).path
        if self._is_local():
            origin = self.headers.get("Origin")
            if origin and origin not in ALLOWED_ORIGINS:
                self._send(403, b"Forbidden origin", "text/plain"); return False
            if not self._site_ok():
                self._send(403, b"Forbidden request", "text/plain"); return False
            return True
        if not REMOTE:
            self._send(403, b"Forbidden host", "text/plain"); return False
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + host and origin != "https://" + host:
            self._send(403, b"Forbidden origin", "text/plain"); return False
        if not self._site_ok():
            self._send(403, b"Forbidden request", "text/plain"); return False
        if path == "/login":
            self._login(post); return False
        if self._authed():
            return True
        if post or path.startswith(("/api/", "/stream/", "/media", "/dlfile", "/animeproxy")):
            self._send(401, b"Not logged in", "text/plain")
        else:
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Content-Length", "0")
            self.end_headers()
        return False

    def do_GET(self):
        if not self._guard():
            return
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            return self._file(os.path.join(UI, "index.html"))
        if p.startswith("/screen/"):
            name = p[len("/screen/"):]
            if name not in SCREENS:
                return self._send(404, b"Unknown screen", "text/plain")
            fp = os.path.join(UI, "screens", name + ".html")
            if not os.path.isfile(fp):
                return self._send(404, b"Missing screen file", "text/plain")
            html = open(fp, encoding="utf-8").read()
            if "</body>" in html:
                html = html.replace("</body>", BRIDGE_TAG + "</body>", 1)
            else:
                html += BRIDGE_TAG
            return self._send(200, html.encode("utf-8"), MIME[".html"])
        if p.startswith("/assets/"):
            rel = os.path.normpath(p[len("/assets/"):]).lstrip("/\\")
            full = os.path.join(UI, "assets", rel)
            if not os.path.abspath(full).startswith(os.path.join(UI, "assets")):
                return self._send(403, b"Forbidden", "text/plain")
            return self._file(full)
        if p == "/media":
            return miko_player.serve_media(self, parse_qs(urlparse(self.path).query).get("p", [""])[0])
        if p.startswith("/animeproxy/"):
            return miko_anime.serve_proxy(self, p)
        if p == "/dlfile":
            fp = miko_downloads.image_file(parse_qs(urlparse(self.path).query).get("p", [""])[0])
            return self._file(fp) if fp else self._send(404, b"Not found", "text/plain")
        if p.startswith("/api/"):
            name = p[5:]
            fn = API.get(name) if name in READ_ONLY else None
            return self._json(fn({}) if fn else {"ok": False, "error": "use POST for this endpoint"},
                              200 if fn else 405)
        self._send(404, b"Not found", "text/plain")

    def do_HEAD(self):
        if not self._guard():
            return
        u = urlparse(self.path)
        if u.path == "/media":
            return miko_player.serve_media(self, parse_qs(u.query).get("p", [""])[0], head_only=True)
        if u.path.startswith("/animeproxy/"):
            return miko_anime.serve_proxy(self, u.path, head_only=True)
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _stream(self, gen):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for piece in gen:
                self.wfile.write(piece.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def do_POST(self):
        if not self._guard(post=True):
            return
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._json({"ok": False, "error": "request too large"}, 413)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json({"ok": False, "error": "bad json"}, 400)
        if p == "/stream/chat":
            return self._stream(miko_chat.chat_stream((body or {}).get("text", ""), (body or {}).get("context", "")))
        if p == "/stream/tts":
            b = body or {}
            try:
                data = miko_voice.tts_bytes(str(b.get("text", ""))[:1500], b.get("voice"), b.get("rate"), b.get("pitch"))
                return self._send(200, data, "audio/mpeg")
            except Exception as e:
                return self._json({"ok": False, "error": "speech failed: " + str(e)[:120]}, 500)
        if p == "/stream/research":
            return self._stream(miko_chat.research_stream((body or {}).get("topic", ""), (body or {}).get("sources", [])))
        fn = API.get(p[5:]) if p.startswith("/api/") else None
        if not fn:
            return self._json({"ok": False, "error": "unknown endpoint"}, 404)
        try:
            self._json(fn(body))
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:200]}, 500)

def open_window(url):
    """Open Miko in its own app-style window (Edge/Chrome app mode, free, already on your PC)."""
    import shutil, subprocess
    cands = []
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""), os.environ.get("LocalAppData", "")):
            cands += [os.path.join(base, r"Microsoft\Edge\Application\msedge.exe"),
                      os.path.join(base, r"Google\Chrome\Application\chrome.exe")]
    for exe in ("msedge", "chrome", "google-chrome", "chromium"):
        cands.append(shutil.which(exe) or "")
    for path in cands:
        if path and os.path.exists(path):
            try:
                subprocess.Popen([path, "--app=" + url, "--window-size=1500,950"])
                return
            except Exception:
                pass
    webbrowser.open(url)

def main(open_browser=True):
    os.chdir(BASE)
    url = LOCAL_URL
    try:
        srv = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        # already running: just bring up another window and leave
        if open_browser:
            open_window(url)
        return
    miko_voice.ENGINE.ui_url = url
    miko_chat.start_game_watcher()
    if miko_chat.load_config().get("voice_enabled"):
        miko_voice.ENGINE.start()
    print("Miko is running at", url)
    if REMOTE:
        key = _access_key()
        for ip in _lan_ips():
            print("From other devices on your network open:  http://%s:%d/" % (ip, PORT))
        print("Access key (also in miko_access_key.txt):", key)
    if open_browser:
        threading.Timer(0.8, lambda: open_window(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main("--no-browser" not in sys.argv)
