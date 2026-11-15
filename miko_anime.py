"""Anime Room backend for Miko Stitch.

What it does
  * saved anime websites (any URL you add), kept in miko_anime.json
  * "reader" browsing of those sites: pages are fetched here and turned into clean cards / episode lists,
    so sites that refuse to be framed still work inside Miko
  * search by anime name (AniList for names/posters + each saved site's own search)
  * finds a playable stream for an episode page and serves it to Miko's player through a small,
    token-protected local relay (handles Referer-protected MP4 and HLS .m3u8)
  * downloads single episodes or ranges through Miko's existing download manager (miko_downloads)
  * anime library (series, episodes, watched/progress/downloaded files)
  * natural-language commands for Miko's chat and voice assistant

Needs: requests (already used by Miko) and beautifulsoup4 (added to install_extra_packages.bat).
yt-dlp (already used by Miko) is used as a fallback resolver / for HLS downloads. ffmpeg is optional.

Safety: only http(s); loopback / private-network addresses are refused unless you saved that exact host:port
as a site; the stream relay only serves URLs that this module itself found for you.
"""
import os, re, json, time, threading, itertools, subprocess, shutil, sys, ipaddress, socket, secrets, hashlib
import queue, unicodedata
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, urljoin, quote_plus, quote, unquote

import requests

try:
    from bs4 import BeautifulSoup
except Exception:                                   # reported to the UI instead of crashing Miko
    BeautifulSoup = None

import miko_downloads

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, "miko_anime.json")
SELF_PORT = 8765
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
MAX_PAGE = 4_000_000
NOWIN = 0x08000000 if os.name == "nt" else 0

_lock = threading.RLock()


# ===================================================================== storage
def _load():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict):
                d.setdefault("sites", [])
                d.setdefault("library", [])
                return d
    except Exception:
        pass
    return {"sites": [], "library": []}


def _save(d):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)


def _sid(*parts):
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:10]


def _bare(host):
    h = (host or "").lower()
    return h[4:] if h.startswith("www.") else h


# ===================================================================== safe HTTP
_sessions = {}
_trusted = set()


def _hostport(u):
    p = urlparse(u)
    return ((p.hostname or "").lower(), p.port or (443 if p.scheme == "https" else 80))


def _refresh_trusted():
    with _lock:
        sites = _load()["sites"]
    _trusted.clear()
    for s in sites:
        try:
            _trusted.add(_hostport(s["url"]))
        except Exception:
            pass


def check_url(u):
    """Raise ValueError unless Miko may fetch this URL."""
    if not isinstance(u, str) or len(u) > 4000:
        raise ValueError("bad link")
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("only http(s) links are supported")
    host, port = _hostport(u)
    if host in ("localhost", "127.0.0.1", "::1") and port == SELF_PORT:
        raise ValueError("that is Miko itself")
    if (host, port) in _trusted:
        return
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError("could not find " + host)
    for inf in infos:
        ip = ipaddress.ip_address(inf[4][0].split("%")[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_unspecified or ip.is_reserved):
            raise ValueError("addresses inside your own network are blocked unless you saved them as a site")


def _site_for(url):
    host = _bare(urlparse(url).hostname or "")
    for s in _load()["sites"]:
        if _bare(urlparse(s["url"]).hostname or "") == host:
            return s
    return None


def _headers_for(url, referer=None, extra=None):
    h = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "Accept-Language": "en-US,en;q=0.9"}
    s = _site_for(url)
    if s:
        if s.get("user_agent"):
            h["User-Agent"] = s["user_agent"]
        if s.get("cookie"):
            h["Cookie"] = s["cookie"]
    if referer:
        h["Referer"] = referer
    if extra:
        h.update(extra)
    return h


def _session(url):
    host = _hostport(url)
    with _lock:
        s = _sessions.get(host)
        if s is None:
            s = _sessions[host] = requests.Session()
            if len(_sessions) > 60:
                _sessions.pop(next(iter(_sessions)))
        return s


def http_get(url, headers=None, stream=False, timeout=15, hops=6):
    """GET with manual redirect handling so every hop is checked. Returns (response, final_url)."""
    cur = url
    for _ in range(hops):
        check_url(cur)
        r = _session(cur).get(cur, headers=headers or _headers_for(cur), allow_redirects=False,
                              stream=stream, timeout=timeout)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            nxt = urljoin(cur, r.headers["Location"])
            r.close()
            cur = nxt
            continue
        return r, cur
    raise ValueError("too many redirects")


def fetch_html(url, referer=None):
    """Return {url, html, status}. Raises ValueError with a readable message."""
    try:
        r, final = http_get(url, _headers_for(url, referer))
    except ValueError:
        raise
    except requests.RequestException as e:
        raise ValueError("could not reach the site (%s)" % type(e).__name__)
    try:
        raw = r.content[:MAX_PAGE]
        ctype = (r.headers.get("Content-Type") or "").lower()
        enc = r.encoding if r.encoding and "charset" in ctype else None
        try:
            html = raw.decode(enc or "utf-8")
        except Exception:
            html = raw.decode(r.apparent_encoding or "utf-8", errors="replace")
    finally:
        r.close()
    if r.status_code in (403, 429, 503) and re.search(r"just a moment|cf-chl|attention required|enable javascript and cookies",
                                                      html[:6000], re.I):
        raise ValueError("this site is protected by an anti-bot check (Cloudflare). Open it once in your browser, then paste "
                         "that browser's cookie into the site settings in Miko, or use Open in my browser.")
    if r.status_code >= 400:
        raise ValueError("the site answered with error %d" % r.status_code)
    return {"url": final, "html": html, "status": r.status_code}


# ===================================================================== text helpers
STOP = {"the", "a", "an", "of", "season", "anime", "episode", "ep", "sub", "dub", "english", "online", "watch", "free",
        "hd", "tv", "and", "to", "no", "wa", "ni", "ga", "de", "wo"}


