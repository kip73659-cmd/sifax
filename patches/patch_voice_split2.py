import os
import shutil

PATH = r"C:\Users\sissi\Desktop\jarvis_voice2.py"
BACKUP = r"C:\Users\sissi\Desktop\jarvis_voice2_before_voicesplit.py"

with open(PATH, encoding="utf-8") as f:
    text = f.read()

OLD_MAKE = "    await edge_tts.Communicate(text, VOICE, pitch='+6Hz', rate='+5%').save('reply.mp3')\n"

NEW_MAKE = (
    "    _m0 = _t.time()\n"
    "    await edge_tts.Communicate(text, VOICE, pitch='+6Hz', rate='+5%').save('reply.mp3')\n"
    "    print('MAKE took', round(_t.time() - _m0, 1), 'sec')\n"
    "    _p0 = _t.time()\n"
)

OLD_END = "    pygame.mixer.quit()\n"

NEW_END = (
    "    pygame.mixer.quit()\n"
    "    print('PLAY took', round(_t.time() - _p0, 1), 'sec')\n"
)

missing = []
if OLD_MAKE not in text:
    missing.append("the edge_tts line in speak()")
if text.count(OLD_END) != 1:
    missing.append("the pygame.mixer.quit() line in speak()")
if "import time as _t" not in text:
    missing.append("the earlier timing patch (import time as _t)")

if missing:
    print("Could not find: " + ", ".join(missing) + ". Nothing was changed.")
else:
    if not os.path.exists(BACKUP):
        shutil.copy(PATH, BACKUP)
        print("Backed up to jarvis_voice2_before_voicesplit.py")
    text = text.replace(OLD_MAKE, NEW_MAKE)
    text = text.replace(OLD_END, NEW_END)
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("Patched. MAKE and PLAY times will print after each answer.")