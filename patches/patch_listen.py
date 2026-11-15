import os
import re
import shutil

desktop = r"C:\Users\sissi\Desktop"
src = os.path.join(desktop, "jarvis_voice2.py")
bak = os.path.join(desktop, "jarvis_voice2_before_listen.py")

if not os.path.exists(bak):
    shutil.copy(src, bak)
    print("Backed up to jarvis_voice2_before_listen.py")

with open(src, encoding="utf-8") as f:
    code = f.read()

if "# LISTEN_ALERTS" in code:
    raise SystemExit("Already installed. Nothing changed.")

pat = re.compile(r"^([ \t]+)data, _ = stream\.read\(chunk\)[ \t]*\r?\n", re.M)
m = pat.search(code)
if not m:
    raise SystemExit("Could not find the spot. Nothing changed.")

ind = m.group(1)
add = ind + "if PENDING_ALERTS and not started:  # LISTEN_ALERTS\n" + ind + "    break\n"
code = code[:m.end()] + add + code[m.end():]

with open(src, "w", encoding="utf-8") as f:
    f.write(code)

print("Patched. Restart Jarvis.")