def _tokens(s):
    s = unicodedata.normalize("NFKD", s or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return [t for t in re.findall(r"[a-z0-9]+", s) if t not in STOP]


def score_title(variants, title):
    tt = set(_tokens(title))
    best = 0.0
    for v in variants:
        vt = set(_tokens(v))
        if not vt or not tt:
            continue
        sc = len(vt & tt) / len(vt)
        if sc == 1 and len(tt) > len(vt) + 4:
            sc = 0.85                                         # long unrelated title that merely contains the words
        best = max(best, sc)
    return round(best, 2)


def slug(q):
    return re.sub(r"[^a-z0-9]+", "-", (q or "").lower()).strip("-")


def safe_name(s, default="Anime"):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", s or "")
    s = re.sub(r"\s+", " ", s).strip(" .")
    return (s[:80] or default)


def _text(el):
    return " ".join(el.get_text(" ", strip=True).split())


# ===================================================================== page parsing
def _soup(html):
    if BeautifulSoup is None:
        raise ValueError("the beautifulsoup4 package is missing. Run install_extra_packages.bat (or: pip install beautifulsoup4)")
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


IMG_ATTRS = ("data-src", "data-lazy-src", "data-original", "data-lazy", "data-cfsrc", "data-img", "src")
BAD_EXT = re.compile(r"\.(?:css|js|png|jpe?g|gif|webp|svg|ico|xml|rss|json|zip|rar|pdf|txt|woff2?|ttf)(?:\?|$)", re.I)
NAV_WORDS = {"home", "login", "log in", "register", "sign in", "sign up", "contact", "dmca", "privacy", "privacy policy",
             "terms", "terms of service", "about", "faq", "donate", "discord", "telegram", "facebook", "twitter", "instagram",
             "reddit", "rss", "next", "prev", "previous", "»", "«", "page", "menu", "search", "more", "genres", "a-z list",
             "random", "schedule", "news", "forum", "advertise", "report", "bookmark", "history"}
WEAK_TITLES = {"watch", "watch now", "play", "more", "view", "read more", "details", "info", "episode", "click here"}
AD_HINT = re.compile(r"doubleclick|googlesyndication|adservice|analytics|facebook\.com|twitter\.com|disqus|histats|"
                     r"popads|propeller|exoclick|juicyads|adsterra|recaptcha|google\.com/(?:maps|recaptcha)", re.I)

EP_TEXT = re.compile(r"\b(?:episode|episodio|épisode|folge|eps?|e)\.?[\s\-_:#]*0*(\d{1,4}(?:\.5)?)(?!\d)", re.I)
EP_JP = re.compile(r"第\s*0*(\d{1,4})\s*[話话集]")
EP_URL = re.compile(r"(?:^|[/_\-.=?&])(?:episode|ep|eps|e)[\-_/=. ]?0*(\d{1,4})(?!\d)", re.I)
EP_STRIP = re.compile(r"(?:^|[/_\-.=?&])(?:episode|ep|eps|e)[\-_/=. ]?0*\d{1,4}.*$", re.I)


def _num(x):
    f = float(x)
    return int(f) if f.is_integer() else f


def episode_number(href, text=""):
    t = text or ""
    m = EP_TEXT.search(t) or EP_JP.search(t)
    if m:
        return _num(m.group(1))
    p = urlparse(href or "")
    m = EP_URL.search((unquote(p.path) + ("?" + p.query if p.query else "")).lower())
    if m:
        return _num(m.group(1))
    return None


def _img_url(img, base):
    if img is None:
        return ""
    for a in IMG_ATTRS:
        v = (img.get(a) or "").strip()
        if v and not v.startswith("data:") and not v.endswith(("blank.gif", "placeholder.png")):
            return urljoin(base, v)
    ss = (img.get("data-srcset") or img.get("srcset") or "").strip()
    if ss:
        first = ss.split(",")[0].strip().split(" ")[0]
        if first and not first.startswith("data:"):
            return urljoin(base, first)
    return ""


def _bg_url(el, base):
    nodes = [el] + list(el.find_all(True, limit=4))
    for n in nodes:
        st = n.get("style") or ""
        m = re.search(r"url\(['\"]?([^'\")]+)", st)
        if m and not m.group(1).startswith("data:"):
            return urljoin(base, m.group(1))
        for a in ("data-bg", "data-background", "data-poster"):
            if n.get(a):
                return urljoin(base, n.get(a))
    return ""


def parse_cards(soup, base):
    items = OrderedDict()
    page_host = _bare(urlparse(base).netloc)
    basecmp = base.split("#")[0].rstrip("/")
    for a in soup.find_all("a", href=True):
        raw = a["href"].strip()
        if not raw or raw[0] == "#" or raw.lower().startswith(("javascript:", "mailto:", "tel:", "data:")):
            continue
        href = urljoin(base, raw).split("#")[0]
        if not href.startswith(("http://", "https://")) or BAD_EXT.search(urlparse(href).path):
            continue
        if href.rstrip("/") == basecmp:
            continue
        img = a.find("img")
        thumb = _img_url(img, base) or _bg_url(a, base)
        title = (a.get("title") or "").strip()
        if not title and img is not None:
            title = (img.get("alt") or img.get("title") or "").strip()
        if not title:
            h = a.find(re.compile(r"^h[1-6]$")) or a.find(class_=re.compile("title|name", re.I))
            title = _text(h) if h else ""
        if not title:
            title = _text(a)
        title = " ".join(title.split())[:160]
        if a.find_parent(["nav", "footer", "header"]) is not None and not thumb:
            continue
        low = title.lower()
        if not thumb and (len(title) < 2 or low in NAV_WORDS):
            continue
        it = items.get(href)
        if it is None:
            items[href] = {"title": title, "href": href, "thumb": thumb, "external": _bare(urlparse(href).netloc) != page_host}
        else:
            if (not it["title"] or it["title"].lower() in WEAK_TITLES) and title and low not in WEAK_TITLES:
                it["title"] = title
            if not it["thumb"] and thumb:
                it["thumb"] = thumb
    out = []
    for it in items.values():
        if not it["title"] or (it["title"].lower() in WEAK_TITLES and not it["thumb"]):
            continue
        it["ep"] = episode_number(it["href"], it["title"])
        it["kind"] = "episode" if it["ep"] is not None else "series"
        out.append(it)
    out = [x for x in out if not (x["external"] and not x["thumb"])]
    out.sort(key=lambda x: 0 if x["thumb"] else 1)           # poster cards first (stable)
    return out[:150]


def extract_episodes(soup, base):
    cands = []
    page_host = _bare(urlparse(base).netloc)
    for a in soup.find_all("a", href=True):
        raw = a["href"].strip()
        if not raw or raw[0] == "#" or raw.lower().startswith(("javascript:", "mailto:")):
            continue
        href = urljoin(base, raw).split("#")[0]
        if not href.startswith(("http://", "https://")) or BAD_EXT.search(urlparse(href).path):
            continue
        if _bare(urlparse(href).netloc) != page_host:
            continue
        if a.find_parent(["nav", "footer"]) is not None:
            continue
        text = " ".join(((a.get("title") or "") + " " + _text(a)).split())
        n = episode_number(href, text)
        if n is None:
            continue
        cands.append((n, _text(a)[:120] or ("Episode %s" % n), href))
    if len(cands) < 2:                                     # lists that only show bare numbers: 1 2 3 ...
        by_dir = {}
        for a in soup.find_all("a", href=True):
            t = _text(a)
            if re.fullmatch(r"0*\d{1,4}", t):
                href = urljoin(base, a["href"].strip()).split("#")[0]
                if href.startswith("http") and _bare(urlparse(href).netloc) == page_host:
                    by_dir.setdefault(href.rsplit("/", 1)[0], []).append((_num(t), "Episode " + t.lstrip("0"), href))
        best = max(by_dir.values(), key=len) if by_dir else []
        if len(best) >= 3:
            cands = best
    if not cands:
        return []
    groups = {}
    for n, title, href in cands:
        key = EP_STRIP.sub("", unquote(urlparse(href).path).lower()) or href
        groups.setdefault(key, []).append((n, title, href))
    best = max(groups.values(), key=len)
    if not (len(best) >= 3 or (len(best) >= 2 and len(best) >= 0.7 * len(cands))):
        return []
    seen, eps = set(), []
    for n, title, href in best:
        if n in seen:
            continue
        seen.add(n)
        eps.append({"n": n, "title": title, "url": href})
    eps.sort(key=lambda e: e["n"])
    return eps


def find_pager(soup, base):
    nxt = None
    a = soup.find("a", href=True, rel=lambda v: v and "next" in (v if isinstance(v, list) else [v]))
    if a is None:
        for x in soup.find_all("a", href=True):
            t = _text(x).lower()
            cls = " ".join(x.get("class") or []).lower()
            if t in ("next", "next »", "next page", "»", ">", ">>", "older", "next ›", "›") or re.search(r"\bnext\b", cls):
                a = x
                break
    if a is not None:
        nxt = urljoin(base, a["href"]).split("#")[0]
        if nxt.rstrip("/") == base.rstrip("/") or nxt.startswith("javascript"):
            nxt = None
    return nxt


def clean_title(t, site_name=""):
    t = " ".join((t or "").split())
    for sep in (" | ", " – ", " — ", " - ", " :: ", " » "):
        if sep in t:
            parts = t.split(sep)
            tail = " ".join(parts[1:]).lower()
            if (site_name and site_name.lower() in tail) or re.search(r"watch|online|stream|free|subbed|dubbed|anime|episode|hd", tail):
                t = parts[0]
                break
    t = re.sub(r"^\s*watch\s+", "", t, flags=re.I)
    t = re.sub(r"\s+(?:online|english\s+(?:sub|dub)(?:bed)?|free)\b.*$", "", t, flags=re.I)
    return t.strip() or "Untitled"


def _meta(soup, *names):
    for n in names:
        el = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if el and el.get("content"):
            return el["content"].strip()
    return ""


MEDIA_RE = re.compile(r"""https?://[^\s"'<>\\)\]}]+?\.(?:m3u8|mp4|webm|mkv)(?:\?[^\s"'<>\\)\]}]*)?""", re.I)
PREVIEW_RE = re.compile(r"trailer|preview|teaser|promo|sample|intro|advert|/ads?/", re.I)


def page_has_video(soup, html):
    if soup.find(["video", "source"]):
        return True
    if MEDIA_RE.search(html.replace("\\/", "/")):
        return True
    for f in soup.find_all("iframe"):
        src = f.get("src") or f.get("data-src") or ""
        if src and not AD_HINT.search(src):
            return True
    return bool(soup.find(attrs={"data-video": True}) or soup.find(attrs={"data-embed": True}))


def infer_template(url):
    """'https://x/watch/naruto-episode-12' -> ('https://x/watch/naruto-episode-{n}', 12)."""
    p = urlparse(url)
    for part in ("path", "query"):
        s = getattr(p, part)
        m = None
        for m in re.finditer(r"(?:episode|ep|eps|e)[\-_/=. ]?0*(\d{1,4})(?!\d)", s, re.I):
            pass
        if m is None and part == "path":
            for m in re.finditer(r"(\d{1,4})(?!\d)", s):
                pass
        if m:
            s2 = s[:m.start(1)] + "{n}" + s[m.end(1):]
            tpl = p._replace(**{part: s2}).geturl().replace("%7Bn%7D", "{n}")
            return tpl, int(m.group(1))
    return None, None


def parse_page(html, url, site_name=""):
    soup = _soup(html)
    title = clean_title(_meta(soup, "og:title", "twitter:title") or (soup.title.string if soup.title and soup.title.string else "")
                        or (_text(soup.find("h1")) if soup.find("h1") else ""), site_name)
    h1 = soup.find("h1")
    if h1 and _text(h1) and score_title([_text(h1)], title) < 0.4 and len(_text(h1)) < 120:
        title = clean_title(_text(h1), site_name)
    items = parse_cards(soup, url)
    episodes = extract_episodes(soup, url)
    has_video = page_has_video(soup, html)
    poster = _meta(soup, "og:image", "twitter:image")
    desc = _meta(soup, "og:description", "description")
    if not desc:
        el = soup.find(attrs={"itemprop": "description"}) or soup.find(class_=re.compile(r"synopsis|description|plot|summary", re.I))
        desc = _text(el)[:600] if el else ""
    if poster:
        poster = urljoin(url, poster)
    kind = "series" if len(episodes) >= 2 else ("episode" if has_video and episode_number(url, title) is not None
                                                else ("episode" if has_video and len(items) < 25 else "listing"))
    out = {"url": url, "title": title, "kind": kind, "items": items, "episodes": episodes, "poster": poster,
           "description": desc[:700], "next": find_pager(soup, url), "has_video": has_video}
    if kind == "episode":
        tpl, n = infer_template(url)
        out["template"], out["ep"] = tpl, n
    return out


# ===================================================================== finding a playable stream
EMBED_ATTRS = ("data-video", "data-embed", "data-src", "data-link", "data-url", "data-player", "data-iframe", "data-hls")


def _origin(u):
    p = urlparse(u)
    return "%s://%s" % (p.scheme, p.netloc)


def _kind_of(u):
    path = urlparse(u).path.lower()
    return "hls" if path.endswith(".m3u8") or ".m3u8" in path else "mp4"


def scan_media(html, base):
    """Direct media URLs mentioned anywhere in a page, best first."""
    txt = html.replace("\\/", "/").replace("&amp;", "&").replace("\\u0026", "&")
    found = []
    soup = _soup(html)
    for tag in soup.find_all(["video", "source"]):
        v = tag.get("src") or tag.get("data-src")
        if v and not v.startswith(("blob:", "data:")):
            found.append(urljoin(base, v))
    og = _meta(soup, "og:video", "og:video:url", "og:video:secure_url")
    if og:
        found.append(urljoin(base, og))
    found += [m.group(0) for m in MEDIA_RE.finditer(txt)]
    out, seen = [], set()
    for u in found:
        if u in seen or AD_HINT.search(u):
            continue
        seen.add(u)
        if re.search(r"\.(?:m3u8|mp4|webm|mkv)(?:\?|$)", urlparse(u).path + ("?" + urlparse(u).query if urlparse(u).query else ""), re.I) \
                or ".m3u8" in u or ".mp4" in u:
            out.append(u)
    out.sort(key=lambda u: (1 if PREVIEW_RE.search(u) else 0, 0 if _kind_of(u) == "mp4" else 1))
    return out


def scan_embeds(html, base):
    """Embedded players: iframes and the data-* attributes that anime sites use for server buttons."""
    soup = _soup(html)
    out, seen = [], set()

    def add(v):
        if not v or not isinstance(v, str):
            return
        v = v.strip()
        if v.startswith("//"):
            v = "https:" + v
        if not v.startswith(("http://", "https://")) and not v.startswith("/"):
            return
        u = urljoin(base, v)
        if u in seen or AD_HINT.search(u) or BAD_EXT.search(urlparse(u).path) or u.rstrip("/") == base.rstrip("/"):
            return
        seen.add(u)
        out.append(u)
    for f in soup.find_all("iframe"):
        add(f.get("src") or f.get("data-src"))
    for tag in soup.find_all(attrs=True):
        for a in EMBED_ATTRS:
            v = tag.get(a)
            if v and re.match(r"^(?:https?:)?//", str(v).strip()):
                add(v)
    for o in soup.find_all("option"):
        v = o.get("value") or ""
        if re.match(r"^(?:https?:)?//", v):
            add(v)
    return out[:8]


def _ytdlp_info(url, referer=None, timeout=50, flat=False):
    cmd = miko_downloads._ytdlp_cmd()
    if not cmd:
        return None
    args = cmd + ["--no-warnings", "--skip-download", "--socket-timeout", "15", "-J",
                  "--flat-playlist" if flat else "--no-playlist"]
    if referer:
        args += ["--referer", referer]
    args.append(url)
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=NOWIN)
        if p.returncode != 0:
            return None
        return json.loads(p.stdout)
    except Exception:
        return None


