"""Video player backend for Miko Stitch (added by the MikoGo player integration).

Standard library only (plus the existing miko_downloads module). It adds three small things:
  * media_file()   - validates a path so only video/audio files inside the Miko downloads folder are served
  * serve_media()  - streams such a file with HTTP Range support (needed for seeking in <video>)
  * library()      - lists the videos Miko has downloaded, for the player's "Downloaded" playlist
  * resolve()      - optional: asks yt-dlp (if installed) for a direct stream URL of a page that cannot be embedded
Nothing here touches search, chat, voice, avatar or the download engine.
"""
import os, re, json, subprocess, shutil, sys, time
from urllib.parse import urlparse

import miko_downloads

# Containers a Chromium/Edge <video> element can play without extra codecs installed.
WEB_VIDEO = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg",
             ".mov": "video/mp4"}
# Containers Miko can list but the browser engine usually cannot play (the UI offers "open with Windows player").
OTHER_VIDEO = {".mkv": "video/x-matroska", ".avi": "video/x-msvideo", ".wmv": "video/x-ms-wmv", ".flv": "video/x-flv"}
AUDIO = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".wav": "audio/wav",
         ".flac": "audio/flac"}
ALL_MEDIA = {**WEB_VIDEO, **OTHER_VIDEO, **AUDIO}
CHUNK = 256 * 1024
_RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


def media_file(path):
    """Return the real path only if it is a media file inside the Miko downloads folder, else None."""
    try:
        if not isinstance(path, str) or not path:
            return None
        root = os.path.realpath(miko_downloads.DOWNLOAD_DIR)
        real = os.path.realpath(path)
        if (os.path.normcase(real).startswith(os.path.normcase(root) + os.sep)    # Windows paths are case-insensitive
                and os.path.splitext(real)[1].lower() in ALL_MEDIA and os.path.isfile(real)):
            return real
    except Exception:
        pass
    return None


def serve_media(handler, path, head_only=False):
    """Stream a validated media file with Range support. `handler` is the BaseHTTPRequestHandler."""
    real = media_file(path)
    if not real:
        handler.send_response(404)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return
    size = os.path.getsize(real)
    ctype = ALL_MEDIA.get(os.path.splitext(real)[1].lower(), "application/octet-stream")
    start, end, status = 0, size - 1, 200
    rng = handler.headers.get("Range")
    if rng:
        m = _RANGE.match(rng.strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            else:                                   # suffix range: last N bytes
                start = max(0, size - int(m.group(2)))
            if start >= size or start > end:
                handler.send_response(416)
                handler.send_header("Content-Range", "bytes */%d" % size)
                handler.send_header("Content-Length", "0")
                handler.end_headers()
                return
            status = 206
    length = end - start + 1 if size else 0
    handler.send_response(status)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(length))
    handler.send_header("Cache-Control", "no-store")
    if status == 206:
        handler.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
    handler.end_headers()
    if head_only or not length:
        return
    try:
        with open(real, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                buf = f.read(min(CHUNK, left))
                if not buf:
                    break
                handler.wfile.write(buf)
                left -= len(buf)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass                                        # the player closed the connection (seek / next video)
    handler.close_connection = True


def library(limit=300):
    """Videos/audio Miko has downloaded: history entries first, then any other media file in the folder."""
    out, seen = [], set()

    def add(path, title, kind, ts):
        real = media_file(path)
        if not real or real in seen:
            return
        seen.add(real)
        ext = os.path.splitext(real)[1].lower()
        out.append({"title": title or os.path.splitext(os.path.basename(real))[0], "path": real,
                    "name": os.path.basename(real), "ext": ext, "kind": "audio" if ext in AUDIO else "video",
                    "playable": ext in WEB_VIDEO or ext in AUDIO, "size": os.path.getsize(real), "ts": ts})
    try:
        for h in miko_downloads.list_history():
            if h.get("kind") in ("video", "audio", "file"):
                add(h.get("path", ""), h.get("title", ""), h.get("kind"), h.get("ts", 0))
    except Exception:
        pass
    count = 0
    for root, _dirs, files in os.walk(miko_downloads.DOWNLOAD_DIR):
        for f in files:
            count += 1
            if count > 20000 or len(out) >= limit:
                break
            full = os.path.join(root, f)
            if os.path.splitext(f)[1].lower() in ALL_MEDIA:
                try:
                    add(full, "", "video", os.path.getmtime(full))
                except OSError:
                    pass
    out.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return out[:limit]


def _ytdlp():
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except Exception:
        return None


def resolve(url, timeout=25):
    """Ask yt-dlp for ONE direct, progressive (non-HLS) stream URL. Only runs when the user asks to play a page
    that cannot be embedded. Returns {ok, url, title, ext} or {ok: False, error}."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")) or len(url) > 2000:
        return {"ok": False, "error": "only http(s) links can be played"}
    cmd = _ytdlp()
    if not cmd:
        return {"ok": False, "error": "yt-dlp is not installed (run: pip install yt-dlp)", "needs_ytdlp": True}
    args = cmd + ["--no-playlist", "--no-warnings", "--skip-download", "--socket-timeout", "15",
                  "-f", "b[protocol^=http][protocol!*=m3u8][ext=mp4]/b[protocol^=http][protocol!*=m3u8][ext=webm]"
                        "/b[protocol^=http][protocol!*=m3u8]",
                  "--dump-single-json", url]
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        if p.returncode != 0:
            return {"ok": False, "error": "this site does not offer a stream that can be played here"}
        info = json.loads(p.stdout)
        direct = info.get("url") or ""
        if not direct and info.get("requested_formats"):
            direct = ""                              # split audio+video streams cannot be played in one <video>
        if not direct.startswith(("http://", "https://")):
            return {"ok": False, "error": "no single playable stream was found for this link"}
        return {"ok": True, "url": direct, "title": (info.get("title") or "")[:200], "ext": info.get("ext", "")}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "the site took too long to answer"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:140]}
