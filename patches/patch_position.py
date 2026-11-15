import os
import shutil

PATH = r"C:\Users\sissi\Desktop\avatar.py"
BACKUP = r"C:\Users\sissi\Desktop\avatar_before_position.py"

with open(PATH, encoding="utf-8") as f:
    text = f.read()

OLD_DRAG = """label.bind("<Button-1>", start_drag)
label.bind("<B1-Motion>", do_drag)
"""

NEW_DRAG = """POS_FILE = os.path.join(FOLDER, "avatar_pos.txt")

def save_pos(e):
    with open(POS_FILE, "w") as f:
        f.write("%d,%d" % (root.winfo_x(), root.winfo_y()))

label.bind("<Button-1>", start_drag)
label.bind("<B1-Motion>", do_drag)
label.bind("<ButtonRelease-1>", save_pos)
"""

OLD_START = 'root.geometry("+100+100")\n'

NEW_START = """start_x, start_y = 100, 100
try:
    with open(POS_FILE) as f:
        a, b = f.read().strip().split(",")
        start_x, start_y = int(a), int(b)
except Exception:
    pass
root.geometry("+%d+%d" % (start_x, start_y))
"""

missing = []
if OLD_DRAG not in text:
    missing.append("the mouse drag lines")
if OLD_START not in text:
    missing.append("the start position line")

if missing:
    print("Could not find " + " and ".join(missing) + ". Nothing was changed.")
else:
    if not os.path.exists(BACKUP):
        shutil.copy(PATH, BACKUP)
        print("Backed up to avatar_before_position.py")
    text = text.replace(OLD_DRAG, NEW_DRAG)
    text = text.replace(OLD_START, NEW_START)
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print("Patched. She will remember her position.")