def ytdlp_streams(url, referer=None):
    info = _ytdlp_info(url, referer)
    if not info:
        return []
    if info.get("_type") == "playlist" and info.get("entries"):
        info = next((e for e in info["entries"] if e), info)
    cands = []
    fm = [f for f in (info.get("formats") or []) if f.get("url")]
    prog = [f for f in fm if str(f.get("protocol", "")).startswith("http") and "m3u8" not in str(f.get("protocol", ""))
            and f.get("vcodec") not in (None, "none") and f.get("acodec") not in (None, "none")]
    prog.sort(key=lambda f: (-(min(f.get("height") or 0, 1080)), f.get("ext") != "mp4"))
    for f in prog[:2]:
        cands.append({"url": f["url"], "kind": "mp4", "headers": f.get("http_headers") or info.get("http_headers") or {}, "via": "yt-dlp"})
    hls = [f for f in fm if "m3u8" in str(f.get("protocol", ""))]
    man = info.get("manifest_url") or (info.get("url") if ".m3u8" in str(info.get("url", "")) else "")
    if man:
        cands.append({"url": man, "kind": "hls", "headers": info.get("http_headers") or {}, "via": "yt-dlp"})
    elif hls:
        hls.sort(key=lambda f: -(f.get("height") or 0))
        cands.append({"url": hls[0]["url"], "kind": "hls", "headers": hls[0].get("http_headers") or info.get("http_headers") or {}, "via": "yt-dlp"})
    if not cands and info.get("url", "").startswith("http"):
        cands.append({"url": info["url"], "kind": _kind_of(info["url"]), "headers": info.get("http_headers") or {}, "via": "yt-dlp"})
    return cands


def _cand(u, page_url, via):
    return {"url": u, "kind": _kind_of(u), "via": via,
            "headers": {"User-Agent": UA, "Referer": page_url, "Origin": _origin(page_url)}}


def probe(c):
    """True when the candidate really answers like media (not an expired link / HTML error page)."""
    try:
        h = dict(c["headers"])
        h["Range"] = "bytes=0-2047"
        r, _ = http_get(c["url"], h, stream=True, timeout=12)
        try:
            if r.status_code >= 400:
                return False
            head = r.raw.read(2048, decode_content=True) or b""
            ctype = (r.headers.get("Content-Type") or "").lower()
        finally:
            r.close()
        if c["kind"] == "hls":
            return head.lstrip().startswith(b"#EXTM3U")
        if "text/html" in ctype or head.lstrip()[:1] == b"<":
            return False
        return True
    except Exception:
        return False


_resolve_cache = {}


def find_streams(page_url, referer=None, use_ytdlp=True):
    """Every playable stream we can find for an episode page: direct tags/URLs, then embedded players, then yt-dlp."""
    cands, notes = [], []
    deadline = time.time() + 40
    try:
        page = fetch_html(page_url, referer)
    except ValueError as e:
        return [], str(e)
    base = page["url"]
    for u in scan_media(page["html"], base):
        cands.append(_cand(urljoin(base, u), base, "page"))
    embeds = [] if len(cands) >= 2 else scan_embeds(page["html"], base)

    def look(emb, depth=1):
        found = []
        try:
            sub = fetch_html(emb, base)
        except ValueError:
            return found
        sb = sub["url"]
        for u in scan_media(sub["html"], sb):
            found.append(_cand(urljoin(sb, u), sb, "embed"))
        if not found and depth < 2:
            for e2 in scan_embeds(sub["html"], sb)[:3]:
                found += look(e2, depth + 1)
        return found
    if embeds:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for res in ex.map(look, embeds[:6]):
                cands += res
    good = []
    for c in cands:
        if time.time() > deadline or len(good) >= 3:
            break
        if probe(c):
            good.append(c)
    if not good and use_ytdlp and time.time() < deadline:
        tried = [(page_url, referer)] + [(e, base) for e in embeds[:3]]
        for u, ref in tried:
            for c in ytdlp_streams(u, ref or base):
                if probe(c):
                    good.append(c)
            if good:
                break
    if not good:
        return [], "no playable stream was found on that page"
    good.sort(key=lambda c: 0 if c["kind"] == "mp4" else 1)
    return good, ""


# ===================================================================== local stream relay (token protected)
SESSIONS = OrderedDict()                  # token -> {"headers", "urls": [..], "ts"}
_slock = threading.Lock()


def _session_new(headers, first_url):
    tok = secrets.token_urlsafe(9)
    with _slock:
        SESSIONS[tok] = {"headers": dict(headers or {}), "urls": [first_url], "ts": time.time()}
        while len(SESSIONS) > 80:
            SESSIONS.popitem(last=False)
    return tok


def _session_add(tok, url):
    with _slock:
        s = SESSIONS.get(tok)
        if not s:
            return None
        if url in s["urls"]:
            return s["urls"].index(url)
        if len(s["urls"]) > 30000:
            return None
        s["urls"].append(url)
        return len(s["urls"]) - 1


def _ext_of(url, default="bin"):
    e = os.path.splitext(urlparse(url).path)[1].lower().lstrip(".")
    return e if re.fullmatch(r"[a-z0-9]{2,5}", e or "") else default


def proxy_path(tok, idx, url):
    return "/animeproxy/%s/%d.%s" % (tok, idx, _ext_of(url))


def make_playable(c):
    tok = _session_new(c["headers"], c["url"])
    return proxy_path(tok, 0, c["url"]), tok


