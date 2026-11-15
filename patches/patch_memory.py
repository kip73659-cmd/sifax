import os
import shutil

PATH = r"C:\Users\sissi\Desktop\jarvis_voice2.py"
BACKUP = r"C:\Users\sissi\Desktop\jarvis_voice2_before_memory.py"

with open(PATH, encoding="utf-8") as f:
    text = f.read()

OLD_THINK = """HISTORY = []
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
"""

NEW_THINK = """HISTORY = []
MAX_HISTORY = 10
MEMORY_FILE = r'C:\\Users\\sissi\\Desktop\\jarvis_memory.txt'

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def save_memory(fact):
    with open(MEMORY_FILE, 'a', encoding='utf-8') as f:
        f.write(fact.strip() + '\\n')

def forget_last():
    facts = load_memory()
    if not facts:
        return False
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        for fact in facts[:-1]:
            f.write(fact + '\\n')
    return True

def forget_all():
    open(MEMORY_FILE, 'w').close()

def auto_remember(question):
    try:
        r = ollama.chat(
            model=BRAIN,
            messages=[
                {'role': 'system', 'content': 'You decide if a spoken sentence contains a lasting personal fact about the speaker worth remembering for months, like their name, family, pets, job, preferences or plans. Ordinary questions and small talk are NOT worth remembering. If it is worth remembering, reply with only the fact written as one short sentence about the user. Otherwise reply with only the word NO.'},
                {'role': 'user', 'content': question},
            ],
            think=False,
        )
        out = r['message']['content'].strip()
    except Exception:
        return None
    if not out or out.upper().startswith('NO') or len(out) > 150:
        return None
    return out

def think(question):
    HISTORY.append({'role': 'user', 'content': question})
    del HISTORY[:-MAX_HISTORY]
    facts = load_memory()
    system = 'You are Jarvis, a friendly assistant. Answer in one or two short sentences.'
    if facts:
        system += ' Things you know about the user: ' + ' '.join(facts)
    reply = ollama.chat(
        model=BRAIN,
        messages=[
            {'role': 'system', 'content': system},
        ] + HISTORY,
        think=False,
    )
"""

OLD_LOOP = """        set_state('thinking')
        answer = try_open(question) or think(question)
        print('Jarvis:', answer)
        set_state('speaking')
        asyncio.run(speak(answer))
"""

NEW_LOOP = """        low = question.lower().strip(' .!?')
        if low in ('forget everything', 'forget all'):
            forget_all()
            answer = 'Okay, I forgot everything I saved.'
        elif low in ('forget that', 'forget it'):
            answer = 'Okay, I forgot the last thing.' if forget_last() else 'I had nothing saved.'
        elif low.startswith('remember'):
            fact = question[len('remember'):].strip(' ,.')
            if fact.lower().startswith('that '):
                fact = fact[5:]
            if fact:
                save_memory(fact)
                answer = 'Okay, I will remember that.'
            else:
                answer = 'What should I remember?'
        else:
            set_state('thinking')
            answer = try_open(question) or think(question)
            fact = auto_remember(question)
            if fact:
                save_memory(fact)
                answer = answer + ' I will remember that.'
        print('Jarvis:', answer)
        set_state('speaking')
        asyncio.run(speak(answer))
"""

missing = []
if OLD_THINK not in text:
    missing.append("the think() function")
if OLD_LOOP not in text:
    missing.append("the part of the main loop that answers")
if "import os" not in text:
    NEED_OS = True
else:
    NEED_OS = False

if missing:
    print("Could not find " + " and ".join(missing) + ". Nothing was changed.")
else:
    if not os.path.exists(BACKUP):
        shutil.copy(PATH, BACKUP)
        print("Backed up to jarvis_voice2_before_memory.py")
    text = text.replace(OLD_THINK, NEW_THINK)
    text = text.replace(OLD_LOOP, NEW_LOOP)
    if NEED_OS:
        text = "import os\n" + text
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print("Patched. Long-term memory is on.")