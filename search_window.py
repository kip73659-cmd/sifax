# Miko Universal Search — approved Design 4
# Keeps the existing Tavily web search, DDGS image search, JSON output,
# thumbnail loading, and command-line integration.
import os, sys, json, threading, webbrowser
import tkinter as tk
from tkinter import ttk
from io import BytesIO
from queue import Queue, Empty
import requests
from ddgs import DDGS
from PIL import Image, ImageTk, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ART_PATH = os.path.join(BASE_DIR, "miko_search_art.png")
QUEUE = Queue()

BG = "#09060d"
PANEL = "#120a13"
CARD = "#160c17"
CARD2 = "#1d0d1a"
PINK = "#ff2d78"
PINK2 = "#ff75a7"
TEXT = "#fff2f7"
MUTED = "#c7a9b8"
FONT = "Segoe UI"

if len(sys.argv) > 2:
    query = " ".join(sys.argv[1:-1])
    output_path = sys.argv[-1]
else:
    query = " ".join(sys.argv[1:]) or "hello"
    output_path = os.path.join(BASE_DIR, "miko_search_results.json")
output_path = os.path.abspath(output_path)

def tavily_search(q):
    key_file = os.path.join(BASE_DIR, "tavily_key.txt")
    with open(key_file, "r", encoding="utf-8") as f:
        key = f.read().strip()
    if not key:
        raise ValueError("tavily_key.txt is empty.")
    r = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": q, "max_results": 8},
        timeout=25,
    )
    r.raise_for_status()
    return [{"title": x.get("title", ""), "body": x.get("content", ""),
             "href": x.get("url", "")} for x in r.json().get("results", [])]

def open_url(url):
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        webbrowser.open(url)

class ScrollArea(tk.Frame):
    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, bd=0, highlightthickness=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self.wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
    def wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

root = tk.Tk()
root.title("Miko Search")
root.geometry("1280x820+70+35")
root.minsize(900, 620)
root.configure(bg=BG)
root.overrideredirect(True)
root.attributes("-topmost", True)

# Neon outline and custom title bar
outer = tk.Frame(root, bg=BG, highlightthickness=2, highlightbackground=PINK)
outer.pack(fill="both", expand=True, padx=2, pady=2)
titlebar = tk.Frame(outer, bg="#170914", height=54)
titlebar.pack(fill="x")
titlebar.pack_propagate(False)
brand = tk.Label(titlebar, text="✿  Miko Search", bg="#170914", fg="#ffb4d0",
                 font=("Georgia", 17, "italic"))
brand.pack(side="left", padx=22)
controls = tk.Frame(titlebar, bg="#170914")
controls.pack(side="right", padx=14)
def title_btn(label, action):
    tk.Button(controls, text=label, command=action, bg="#170914", fg=PINK2,
              activebackground="#351126", activeforeground="white",
              relief="flat", bd=0, font=(FONT, 17), width=3, cursor="hand2").pack(side="left")
title_btn("—", root.iconify)
title_btn("□", lambda: root.geometry("1280x820+70+35"))
title_btn("×", root.destroy)

# Drag the frameless window by its title strip
_drag = {"x": 0, "y": 0}
def drag_start(e):
    _drag["x"], _drag["y"] = e.x_root - root.winfo_x(), e.y_root - root.winfo_y()
def drag_move(e):
    root.geometry(f"+{e.x_root-_drag['x']}+{e.y_root-_drag['y']}")
titlebar.bind("<Button-1>", drag_start)
titlebar.bind("<B1-Motion>", drag_move)
brand.bind("<Button-1>", drag_start)
brand.bind("<B1-Motion>", drag_move)

body = tk.Frame(outer, bg=BG)
body.pack(fill="both", expand=True)
body.grid_rowconfigure(0, weight=1)
body.grid_columnconfigure(0, minsize=430, weight=0)
body.grid_columnconfigure(1, weight=1)