def image_proxy(url, referer):
    """Poster fallback for hot-link protected images. Returns a local path."""
    tok = _session_new({"User-Agent": UA, "Referer": referer, "Accept": "image/*,*/*;q=0.8"}, url)
    return "/animeproxy/%s/0.img" % tok


_URI_RE = re.compile(r'URI="([^"]+)"')


def _rewrite_playlist(text, base_url, tok):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            out.append(line)
        elif s.startswith("#"):
            def sub(m):
                u = urljoin(base_url, m.group(1))
                i = _session_add(tok, u)
                return 'URI="%s"' % (proxy_path(tok, i, u) if i is not None else m.group(1))
            out.append(_URI_RE.sub(sub, line))
        else:
            u = urljoin(base_url, s)
            i = _session_add(tok, u)
            out.append(proxy_path(tok, i, u) if i is not None else s)
    return "\n".join(out) + "\n"


def serve_proxy(handler, path, head_only=False):
    """GET /animeproxy/<token>/<index>.<ext>  - relays one registered URL with the right headers (Range supported)."""
    m = re.fullmatch(r"/animeproxy/([\w\-]{6,24})/(\d+)\.[a-z0-9]{1,5}", path or "")

    def fail(code, msg=b""):
        handler.send_response(code)
        handler.send_header("Content-Length", str(len(msg)))
        handler.end_headers()
        if msg and not head_only:
            handler.wfile.write(msg)
    if not m:
        return fail(404)
    with _slock:
        s = SESSIONS.get(m.group(1))
        idx = int(m.group(2))
        url = s["urls"][idx] if s and idx < len(s["urls"]) else None
        headers = dict(s["headers"]) if s else {}
    if not url:
        return fail(404)
    rng = handler.headers.get("Range")
    if rng and re.fullmatch(r"bytes=\d*-\d*", rng.strip()):
        headers["Range"] = rng.strip()
    else:
        headers.pop("Range", None)
    try:
        r, final = http_get(url, headers, stream=True, timeout=(10, 40))
    except Exception:
        return fail(502)
    try:
        ctype = (r.headers.get("Content-Type") or "").lower()
        is_pl = "mpegurl" in ctype or urlparse(final).path.lower().endswith(".m3u8")
        if is_pl:
            body = r.content[:3_000_000]
            if body.lstrip().startswith(b"#EXTM3U"):
                data = _rewrite_playlist(body.decode("utf-8", "replace"), final, m.group(1)).encode("utf-8")
                handler.send_response(200)
                handler.send_header("Content-Type", "application/vnd.apple.mpegurl")
                handler.send_header("Content-Length", str(len(data)))
                handler.send_header("Cache-Control", "no-store")
                handler.end_headers()
                if not head_only:
                    handler.wfile.write(data)
                return
            handler.send_response(r.status_code if r.status_code < 400 else 502)
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            if not head_only:
                handler.wfile.write(body)
            return
        code = r.status_code if r.status_code in (200, 206) else 502
        handler.send_response(code)
        ct = r.headers.get("Content-Type") or ""
        if not ct or "octet-stream" in ct or "text/html" in ct:
            ct = {"mp4": "video/mp4", "webm": "video/webm", "ts": "video/mp2t"}.get(_ext_of(final), "application/octet-stream")
        handler.send_header("Content-Type", ct)
        for k in ("Content-Length", "Content-Range", "Accept-Ranges"):
            if r.headers.get(k):
                handler.send_header(k, r.headers[k])
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        if head_only:
            return
        try:
            for chunk in r.iter_content(65536):
                if chunk:
                    handler.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, requests.RequestException):
            pass
        handler.close_connection = True
    finally:
        r.close()


# ===================================================================== anime names (AniList) - posters, titles, episode counts
_meta_cache = {}
ANILIST_Q = """query($q:String){Page(perPage:6){media(search:$q,type:ANIME,sort:SEARCH_MATCH){
id title{romaji english native} synonyms coverImage{large} episodes status format seasonYear averageScore genres
description(asHtml:false) nextAiringEpisode{episode}}}}"""


def anilist_search(q):
    key = (q or "").lower().strip()
    hit = _meta_cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    out = []
    try:
        r = requests.post("https://graphql.anilist.co", json={"query": ANILIST_Q, "variables": {"q": q}},
                          headers={"User-Agent": UA}, timeout=8)
        for m in (r.json().get("data", {}).get("Page", {}).get("media") or []):
            t = m.get("title") or {}
            out.append({"id": m["id"], "romaji": t.get("romaji") or "", "english": t.get("english") or "", "native": t.get("native") or "",
                        "title": t.get("english") or t.get("romaji") or t.get("native") or "",
                        "synonyms": (m.get("synonyms") or [])[:6], "poster": (m.get("coverImage") or {}).get("large") or "",
                        "episodes": m.get("episodes"), "status": m.get("status") or "", "format": m.get("format") or "",
                        "year": m.get("seasonYear"), "score": m.get("averageScore"), "genres": (m.get("genres") or [])[:4],
                        "description": re.sub(r"<[^>]+>", "", m.get("description") or "")[:400],
                        "next_ep": ((m.get("nextAiringEpisode") or {}).get("episode"))})
    except Exception:
        out = []
    _meta_cache[key] = (time.time(), out)
    return out


