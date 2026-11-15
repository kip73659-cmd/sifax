"""Search backend for Miko Stitch (piece 3).
Web: your existing Tavily key (tavily_key.txt).  Images: ddgs, exactly as search_window.py does.
News: ddgs news.  Videos: ddgs videos.  Every call fails soft and returns an error message
instead of crashing the app."""
import os, json, time, requests

BASE = os.path.dirname(os.path.abspath(__file__))
_cache = {}
CACHE_SECONDS = 600

def _cached(key, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val

def _key():
    for p in (os.path.join(BASE, "tavily_key.txt"),):
        if os.path.exists(p):
            k = open(p, encoding="utf-8").read().strip()
            if k:
                return k
    raise ValueError("tavily_key.txt is missing or empty")

def web(q, n=8):
    def run():
        r = requests.post("https://api.tavily.com/search",
                          json={"api_key": _key(), "query": q, "max_results": n}, timeout=25)
        r.raise_for_status()
        return [{"title": x.get("title", ""), "body": x.get("content", ""),
                 "href": x.get("url", "")} for x in r.json().get("results", [])]
    return _cached(("web", q, n), run)

def images(q, n=24):
    def run():
        from ddgs import DDGS
        out = []
        for x in DDGS().images(q, max_results=n):
            out.append({"title": x.get("title", ""), "image": x.get("image", ""),
                        "thumb": x.get("thumbnail", ""), "href": x.get("url", ""),
                        "source": x.get("source", ""), "w": x.get("width"), "h": x.get("height")})
        return out
    return _cached(("img", q, n), run)

def news(q, n=12):
    def run():
        from ddgs import DDGS
        return [{"title": x.get("title", ""), "body": x.get("body", ""), "href": x.get("url", ""),
                 "source": x.get("source", ""), "date": x.get("date", ""), "image": x.get("image", "")}
                for x in DDGS().news(q, max_results=n)]
    return _cached(("news", q, n), run)

def videos(q, n=12):
    def run():
        from ddgs import DDGS
        return [{"title": x.get("title", ""), "href": x.get("content", ""), "thumb": (x.get("images") or {}).get("medium", ""),
                 "duration": x.get("duration", ""), "publisher": x.get("publisher", ""),
                 "uploader": x.get("uploader", ""), "published": x.get("published", "")}
                for x in DDGS().videos(q, max_results=n)]
    return _cached(("vid", q, n), run)

def run_search(kind, q, n=None):
    fn = {"web": web, "images": images, "news": news, "videos": videos}.get(kind)
    if not fn:
        return {"ok": False, "error": "unknown search type"}
    try:
        return {"ok": True, "kind": kind, "query": q, "results": fn(q, n) if n else fn(q)}
    except Exception as e:
        return {"ok": False, "kind": kind, "query": q, "results": [],
                "error": "%s search failed: %s" % (kind, str(e)[:160])}


def page_info(url):
    """Fetch a web page and return its title plus the first chunk of readable text."""
    from html.parser import HTMLParser
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError("only http(s) links are supported")
    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
    r.raise_for_status()
    raw = b""
    for chunk in r.iter_content(65536):
        raw += chunk
        if len(raw) > 1_500_000:
            break
    enc = r.encoding or "utf-8"
    html = raw.decode(enc, errors="replace")

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.skip = 0; self.in_title = False; self.title = ""; self.parts = []
        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "noscript", "svg", "nav", "footer", "header"): self.skip += 1
            if tag == "title": self.in_title = True
        def handle_endtag(self, tag):
            if tag in ("script", "style", "noscript", "svg", "nav", "footer", "header") and self.skip: self.skip -= 1
            if tag == "title": self.in_title = False
        def handle_data(self, d):
            if self.in_title: self.title += d
            elif not self.skip and d.strip(): self.parts.append(d.strip())
    p = P(); p.feed(html)
    text = " ".join(p.parts)
    text = " ".join(text.split())
    return {"title": (p.title or url).strip()[:200], "text": text[:1500], "url": url}
