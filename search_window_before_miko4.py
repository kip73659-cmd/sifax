import sys
import os
import json
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk
from io import BytesIO
from queue import Queue, Empty

import requests
from ddgs import DDGS
from PIL import Image, ImageTk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
messages = Queue()

# Miko palette — elegant dark interface, restrained crimson accents.
BG = "#100d12"
PANEL = "#19131b"
PANEL_ALT = "#211923"
CARD = "#241a25"
CARD_HOVER = "#30202f"
CRIMSON = "#b52d4b"
CRIMSON_BRIGHT = "#e14a68"
ROSE = "#e7a0b1"
TEXT = "#f4edf0"
MUTED = "#a997a1"
BORDER = "#49303d"
GREEN = "#a9c9ad"


def tavily_search(query):
    key_path = os.path.join(BASE_DIR, "tavily_key.txt")
    with open(key_path, "r", encoding="utf-8") as f:
        key = f.read().strip()

    response = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": query, "max_results": 6},
        timeout=25
    )
    response.raise_for_status()
    return [
        {
            "title": item.get("title", ""),
            "body": item.get("content", ""),
            "href": item.get("url", "")
        }
        for item in response.json().get("results", [])
    ]


def open_url(url):
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        webbrowser.open(url)


if len(sys.argv) > 2:
    query = " ".join(sys.argv[1:-1])
    output_path = sys.argv[-1]
else:
    query = " ".join(sys.argv[1:]) or "hello"
    output_path = os.path.join(BASE_DIR, "miko_search_results.json")

output_path = os.path.abspath(output_path)

root = tk.Tk()
root.title("Miko | Search")
root.geometry("1120x740+100+55")
root.minsize(780, 520)
root.configure(bg=BG)
root.attributes("-topmost", True)

# A custom title bar keeps the layout visually consistent across Windows themes.
root.overrideredirect(False)

style = ttk.Style()
style.theme_use("clam")
style.configure(
    "Miko.TNotebook",
    background=BG,
    borderwidth=0,
    tabmargins=(0, 0, 8, 0)
)
style.configure(
    "Miko.TNotebook.Tab",
    background=PANEL_ALT,
    foreground=MUTED,
    padding=(20, 11),
    font=("Segoe UI", 10, "bold"),
    borderwidth=0
)
style.map(
    "Miko.TNotebook.Tab",
    background=[("selected", CRIMSON), ("active", CARD_HOVER)],
    foreground=[("selected", TEXT), ("active", TEXT)]
)
style.configure(
    "Miko.Vertical.TScrollbar",
    background=PANEL_ALT,
    troughcolor=BG,
    bordercolor=BG,
    arrowcolor=ROSE
)

# Main outer frame
outer = tk.Frame(root, bg=BG)
outer.pack(fill="both", expand=True, padx=14, pady=14)

# Header
header = tk.Frame(outer, bg=BG)
header.pack(fill="x", pady=(0, 12))

brand = tk.Frame(header, bg=BG)
brand.pack(side="left", fill="x", expand=True)

tk.Label(
    brand, text="MIKO", bg=BG, fg=TEXT,
    font=("Segoe UI", 18, "bold")
).pack(anchor="w")

tk.Label(
    brand, text="YOUR PERSONAL SEARCH COMPANION",
    bg=BG, fg=ROSE, font=("Segoe UI", 8, "bold")
).pack(anchor="w", pady=(1, 0))

status_pill = tk.Label(
    header, text="●  SEARCHING",
    bg=PANEL_ALT, fg=ROSE,
    font=("Segoe UI", 9, "bold"),
    padx=12, pady=7
)
status_pill.pack(side="right", padx=(8, 0))

# Search query strip
query_panel = tk.Frame(
    outer, bg=PANEL, highlightthickness=1, highlightbackground=BORDER
)
query_panel.pack(fill="x", pady=(0, 13))

tk.Label(
    query_panel, text="SEARCH QUERY",
    bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold")
).pack(anchor="w", padx=15, pady=(10, 2))

query_label = tk.Label(
    query_panel, text=query,
    bg=PANEL, fg=TEXT, font=("Segoe UI", 12),
    anchor="w", justify="left", wraplength=950
)
query_label.pack(fill="x", padx=15, pady=(0, 12))

# Content area: slim avatar rail + search results
content = tk.Frame(outer, bg=BG)
content.pack(fill="both", expand=True)

avatar_panel = tk.Frame(
    content, bg=PANEL, width=218,
    highlightthickness=1, highlightbackground=BORDER
)
avatar_panel.pack(side="left", fill="y", padx=(0, 12))
avatar_panel.pack_propagate(False)

tk.Label(
    avatar_panel, text="MIKO",
    bg=PANEL, fg=ROSE, font=("Segoe UI", 11, "bold")
).pack(pady=(16, 8))

