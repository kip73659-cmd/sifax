p = 'jarvis_voice2.py'
s = open(p, encoding='utf-8').read()

old = "    os.startfile('reply.mp3')"
new = """    import pygame
    pygame.mixer.init()
    pygame.mixer.music.load('reply.mp3')
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.1)
    pygame.mixer.music.unload()
    pygame.mixer.quit()"""
s = s.replace(old, new, 1)

open(p, 'w', encoding='utf-8').write(s)
print('Patched!')