# ===================================================================== saved sites
def _norm_site_url(u):
    u = (u or "").strip()
    if not u:
        raise ValueError("type or paste a website address")
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    p = urlparse(u)
    if not p.hostname or "." not in p.hostname and p.hostname != "localhost" and not re.fullmatch(r"[\d.]+", p.hostname):
        raise ValueError("that does not look like a website address")
    return "%s://%s%s" % (p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") if p.path not in ("", "/") else "")


def _pub_site(s):
    return {"id": s["id"], "name": s.get("name", ""), "url": s["url"], "search_url": s.get("search_url", ""),
            "enabled": s.get("enabled", True), "has_cookie": bool(s.get("cookie")), "user_agent": s.get("user_agent", ""),
            "added": s.get("added", 0), "note": s.get("note", "")}


def sites_list():
    with _lock:
        return [_pub_site(s) for s in _load()["sites"]]


def site_add(url, name=""):
    url = _norm_site_url(url)
    with _lock:
        d = _load()
        host = _bare(urlparse(url).hostname)
        for s in d["sites"]:
            if _bare(urlparse(s["url"]).hostname) == host:
                raise ValueError("that website is already saved (%s)" % (s.get("name") or host))
        s = {"id": _sid(url, str(time.time())), "name": (name or "").strip()[:60] or host, "url": url, "search_url": "",
             "enabled": True, "cookie": "", "user_agent": "", "added": time.time(), "note": ""}
        d["sites"].append(s)
        _save(d)
    _refresh_trusted()
    return _pub_site(s)


def site_update(sid, body):
    with _lock:
        d = _load()
        s = next((x for x in d["sites"] if x["id"] == sid), None)
        if not s:
            raise ValueError("unknown site")
        if "name" in body and str(body["name"]).strip():
            s["name"] = str(body["name"]).strip()[:60]
        if "url" in body and str(body["url"]).strip():
            s["url"] = _norm_site_url(body["url"])
        if "search_url" in body:
            su = str(body["search_url"]).strip()
            if su and "{q}" not in su and "{slug}" not in su:
                raise ValueError("the search address must contain {q} where the anime name goes, e.g. https://site.com/?s={q}")
            s["search_url"] = su
        if "enabled" in body:
            s["enabled"] = bool(body["enabled"])
        if body.get("cookie"):
            s["cookie"] = str(body["cookie"]).strip()[:4000]
        if body.get("clear_cookie"):
            s["cookie"] = ""
        if "user_agent" in body:
            s["user_agent"] = str(body["user_agent"]).strip()[:300]
        if "note" in body:
            s["note"] = str(body["note"]).strip()[:200]
        _save(d)
    _refresh_trusted()
    return _pub_site(s)


def site_remove(sid):
    with _lock:
        d = _load()
        n = len(d["sites"])
        d["sites"] = [s for s in d["sites"] if s["id"] != sid]
        _save(d)
    _refresh_trusted()
    return len(d["sites"]) < n


def _get_site(sid):
    for s in _load()["sites"]:
        if s["id"] == sid:
            return s
    return None


def site_test(sid):
    s = _get_site(sid)
    if not s:
        raise ValueError("unknown site")
    t0 = time.time()
    page = fetch_html(s["url"])
    info = parse_page(page["html"], page["url"], s.get("name", ""))
    tpl = s.get("search_url") or discover_search(page["html"], page["url"])
    if tpl and not s.get("search_url"):
        _remember_search(sid, tpl)
    return {"ok": True, "title": info["title"], "cards": len(info["items"]), "search_url": tpl or "",
            "ms": int((time.time() - t0) * 1000)}


# ===================================================================== search
COMMON_SEARCH = ["/?s={q}", "/search?keyword={q}", "/search?q={q}", "/search/{slug}", "/search.html?keyword={q}",
                 "/?search={q}", "/filter?keyword={q}", "/search?query={q}"]
SEARCH_NAMES = ("s", "q", "keyword", "keywords", "search", "query", "title", "name", "term", "k")


def discover_search(html, base):
    """Find the site's own search form: returns a URL template containing {q}, or ''."""
    try:
        soup = _soup(html)
    except ValueError:
        return ""
    for form in soup.find_all("form"):
        if (form.get("method") or "get").lower() != "get":
            continue
        fields = [i for i in form.find_all("input") if (i.get("type") or "text").lower() in ("search", "text") and i.get("name")]
        if not fields:
            continue
        fld = sorted(fields, key=lambda i: SEARCH_NAMES.index(i["name"].lower()) if i["name"].lower() in SEARCH_NAMES else 99)[0]
        if fld["name"].lower() not in SEARCH_NAMES and (fld.get("type") or "").lower() != "search":
            continue
        action = urljoin(base, form.get("action") or base).split("#")[0].split("?")[0]
        params = [(i["name"], i.get("value", "")) for i in form.find_all("input", attrs={"type": "hidden"}) if i.get("name")]
        qs = "&".join("%s=%s" % (quote_plus(k), quote_plus(v)) for k, v in params + [(fld["name"], "{q}")])
        return action + "?" + qs.replace("%7Bq%7D", "{q}")
    return ""


def _remember_search(sid, tpl):
    with _lock:
        d = _load()
        for s in d["sites"]:
            if s["id"] == sid:
                s["search_url"] = tpl
        _save(d)


def _fill(tpl, q):
    return tpl.replace("{q}", quote_plus(q)).replace("{slug}", slug(q))


def search_site(site, variants):
    """Search one saved site for any of the title variants. Returns {ok, items, error, search_url}."""
    base = site["url"]
    tpls = []                                              # (template, trusted): trusted ones come from the user or the site's own form
    last_err, first_url = "", ""
    try:
        if site.get("search_url"):
            tpls.append((site["search_url"], True))
        else:
            home = fetch_html(base)
            found = discover_search(home["html"], home["url"])
            if found:
                tpls.append((found, True))
            tpls += [(base.rstrip("/") + c, False) for c in COMMON_SEARCH]
        for tpl, trusted in tpls[:1 if site.get("search_url") else 5]:
            for q in variants[:3]:
                url = _fill(tpl, q)
                first_url = first_url or url
                try:
                    page = fetch_html(url, base)
                    info = parse_page(page["html"], page["url"], site.get("name", ""))
                except ValueError as e:
                    last_err = str(e)
                    if "anti-bot" in last_err:
                        return {"ok": False, "error": last_err, "items": []}
                    break                                   # this template does not work on this site; try the next one
                items = [x for x in info["items"] if not x["external"]]
                for x in items:
                    x["score"] = score_title(variants, x["title"])
                good = [x for x in items if x["score"] >= 0.5]
                if good or (trusted and items):
                    if not site.get("search_url"):
                        _remember_search(site["id"], tpl)
                    items.sort(key=lambda x: -x["score"])
                    return {"ok": True, "items": items[:40], "search_url": url, "variant": q, "page_kind": info["kind"],
                            "episodes": info["episodes"] if info["kind"] == "series" else []}
        return {"ok": True, "items": [], "search_url": first_url,
                "error": last_err or "no results (or this site's search could not be detected - set its search address in Sites)"}
    except ValueError as e:
        return {"ok": False, "error": str(e), "items": []}
    except Exception as e:
        return {"ok": False, "error": "search failed: " + str(e)[:100], "items": []}


def _thumbs(items, referer):
    for it in items:
        if it.get("thumb"):
            it["thumb_p"] = image_proxy(it["thumb"], referer)
    return items


def search(q, site_ids=None, meta=True):
    q = (q or "").strip()
    if not q:
        return {"ok": False, "error": "type an anime name"}
    m = anilist_search(q) if meta else []
    variants = [q]
    if m:
        top = m[0]
        qs = set(_tokens(q))
        names = [top["english"], top["romaji"]] + top["synonyms"][:2]
        # only add alternates when the top AniList hit really is this anime (shares words with the query or one of its names)
        if score_title([q], top["english"] + " " + top["romaji"] + " " + " ".join(top["synonyms"])) >= 0.5 or \
                (len(qs) <= 3 and any(qs & set(_tokens(n)) for n in names if n)):
            for n in names[:2]:
                if n and n.lower() not in [v.lower() for v in variants]:
                    variants.append(n)
    with _lock:
        sites = [s for s in _load()["sites"] if s.get("enabled", True) and (not site_ids or s["id"] in site_ids)]
    results = []
    if sites:
        with ThreadPoolExecutor(max_workers=min(6, len(sites))) as ex:
            futs = [(s, ex.submit(search_site, s, variants)) for s in sites]
            for s, f in futs:
                try:
                    r = f.result(timeout=75)
                except Exception as e:
                    r = {"ok": False, "error": "timed out", "items": []}
                r["items"] = _thumbs(r.get("items", []), s["url"])
                r.update({"site_id": s["id"], "site": s.get("name", "")})
                results.append(r)
    return {"ok": True, "q": q, "variants": variants, "meta": m, "sites": results, "no_sites": not sites}


# ===================================================================== browsing / series
def _lib_find(d, url=None, sid=None):
    for e in d["library"]:
        if (sid and e["id"] == sid) or (url and e.get("url") == url):
            return e
    return None


def open_page(url, site_id=None):
    s = _get_site(site_id) if site_id else _site_for(url)
    page = fetch_html(url)
    info = parse_page(page["html"], page["url"], (s or {}).get("name", ""))
    info["site_id"] = (s or {}).get("id")
    info["site"] = (s or {}).get("name", "")
    if info["kind"] == "series" or info["episodes"]:
        d = _load()
        e = _lib_find(d, url=info["url"])
        info["library_id"] = e["id"] if e else None
        info["episodes"] = _mark_episodes(info["episodes"], e)
    if info["kind"] == "listing":
        _thumbs(info["items"], info["url"])
    if info.get("poster"):
        info["poster_p"] = image_proxy(info["poster"], info["url"])
    if info["kind"] == "series" and not info["episodes"]:
        info["episodes"] = []
    return info


def _mark_episodes(eps, entry):
    out = []
    for e in eps:
        e = dict(e)
        if entry:
            k = str(e["n"])
            e["watched"] = bool(entry.get("watched", {}).get(k))
            e["pos"] = (entry.get("progress", {}).get(k) or {}).get("pos", 0)
            e["dur"] = (entry.get("progress", {}).get(k) or {}).get("dur", 0)
            p = (entry.get("files") or {}).get(k)
            e["path"] = p if p and os.path.exists(p) else ""
        out.append(e)
    return out


def episodes_from_template(tpl, start, end):
    if "{n}" not in (tpl or ""):
        raise ValueError("the address must contain {n} where the episode number goes")
    start, end = int(start), int(end)
    if start < 1 or end < start or end - start > 400:
        raise ValueError("choose a sensible range (up to 400 episodes)")
    return [{"n": n, "title": "Episode %d" % n, "url": tpl.replace("{n}", str(n))} for n in range(start, end + 1)]


def ytdlp_episode_list(url):
    info = _ytdlp_info(url, flat=True, timeout=60)
    if not info or not info.get("entries"):
        return []
    eps = []
    for i, e in enumerate([x for x in info["entries"] if x], 1):
        u = e.get("url") or e.get("webpage_url") or ""
        if u.startswith("http"):
            n = episode_number(u, e.get("title") or "") or i
            eps.append({"n": n, "title": (e.get("title") or "Episode %s" % n)[:120], "url": u})
    return eps


# ===================================================================== library
def library_list():
    with _lock:
        d = _load()
    out = []
    for e in d["library"]:
        eps = e.get("episodes", [])
        watched = e.get("watched", {})
        nxt = next((x for x in eps if not watched.get(str(x["n"]))), None)
        out.append({"id": e["id"], "title": e["title"], "poster": e.get("poster", ""), "url": e.get("url", ""), "site": e.get("site", ""),
                    "site_id": e.get("site_id", ""), "total": len(eps), "watched": sum(1 for v in watched.values() if v),
                    "downloaded": sum(1 for p in (e.get("files") or {}).values() if p and os.path.exists(p)),
                    "next": nxt, "last_ep": e.get("last_ep"), "updated": e.get("updated", 0), "anilist": e.get("anilist")})
    out.sort(key=lambda x: -x["updated"])
    return out


def library_get(lid):
    d = _load()
    e = _lib_find(d, sid=lid)
    if not e:
        return None
    r = dict(e)
    r["episodes"] = _mark_episodes(e.get("episodes", []), e)
    return r


def library_save(body):
    url = str(body.get("url") or "").strip()
    title = str(body.get("title") or "").strip()
    if not url or not title:
        raise ValueError("missing title or link")
    with _lock:
        d = _load()
        e = _lib_find(d, url=url)
        if not e:
            e = {"id": _sid("lib", url), "title": title[:120], "url": url, "added": time.time(), "episodes": [], "watched": {},
                 "progress": {}, "files": {}}
            d["library"].append(e)
        e["title"] = title[:120] or e["title"]
        for k in ("poster", "site", "site_id", "anilist", "description"):
            if body.get(k):
                e[k] = body[k]
        eps = body.get("episodes")
        if isinstance(eps, list) and eps:
            keep = {str(x["n"]): x for x in e.get("episodes", [])}
            for x in eps:
                if isinstance(x, dict) and x.get("url"):
                    keep[str(x["n"])] = {"n": x["n"], "title": str(x.get("title", ""))[:120], "url": x["url"]}
            e["episodes"] = sorted(keep.values(), key=lambda x: x["n"])
        e["updated"] = time.time()
        _save(d)
        return e["id"]


def library_remove(lid):
    with _lock:
        d = _load()
        n = len(d["library"])
        d["library"] = [e for e in d["library"] if e["id"] != lid]
        _save(d)
        return len(d["library"]) < n


def library_refresh(lid):
    d = _load()
    e = _lib_find(d, sid=lid)
    if not e:
        raise ValueError("not in your library")
    info = open_page(e["url"], e.get("site_id"))
    eps = info["episodes"] or ytdlp_episode_list(e["url"])
    before = len(e.get("episodes", []))
    library_save({"url": e["url"], "title": e["title"], "episodes": eps})
    after = len(library_get(lid)["episodes"])
    return {"added": max(0, after - before), "total": after}


def progress_set(lid, n, pos=None, dur=None, watched=None):
    with _lock:
        d = _load()
        e = _lib_find(d, sid=lid)
        if not e:
            return False
        k = str(n)
        if pos is not None:
            e.setdefault("progress", {})[k] = {"pos": round(float(pos), 1), "dur": round(float(dur or 0), 1), "ts": time.time()}
            if dur and pos and float(pos) >= 0.9 * float(dur):
                e.setdefault("watched", {})[k] = True
        if watched is not None:
            e.setdefault("watched", {})[k] = bool(watched)
        e["last_ep"] = n
        e["updated"] = time.time()
        _save(d)
    return True


def _note_file(series_url, n, path):
    with _lock:
        d = _load()
        e = _lib_find(d, url=series_url)
        if e:
            e.setdefault("files", {})[str(n)] = path
            e["updated"] = time.time()
            _save(d)


# ===================================================================== resolve for the player
def resolve(url, index=0, force=False):
    now = time.time()
    hit = _resolve_cache.get(url)
    if hit and now - hit["ts"] < 600 and not force:
        cands, err = hit["cands"], hit["err"]
    else:
        cands, err = find_streams(url)
        _resolve_cache[url] = {"ts": now, "cands": cands, "err": err}
        if len(_resolve_cache) > 100:
            _resolve_cache.pop(next(iter(_resolve_cache)))
    if not cands:
        return {"ok": False, "error": err or "no playable stream was found", "needs_ytdlp": miko_downloads._ytdlp_cmd() is None}
    c = cands[index % len(cands)]
    path, _tok = make_playable(c)
    return {"ok": True, "url": path, "hls": c["kind"] == "hls", "via": c["via"], "count": len(cands), "index": index % len(cands)}


# ===================================================================== downloads (through Miko's own download manager)
_dq = queue.Queue()
_workers = []
_wlock = threading.Lock()


def parse_range(spec, available):
    """'1-12', '3', '1,4,6-8', 'all', 'latest', 'next', 'last 3' -> list of episode numbers that exist in `available`."""
    nums = sorted({e["n"] for e in available})
    spec = (spec or "").strip().lower()
    if not nums:
        return []
    if spec in ("", "all", "everything"):
        return nums
    if spec in ("latest", "newest", "last"):
        return [nums[-1]]
    if spec in ("first",):
        return [nums[0]]
    m = re.fullmatch(r"last\s+(\d+)", spec)
    if m:
        return nums[-int(m.group(1)):]
    out = set()
    for part in re.split(r"[,\s]+", spec):
        m = re.fullmatch(r"(\d+)\s*(?:-|to|\.\.)\s*(\d+)", part)
        if m:
            a, b = sorted((int(m.group(1)), int(m.group(2))))
            out.update(n for n in nums if a <= n <= b)
        elif re.fullmatch(r"\d+", part):
            out.update(n for n in nums if n == int(part))
    return sorted(out)


def _http_download(jid, cand, dest_noext):
    h = dict(cand["headers"])
    r, final = http_get(cand["url"], h, stream=True, timeout=(10, 40))
    try:
        if r.status_code >= 400:
            raise ValueError("the server refused the download (%d)" % r.status_code)
        ext = _ext_of(final, "mp4")
        ext = ext if ext in ("mp4", "webm", "mkv", "m4v", "mov") else "mp4"
        path = dest_noext + "." + ext
        total = int(r.headers.get("Content-Length") or 0)
        miko_downloads._set(jid, total=total)
        got = lastgot = 0
        last = time.time()
        with open(path + ".part", "wb") as f:
            for chunk in r.iter_content(131072):
                if miko_downloads.JOBS[jid]["cancel"]:
                    f.close()
                    os.remove(path + ".part")
                    return None
                f.write(chunk)
                got += len(chunk)
                now = time.time()
                if now - last >= 0.7:
                    sp = (got - lastgot) / (now - last)
                    old = miko_downloads.JOBS[jid]["speed"]
                    miko_downloads._set(jid, speed=(0.6 * old + 0.4 * sp) if old else sp, got=got,
                                        progress=int(got * 100 / total) if total else 0)
                    last, lastgot = now, got
        os.replace(path + ".part", path)
        miko_downloads._set(jid, got=got, total=got)
        return path
    finally:
        r.close()


def _ytdlp_download(jid, url, dest_noext, headers=None, referer=None):
    cmd = miko_downloads._ytdlp_cmd()
    if not cmd:
        raise ValueError("yt-dlp is not installed. Run install_extra_packages.bat (or: pip install yt-dlp)")
    args = cmd + ["--no-playlist", "--newline", "--concurrent-fragments", "3", "--no-warnings",
                  "-o", dest_noext + ".%(ext)s", "--print", "after_move:filepath",
                  "-f", "bv*[height<=1080]+ba/b[height<=1080]/b"]
    if shutil.which("ffmpeg"):
        args += ["--merge-output-format", "mp4", "--remux-video", "mp4"]
    for k, v in (headers or {}).items():
        if k.lower() in ("referer", "origin", "user-agent", "cookie"):
            args += ["--add-header", "%s:%s" % (k, v)]
    if referer and not (headers or {}).get("Referer"):
        args += ["--referer", referer]
    args.append(url)
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=NOWIN)
    last = ""
    for line in p.stdout:
        line = line.strip()
        m = re.search(r"\[download\]\s+([\d.]+)%\s+of\s+~?\s*([\d.]+)\s*(\w+)(?:\s+at\s+([\d.]+)\s*(\w+)/s)?(?:\s+ETA\s+([\d:]+))?", line)
        if m:
            upd = {"progress": int(float(m.group(1))), "total": int(miko_downloads._bytes(m.group(2), m.group(3)))}
            if m.group(4):
                upd["speed"] = miko_downloads._bytes(m.group(4), m.group(5))
            if m.group(6):
                upd["eta"] = m.group(6)
            upd["got"] = int(upd["total"] * upd["progress"] / 100)
            miko_downloads._set(jid, **upd)
        elif line and os.path.exists(line):
            last = line
        if miko_downloads.JOBS[jid]["cancel"]:
            p.terminate()
            return None
    p.wait()
    if p.returncode != 0 or not last:
        raise ValueError("yt-dlp could not download this episode")
    return last


