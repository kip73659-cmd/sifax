p = 'jarvis_voice2.py'
s = open(p, encoding='utf-8').read()
s = s.replace("BRAIN = 'qwen3.5:0.8b'", "BRAIN = 'qwen3.5:4b'")
open(p, 'w', encoding='utf-8').write(s)
print('Patched!')