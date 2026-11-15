import shutil

p = 'jarvis_voice2.py'
shutil.copy(p, 'jarvis_voice2_before_timing.py')
s = open(p, encoding='utf-8').read()

if 'import time as _t' in s:
    raise SystemExit('Already installed. Nothing changed.')

s = 'import time as _t\n' + s

a = "segments, info = ears_big.transcribe("
if a in s:
    s = s.replace(a, "_t0 = _t.time()\n    segments, info = ears_big.transcribe(", 1)
    s = s.replace("    return ' '.join(x.text for x in segments).strip()", "    _txt = ' '.join(x.text for x in segments).strip()\n    print('EARS took', round(_t.time() - _t0, 1), 'sec')\n    return _txt", 1)

b = "answer = try_open(question) or think(question)"
if b in s:
    s = s.replace(b, "_t1 = _t.time()\n    answer = try_open(question) or think(question)\n    print('BRAIN took', round(_t.time() - _t1, 1), 'sec')", 1)

c = "asyncio.run(speak(answer))"
if c in s:
    s = s.replace(c, "_t2 = _t.time()\n    asyncio.run(speak(answer))\n    print('VOICE took', round(_t.time() - _t2, 1), 'sec')", 1)

open(p, 'w', encoding='utf-8').write(s)
print('Patched! Restart Miko.')