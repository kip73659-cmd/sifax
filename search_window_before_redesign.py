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


def tavily_search(query):
    key_path = os.path.join(BASE_DIR, "tavily_key.txt")

    with open(key_path, "r", encoding="utf-8") as f:
        key = f.read().strip()

    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": key,
            "query": query,
            "max_results": 6
        },
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


# ---------------- WINDOW ----------------

root = tk.Tk()
root.title("Miko - Anime Universal Search")
root.geometry("1050x760+120+50")
root.minsize(650, 450)
root.attributes("-topmost", True)
root.configure(bg="#171323")

tk.Label(
    root,
    text="✦ MIKO'S DREAM SEARCH ✦",
    font=("Segoe UI", 19, "bold"),
    fg="#e6b8ff",
    bg="#171323"
).pack(anchor="w", padx=18, pady=(14, 3))

tk.Label(
    root,
    text=query,
    font=("Segoe UI", 12),
    fg="white",
    bg="#171323",
    wraplength=800,
    justify="left"
).pack(anchor="w", padx=18, pady=(2, 12))


# ---------------- TABS ----------------

style = ttk.Style()
style.theme_use("clam")
style.configure("TNotebook", background="#1e1e2e", borderwidth=0)
style.configure(
    "TNotebook.Tab",
    background="#30213f",
    foreground="white",
    padding=(20, 9),
    font=("Segoe UI", 10, "bold")
)
style.map(
    "TNotebook.Tab",
    background=[("selected", "#45475a")],
    foreground=[("selected", "#cba6f7")]
)

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True, padx=14, pady=(0, 14))

web_tab = tk.Frame(notebook, bg="#171323")
images_tab = tk.Frame(notebook, bg="#171323")

notebook.add(web_tab, text="🌐 WEB")
notebook.add(images_tab, text="🌸 IMAGES")


# ---------------- WEB TAB ----------------

web_status = tk.Label(
    web_tab,
    text="Preparing web search...",
    bg="#171323",
    fg="#a6adc8"
)
web_status.pack(anchor="w", padx=10, pady=8)

web_frame = tk.Frame(web_tab, bg="#171323")
web_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

web_scroll = ttk.Scrollbar(web_frame)
web_scroll.pack(side="right", fill="y")

web_box = tk.Text(
    web_frame,
    wrap="word",
    font=("Segoe UI", 11),
    fg="#e6e6e6",
    bg="#2a2a3d",
    bd=0,
    padx=12,
    pady=10,
    yscrollcommand=web_scroll.set
)
web_box.pack(side="left", fill="both", expand=True)
web_scroll.config(command=web_box.yview)

web_box.tag_config(
    "title",
    foreground="#89b4fa",
    font=("Segoe UI", 12, "bold")
)


def show_web_results(results, error):
    web_box.config(state="normal")
    web_box.delete("1.0", "end")

    if error:
        web_box.insert("end", "Search issue:\n" + error + "\n\n")

    if not results and not error:
        web_box.insert("end", "No web results were found.")

    for index, item in enumerate(results):
        web_box.insert("end", item.get("title", "") + "\n", "title")
        web_box.insert("end", item.get("body", "") + "\n")

        url = item.get("href", "")
        if url:
            tag = "link_" + str(index)
            web_box.insert("end", url + "\n\n", tag)
            web_box.tag_config(tag, foreground="#a6e3a1")
            web_box.tag_bind(
                tag,
                "<Button-1>",
                lambda event, u=url: open_url(u)
            )

    web_box.config(state="disabled")
    web_status.config(text="Web search complete")


# ---------------- IMAGES TAB ----------------

images_status = tk.Label(
    images_tab,
    text="Searching for pictures...",
    bg="#171323",
    fg="#a6adc8"
)
images_status.pack(anchor="w", padx=10, pady=8)

image_frame = tk.Frame(images_tab, bg="#171323")
image_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

image_canvas = tk.Canvas(
    image_frame,
    bg="#171323",
    highlightthickness=0
)
image_scroll = ttk.Scrollbar(
    image_frame,
    orient="vertical",
    command=image_canvas.yview
)

image_scroll.pack(side="right", fill="y")
image_canvas.pack(side="left", fill="both", expand=True)
image_canvas.configure(yscrollcommand=image_scroll.set)

image_inner = tk.Frame(image_canvas, bg="#171323")
canvas_window = image_canvas.create_window(
    (0, 0),
    window=image_inner,
    anchor="nw"
)

image_labels = []
photo_refs = []


def update_scroll(event=None):
    image_canvas.configure(
        scrollregion=image_canvas.bbox("all")
    )


def resize_canvas(event):
    image_canvas.itemconfigure(
        canvas_window,
        width=event.width
    )


image_inner.bind("<Configure>", update_scroll)
image_canvas.bind("<Configure>", resize_canvas)


def load_thumbnail(item, index):
    url = item.get("thumbnail") or item.get("image")

    try:
        if not url:
            raise ValueError("No thumbnail URL")

        response = requests.get(
            url,
            timeout=15,
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
        images_status.config(text="Image search failed: " + error)
        return

    if not items:
        images_status.config(text="No images were found.")
        return

    images_status.config(
        text=str(len(items)) + " image results. Click a picture to open it."
    )

    photo_refs = [None] * len(items)

    for index, item in enumerate(items):
        card = tk.Frame(
            image_inner,
            bg="#30213f",
            padx=8,
            pady=8
        )
        card.grid(
            row=index // 3,
            column=index % 3,
            padx=7,
            pady=7,
            sticky="n"
        )

        image_url = item.get("image") or item.get("thumbnail")
        page_url = item.get("url") or image_url

        preview = tk.Label(
            card,
            text="Loading preview...",
            width=32,
            height=9,
            bg="#49335f",
            fg="white",
            cursor="hand2"
        )
        preview.pack(pady=(0, 7))
        preview.bind(
            "<Button-1>",
            lambda event, u=image_url: open_url(u)
        )

        image_labels.append(preview)

        title = str(item.get("title", "Image result"))

        tk.Label(
            card,
            text=title[:100],
            bg="#30213f",
            fg="white",
            wraplength=270,
            justify="left",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=3)

        tk.Button(
            card,
            text="Open result",
            command=lambda u=page_url: open_url(u),
            bg="#585b70",
            fg="white",
            activebackground="#6c7086",
            activeforeground="white",
            relief="flat",
            padx=12,
            pady=4
        ).pack(anchor="w", pady=(5, 0))

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
        picture.thumbnail((300, 190))

        photo = ImageTk.PhotoImage(picture)
        photo_refs[index] = photo

        image_labels[index].configure(
            image=photo,
            text="",
            width=260,
            height=160
        )

    except Exception:
        image_labels[index].config(text="Preview unavailable")


# ---------------- BACKGROUND SEARCH ----------------

def search_worker():
    results = []
    error = None

    try:
        results = tavily_search(query)
    except Exception as e:
        error = str(e)

    payload = {
        "query": query,
        "results": results,
        "error": error
    }

    # Save JSON into the correct folder or the exact path
    # supplied by Miko's main assistant.
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
                    image_labels[data].config(text="Preview unavailable")

    except Empty:
        pass

    if root.winfo_exists():
        root.after(120, process_messages)


threading.Thread(
    target=search_worker,
    daemon=True
).start()

root.after(120, process_messages)
root.mainloop()

