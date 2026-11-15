import os
import shutil

desktop = r"C:\Users\sissi\Desktop"
src = os.path.join(desktop, "jarvis_voice2.py")
bak = os.path.join(desktop, "jarvis_voice2_before_voice.py")

if not os.path.exists(bak):
    shutil.copy(src, bak)
    print("Backed up to jarvis_voice2_before_voice.py")

with open(src, encoding="utf-8") as f:
    code = f.read()

old_voice = "VOICE = 'en-US-JennyNeural'"
old_call = "edge_tts.Communicate(text, VOICE)"

if old_voice not in code or old_call not in code:
    raise SystemExit("Could not find the voice lines. Nothing changed.")

code = code.replace(old_voice, "VOICE = 'en-US-AvaNeural'", 1)
code = code.replace(old_call, "edge_tts.Communicate(text, VOICE, pitch='+6Hz', rate='+5%')", 1)

with open(src, "w", encoding="utf-8") as f:
    f.write(code)

print("Patched. Restart Jarvis.")import os
import re
import shutil

desktop = r"C:\Users\sissi\Desktop"
src = os.path.join(desktop, "jarvis_voice2.py")
bak = os.path.join(desktop, "jarvis_voice2_before_wake.py")

if not os.path.exists(bak):
    shutil.copy(src, bak)
    print("Backed up to jarvis_voice2_before_wake.py")

with open(src, encoding="utf-8") as f:
    code = f.read()

if "# NEW_WAKE" in code:
    raise SystemExit("Already installed. Nothing changed.")

pat = re.compile(r"^def wait_for_wake_word\(\):.*?(?=^def listen\(\):)", re.S | re.M)
if not pat.search(code):
    raise SystemExit("Could not find the wake word function. Nothing changed.")

NEW = '''def wait_for_wake_word():  # NEW_WAKE
    import numpy as np
    set_state('idle')
    print('Waiting for wake word: Miko...')
    WAKE_WORDS = ['miko', 'mico', 'mica', 'meeko', 'mikko', 'nico', 'micro', 'jarvis']
    rate = 16000
    window = np.zeros(rate * 2, dtype='float32')
    new_samples = 0
    with sd.InputStream(samplerate=rate, channels=1, dtype='float32', device=1) as stream:
        while True:
            while PENDING_ALERTS:
                set_state('speaking')
                asyncio.run(speak(PENDING_ALERTS.pop(0)))
                set_state('idle')
            data, _ = stream.read(8000)
            data = data.flatten()
            window = np.concatenate([window[len(data):], data])
            new_samples += len(data)
            if new_samples < rate:
                continue
            new_samples = 0
            if float(np.abs(window).mean()) < 0.004:
                continue
            segs, _ = ears.transcribe(window, language='en', initial_prompt='Miko, Jarvis')
            heard = ' '.join(x.text for x in segs).lower()
            if any(w in heard for w in WAKE_WORDS):
                return

'''

code = pat.sub(lambda m: NEW, code, count=1)

with open(src, "w", encoding="utf-8") as f:
    f.write(code)

print("Patched. Restart Jarvis.")