# Full-height illustrated left panel, cropped from the approved mockup artwork.
left = tk.Frame(body, bg="#180b16")
left.grid(row=0, column=0, sticky="nsew")
art_label = tk.Label(left, bg="#180b16", bd=0)
art_label.place(relx=0, rely=0, relwidth=1, relheight=1)
_art_ref = None
try:
    raw = Image.open(ART_PATH).convert("RGB")
    def fit_art():
        global _art_ref
        w, h = max(1, left.winfo_width()), max(1, left.winfo_height())
        fitted = ImageOps.fit(raw, (w, h), method=Image.Resampling.LANCZOS)
        _art_ref = ImageTk.PhotoImage(fitted)
        art_label.configure(image=_art_ref)
    left.bind("<Configure>", lambda e: fit_art())
except Exception:
    tk.Label(left, text="MIKO", bg="#180b16", fg=PINK2,
             font=("Georgia", 44, "italic")).place(relx=.5, rely=.48, anchor="center")

# Right search workspace
right = tk.Frame(body, bg=BG)
right.grid(row=0, column=1, sticky="nsew", padx=(0, 16))
right.grid_columnconfigure(0, weight=1)
right.grid_rowconfigure(3, weight=1)

prompt = tk.Label(right, text="What would you like to search for? ♡",
                  bg=BG, fg="#ff9fbe", font=("Georgia", 20, "italic"))
prompt.grid(row=0, column=0, pady=(32, 18), sticky="ew")

searchrow = tk.Frame(right, bg="#170b17", highlightthickness=2, highlightbackground=PINK)
searchrow.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 18))
searchrow.grid_columnconfigure(0, weight=1)
entry = tk.Entry(searchrow, bg="#170b17", fg=TEXT, insertbackground=PINK2,
                 relief="flat", bd=0, font=(FONT, 15))
entry.insert(0, query)
entry.grid(row=0, column=0, sticky="ew", padx=(18, 8), ipady=14)
search_button = tk.Button(searchrow, text="⌕", bg=PINK, fg="white",
                           activebackground="#ff6c9f", relief="flat", bd=0,
                           font=(FONT, 22, "bold"), width=4, cursor="hand2")
search_button.grid(row=0, column=1, padx=5, pady=5)

tabrow = tk.Frame(right, bg=BG)
tabrow.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
panels = tk.Frame(right, bg=BG)
panels.grid(row=3, column=0, sticky="nsew", padx=8)
panels.grid_rowconfigure(0, weight=1)
panels.grid_columnconfigure(0, weight=1)
web_panel, image_panel = tk.Frame(panels, bg=BG), tk.Frame(panels, bg=BG)
for p in (web_panel, image_panel):
    p.grid(row=0, column=0, sticky="nsew")
active = "web"
tab_btns = {}
def switch_tab(name):
    global active
    active = name
    (web_panel if name == "web" else image_panel).tkraise()
    for n, b in tab_btns.items():
        b.configure(bg=PINK if n == name else "#24101f",
                    fg="white" if n == name else MUTED)
def add_tab(name, text):
    b = tk.Button(tabrow, text=text, command=lambda: switch_tab(name),
                  bg="#24101f", fg=MUTED, activebackground=PINK,
                  activeforeground="white", relief="flat", bd=0,
                  font=(FONT, 11, "bold"), padx=24, pady=12, cursor="hand2")
    b.pack(side="left", padx=(0, 5))
    tab_btns[name] = b
add_tab("web", "◎  Web")
add_tab("images", "▧  Images")

web_count = tk.Label(tabrow, text="✧  Searching...", bg=BG, fg=PINK2, font=(FONT, 10))
web_count.pack(side="right", padx=8)
web_status = tk.Label(web_panel, text="Searching the web...", bg=BG, fg=MUTED, font=(FONT, 9))
web_status.pack(anchor="w", pady=(0, 8))
web_area = ScrollArea(web_panel)
web_area.pack(fill="both", expand=True)
img_status = tk.Label(image_panel, text="Searching for images...", bg=BG, fg=MUTED, font=(FONT, 9))
img_status.pack(anchor="w", pady=(0, 8))
img_area = ScrollArea(image_panel)
img_area.pack(fill="both", expand=True)

