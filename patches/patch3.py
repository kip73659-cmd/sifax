import re

p = 'jarvis_voice2.py'
s = open(p, encoding='utf-8').read()

new_listen = '''def listen():
    import numpy as np
    print('Listening... speak now')
    chunk = 1600
    threshold = 0.01
    silence_limit = 12
    max_chunks = 300
    frames = []
    started = False
    quiet = 0
    with sd.InputStream(samplerate=16000, channels=1, dtype='float32', device=1) as stream:
        for _ in range(max_chunks):
            data, _ = stream.read(chunk)
            loud = float(np.abs(data).mean()) > threshold
            if loud:
                started = True
                quiet = 0
            elif started:
                quiet += 1
            if started:
                frames.append(data)
            if started and quiet >= silence_limit:
                break
    if not frames:
        return ''
    audio = np.concatenate(frames).flatten()
    segments, info = ears.transcribe(audio, language='en', initial_prompt='Discord, Steam, Brave, Jarvis, Notepad, Spotify')
    return ' '.join(x.text for x in segments).strip()

'''

s = re.sub(r"def listen\(\):.*?(?=def think)", lambda m: new_listen, s, count=1, flags=re.S)
open(p, 'w', encoding='utf-8').write(s)
print('Patched!')