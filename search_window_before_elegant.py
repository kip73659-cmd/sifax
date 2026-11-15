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
from PIL import Image, ImageTk, ImageSequence, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
messages = Queue()

# Miko's visual theme: charcoal, black, crimson, and a restrained rose accent.
BG = "#100b10"
PANEL = "#191117"
PANEL_ALT = "#21151d"
CARD = "#251923"
CARD_HOVER = "#30202b"
RED = "#b52b45"
RED_BRIGHT = "#e34b68"
ROSE = "#e9a1ad"
TEXT = "#f6edf0"
MUTED = "#b69da6"
SOFT = "#806b74"
GREEN = "#9bc7ad"

FONT = "Segoe UI"


def tavily_search(query):
    key_path = os.path.join(BASE_DIR, "tavily_key.txt")
    with open(key_path, "r", encoding="utf-8") as f:
        key = f.read().strip()

    if not key:
        raise ValueError("Your tavily_key.txt file is empty.")

    response = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": query, "max_results": 6},
        timeout=25,
    )
    response.raise_for_status()

    return [
        {
            "title": item.get("title", ""),
            "body": item.get("content", ""),
            "href": item.get("url", ""),
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


class ScrollableFrame(tk.Frame):
    """A compact dark scroll area for web and image result cards."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._update_scrollregion)
        self.canvas.bind("<Configure>", self._resize_inner)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", self._enable_mousewheel)
        self.canvas.bind("<Leave>", self._disable_mousewheel)

    def _update_scrollregion(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_inner(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _enable_mousewheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>", self._mousewheel)

    def _disable_mousewheel(self, _event=None):
        self.canvas.unbind_all("<MouseWheel>")

    def _mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


# ---------------- WINDOW ----------------

root = tk.Tk()
root.title("Miko | Universal Search")
root.geometry("1160x780+90+40")
root.minsize(820, 600)
root.configure(bg=BG)
root.attributes("-topmost", True)

style = ttk.Style()
try:
    style.theme_use("clam")
except tk.TclError:
    pass
style.configure(
    "Miko.Vertical.TScrollbar",
    background=PANEL_ALT,
    troughcolor=BG,
    bordercolor=BG,
    arrowcolor=ROSE,
    lightcolor=PANEL_ALT,
    darkcolor=PANEL_ALT,
)

# Thin crimson accent line at the top.
accent = tk.Frame(root, bg=RED, height=3)
accent.pack(fill="x")

page = tk.Frame(root, bg=BG)
page.pack(fill="both", expand=True, padx=18, pady=16)

# Header
header = tk.Frame(page, bg=BG)
header.pack(fill="x", pady=(0, 15))

brand_row = tk.Frame(header, bg=BG)
brand_row.pack(fill="x")

tk.Label(
    brand_row,
    text="✦",
    font=(FONT, 23, "bold"),
    fg=RED_BRIGHT,
    bg=BG,
).pack(side="left", padx=(0, 9))

tk.Label(
    brand_row,
    text="MIKO",
    font=(FONT, 22, "bold"),
    fg=TEXT,
    bg=BG,
).pack(side="left")

tk.Label(
    brand_row,
    text="UNIVERSAL SEARCH",
    font=(FONT, 9, "bold"),
    fg=ROSE,
    bg=BG,
).pack(side="left", padx=(12, 0), pady=(7, 0))

tk.Label(
    header,
    text="A little help, whenever you need it.",
    font=(FONT, 9),
    fg=MUTED,
    bg=BG,
).pack(anchor="w", padx=(38, 0), pady=(1, 0))

# Main two-column layout: Miko's avatar rail + search workspace.
main = tk.Frame(page, bg=BG)
main.pack(fill="both", expand=True)
main.grid_columnconfigure(0, minsize=218, weight=0)
main.grid_columnconfigure(1, weight=1)
main.grid_rowconfigure(0, weight=1)

sidebar = tk.Frame(main, bg=PANEL, highlightthickness=1, highlightbackground="#39232e")
sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
sidebar.grid_columnconfigure(0, weight=1)

# Sidebar identity
identity = tk.Frame(sidebar, bg=PANEL)
identity.pack(fill="x", padx=15, pady=(17, 10))
tk.Label(identity, text="YOUR ASSISTANT", font=(FONT, 8, "bold"), fg=SOFT, bg=PANEL).pack(anchor="w")
tk.Label(identity, text="Miko", font=(FONT, 17, "bold"), fg=TEXT, bg=PANEL).pack(anchor="w", pady=(2, 0))
tk.Label(identity, text="Here to help.", font=(FONT, 9), fg=MUTED, bg=PANEL).pack(anchor="w")

avatar_shell = tk.Frame(sidebar, bg="#2d1721", highlightthickness=1, highlightbackground="#713043")
avatar_shell.pack(fill="x", padx=14, pady=(6, 12))
avatar_label = tk.Label(avatar_shell, bg="#21131b", fg=ROSE, bd=0)
avatar_label.pack(fill="both", padx=5, pady=5)

# Fallback avatar panel until the user's art is copied beside this script.
avatar_placeholder = tk.Canvas(
    avatar_label,
    width=178,
    height=222,
    bg="#21131b",
    highlightthickness=0,
    bd=0,
)
avatar_placeholder.pack()
avatar_placeholder.create_oval(21, 18, 157, 154, outline="#653044", width=2)
avatar_placeholder.create_oval(31, 28, 147, 144, outline="#a33750", width=1)
avatar_placeholder.create_text(89, 77, text="M", fill=ROSE, font=("Georgia", 53, "italic"))
avatar_placeholder.create_line(37, 169, 141, 169, fill="#713043", width=1)
avatar_placeholder.create_text(89, 190, text="MIKO", fill=TEXT, font=(FONT, 12, "bold"))
avatar_placeholder.create_text(89, 207, text="AVATAR NOT ADDED", fill=SOFT, font=(FONT, 7, "bold"))

status_card = tk.Frame(sidebar, bg=PANEL_ALT)
status_card.pack(fill="x", padx=14, pady=(1, 10))
status_row = tk.Frame(status_card, bg=PANEL_ALT)
status_row.pack(fill="x", padx=11, pady=(10, 3))
tk.Label(status_row, text="●", fg=GREEN, bg=PANEL_ALT, font=(FONT, 9)).pack(side="left")
tk.Label(status_row, text="SEARCH READY", fg=TEXT, bg=PANEL_ALT, font=(FONT, 8, "bold")).pack(side="left", padx=(6, 0))
tk.Label(status_card, text="WEB  •  IMAGES", fg=ROSE, bg=PANEL_ALT, font=(FONT, 8)).pack(anchor="w", padx=11, pady=(0, 10))

hint = tk.Label(
    sidebar,
    text="Your character art can be added as\nmiko_avatar.png or miko_avatar.gif.",
    font=(FONT, 8),
    fg=SOFT,
    bg=PANEL,
    justify="left",
    wraplength=180,
)
hint.pack(anchor="w", padx=15, pady=(3, 12))

# Right-hand search workspace.
workspace = tk.Frame(main, bg=BG)
workspace.grid(row=0, column=1, sticky="nsew")
workspace.grid_columnconfigure(0, weight=1)
workspace.grid_rowconfigure(2, weight=1)

query_card = tk.Frame(workspace, bg=PANEL, highlightthickness=1, highlightbackground="#39232e")
query_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
tk.Label(query_card, text="SEARCHING FOR", font=(FONT, 8, "bold"), fg=SOFT, bg=PANEL).pack(anchor="w", padx=14, pady=(10, 2))
tk.Label(
    query_card,
    text=query,
    font=(FONT, 11, "bold"),
    fg=TEXT,
    bg=PANEL,
    wraplength=760,
    justify="left",
).pack(anchor="w", padx=14, pady=(0, 11))

# Custom tab buttons, rather than the default square notebook tabs.
tab_bar = tk.Frame(workspace, bg=BG)
tab_bar.grid(row=1, column=0, sticky="ew", pady=(0, 9))

content = tk.Frame(workspace, bg=BG)
content.grid(row=2, column=0, sticky="nsew")
content.grid_rowconfigure(0, weight=1)
content.grid_columnconfigure(0, weight=1)

web_panel = tk.Frame(content, bg=BG)
images_panel = tk.Frame(content, bg=BG)
for panel in (web_panel, images_panel):
    panel.grid(row=0, column=0, sticky="nsew")

active_tab = "web"
tab_buttons = {}


def show_tab(name):
    global active_tab
    active_tab = name
    if name == "web":
        web_panel.tkraise()
    else:
        images_panel.tkraise()
    for key, button in tab_buttons.items():
        if key == name:
            button.configure(bg=RED, fg="white", activebackground=RED_BRIGHT)
        else:
            button.configure(bg=PANEL_ALT, fg=MUTED, activebackground=CARD_HOVER)


def make_tab(name, label):
    button = tk.Button(
        tab_bar,
        text=label,
        command=lambda: show_tab(name),
        font=(FONT, 9, "bold"),
        bg=PANEL_ALT,
        fg=MUTED,
        activebackground=CARD_HOVER,
        activeforeground=TEXT,
        relief="flat",
        bd=0,
        padx=18,
        pady=9,
        cursor="hand2",
    )
    button.pack(side="left", padx=(0, 7))
    tab_buttons[name] = button


make_tab("web", "◉   WEB")
make_tab("images", "▧   IMAGES")

# WEB RESULTS
web_status = tk.Label(web_panel, text="Preparing web search...", bg=BG, fg=MUTED, font=(FONT, 9))
web_status.pack(anchor="w", padx=2, pady=(0, 8))
web_results = ScrollableFrame(web_panel, bg=BG)
web_results.pack(fill="both", expand=True)


def show_web_results(results, error):
    for widget in web_results.inner.winfo_children():
        widget.destroy()

    if error:
        tk.Label(
            web_results.inner,
            text="Web search issue\n" + error,
            bg=CARD,
            fg=ROSE,
            justify="left",
            wraplength=650,
            padx=14,
            pady=14,
        ).pack(fill="x", pady=(0, 9))

    if not results and not error:
        tk.Label(web_results.inner, text="No web results were found.", bg=BG, fg=MUTED, font=(FONT, 10)).pack(anchor="w", pady=12)

    for item in results:
        card = tk.Frame(web_results.inner, bg=CARD, highlightthickness=1, highlightbackground="#38232d")
        card.pack(fill="x", pady=(0, 9), padx=(0, 5))

        title = item.get("title") or "Untitled result"
        body = item.get("body") or "No description available."
        url = item.get("href", "")

        tk.Label(
            card,
            text=title,
            bg=CARD,
            fg=ROSE,
            font=(FONT, 11, "bold"),
            wraplength=700,
            justify="left",
        ).pack(anchor="w", padx=13, pady=(11, 4))

        tk.Label(
            card,
            text=body,
            bg=CARD,
            fg=TEXT,
            font=(FONT, 9),
            wraplength=700,
            justify="left",
        ).pack(anchor="w", padx=13, pady=(0, 8))

        if url:
            tk.Button(
                card,
                text="OPEN SOURCE  ↗",
                command=lambda u=url: open_url(u),
                bg="#3a202c",
                fg=ROSE,
                activebackground="#512535",
                activeforeground="white",
                relief="flat",
                bd=0,
                font=(FONT, 8, "bold"),
                padx=11,
                pady=6,
                cursor="hand2",
            ).pack(anchor="w", padx=13, pady=(0, 11))
        else:
            tk.Frame(card, bg=CARD, height=8).pack()

    web_status.config(text=f"{len(results)} web result(s)" if not error else "Web search finished with an issue")


# IMAGE RESULTS
images_status = tk.Label(images_panel, text="Searching for pictures...", bg=BG, fg=MUTED, font=(FONT, 9))
images_status.pack(anchor="w", padx=2, pady=(0, 8))
images_results = ScrollableFrame(images_panel, bg=BG)
images_results.pack(fill="both", expand=True)

image_labels = []
photo_refs = []
current_image_items = []


def load_thumbnail(item, index):
    url = item.get("thumbnail") or item.get("image")
    try:
        if not url:
            raise ValueError("No thumbnail URL")
        response = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        messages.put(("thumbnail", index, response.content))
    except Exception:
        messages.put(("thumbnail_error", index, None))


def show_images(items, error):
    global image_labels, photo_refs, current_image_items

    for widget in images_results.inner.winfo_children():
        widget.destroy()

    current_image_items = items
    image_labels = []
    photo_refs = []

    if error:
        images_status.config(text="Image search failed")
        tk.Label(
            images_results.inner,
            text=error,
            bg=CARD,
            fg=ROSE,
            justify="left",
            wraplength=650,
            padx=14,
            pady=14,
        ).pack(fill="x")
        return

    if not items:
        images_status.config(text="No images were found.")
        return

    images_status.config(text=f"{len(items)} image result(s)  •  Select a preview to open it")
    photo_refs = [None] * len(items)

    for index, item in enumerate(items):
        card = tk.Frame(images_results.inner, bg=CARD, highlightthickness=1, highlightbackground="#38232d")
        card.grid(row=index // 2, column=index % 2, padx=(0, 9), pady=(0, 9), sticky="nsew")
        images_results.inner.grid_columnconfigure(index % 2, weight=1, uniform="image_cards")

        image_url = item.get("image") or item.get("thumbnail")
        page_url = item.get("url") or image_url

        preview = tk.Label(
            card,
            text="Loading preview...",
            width=34,
            height=9,
            bg="#321c28",
            fg=MUTED,
            cursor="hand2",
            font=(FONT, 9),
        )
        preview.pack(fill="x", padx=8, pady=(8, 7))
        preview.bind("<Button-1>", lambda event, u=image_url: open_url(u))
        image_labels.append(preview)

        title = str(item.get("title") or "Image result")
        tk.Label(
            card,
            text=title[:100],
            bg=CARD,
            fg=TEXT,
            wraplength=280,
            justify="left",
            font=(FONT, 9, "bold"),
        ).pack(anchor="w", padx=10, pady=(0, 7))

        tk.Button(
            card,
            text="OPEN RESULT  ↗",
            command=lambda u=page_url: open_url(u),
            bg="#3a202c",
            fg=ROSE,
            activebackground="#512535",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            font=(FONT, 8, "bold"),
            cursor="hand2",
        ).pack(anchor="w", padx=9, pady=(0, 9))

        threading.Thread(target=load_thumbnail, args=(item, index), daemon=True).start()


def set_thumbnail(index, image_data):
    if index >= len(image_labels) or index >= len(photo_refs):
        return
    try:
        picture = Image.open(BytesIO(image_data)).convert("RGB")
        picture.thumbnail((360, 205))
        photo = ImageTk.PhotoImage(picture)
        photo_refs[index] = photo
        image_labels[index].configure(image=photo, text="", width=1, height=1)
    except Exception:
        image_labels[index].configure(text="Preview unavailable")


# ---------------- OPTIONAL AVATAR ART ----------------

avatar_frames = []
avatar_frame_durations = []
avatar_frame_index = 0
avatar_photo = None


def load_avatar():
    """Load miko_avatar.gif (animated) or miko_avatar.png (static), if present."""
    global avatar_frames, avatar_frame_durations
    gif_path = os.path.join(BASE_DIR, "miko_avatar.gif")
    png_path = os.path.join(BASE_DIR, "miko_avatar.png")

    chosen_path = gif_path if os.path.isfile(gif_path) else png_path if os.path.isfile(png_path) else None
    if not chosen_path:
        return

    try:
        source = Image.open(chosen_path)
        frames = []
        durations = []
        iterator = ImageSequence.Iterator(source) if chosen_path.lower().endswith(".gif") else [source]

        for frame in iterator:
            frame_copy = frame.convert("RGBA")
            fitted = ImageOps.fit(frame_copy, (178, 222), method=Image.Resampling.LANCZOS)
            frames.append(ImageTk.PhotoImage(fitted))
            durations.append(max(80, int(frame.info.get("duration", 140))))
            if len(frames) >= 50:
                break

        if frames:
            avatar_frames = frames
            avatar_frame_durations = durations
            avatar_placeholder.destroy()
            animate_avatar(0)
    except Exception as exc:
        print("Miko avatar could not be loaded:", exc)


def animate_avatar(index):
    global avatar_frame_index, avatar_photo
    if not avatar_frames or not root.winfo_exists():
        return
    avatar_frame_index = index % len(avatar_frames)
    avatar_photo = avatar_frames[avatar_frame_index]
    avatar_label.configure(image=avatar_photo, text="")
    delay = avatar_frame_durations[avatar_frame_index]
    root.after(delay, lambda: animate_avatar(index + 1))


# ---------------- BACKGROUND SEARCH ----------------


def search_worker():
    results = []
    error = None

    try:
        results = tavily_search(query)
    except Exception as exc:
        error = str(exc)

    payload = {"query": query, "results": results, "error": error}
    try:
        output_folder = os.path.dirname(output_path)
        os.makedirs(output_folder, exist_ok=True)
        temp_path = output_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, output_path)
    except Exception as exc:
        error = "Could not save search results: " + str(exc)

    messages.put(("web", results, error))

    try:
        image_results = list(
            DDGS(timeout=20).images(
                query=query,
                region="us-en",
                safesearch="off",
                max_results=10,
            )
        )
        messages.put(("images", image_results, None))
    except Exception as exc:
        messages.put(("images", [], str(exc)))


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


# Set initial tab styles and start everything.
show_tab("web")
load_avatar()
threading.Thread(target=search_worker, daemon=True).start()
root.after(120, process_messages)
root.mainloop()
