import os
import shutil

desktop = r"C:\Users\sissi\Desktop"
src = os.path.join(desktop, "jarvis_voice2.py")
bak = os.path.join(desktop, "jarvis_voice2_before_speed.py")

if not os.path.exists(bak):
    shutil.copy(src, bak)
    print("Backed up to jarvis_voice2_before_speed.py")

with open(src, encoding="utf-8") as f:
    code = f.read()

old1 = """        low = question.lower().strip(' .!?')
"""
new1 = """        low = question.lower().strip(' .!?')
        check_memory = False
"""

old2 = """            answer = try_open(question) or think(question)
            fact = auto_remember(question)
            if fact:
                save_memory(fact)
                answer = answer + ' I will remember that.'
        print('Jarvis:', answer)
        set_state('speaking')
        asyncio.run(speak(answer))
"""
new2 = """            answer = try_open(question) or think(question)
            check_memory = True
        print('Jarvis:', answer)
        set_state('speaking')
        asyncio.run(speak(answer))
        if check_memory:
            fact = auto_remember(question)
            if fact:
                save_memory(fact)
"""

if old1 not in code or old2 not in code:
    print("Could not find the blocks. Nothing was changed.")
else:
    code = code.replace(old1, new1).replace(old2, new2)
    with open(src, "w", encoding="utf-8") as f:
        f.write(code)
    print("Patched jarvis_voice2.py")