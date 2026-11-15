import os
import shutil

desktop = r"C:\Users\sissi\Desktop"
src = os.path.join(desktop, "jarvis_voice2.py")
bak = os.path.join(desktop, "jarvis_voice2_before_gamemode.py")

if not os.path.exists(bak):
    shutil.copy(src, bak)
    print("Backed up to jarvis_voice2_before_gamemode.py")

with open(src, encoding="utf-8") as f:
    code = f.read()

if "GAME_MODE" in code:
    raise SystemExit("Game mode is already installed. Nothing changed.")

# 1) Add the watcher after the BRAIN / VOICE lines
old_head = "VOICE = 'en-US-JennyNeural'\n"
new_head = old_head + '''
import threading, time, subprocess

GAME_MODE = [False]
BUSY = [False]
GPU_ON_PERCENT = 12
GPU_CMD = ('(Get-Counter "\\\\GPU Engine(*engtype_3D)\\\\Utilization Percentage")'
           '.CounterSamples | Measure-Object CookedValue -Sum | '
           'Select-Object -ExpandProperty Sum')

def gpu_load():
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-Command', GPU_CMD],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return float(out.replace(',', '.'))
    except Exception:
        return 0.0

def game_watcher():
    high = 0
    low = 0
    while True:
        time.sleep(3)
        if BUSY[0]:
            continue
        load = gpu_load()
        if load > GPU_ON_PERCENT:
            high += 1
            low = 0
        else:
            low += 1
            high = 0
        if not GAME_MODE[0] and high >= 4:
            GAME_MODE[0] = True
            try:
                ollama.generate(model=BRAIN, prompt='', keep_alive=0)
            except Exception:
                pass
            print('Game mode ON (CPU only)')
        elif GAME_MODE[0] and low >= 7:
            GAME_MODE[0] = False
            try:
                ollama.generate(model=BRAIN, prompt='', keep_alive=0)
            except Exception:
                pass
            print('Game mode OFF (GPU)')

def ollama_options():
    return {'num_gpu': 0} if GAME_MODE[0] else {}

threading.Thread(target=game_watcher, daemon=True).start()
'''
code = code.replace(old_head, new_head, 1)

# 2) Make both Ollama calls respect game mode
count = code.count("think=False,")
code = code.replace("think=False,", "think=False,\n            options=ollama_options(),")

# 3) Mark Jarvis as busy while he answers, so his own load is ignored
old_think = "            answer = try_open(question) or think(question)\n"
new_think = ("            BUSY[0] = True\n"
             "            answer = try_open(question) or think(question)\n"
             "            BUSY[0] = False\n")
code = code.replace(old_think, new_think, 1)

with open(src, "w", encoding="utf-8") as f:
    f.write(code)

print("Patched jarvis_voice2.py (changed", count, "Ollama calls)")