"""Downloads backend for Miko Stitch (piece 4, upgraded).
- Files/images: plain HTTP download with real speed, size, pause/resume (low CPU).
- Videos / MP3: uses yt-dlp if installed (free). Never required for the rest of Miko.
- History of finished downloads is kept in miko_downloads.json so it survives restarts.
- Wallpaper: Windows only, via the built-in SystemParametersInfo call."""
import os, re, sys, time, json, shutil, threading, subprocess, itertools, zipfile, requests
from urllib.parse import urlparse, unquote

BASE = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Miko")
HISTORY_FILE = os.path.join(BASE, "miko_downloads.json")
JOBS = {}
_ids = itertools.count(1)
_lock = threading.Lock()
_hlock = threading.Lock()
MAX_PARALLEL = 2
_slots = threading.Semaphore(MAX_PARALLEL)   # keeps CPU / network use low while gaming
SETTINGS_GETTER = None                        # set by the server: returns the config dict
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
TERMINAL = ("done", "error", "cancelled")

def _cfg():
    try:
        return SETTINGS_GETTER() if SETTINGS_GETTER else {}
    except Exception:
        return {}

def _safe_name(name, default="file"):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .") or default
    return name[:120]

def _unique(path):
    root, ext = os.path.splitext(path)
    n, p = 1, path
    while os.path.exists(p):
        n += 1
        p = "%s (%d)%s" % (root, n, ext)
    return p

def _new_job(kind, title, url):
    jid = next(_ids)
    with _lock:
        JOBS[jid] = {"id": jid, "kind": kind, "title": title, "url": url, "status": "queued",
                     "progress": 0, "path": "", "error": "", "started": time.time(), "cancel": False,
                     "paused": False, "got": 0, "total": 0, "speed": 0.0, "eta": "", "size": 0}
    return jid

def _set(jid, **kw):
    with _lock:
        if jid in JOBS:
            JOBS[jid].update(kw)

# ---------------- history (finished downloads) ----------------
def _hist_load():
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except Exception:
        return []

def _hist_save(items):
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items[:200], f, indent=1, ensure_ascii=False)
    os.replace(tmp, HISTORY_FILE)

def _record(path, title, kind, url, size):
    with _hlock:
        items = _hist_load()
        items.insert(0, {"id": int(time.time() * 1000), "path": path, "name": os.path.basename(path) or title,
                         "title": title, "kind": kind, "url": url, "size": size, "ts": time.time()})
        _hist_save(items)

def list_history():
    with _hlock:
        items = _hist_load()
    for i in items:
        i["missing"] = not os.path.exists(i.get("path", ""))
    return items

def clear_history():
    with _hlock:
        _hist_save([])
    with _lock:
        for k in [k for k, j in JOBS.items() if j["status"] in TERMINAL]:
            del JOBS[k]

def _after_done(jid, kind, url, title):
    path = JOBS[jid]["path"]
    size = os.path.getsize(path) if path and os.path.exists(path) else 0
    _set(jid, size=size, speed=0.0, eta="")
    if path and path.lower().endswith(".zip") and _cfg().get("auto_extract"):
        try:
            extract(path)
        except Exception:
            pass
    if path:
        _record(path, title, kind, url, size)
    if _cfg().get("notify_done", True) and os.name == "nt":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

# ---------------- plain file downloads ----------------
def _guess_ext(url, ctype):
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".mp4", ".zip", ".pdf", ".mp3", ".7z", ".txt"):
        return ext
    return {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
            "application/zip": ".zip", "application/pdf": ".pdf"}.get((ctype or "").split(";")[0], ".bin")