avatar_area = tk.Frame(
    avatar_panel, bg=PANEL_ALT,
    highlightthickness=1, highlightbackground=BORDER
)
avatar_area.pack(fill="both", expand=True, padx=12, pady=(0, 12))

avatar_label = tk.Label(
    avatar_area,
    text="MIKO\n\nAvatar artwork\nnot added yet",
    bg=PANEL_ALT, fg=MUTED,
    font=("Segoe UI", 10),
    justify="center"
)
avatar_label.pack(fill="both", expand=True, padx=8, pady=8)

avatar_status = tk.Label(
    avatar_panel,
    text="Ready when you are.",
    bg=PANEL, fg=MUTED,
    font=("Segoe UI", 9),
    wraplength=180
)
avatar_status.pack(pady=(0, 15))

# Optional avatar image support.
avatar_image = None
avatar_path = None
for candidate in ("miko_avatar.png", "miko_avatar.jpg", "miko_avatar.gif"):
    possible = os.path.join(BASE_DIR, candidate)
    if os.path.isfile(possible):
        avatar_path = possible
        break

if avatar_path:
    try:
        loaded = Image.open(avatar_path).convert("RGBA")
        loaded.thumbnail((185, 390))
        avatar_image = ImageTk.PhotoImage(loaded)
        avatar_label.configure(image=avatar_image, text="")
    except Exception:
        avatar_label.configure(
            text="Avatar image found,\nbut couldn't be loaded."
        )

# Right-side results panel
results_panel = tk.Frame(
    content, bg=PANEL,
    highlightthickness=1, highlightbackground=BORDER
)
results_panel.pack(side="left", fill="both", expand=True)

tabs_header = tk.Frame(results_panel, bg=PANEL)
tabs_header.pack(fill="x", padx=14, pady=(13, 8))

tk.Label(
    tabs_header, text="SEARCH RESULTS",
    bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")
).pack(side="left")

notebook = ttk.Notebook(results_panel, style="Miko.TNotebook")
notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))

web_tab = tk.Frame(notebook, bg=PANEL)
images_tab = tk.Frame(notebook, bg=PANEL)
notebook.add(web_tab, text="  WEB  ")
notebook.add(images_tab, text="  IMAGES  ")

web_status = tk.Label(
    web_tab, text="Preparing web search...",
    bg=PANEL, fg=MUTED, font=("Segoe UI", 9)
)
web_status.pack(anchor="w", padx=12, pady=(10, 7))

web_frame = tk.Frame(web_tab, bg=PANEL)
web_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

web_scroll = ttk.Scrollbar(
    web_frame, style="Miko.Vertical.TScrollbar"
)
web_scroll.pack(side="right", fill="y")

web_box = tk.Text(
    web_frame, wrap="word",
    font=("Segoe UI", 10),
    fg=TEXT, bg=PANEL_ALT,
    insertbackground=TEXT,
    selectbackground=CRIMSON,
    bd=0, padx=15, pady=13,
    spacing1=3, spacing3=8,
    yscrollcommand=web_scroll.set
)
web_box.pack(side="left", fill="both", expand=True)
web_scroll.config(command=web_box.yview)
web_box.tag_config("title", foreground=ROSE, font=("Segoe UI", 11, "bold"))
web_box.tag_config("body", foreground=TEXT)
web_box.tag_config("link", foreground=GREEN, underline=True)


def show_web_results(results, error):
    web_box.config(state="normal")
    web_box.delete("1.0", "end")

    if error:
        web_box.insert("end", "Search issue\n", "title")
        web_box.insert("end", error + "\n\n", "body")

    if not results and not error:
        web_box.insert("end", "No web results were found.", "body")

    for index, item in enumerate(results):
        title = item.get("title", "Untitled result")
        body = item.get("body", "")
        url = item.get("href", "")

        web_box.insert("end", title + "\n", "title")
        if body:
            web_box.insert("end", body + "\n", "body")

        if url:
            tag = "link_" + str(index)
            web_box.insert("end", url + "\n\n", tag)
            web_box.tag_config(tag, foreground=GREEN, underline=True)
            web_box.tag_bind(
                tag, "<Button-1>",
                lambda event, u=url: open_url(u)
            )

    web_box.config(state="disabled")
    web_status.config(text=f"{len(results)} web results" if not error else "Web search needs attention")
    status_pill.config(text="●  SEARCH COMPLETE" if not error else "●  CHECK SEARCH")


# Images tab with scrollable three-column cards
images_status = tk.Label(
    images_tab, text="Searching for pictures...",
    bg=PANEL, fg=MUTED, font=("Segoe UI", 9)
)
images_status.pack(anchor="w", padx=12, pady=(10, 7))

image_frame = tk.Frame(images_tab, bg=PANEL)
image_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