def _hls_parse(url, headers, _depth=0):
    """Read an .m3u8 (master or media playlist) -> {segs: [(url, seconds)], duration, encrypted, fmp4, separate_audio}."""
    r, final = http_get(url, headers, timeout=20)
    try:
        if r.status_code >= 400:
            raise ValueError("the playlist was refused (%d)" % r.status_code)
        text = r.text
    finally:
        r.close()
    if "#EXTM3U" not in text[:200]:
        raise ValueError("not a playlist")
    lines = [l.strip() for l in text.splitlines()]
    if any(l.startswith("#EXT-X-STREAM-INF") for l in lines) and _depth < 2:
        best, bscore = None, None
        for i, l in enumerate(lines):
            if l.startswith("#EXT-X-STREAM-INF"):
                bw = re.search(r"BANDWIDTH=(\d+)", l)
                rs = re.search(r"RESOLUTION=\d+x(\d+)", l)
                score = ((int(rs.group(1)) <= 1080) if rs else True, int(bw.group(1)) if bw else 0)
                nxt = next((x for x in lines[i + 1:] if x and not x.startswith("#")), None)
                if nxt and (bscore is None or score > bscore):
                    best, bscore = urljoin(final, nxt), score
        info = _hls_parse(best, headers, _depth + 1) if best else None
        if info is None:
            raise ValueError("empty playlist")
        info["separate_audio"] = any(l.startswith("#EXT-X-MEDIA") and "TYPE=AUDIO" in l and "URI=" in l for l in lines)
        return info
    segs, enc, fmp4, pend = [], False, False, None
    for l in lines:
        if l.startswith("#EXT-X-KEY") and "METHOD=NONE" not in l:
            enc = True
        elif l.startswith("#EXT-X-MAP"):
            fmp4 = True
        elif l.startswith("#EXTINF"):
            m = re.match(r"#EXTINF:([\d.]+)", l)
            pend = float(m.group(1)) if m else 0.0
        elif l and not l.startswith("#") and pend is not None:
            segs.append((urljoin(final, l), pend))
            pend = None
    if not segs:
        raise ValueError("the playlist has no video parts")
    return {"segs": segs, "duration": sum(d for _, d in segs), "encrypted": enc, "fmp4": fmp4, "separate_audio": False}


