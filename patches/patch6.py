p = 'jarvis_voice2.py'
s = open(p, encoding='utf-8').read()

helper = '''def set_state(name):
    open('state.txt', 'w').write(name)

'''
s = s.replace('def wait_for_wake_word():', helper + 'def wait_for_wake_word():', 1)

s = s.replace("print('Waiting for wake word: Jarvis...')", "set_state('idle')\n    print('Waiting for wake word: Jarvis...')", 1)
s = s.replace("print('Listening... speak now')", "set_state('listening')\n    print('Listening... speak now')", 1)
s = s.replace("answer = try_open(question) or think(question)", "set_state('thinking')\n    answer = try_open(question) or think(question)", 1)
s = s.replace("asyncio.run(speak(answer))", "set_state('speaking')\n    asyncio.run(speak(answer))", 1)

open(p, 'w', encoding='utf-8').write(s)
print('Patched!')