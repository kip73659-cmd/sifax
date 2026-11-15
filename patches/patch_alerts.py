import os
import re
import shutil

desktop = r"C:\Users\sissi\Desktop"
src = os.path.join(desktop, "jarvis_voice2.py")
bak = os.path.join(desktop, "jarvis_voice2_before_alerts.py")

if not os.path.exists(bak):
    shutil.copy(src, bak)
    print("Backed up to jarvis_voice2_before_alerts.py")

with open(src, encoding="utf-8") as f:
    code = f.read()

if "# WAKE_ALERTS" in code:
    raise SystemExit("Already installed. Nothing changed.")

pat = re.compile(r"^([ \t]+)clip = sd\.rec\(32000", re.M)
m = pat.search(code)
if not m:
    raise SystemExit("Could not find the spot. Nothing changed.")

ind = m.group(1)
add = (ind + "while PENDING_ALERTS:  # WAKE_ALERTS\n" +
       ind + "    set_state('speaking')\n" +
       ind + "    asyncio.run(speak(PENDING_ALERTS.pop(0)))\n" +
       ind + "    set_state('idle')\n")
code = code[:m.start()] + add + code[m.start():]

with open(src, "w", encoding="utf-8") as f:
    f.write(code)

print("Patched. Restart Jarvis.")