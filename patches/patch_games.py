import os
import re
import shutil

desktop = r"C:\Users\sissi\Desktop"
src = os.path.join(desktop, "jarvis_tools.py")
bak = os.path.join(desktop, "jarvis_tools_before_games.py")

if not os.path.exists(bak):
    shutil.copy(src, bak)
    print("Backed up to jarvis_tools_before_games.py")

with open(src, encoding="utf-8") as f:
    code = f.read()

if "GAME_SHORTCUTS" in code:
    raise SystemExit("Already installed. Nothing changed.")

NEW_TOP = '''import os
import subprocess

GAME_SHORTCUTS = {
    'counter-strike 2': 'Counter-Strike 2.url',
    'counter strike': 'Counter-Strike 2.url',
    'cs2': 'Counter-Strike 2.url',
    'cs 2': 'Counter-Strike 2.url',
    'deadlock': 'Deadlock.url',
    'fortnite': 'Fortnite.url',
    'league of legends': 'League of Legends.url',
    'league': 'League of Legends.url',
    'monster hunter': 'MONSTER HUNTER RISE.url',
    'overwatch': 'Overwatch\\u00ae.url',
    'rocket league': 'Rocket League\\u00ae.url',
    'outlast': 'The Outlast Trials.url',
}

def find_game_link(name):
    for key, filename in GAME_SHORTCUTS.items():
        if key in name:
            folders = [os.path.join(os.environ['USERPROFILE'], 'OneDrive', 'Desktop'),
                       os.path.join(os.environ['USERPROFILE'], 'Desktop')]
            for folder in folders:
                path = os.path.join(folder, filename)
                if os.path.exists(path):
                    with open(path, encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            if line.startswith('URL='):
                                return line[4:].strip()
    return None

'''

code = code.replace("def try_open(q):", NEW_TOP + "def try_open(q):", 1)

pattern = re.compile(r"^([ \t]+)name = q\.split\('open ', 1\)\[1\]\.strip\(' \.!\?'\)[ \t]*\r?\n", re.M)
m = pattern.search(code)
if not m:
    raise SystemExit("Could not find the right spot. Nothing changed.")

ind = m.group(1)
extra = (ind + "link = find_game_link(name)\n" +
         ind + "if link:\n" +
         ind + ind + "os.startfile(link)\n" +
         ind + ind + "return 'Opening ' + name\n")
code = code[:m.end()] + extra + code[m.end():]

with open(src, "w", encoding="utf-8") as f:
    f.write(code)

print("Patched jarvis_tools.py")