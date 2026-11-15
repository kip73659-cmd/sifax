"""Tiny JSON store for Miko's research collection and saved news (piece 5).
type 'research' = items added to the Research workspace, type 'saved' = bookmarked stories.
Plain file, no database, nothing running in the background."""
import json, os, time, threading, itertools

BASE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(BASE, "miko_research.json")
_lock = threading.Lock()
_seq = itertools.count(1)

def _load():
    try:
        with open(FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def _save(items):
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1, ensure_ascii=False)
    os.replace(tmp, FILE)

def list_items(kind=None):
    with _lock:
        items = _load()
    if kind:
        items = [i for i in items if i.get("type") == kind]
    return sorted(items, key=lambda i: -i.get("ts", 0))

def add(item):
    kind = item.get("type", "research")
    url = (item.get("url") or "").strip()
    if kind not in ("research", "saved"):
        raise ValueError("unknown type")
    if not url.startswith(("http://", "https://")):
        raise ValueError("a web link is required")
    with _lock:
        items = _load()
        for i in items:
            if i.get("type") == kind and i.get("url") == url:
                return i, False            # already there
        rec = {"id": int(time.time() * 1000) * 100 + next(_seq) % 100, "type": kind,
               "title": (item.get("title") or url)[:200], "url": url,
               "body": (item.get("body") or "")[:800], "source": (item.get("source") or "")[:80],
               "image": (item.get("image") or "")[:500], "date": (item.get("date") or "")[:40],
               "note": "", "ts": time.time()}
        items.append(rec)
        _save(items)
        return rec, True

def remove(item_id):
    with _lock:
        items = _load()
        keep = [i for i in items if i.get("id") != item_id]
        _save(keep)
        return len(keep) != len(items)

def update(item_id, fields):
    with _lock:
        items = _load()
        for i in items:
            if i.get("id") == item_id:
                for k in ("note", "title"):
                    if k in fields:
                        i[k] = str(fields[k])[:2000]
                _save(items)
                return i
    return None

def clear(kind=None):
    with _lock:
        items = _load()
        keep = [i for i in items if kind and i.get("type") != kind]
        _save(keep)
