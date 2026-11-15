import os
import shutil

PATH = r"C:\Users\sissi\Desktop\jarvis_voice2.py"
BACKUP = r"C:\Users\sissi\Desktop\jarvis_voice2_before_chat.py"

with open(PATH, encoding="utf-8") as f:
    text = f.read()

OLD_THINK = """def think(question):
    reply = ollama.chat(
        model=BRAIN,
        messages=[
            {'role': 'system', 'content': 'You are Jarvis, a friendly assistant. Answer in one or two short sentences.'},
            {'role': 'user', 'content': question},
        ],
        think=False,
    )
    return reply['message']['content']
"""

NEW_THINK = """HISTORY = []
MAX_HISTORY = 10

def think(question):
    HISTORY.append({'role': 'user', 'content': question})
    del HISTORY[:-MAX_HISTORY]
    reply = ollama.chat(
        model=BRAIN,
        messages=[
            {'role': 'system', 'content': 'You are Jarvis, a friendly assistant. Answer in one or two short sentences.'},
        ] + HISTORY,
        think=False,
    )
    answer = reply['message']['content']
    HISTORY.append({'role': 'assistant', 'content': answer})
    del HISTORY[:-MAX_HISTORY]
    return answer
"""

OLD_LOOP = """while True:
    wait_for_wake_word()
    question = listen()
    print('You said:', question)
    if not question:
        continue
    set_state('thinking')
    answer = try_open(question) or think(question)
    print('Jarvis:', answer)
    set_state('speaking')
    asyncio.run(speak(answer))
"""

NEW_LOOP = """STOP_WORDS = ['stop', 'go to sleep', 'goodbye', 'turn off']

def wants_to_stop(q):
    q = q.lower()
    return any(w in q for w in STOP_WORDS)

while True:
    wait_for_wake_word()
    while True:
        question = listen()
        print('You said:', question)
        if not question:
            continue
        if wants_to_stop(question):
            set_state('speaking')
            asyncio.run(speak('Okay, going to sleep.'))
            HISTORY.clear()
            set_state('idle')
            break
        set_state('thinking')
        answer = try_open(question) or think(question)
        print('Jarvis:', answer)
        set_state('speaking')
        asyncio.run(speak(answer))
"""

missing = []
if OLD_THINK not in text:
    missing.append("the think() function")
if OLD_LOOP not in text:
    missing.append("the main loop at the bottom")

if missing:
    print("Could not find " + " and ".join(missing) + ". Nothing was changed.")
else:
    if not os.path.exists(BACKUP):
        shutil.copy(PATH, BACKUP)
        print("Backed up to jarvis_voice2_before_chat.py")
    text = text.replace(OLD_THINK, NEW_THINK)
    text = text.replace(OLD_LOOP, NEW_LOOP)
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print("Patched. Continuous chat and memory are on.")