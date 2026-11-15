p = 'jarvis_voice2.py'
s = open(p, encoding='utf-8').read()
s = s.replace("initial_prompt='Discord, Steam, Brave, Jarvis, Notepad, Spotify'", "initial_prompt='Jarvis'")
open(p, 'w', encoding='utf-8').write(s)
print('Patched!')