def _ffmpeg():
    return shutil.which("ffmpeg")


def _remux_mp4(src, dst):
    p = subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-i", src, "-c", "copy", "-bsf:a", "aac_adtstoasc", dst],
                       capture_output=True, timeout=1800, creationflags=NOWIN)
    return p.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0


def _hls_native(jid, url, headers, dest_noext):
    """Download the HLS parts ourselves (4 at a time, in order). MP4 when ffmpeg is installed, otherwise .ts."""
    info = _hls_parse(url, headers)
    if info["encrypted"] or info["fmp4"] or info["separate_audio"]:
        raise NotImplementedError("this stream needs yt-dlp or ffmpeg")
    segs = info["segs"]
    ts = dest_noext + ".ts.part"
    done = 0
    last = time.time()
    lastdone = 0
    got = 0

    def grab(seg):
        for attempt in range(3):
            try:
                r, _ = http_get(seg[0], headers, stream=True, timeout=(10, 40))
                try:
                    if r.status_code >= 400:
                        raise ValueError("part refused (%d)" % r.status_code)
                    return r.content
                finally:
                    r.close()
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1 + attempt)
    with open(ts, "wb") as f, ThreadPoolExecutor(max_workers=4) as ex:
        for start in range(0, len(segs), 16):
            if miko_downloads.JOBS[jid]["cancel"]:
                f.close()
                os.remove(ts)
                return None
            for data in ex.map(grab, segs[start:start + 16]):
                f.write(data)
                got += len(data)
                done += 1
            now = time.time()
            if now > last:
                miko_downloads._set(jid, speed=(got - lastdone) / (now - last))
                last, lastdone = now, got
            miko_downloads._set(jid, progress=int(done * 100 / len(segs)), got=got,
                                total=int(got * len(segs) / max(1, done)))
    if _ffmpeg():
        mp4 = dest_noext + ".mp4"
        if _remux_mp4(ts, mp4):
            os.remove(ts)
            return mp4
    final = dest_noext + ".ts"
    os.replace(ts, final)
    return final


def _ffmpeg_direct(jid, url, headers, dest_noext):
    if not _ffmpeg():
        raise ValueError("ffmpeg is not installed")
    hdr = "".join("%s: %s\r\n" % (k, v) for k, v in headers.items() if k.lower() in ("referer", "origin", "user-agent", "cookie"))
    out = dest_noext + ".mp4"
    p = subprocess.Popen([_ffmpeg(), "-y", "-loglevel", "error", "-headers", hdr, "-i", url, "-c", "copy",
                          "-bsf:a", "aac_adtstoasc", out], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NOWIN)
    while p.poll() is None:
        if miko_downloads.JOBS[jid]["cancel"]:
            p.terminate()
            return None
        time.sleep(0.5)
    if p.returncode != 0 or not os.path.exists(out):
        raise ValueError("ffmpeg could not download this episode")
    return out


def _hls_download(jid, c, dest_noext):
    errs = []
    for how in ("native", "yt-dlp", "ffmpeg"):
        try:
            if how == "native":
                return _hls_native(jid, c["url"], c["headers"], dest_noext)
            if how == "yt-dlp" and miko_downloads._ytdlp_cmd():
                return _ytdlp_download(jid, c["url"], dest_noext, c["headers"])
            if how == "ffmpeg" and _ffmpeg():
                return _ffmpeg_direct(jid, c["url"], c["headers"], dest_noext)
        except Exception as e:
            errs.append(str(e)[:100])
            if miko_downloads.JOBS[jid]["cancel"]:
                return None
    raise ValueError(errs[-1] if errs else "this stream could not be downloaded")


def _run_episode(task):
    jid = task["jid"]
    J = miko_downloads.JOBS
    if J[jid]["cancel"]:
        return miko_downloads._set(jid, status="cancelled")
    miko_downloads._set(jid, status="downloading", progress=0)
    dest_noext = task["dest"]
    try:
        os.makedirs(os.path.dirname(dest_noext), exist_ok=True)
        for ext in (".mp4", ".webm", ".mkv", ".m4v"):               # already have it? skip
            if os.path.exists(dest_noext + ext) and os.path.getsize(dest_noext + ext) > 100_000:
                miko_downloads._set(jid, status="done", progress=100, path=dest_noext + ext)
                miko_downloads._after_done(jid, "video", task["url"], task["title"])
                _note_file(task["series_url"], task["n"], dest_noext + ext)
                return
        cands, err = find_streams(task["url"], use_ytdlp=False)
        path = None
        errs = []
        for c in cands:
            try:
                path = _http_download(jid, c, dest_noext) if c["kind"] == "mp4" else _hls_download(jid, c, dest_noext)
                if path or J[jid]["cancel"]:
                    break
            except Exception as e:
                errs.append(str(e)[:100])
        if not path and not J[jid]["cancel"]:
            try:                                                    # last resort: let yt-dlp work the page out
                path = _ytdlp_download(jid, task["url"], dest_noext, referer=task["url"])
            except Exception as e:
                errs.append(str(e)[:100])
        if J[jid]["cancel"]:
            return miko_downloads._set(jid, status="cancelled", speed=0.0)
        if not path:
            raise ValueError((errs[-1] if errs else "no downloadable stream was found for this episode"))
        miko_downloads._set(jid, status="done", progress=100, path=path, speed=0.0, eta="")
        miko_downloads._after_done(jid, "video", task["url"], task["title"])
        _note_file(task["series_url"], task["n"], path)
    except Exception as e:
        miko_downloads._set(jid, status="error", error=str(e)[:160], speed=0.0)


def _worker():
    while True:
        task = _dq.get()
        try:
            with miko_downloads._slots:
                _run_episode(task)
        except Exception as e:
            try:
                miko_downloads._set(task["jid"], status="error", error=str(e)[:160])
            except Exception:
                pass
        finally:
            _dq.task_done()


def _ensure_workers():
    with _wlock:
        while len(_workers) < miko_downloads.MAX_PARALLEL:
            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            _workers.append(t)


def download_episodes(series_title, series_url, episodes, meta=None):
    """Queue episodes (list of {n,title,url}) into Miko's download manager. Returns the job ids."""
    if not episodes:
        raise ValueError("no episodes selected")
    if len(episodes) > 400:
        raise ValueError("that is too many episodes at once (limit 400)")
    for e in episodes:
        check_url(e["url"])
    meta = meta or {}
    library_save({"url": series_url, "title": series_title, "poster": meta.get("poster", ""), "site": meta.get("site", ""),
                  "site_id": meta.get("site_id", ""), "episodes": episodes})
    folder = os.path.join(miko_downloads.DOWNLOAD_DIR, "Anime", safe_name(series_title))
    gid = _sid("grp", series_url, str(time.time()))
    ids = []
    for e in sorted(episodes, key=lambda x: x["n"]):
        n = e["n"]
        label = "E%02d" % n if isinstance(n, int) else "E%s" % n
        title = "%s - %s" % (series_title, label)
        jid = miko_downloads._new_job("video", title, e["url"])
        miko_downloads._set(jid, group=gid, anime=series_title, ep=n)
        _dq.put({"jid": jid, "url": e["url"], "title": title, "n": n, "series_url": series_url,
                 "dest": os.path.join(folder, safe_name("%s - %s" % (series_title, label)))})
        ids.append(jid)
    _ensure_workers()
    return ids


def anime_jobs():
    return [j for j in miko_downloads.list_jobs() if j.get("anime")]


# ===================================================================== Miko chat / voice commands
PENDING = []
_NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
         "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}


def push_pending(act):
    PENDING.append(act)
    del PENDING[:-20]


def pop_pending():
    out = list(PENDING)
    del PENDING[:]
    return out


def _wordnum(w):
    parts = w.split("-")
    return str(_NUMW[parts[0]] + (_NUMW.get(parts[1], 0) if len(parts) > 1 else 0))


_NW = r"(?:%s)(?:-(?:%s))?" % ("|".join(_NUMW), "|".join(k for k, v in _NUMW.items() if v < 10))


def _numwords(t):
    """'episode twelve' -> 'episode 12', '1 to twelve' -> '1 to 12'. Number words elsewhere ('one piece') stay as they are."""
    t = re.sub(r"\b((?:episodes?|eps?)\s+)(%s)\b" % _NW, lambda m: m.group(1) + _wordnum(m.group(2)), t)
    t = re.sub(r"\b(\d+\s*(?:to|through|thru|until|and|-)\s*)(%s)\b" % _NW, lambda m: m.group(1) + _wordnum(m.group(2)), t)
    return t