thumb_labels, thumb_refs, image_items = [], [], []

def render_web(results, error):
    for w in web_area.inner.winfo_children(): w.destroy()
    if error:
        tk.Label(web_area.inner, text="Search error: " + error, bg=CARD, fg=PINK2,
                 wraplength=650, justify="left", padx=16, pady=14).pack(fill="x", pady=6)
    for i, item in enumerate(results):
        card = tk.Frame(web_area.inner, bg=CARD, highlightthickness=1, highlightbackground="#6d1b42")
        card.pack(fill="x", pady=(0, 10), padx=(1, 8))
        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(row, text=f"{i+1:02d}", bg="#351126", fg=PINK2,
                 font=(FONT, 10, "bold"), padx=9, pady=5).pack(side="left", padx=(0, 12))
        tk.Label(row, text=item.get("title") or "Untitled result", bg=CARD, fg=TEXT,
                 font=(FONT, 12, "bold"), wraplength=600, justify="left").pack(side="left", fill="x")
        tk.Label(card, text=item.get("body") or "No description available.",
                 bg=CARD, fg="#e5cbd6", font=(FONT, 10), wraplength=700,
                 justify="left").pack(anchor="w", padx=14, pady=(4, 7))
        url = item.get("href", "")
        tk.Button(card, text=("↗  " + url[:100]), command=lambda u=url: open_url(u),
                  bg=CARD2, fg=PINK2, activebackground="#40142b",
                  relief="flat", bd=0, anchor="w", font=(FONT, 9),
                  padx=12, pady=8, cursor="hand2").pack(fill="x", padx=12, pady=(0, 11))
    if not results and not error:
        tk.Label(web_area.inner, text="No web results found.", bg=BG, fg=MUTED,
                 font=(FONT, 11)).pack(anchor="w", pady=20)
    web_status.config(text=f"{len(results)} web result(s)" if not error else "Search finished with an issue")
    web_count.config(text=f"✧  {len(results)} results found" if not error else "✧  Search issue")

def thumb_worker(item, idx):
    try:
        url = item.get("thumbnail") or item.get("image")
        if not url: raise ValueError("No preview")
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        QUEUE.put(("thumb", idx, r.content))
    except Exception:
        QUEUE.put(("thumb_error", idx, None))