def _run_file(jid, url, title):
    with _slots:
        if JOBS[jid]["cancel"]:
            return _set(jid, status="cancelled")
        _set(jid, status="downloading")
        path = ""
        try:
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            with requests.get(url, stream=True, timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as r:
                r.raise_for_status()
                ext = _guess_ext(url, r.headers.get("Content-Type"))
                base = _safe_name(title or os.path.basename(unquote(urlparse(url).path)) or "download")
                if not base.lower().endswith(ext):
                    base += ext
                path = _unique(os.path.join(DOWNLOAD_DIR, base))
                total = int(r.headers.get("Content-Length") or 0)
                _set(jid, total=total)
                got = lastgot = 0
                last = time.time()
                with open(path, "wb") as f:
                    for chunk in r.iter_content(65536):
                        while JOBS[jid]["paused"] and not JOBS[jid]["cancel"]:
                            _set(jid, status="paused", speed=0.0)
                            time.sleep(0.3)
                            last, lastgot = time.time(), got
                        if JOBS[jid]["status"] == "paused":
                            _set(jid, status="downloading")
                        if JOBS[jid]["cancel"]:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        now = time.time()
                        if now - last >= 0.7:
                            sp = (got - lastgot) / (now - last)
                            old = JOBS[jid]["speed"]
                            sp = sp if not old else 0.6 * old + 0.4 * sp
                            _set(jid, speed=sp, got=got, progress=int(got * 100 / total) if total else 0)
                            last, lastgot = now, got
            if JOBS[jid]["cancel"]:
                try:
                    os.remove(path)
                except OSError:
                    pass
                return _set(jid, status="cancelled")
            _set(jid, status="done", progress=100, path=path, got=got, total=got)
            _after_done(jid, "file", url, title or os.path.basename(path))
        except Exception as e:
            if path and os.path.exists(path) and not JOBS[jid]["path"]:
                try:
                    os.remove(path)
                except OSError:
                    pass
            _set(jid, status="error", error=str(e)[:160], speed=0.0)

# ---------------- videos / audio through yt-dlp ----------------
def _ytdlp_cmd():
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    try:
        import yt_dlp  # noqa
        return [sys.executable, "-m", "yt_dlp"]
    except Exception:
        return None

def ytdlp_available():
    return _ytdlp_cmd() is not None

_UNITS = {"B": 1, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "KIB": 1024, "MIB": 1024 ** 2, "GIB": 1024 ** 3}
def _bytes(val, unit):
    return float(val) * _UNITS.get(unit.upper(), 1)

def _run_video(jid, url, title, audio_only):
    with _slots:
        if JOBS[jid]["cancel"]:
            return _set(jid, status="cancelled")
        cmd = _ytdlp_cmd()
        if not cmd:
            return _set(jid, status="error", error="yt-dlp is not installed. Run: pip install yt-dlp")
        _set(jid, status="downloading")
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        args = cmd + ["--no-playlist", "--newline", "-o", os.path.join(DOWNLOAD_DIR, "%(title).100s.%(ext)s"),
                      "--print", "after_move:filepath"]
        if audio_only:
            args += ["-x", "--audio-format", "mp3"]
        else:
            args += ["-f", "bv*[height<=1080]+ba/b[height<=1080]/b"]
        args.append(url)
        try:
            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 creationflags=0x08000000 if os.name == "nt" else 0)
            last = ""
            for line in p.stdout:
                line = line.strip()
                m = re.search(r"\[download\]\s+([\d.]+)%\s+of\s+~?\s*([\d.]+)\s*(\w+)"
                              r"(?:\s+at\s+([\d.]+)\s*(\w+)/s)?(?:\s+ETA\s+([\d:]+))?", line)
                if m:
                    upd = {"progress": int(float(m.group(1))), "total": int(_bytes(m.group(2), m.group(3)))}
                    if m.group(4):
                        upd["speed"] = _bytes(m.group(4), m.group(5))
                    if m.group(6):
                        upd["eta"] = m.group(6)
                    upd["got"] = int(upd["total"] * upd["progress"] / 100)
                    _set(jid, **upd)
                elif line and os.path.exists(line):
                    last = line
                if JOBS[jid]["cancel"]:
                    p.terminate()
                    return _set(jid, status="cancelled")
            p.wait()
            if p.returncode == 0:
                _set(jid, status="done", progress=100, path=last)
                _after_done(jid, "audio" if audio_only else "video", url, title)
            else:
                _set(jid, status="error", error="yt-dlp could not download this link", speed=0.0)
        except Exception as e:
            _set(jid, status="error", error=str(e)[:160], speed=0.0)

# ---------------- public API ----------------
def start(kind, url, title=""):
    """kind: 'file' | 'video' | 'audio'. Returns the new job id."""
    if kind not in ("file", "video", "audio"):
        raise ValueError("unknown download type")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError("only http(s) links can be downloaded")
    if not title:
        if kind == "file":
            title = _safe_name(os.path.basename(unquote(urlparse(url).path)) or urlparse(url).netloc or "download")
        else:
            title = "%s from %s" % ("Audio" if kind == "audio" else "Video", urlparse(url).netloc.replace("www.", ""))
    jid = _new_job(kind, title, url)
    if kind == "file":
        target, args = _run_file, (jid, url, title)
    else:
        target, args = _run_video, (jid, url, title, kind == "audio")
    threading.Thread(target=target, args=args, daemon=True).start()
    return jid