def parse_command(text):
    """Natural-language anime commands for Miko's chat and voice assistant. Returns {reply, act} or None."""
    raw = (text or "").strip()
    low = _numwords(raw.lower()).strip(" .!?")
    if not low:
        return None
    has_anime = bool(re.search(r"\banime\b", low))
    has_ep = bool(re.search(r"\b(?:episodes?|eps?)\b", low))

    if re.search(r"\b(?:open|show|go to|take me to|switch to)\b.*\banime(?: room)?\b", low) and not has_ep and len(low.split()) <= 6:
        return {"reply": "Opening the Anime Room.", "act": {"do": "open"}}
    if re.fullmatch(r"(?:yes[, ]*)?(?:please )?(?:confirm|start|go ahead(?: and)?|begin)(?: with)?(?: the| that| those)? downloads?", low):
        return {"reply": "Starting the download.", "act": {"do": "confirm"}}
    if re.search(r"\b(?:continue|resume)\b.*\b(?:watching|anime)\b|\bcontinue watching\b|\bwhat should i watch next\b", low) and (has_anime or "continue watching" in low):
        return {"reply": "Picking up where you left off.", "act": {"do": "continue"}}
    m = re.search(r"\b(?:add|save)\b.*?\b(?:anime )?(?:site|website|page|source)\b.*?(https?://\S+|(?:[a-z0-9-]+\.)+[a-z]{2,}\S*)", raw, re.I)
    if m and (has_anime or "site" in low or "website" in low):
        url = m.group(1).strip(".,;")
        return {"reply": "Okay, I'll add that website to your Anime Room.", "act": {"do": "add_site", "url": url}}

    if not (has_anime or has_ep):
        return None

    # ---- episode selection phrases
    rng = None
    m = re.search(r"\b(?:episodes?|eps?)\s*(\d+)\s*(?:to|through|thru|until|-|and)\s*(\d+)", low)
    if m:
        rng = "%s-%s" % (m.group(1), m.group(2))
    m2 = re.search(r"\b(?:episodes?|eps?)\s*(\d+)\b", low)
    if not rng and m2:
        rng = m2.group(1)
    if not rng:
        if re.search(r"\b(?:all|every|entire|whole)\b.*\bepisodes?\b|\ball of\b", low):
            rng = "all"
        elif re.search(r"\b(?:latest|newest|last|most recent)\s+episode\b", low):
            rng = "latest"
        elif re.search(r"\bfirst episode\b", low):
            rng = "1"
        elif re.search(r"\bnext episode\b", low):
            rng = "next"
        else:
            m3 = re.search(r"\blast (\d+) episodes\b", low)
            if m3:
                rng = "last " + m3.group(1)

    name = low
    name = re.sub(r"\b(?:episodes?|eps?)\s*\d+\s*(?:to|through|thru|until|-|and)\s*\d+", " ", name)
    name = re.sub(r"\b(?:episodes?|eps?)\s*\d+\b", " ", name)
    name = re.sub(r"\b(?:all|every|entire|whole)(?: of)?(?: the)?\s*(?:episodes?)?\b|\b(?:latest|newest|most recent|first|next)\s+episode\b|\blast \d+ episodes\b|\blast episode\b", " ", name)
    name = re.sub(r"\b(?:please|miko|hey|can you|could you|would you|for me|i want to|i wanna|i'd like to|let's|lets)\b", " ", name)
    name = re.sub(r"\b(?:in|on|from|at)\s+(?:the\s+)?anime(?:\s+room)?\b", " ", name)
    verb = None
    m = re.match(r"\s*(?:and\s+)?(?:then\s+)?(download|grab|save|watch|play|stream|find|search(?:\s+for)?|look\s+(?:up|for)|continue|resume)\b", name)
    if m:
        verb = m.group(1).split()[0]
        name = name[m.end():]
    name = re.sub(r"\b(?:the\s+)?anime\b|\bseries\b|\bshow\b|\bepisodes?\b|\bof\b|\bfor\b", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" ,.-")
    if not verb:
        verb = "download" if re.search(r"\bdownload\b", low) else "watch" if re.search(r"\b(?:watch|play|stream)\b", low) \
            else "find" if re.search(r"\b(?:find|search|look)\b", low) else None
    if not verb or not name:
        return None
    if verb in ("download", "grab", "save"):
        what = ("episodes " + rng) if rng and rng not in ("all", "latest", "next") and "-" in rng else \
            ("episode " + rng if rng and rng.isdigit() else ("all episodes" if rng == "all" else "the latest episode" if rng == "latest" else "the episodes"))
        return {"reply": "Okay, I'll find %s and set up %s. Press Download in the Anime Room, or say confirm download." % (name.title(), what),
                "act": {"do": "download", "q": name, "range": rng or "all"}}
    if verb in ("watch", "play", "stream", "continue", "resume"):
        return {"reply": "Okay, getting %s%s ready to watch." % (name.title(), (" episode " + rng) if rng and rng.isdigit() else ""),
                "act": {"do": "watch", "q": name, "ep": rng or "1"}}
    return {"reply": "Okay, looking for %s in your Anime Room." % name.title(), "act": {"do": "search", "q": name}}


def command(text):
    """Used by miko_chat: returns (reply, action_dict) or None. Also queues the action for the Anime Room screen."""
    r = parse_command(text)
    if not r:
        return None
    act = dict(r["act"])
    act["action"] = "anime"
    push_pending(act)
    return r["reply"], act


# ===================================================================== API endpoints (registered by miko_server as anime/<name>)
def _guard(fn):
    def run(body):
        try:
            return fn(body or {})
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        except requests.RequestException as e:
            return {"ok": False, "error": "network problem (%s)" % type(e).__name__}
    return run


def _state(b):
    return {"ok": True, "sites": sites_list(), "library": library_list(), "jobs": anime_jobs(),
            "ytdlp": miko_downloads.ytdlp_available(), "ffmpeg": bool(shutil.which("ffmpeg")), "bs4": BeautifulSoup is not None,
            "folder": os.path.join(miko_downloads.DOWNLOAD_DIR, "Anime")}


def _frameable(b):
    url = str(b.get("url", ""))
    r, final = http_get(url, _headers_for(url), stream=True, timeout=10)
    try:
        xfo = (r.headers.get("X-Frame-Options") or "").lower()
        csp = (r.headers.get("Content-Security-Policy") or "").lower()
    finally:
        r.close()
    blocked = bool(xfo and xfo != "allowall") or ("frame-ancestors" in csp and not re.search(r"frame-ancestors[^;]*\*", csp))
    return {"ok": True, "frameable": not blocked, "url": final}


def _dl_api(b):
    title = str(b.get("title") or "Anime").strip()
    url = str(b.get("url") or "").strip()
    eps = [e for e in (b.get("episodes") or []) if isinstance(e, dict) and e.get("url")]
    if not url:
        raise ValueError("missing series link")
    meta = {"poster": b.get("poster", ""), "site": b.get("site", ""), "site_id": b.get("site_id", "")}
    if eps:
        library_save({"url": url, "title": title, "episodes": eps, **meta})      # remember the whole episode list, not just the range
    if b.get("range"):
        want = set(parse_range(str(b["range"]), eps))
        eps = [e for e in eps if e["n"] in want]
    ids = download_episodes(title, url, eps, meta)
    return {"ok": True, "ids": ids, "count": len(ids)}


ENDPOINTS = {
    "state": _guard(_state),
    "sites/add": _guard(lambda b: {"ok": True, "site": site_add(b.get("url", ""), b.get("name", ""))}),
    "sites/update": _guard(lambda b: {"ok": True, "site": site_update(str(b.get("id", "")), b)}),
    "sites/remove": _guard(lambda b: {"ok": site_remove(str(b.get("id", "")))}),
    "sites/test": _guard(lambda b: site_test(str(b.get("id", "")))),
    "search": _guard(lambda b: search(b.get("q", ""), b.get("sites") or None, b.get("meta", True))),
    "page": _guard(lambda b: {"ok": True, **open_page(str(b.get("url", "")), b.get("site_id"))}),
    "frameable": _guard(_frameable),
    "episodes/template": _guard(lambda b: {"ok": True, "episodes": episodes_from_template(b.get("template", ""), b.get("start", 1), b.get("end", 12))}),
    "episodes/ytdlp": _guard(lambda b: {"ok": True, "episodes": ytdlp_episode_list(str(b.get("url", "")))}),
    "resolve": _guard(lambda b: resolve(str(b.get("url", "")), int(b.get("index", 0)), bool(b.get("force")))),
    "download": _guard(_dl_api),
    "library/list": _guard(lambda b: {"ok": True, "library": library_list()}),
    "library/get": _guard(lambda b: {"ok": True, "entry": library_get(str(b.get("id", "")))}),
    "library/save": _guard(lambda b: {"ok": True, "id": library_save(b)}),
    "library/remove": _guard(lambda b: {"ok": library_remove(str(b.get("id", "")))}),
    "library/refresh": _guard(lambda b: {"ok": True, **library_refresh(str(b.get("id", "")))}),
    "progress": _guard(lambda b: {"ok": progress_set(str(b.get("id", "")), b.get("n"), b.get("pos"), b.get("dur"), b.get("watched"))}),
    "pending": _guard(lambda b: {"ok": True, "actions": pop_pending()}),
    "parse": _guard(lambda b: {"ok": True, "result": parse_command(b.get("text", ""))}),
}

_refresh_trusted()
