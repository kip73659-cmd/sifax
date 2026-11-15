import os
import re
import shutil

PATH = r"C:\Users\sissi\Desktop\jarvis_voice2.py"
BACKUP = r"C:\Users\sissi\Desktop\jarvis_voice2_before_gpulimit.py"
NEW_LIMIT = 50

with open(PATH, encoding="utf-8") as f:
    text = f.read()

pattern = r"GPU_ON_PERCENT = \d+"

if not re.search(pattern, text):
    print("Could not find the GPU_ON_PERCENT line. Nothing was changed.")
else:
    if not os.path.exists(BACKUP):
        shutil.copy(PATH, BACKUP)
        print("Backed up to jarvis_voice2_before_gpulimit.py")
    text = re.sub(pattern, "GPU_ON_PERCENT = " + str(NEW_LIMIT), text, count=1)
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("Game mode limit set to", NEW_LIMIT)