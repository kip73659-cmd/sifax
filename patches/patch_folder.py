import os
import shutil

desktop = r"C:\Users\sissi\Desktop"
dest = os.path.join(desktop, "Miko")
os.makedirs(dest, exist_ok=True)
os.makedirs(os.path.join(dest, "backups"), exist_ok=True)
os.makedirs(os.path.join(dest, "patches"), exist_ok=True)

files = [
    "jarvis_voice2.py", "jarvis_tools.py", "avatar.py",
    "start_jarvis.bat", "state.txt", "jarvis_memory.txt",
    "idle.png", "listening.png", "thinking.png", "speaking.png",
]

for name in files:
    src = os.path.join(desktop, name)
    if os.path.exists(src):
        shutil.copy2(src, dest)
        print("Copied", name)
    else:
        print("Not found, skipped:", name)

for name in os.listdir(desktop):
    if "_before_" in name or name.endswith("_backup.py") or name == "jarvis_voice2_wake.py":
        shutil.copy2(os.path.join(desktop, name), os.path.join(dest, "backups"))
        print("Backup copied", name)
    elif name.startswith("patch") and name.endswith(".py"):
        shutil.copy2(os.path.join(desktop, name), os.path.join(dest, "patches"))
        print("Patch copied", name)

model_src = os.path.join(desktop, "model")
if os.path.isdir(model_src):
    shutil.copytree(model_src, os.path.join(dest, "model"), dirs_exist_ok=True)
    print("Copied model folder")

for name in os.listdir(desktop):
    lower = name.lower()
    if "note" in lower and lower.endswith((".txt", ".md", ".docx")):
        shutil.copy2(os.path.join(desktop, name), dest)
        print("Copied notes:", name)

print("Done! Your project is in", dest)