def render_images(items, error):
    global thumb_labels, thumb_refs, image_items
    for w in img_area.inner.winfo_children(): w.destroy()
    image_items, thumb_labels, thumb_refs = items, [], [None] * len(items)
    if error:
        img_status.config(text="Image search failed: " + error)
        return
    img_status.config(text=f"{len(items)} image result(s)  •  Select a preview to open it")
    for i, item in enumerate(items):
        card = tk.Frame(img_area.inner, bg=CARD, highlightthickness=1, highlightbackground="#6d1b42")
        card.grid(row=i//2, column=i%2, sticky="nsew", padx=(0, 10), pady=(0, 10))
        img_area.inner.grid_columnconfigure(i%2, weight=1, uniform="img")
        url = item.get("image") or item.get("thumbnail")
        preview = tk.Label(card, text="Loading preview...", bg="#281323", fg=MUTED,
                            cursor="hand2", font=(FONT, 9))
        preview.pack(fill="x", padx=8, pady=8)
        preview.bind("<Button-1>", lambda e, u=url: open_url(u))
        thumb_labels.append(preview)
        tk.Label(card, text=(item.get("title") or "Image result")[:90],
                 bg=CARD, fg=TEXT, font=(FONT, 9, "bold"),
                 wraplength=280, justify="left").pack(anchor="w", padx=10, pady=(0, 8))
        tk.Button(card, text="OPEN IMAGE  ↗", command=lambda u=url: open_url(u),
                  bg=CARD2, fg=PINK2, relief="flat", bd=0, padx=10, pady=7,
                  cursor="hand2").pack(anchor="w", padx=9, pady=(0, 9))
        threading.Thread(target=thumb_worker, args=(item, i), daemon=True).start()

def set_thumb(i, data):
    if i >= len(thumb_labels): return
    try:
        im = Image.open(BytesIO(data)).convert("RGB")
        im.thumbnail((420, 210))
        photo = ImageTk.PhotoImage(im)
        thumb_refs[i] = photo
        thumb_labels[i].configure(image=photo, text="")
    except Exception:
        thumb_labels[i].configure(text="Preview unavailable")

def worker(q):
    try:
        results = tavily_search(q)
        error = None
    except Exception as e:
        results, error = [], str(e)
    try:
        os.makedirs(os.path.dirname(output_path) or BASE_DIR, exist_ok=True)
        temp = output_path + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump({"query": q, "results": results, "error": error},
                      f, ensure_ascii=False, indent=2)
        os.replace(temp, output_path)
    except Exception as e:
        error = "Could not save results: " + str(e)
    QUEUE.put(("web", results, error))
    try:
        pics = list(DDGS(timeout=20).images(query=q, region="us-en",
                     safesearch="off", max_results=10))
        QUEUE.put(("images", pics, None))
    except Exception as e:
        QUEUE.put(("images", [], str(e)))

def run_search():
    q = entry.get().strip()
    if not q: return
    web_status.config(text="Searching the web...")
    img_status.config(text="Searching for images...")
    web_count.config(text="✧  Searching...")
    for w in web_area.inner.winfo_children(): w.destroy()
    for w in img_area.inner.winfo_children(): w.destroy()
    threading.Thread(target=web_worker, args=(query,), daemon=True).start()
    threading.Thread(target=image_worker, args=(query,), daemon=True).start()

search_button.configure(command=run_search)
entry.bind("<Return>", lambda e: run_search())

# Footer navigation styled like the reference; Home returns to Web.
footer = tk.Frame(right, bg="#100812", highlightthickness=1, highlightbackground="#4e1834")
footer.grid(row=4, column=0, sticky="ew", padx=8, pady=(10, 8))
for label, cmd in [
    ("⌂  Home", lambda: switch_tab("web")),
    ("☆  Favorites", lambda: web_count.config(text="✧  Favorites coming soon")),
    ("◷  History", lambda: web_count.config(text="✧  History coming soon")),
]:
    tk.Button(footer, text=label, command=cmd, bg="#100812", fg=PINK2,
              activebackground="#351126", activeforeground="white",
              relief="flat", bd=0, font=(FONT, 10), padx=16, pady=11,
              cursor="hand2").pack(side="left")
online = tk.Label(footer, text="● Online", bg="#100812", fg="#55f58d",
                  font=(FONT, 10, "bold"))
online.pack(side="right", padx=18)

def poll():
    try:
        while True:
            kind, data, extra = QUEUE.get_nowait()
            if kind == "web": render_web(data, extra)
            elif kind == "images": render_images(data, extra)
            elif kind == "thumb": set_thumb(data, extra)
            elif kind == "thumb_error" and data < len(thumb_labels):
                thumb_labels[data].configure(text="Preview unavailable")
    except Empty:
        pass
    if root.winfo_exists(): root.after(100, poll)
# AUTOCLOSE
def _write_pid():
    open(os.path.join(BASE_DIR, 'search_window.pid'), 'w').write(str(os.getpid()))
_write_pid()
_left = [20]
def _reset(e=None):
    _left[0] = 20
def _tick():
    _left[0] -= 1
    if _left[0] <= 0:
        root.destroy()
        return
    root.after(1000, _tick)
root.bind_all('<Motion>', _reset)
root.bind_all('<Button-1>', _reset)
root.bind_all('<MouseWheel>', _reset)
root.bind_all('<Key>', _reset)
root.after(1000, _tick)


switch_tab("web")
threading.Thread(target=worker, args=(query,), daemon=True).start()
root.after(100, poll)
root.mainloop()
