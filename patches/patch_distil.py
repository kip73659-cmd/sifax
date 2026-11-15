import os
import shutil

PATH = r"C:\Users\sissi\Desktop\jarvis_voice2.py"
BACKUP = r"C:\Users\sissi\Desktop\jarvis_voice2_before_distil.py"

with open(PATH, encoding="utf-8") as f:
    text = f.read()

OLD = "ears_big = WhisperModel('medium.en', device='cpu', compute_type='int8')"
NEW = "ears_big = WhisperModel('distil-medium.en', device='cpu', compute_type='int8')"

if OLD not in text:
    print("Could not find the ears_big line. Nothing was changed.")
else:
    if not os.path.exists(BACKUP):
        shutil.copy(PATH, BACKUP)
        print("Backed up to jarvis_voice2_before_distil.py")
    text = text.replace(OLD, NEW)
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("Changed to distil-medium.en. Start Jarvis and wait for the download.")