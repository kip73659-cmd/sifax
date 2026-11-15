import os
import shutil

PATH = r"C:\Users\sissi\Desktop\jarvis_voice2.py"
BACKUP = r"C:\Users\sissi\Desktop\jarvis_voice2_before_prompt.py"

with open(PATH, encoding="utf-8") as f:
    text = f.read()

OLD1 = "    system = 'You are Jarvis, a friendly assistant. Answer in one or two short sentences.'\n"

NEW1 = (
    "    system = ('You are a warm, relaxed, friendly voice assistant who talks like a kind friend. "
    "Answer in one or two short, natural sentences. Do not start with disclaimers like '\n"
    "              '\"As an AI\" and do not lecture. Do not end with offers of more help or follow-up questions. '\n"
    "              'If the user directly asks whether you are a person or an AI, answer honestly in a light, friendly way.')\n"
)

OLD2 = "        system += ' Things you know about the user: ' + ' '.join(facts)\n"

NEW2 = (
    "        system += (' Background facts about the user, to use ONLY when they clearly help answer the '\n"
    "                   'current question. Never mention them otherwise, and never mention the user name unless asked: ' + ' '.join(facts))\n"
)

missing = []
if OLD1 not in text:
    missing.append("the system prompt line in think()")
if OLD2 not in text:
    missing.append("the saved facts line in think()")

if missing:
    print("Could not find: " + ", ".join(missing) + ". Nothing was changed.")
else:
    if not os.path.exists(BACKUP):
        shutil.copy(PATH, BACKUP)
        print("Backed up to jarvis_voice2_before_prompt.py")
    text = text.replace(OLD1, NEW1)
    text = text.replace(OLD2, NEW2)
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("Patched. New personality and memory-use rules are on.")