image_canvas = tk.Canvas(image_frame, bg=PANEL, highlightthickness=0)
image_scroll = ttk.Scrollbar(
    image_frame, orient="vertical",
    command=image_canvas.yview,
    style="Miko.Vertical.TScrollbar"
)
image_scroll.pack(side="right", fill="y")
image_canvas.pack(side="left", fill="both", expand=True)
image_canvas.configure(yscrollcommand=image_scroll.set)

image_inner = tk.Frame(image_canvas, bg=PANEL)
canvas_window = image_canvas.create_window(
    (0, 0), window=image_inner, anchor="nw"
)

image_labels = []
photo_refs = []


def update_scroll(event=None):
    image_canvas.configure(scrollregion=image_canvas.bbox("all"))


def resize_canvas(event):
    image_canvas.itemconfigure(canvas_window, width=event.width)


image_inner.bind("<Configure>", update_scroll)
image_canvas.bind("<Configure>", resize_canvas)


def load_thumbnail(item, index):
    url = item.get("thumbnail") or item.get("image")
    try:
        if not url:
            raise ValueError("No thumbnail URL")
        response = requests.get(
            url, timeout=15,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()
        messages.put(("thumbnail", index, response.content))
    except Exception:
        messages.put(("thumbnail_error", index, None))


def show_images(items, error):
    global image_labels, photo_refs

    for widget in image_inner.winfo_children():
        widget.destroy()

    image_labels = []
    photo_refs = []

    if error:
        images_status.config(text="Image search issue: " + error)
        return

    if not items:
        images_status.config(text="No images were found.")
        return

    images_status.config(
        text=f"{len(items)} image results · Select a preview to open it"
    )
    photo_refs = [None] * len(items)

    for index, item in enumerate(items):
        card = tk.Frame(
            image_inner, bg=CARD,
            highlightthickness=1, highlightbackground=BORDER,
            padx=9, pady=9
        )
        card.grid(
            row=index // 3, column=index % 3,
            padx=7, pady=7, sticky="n"
        )

        image_url = item.get("image") or item.get("thumbnail")
        page_url = item.get("url") or image_url

        preview = tk.Label(
            card, text="Loading preview...",
            width=27, height=8,
            bg=PANEL_ALT, fg=MUTED,
            cursor="hand2", font=("Segoe UI", 9)
        )
        preview.pack(pady=(0, 8))
        preview.bind(
            "<Button-1>",
            lambda event, u=image_url: open_url(u)
        )
        image_labels.append(preview)

        title = str(item.get("title") or "Image result")
        tk.Label(
            card, text=title[:90],
            bg=CARD, fg=TEXT,
            wraplength=220, justify="left",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(0, 7))

        tk.Button(
            card, text="OPEN RESULT",
            command=lambda u=page_url: open_url(u),
            bg=PANEL_ALT, fg=ROSE,
            activebackground=CRIMSON,
            activeforeground=TEXT,
            relief="flat", bd=0,
            padx=11, pady=5,
            cursor="hand2",
            font=("Segoe UI", 8, "bold")
        ).pack(anchor="w")

        threading.Thread(
            target=load_thumbnail,
            args=(item, index),
            daemon=True
        ).start()


def set_thumbnail(index, image_data):
    if index >= len(image_labels):
        return
    try:
        picture = Image.open(BytesIO(image_data)).convert("RGB")
        picture.thumbnail((260, 155))
        photo = ImageTk.PhotoImage(picture)
        photo_refs[index] = photo
        image_labels[index].configure(
            image=photo, text="", width=260, height=155
        )
    except Exception:
        image_labels[index].configure(text="Preview unavailable")


def search_worker():
    results = []
    error = None
    try:
        results = tavily_search(query)
    except Exception as e:
        error = str(e)

    payload = {"query": query, "results": results, "error": error}
    try:
        output_folder = os.path.dirname(output_path)
        os.makedirs(output_folder, exist_ok=True)
        temp_path = output_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, output_path)
    except Exception as e:
        error = "Could not save search results: " + str(e)

    messages.put(("web", results, error))

    try:
        image_results = list(
            DDGS(timeout=20).images(
                query=query,
                region="us-en",
                safesearch="off",
                max_results=10
            )
        )
        messages.put(("images", image_results, None))
    except Exception as e:
        messages.put(("images", [], str(e)))


def process_messages():
    try:
        while True:
            kind, data, extra = messages.get_nowait()
            if kind == "web":
                show_web_results(data, extra)
            elif kind == "images":
                show_images(data, extra)
            elif kind == "thumbnail":
                set_thumbnail(data, extra)
            elif kind == "thumbnail_error":
                if data < len(image_labels):
                    image_labels[data].configure(text="Preview unavailable")
    except Empty:
        pass

    if root.winfo_exists():
        root.after(120, process_messages)


threading.Thread(target=search_worker, daemon=True).start()
root.after(120, process_messages)
root.mainloop()
