p = 'jarvis_voice2.py'
s = open(p, encoding='utf-8').read()

func = '''def wait_for_wake_word():
    print('Waiting for wake word: Jarvis...')
    while True:
        clip = sd.rec(32000, samplerate=16000, channels=1, dtype='float32', device=1)
        sd.wait()
        segs, _ = ears.transcribe(clip.flatten(), language='en', initial_prompt='Jarvis')
        heard = ' '.join(x.text for x in segs).lower()
        if 'jarvis' in heard:
            return

'''

s = s.replace('def listen():', func + 'def listen():', 1)
s = s.replace("input('Press Enter, then speak for 5 seconds...')", 'wait_for_wake_word()')
open(p, 'w', encoding='utf-8').write(s)
print('Patched!')