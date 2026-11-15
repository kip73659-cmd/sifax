import os
import shutil

desktop = r"C:\Users\sissi\Desktop"
src = os.path.join(desktop, "jarvis_voice2.py")
bak = os.path.join(desktop, "jarvis_voice2_before_ears.py")

if not os.path.exists(bak):
    shutil.copy(src, bak)
    print("Backed up to jarvis_voice2_before_ears.py")

with open(src, encoding="utf-8") as f:
    code = f.read()

if "ears_big" in code:
    raise SystemExit("Already installed. Nothing changed.")

old_load = "ears = WhisperModel('small.en', device='cpu', compute_type='int8')"
old_listen = "    segments, info = ears.transcribe(audio, language='en', initial_prompt='Jarvis')"

if old_load not in code or old_listen not in code:
    raise SystemExit("Could not find the lines. Nothing changed.")

code = code.replace(old_load, old_load + "\nears_big = WhisperModel('medium.en', device='cpu', compute_type='int8')", 1)
code = code.replace(old_listen, "    segments, info = ears_big.transcribe(audio, language='en', initial_prompt='Miko, Jarvis', beam_size=5)", 1)

with open(src, "w", encoding="utf-8") as f:
    f.write(code)

print("Patched. Restart Miko. The first start downloads the medium model, so wait a few minutes.")