import os
import shutil

desktop = r"C:\Users\sissi\Desktop"
src = os.path.join(desktop, "avatar.py")
bak = os.path.join(desktop, "avatar_backup.py")

if os.path.exists(src) and not os.path.exists(bak):
    shutil.copy(src, bak)
    print("Backed up avatar.py to avatar_backup.py")

NEW = r'''
import os
import tkinter as tk
from PIL import Image, ImageTk

FOLDER = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(FOLDER, "state.txt")
STATES = ["idle", "listening", "thinking", "speaking"]
KEY = "#010203"   # this color becomes see-through
MAX_HEIGHT = 450  # change this to make the girl bigger or smaller

root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.attributes("-transparentcolor", KEY)
root.config(bg=KEY)

images = {}
for name in STATES:
    path = os.path.join(FOLDER, name + ".png")
    if not os.path.exists(path):
        continue
    img = Image.open(path).convert("RGBA")
    scale = MAX_HEIGHT / img.height
    img = img.resize((int(img.width * scale), MAX_HEIGHT), Image.LANCZOS)
    flat = Image.new("RGBA", img.size, KEY)
    flat.alpha_composite(img)
    images[name] = ImageTk.PhotoImage(flat.convert("RGB"))

if "idle" not in images:
    with open(os.path.join(FOLDER, "avatar_error.txt"), "w") as f:
        f.write("idle.png not found on the Desktop")
    raise SystemExit

label = tk.Label(root, bg=KEY, bd=0, highlightthickness=0)
label.pack()

current = [None]

def update():
    try:
        with open(STATE_FILE) as f:
            state = f.read().strip().lower()
    except Exception:
        state = "idle"
    if state not in images:
        state = "idle"
    if state != current[0]:
        label.config(image=images[state])
        current[0] = state
    root.after(200, update)

drag = {"x": 0, "y": 0}

def start_drag(e):
    drag["x"] = e.x
    drag["y"] = e.y

def do_drag(e):
    x = root.winfo_x() + e.x - drag["x"]
    y = root.winfo_y() + e.y - drag["y"]
    root.geometry("+%d+%d" % (x, y))

label.bind("<Button-1>", start_drag)
label.bind("<B1-Motion>", do_drag)
label.bind("<Button-3>", lambda e: root.destroy())  # right-click closes

root.geometry("+100+100")
update()
root.mainloop()
'''

with open(src, "w", encoding="utf-8") as f:
    f.write(NEW.lstrip())

print("New avatar.py written.")