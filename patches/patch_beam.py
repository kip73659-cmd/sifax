import shutil

p = 'jarvis_voice2.py'
shutil.copy(p, 'jarvis_voice2_before_beam.py')
s = open(p, encoding='utf-8').read()

if 'beam_size=5' not in s:
    raise SystemExit('Could not find beam_size=5. Nothing changed.')

s = s.replace('beam_size=5', 'beam_size=1', 1)
open(p, 'w', encoding='utf-8').write(s)
print('Patched! Restart Miko.')