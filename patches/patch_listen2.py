import os
import re
import shutil

desktop = r"C:\Users\sissi\Desktop"
src = os.path.join(desktop, "jarvis_voice2.py")
bak = os.path.join(desktop, "jarvis_voice2_before_listen2.py")

if not os.path.exists(bak):
    shutil.copy(src, bak)
    print("Backed up to jarvis_voice2_before_listen2.py")

with open(src, encoding="utf-8") as f:
    code = f.read()

if "# LISTEN_ALERTS2" in code:
    raise SystemExit("Already installed. Nothing changed.")

pat = re.compile(r"^([ \t]+)print\('You said:', question\)[ \t]*\r?\n", re.M)
m = pat.search(code)
if not m:
    raise SystemExit("Could not find the spot. Nothing changed.")

ind = m.group(1)
add = (ind + "while PENDING_ALERTS:  # LISTEN_ALERTS2\n" +
       ind + "    set_state('speaking')\n" +
       ind + "    asyncio.run(speak(PENDING_ALERTS.pop(0)))\n" +
       ind + "    set_state('idle')\n")
code = code[:m.start()] + add + code[m.start():]

with open(src, "w", encoding="utf-8") as f:
    f.write(code)

print("Patched. Restart Jarvis.")