def list_jobs():
    with _lock:
        out = []
        for j in sorted(JOBS.values(), key=lambda x: -x["id"]):
            d = {k: v for k, v in j.items() if k != "cancel"}
            d["name"] = os.path.basename(j["path"]) if j["path"] else j["title"]
            out.append(d)
        return out

def cancel(jid):
    with _lock:
        j = JOBS.get(jid)
        if not j:
            return
        j["cancel"] = True
        j["paused"] = False
        if j["status"] == "queued":
            j["status"] = "cancelled"

def pause(jid, flag=True):
    """Pause/resume a plain file download. Video downloads (yt-dlp) cannot be paused."""
    with _lock:
        j = JOBS.get(jid)
        if not j or j["kind"] != "file" or j["status"] not in ("queued", "downloading", "paused"):
            return False
        j["paused"] = bool(flag)
        return True

def pause_all(flag=True):
    n = 0
    for j in list_jobs():
        if pause(j["id"], flag):
            n += 1
    return n

def remove(jid):
    with _lock:
        j = JOBS.get(jid)
        if j and j["status"] in TERMINAL:
            del JOBS[jid]
            return True
    return False

def extract(path):
    if not path.lower().endswith(".zip"):
        raise ValueError("only .zip files can be extracted")
    dest = os.path.splitext(path)[0]
    n, d = 1, dest
    while os.path.exists(d):
        n += 1
        d = "%s (%d)" % (dest, n)
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > 8 * 1024 ** 3:
            raise ValueError("this archive is too large to extract here")
        z.extractall(d)
    return d

def image_file(path):
    """Return the path only if it is an image inside the Miko downloads folder."""
    try:
        root = os.path.realpath(DOWNLOAD_DIR)
        real = os.path.realpath(path)
        if real.startswith(root + os.sep) and real.lower().endswith(IMAGE_EXT) and os.path.isfile(real):
            return real
    except Exception:
        pass
    return None

def disk():
    try:
        d = DOWNLOAD_DIR if os.path.exists(DOWNLOAD_DIR) else os.path.expanduser("~")
        u = shutil.disk_usage(d)
        return {"free": u.free, "total": u.total, "drive": os.path.splitdrive(d)[0] or "/"}
    except Exception:
        return {"free": 0, "total": 0, "drive": ""}

def usage():
    cats = {"images": 0, "media": 0, "other": 0}
    count = 0
    for root, _dirs, files in os.walk(DOWNLOAD_DIR):
        for f in files:
            count += 1
            if count > 20000:
                break
            try:
                sz = os.path.getsize(os.path.join(root, f))
            except OSError:
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXT:
                cats["images"] += sz
            elif ext in (".mp4", ".mkv", ".webm", ".mov", ".avi", ".mp3", ".m4a", ".flac", ".wav", ".ogg"):
                cats["media"] += sz
            else:
                cats["other"] += sz
    cats["total"] = cats["images"] + cats["media"] + cats["other"]
    cats["files"] = count
    return cats

def reveal(path):
    """Open the folder (and select the file) in Explorer."""
    if os.name != "nt":
        return False
    if path and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        os.startfile(DOWNLOAD_DIR)
    return True

def open_path(path):
    if os.name == "nt" and path and os.path.exists(path):
        os.startfile(path)
        return True
    return False

def set_wallpaper(path):
    """Windows only. Sets the desktop wallpaper from an image file."""
    if os.name != "nt":
        raise OSError("Setting the wallpaper only works on Windows")
    import ctypes
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if not path.lower().endswith((".jpg", ".jpeg", ".bmp", ".png")):
        from PIL import Image
        jpg = os.path.splitext(path)[0] + ".jpg"
        Image.open(path).convert("RGB").save(jpg, "JPEG", quality=95)
        path = jpg
    SPI_SETDESKWALLPAPER, UPDATE = 20, 3
    ok = ctypes.windll.user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, path, UPDATE)
    if not ok:
        raise OSError("Windows refused to change the wallpaper")
    return path
