"""Chat + memory backend for Miko Stitch.
Faithful to the original jarvis_voice2.py: same personality prompt, same memory file and commands,
same Ollama options, same GPU 'game mode' behaviour, same app/volume/timer commands (jarvis_tools).
Everything is lazy: nothing heavy runs until you actually chat."""
import json, os, re, sys, threading, time, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "miko_config.json")

def _default_memory():
    # Same file the original Miko uses (Desktop\jarvis_memory.txt) so both share one memory.
    desk = os.path.join(os.path.expanduser("~"), "Desktop", "jarvis_memory.txt")
    return desk if os.path.exists(desk) else os.path.join(BASE, "jarvis_memory.txt")

BASE_PERSONALITY = ("You are a warm, relaxed, friendly voice assistant who talks like a kind friend. "
                    "Answer in one or two short, natural sentences. Do not start with disclaimers like "
                    "\"As an AI\" and do not lecture. Do not end with offers of more help or follow-up questions. "
                    "If the user directly asks whether you are a person or an AI, answer honestly in a light, friendly way.")

ARCHETYPES = {
    "original": BASE_PERSONALITY,
    "tsundere": ("You are Miko, a playful kawaii tsundere assistant: cheeky teasing banter, gaming and anime references, "
                 "but secretly caring. Answer in one or two short sentences. Never start with \"As an AI\". "
                 "If asked directly whether you are an AI, answer honestly in a playful way."),
    "researcher": ("You are Miko, a precise and formal research assistant. Give accurate, well-structured, concise answers, "
                   "mention uncertainty when it exists, and avoid playful interruptions. "
                   "If asked directly whether you are an AI, answer honestly."),
    "lofi": ("You are Miko, a gentle, soothing study companion. Speak calmly in short, warm, encouraging sentences. "
             "If asked directly whether you are an AI, answer honestly and gently."),
    "hacker": ("You are Miko, a terse cyberpunk hacker-style assistant: crisp answers with technical metaphors and "
               "command-line flavour, still accurate and helpful. If asked directly whether you are an AI, answer honestly."),
}

DEFAULTS = {
    "brain": "qwen3.5:4b",
    "memory_file": "",                 # empty = shared Desktop file when it exists
    "max_history": 10,
    "auto_extract": False,
    "notify_done": True,
    "auto_remember": True,             # same as the original voice loop
    "game_mode_auto": True,            # GPU watcher, same thresholds idea as the original
    "voice_enabled": False,
    "speak_replies": False,           # read text-chat replies aloud
    "voice": "en-US-AvaNeural",        # original voice
    "voice_rate": 5,                   # percent, original '+5%'
    "voice_pitch": 6,                  # Hz, original '+6Hz'
    "mic_device": 1,                   # original used device=1
    "archetype": "original",
    "tone": {},                        # slider values, only applied once you move a slider
    "render_mode": "window",
}
_lock = threading.Lock()
HISTORY = []
STATS = {"last_latency": None, "ollama_ok": None, "last_error": ""}
GAME_MODE = [False]
BUSY = [False]

def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    if not cfg.get("memory_file"):
        cfg["memory_file"] = _default_memory()
    return cfg

def save_config(updates):
    cur = {}
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cur = json.load(f)
    except Exception:
        pass
    cur.update({k: v for k, v in updates.items() if k in DEFAULTS})
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2)
    os.replace(tmp, CONFIG_FILE)
    return load_config()

def reset_personality():
    return save_config({"archetype": "original", "tone": {}})

# ---- memory: same plain text file format Miko already uses ----
def load_memory():
    p = load_config()["memory_file"]
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]

def save_memory(fact):
    with open(load_config()["memory_file"], "a", encoding="utf-8") as f:
        f.write(fact.strip() + "\n")

def forget_last():
    facts = load_memory()
    if not facts:
        return False
    with open(load_config()["memory_file"], "w", encoding="utf-8") as f:
        for x in facts[:-1]:
            f.write(x + "\n")
    return True

def forget_all():
    open(load_config()["memory_file"], "w").close()

# ---- game mode: move Ollama to the CPU while a game is using the GPU (as in the original) ----
GPU_ON_PERCENT = 50
GPU_CMD = ('(Get-Counter "\\GPU Engine(*engtype_3D)\\Utilization Percentage")'
           '.CounterSamples | Measure-Object CookedValue -Sum | Select-Object -ExpandProperty Sum')
_watcher = [False]

def ollama_options():
    return {"num_gpu": 0} if GAME_MODE[0] else {}

def _ollama():
    import ollama  # imported lazily so the UI starts instantly
    return ollama

def gpu_load():
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", GPU_CMD], capture_output=True, text=True,
                             timeout=10, creationflags=0x08000000).stdout.strip()
        return float(out.replace(",", "."))
    except Exception:
        return 0.0

def _unload():
    try:
        _ollama().generate(model=load_config()["brain"], prompt="", keep_alive=0)
    except Exception:
        pass

def _watch():
    high = low = 0
    while True:
        time.sleep(5)
        if BUSY[0] or not load_config().get("game_mode_auto", True):
            continue
        load = gpu_load()
        if load > GPU_ON_PERCENT:
            high, low = high + 1, 0
        else:
            low, high = low + 1, 0
        if not GAME_MODE[0] and high >= 3:
            GAME_MODE[0] = True
            _unload()
        elif GAME_MODE[0] and low >= 5:
            GAME_MODE[0] = False
            _unload()

def start_game_watcher():
    if os.name == "nt" and not _watcher[0]:
        _watcher[0] = True
        threading.Thread(target=_watch, daemon=True).start()

# ---- personality ----
def build_system(extra=""):
    cfg = load_config()
    s = ARCHETYPES.get(cfg.get("archetype"), BASE_PERSONALITY)
    t = cfg.get("tone") or {}
    mods = []
    if "sass" in t:
        mods.append("Tease the user playfully with cheeky banter." if t["sass"] > 66 else
                    "Be mild and polite, with no teasing." if t["sass"] < 33 else "")
    if "affection" in t:
        mods.append("Be warm and affectionate, and praise the user often." if t["affection"] > 66 else
                    "Stay neutral and professional, with no pet names or gushing." if t["affection"] < 33 else "")
    if "precision" in t:
        mods.append("Give technical detail and exact terms when relevant." if t["precision"] > 66 else
                    "Keep explanations simple and brief." if t["precision"] < 33 else "")
    s += " " + " ".join(m for m in mods if m)
    facts = load_memory()
    if facts:
        s += (" Background facts about the user, to use ONLY when they clearly help answer the "
              "current question. Never mention them otherwise, and never mention the user name unless asked: " + " ".join(facts))
    if extra:
        s += " " + extra
    return s.strip()

def handle_commands(text):
    """Same remember/forget commands as the voice loop. Returns a reply or None."""
    low = text.lower().strip(" .!?")
    if low in ("forget everything", "forget all"):
        forget_all()
        return "Okay, I forgot everything I saved."
    if low in ("forget that", "forget it"):
        return "Okay, I forgot the last thing." if forget_last() else "I had nothing saved."
    if low.startswith("remember"):
        fact = text[len("remember"):].strip(" ,.")
        if fact.lower().startswith("that "):
            fact = fact[5:]
        if fact:
            save_memory(fact)
            return "Okay, I will remember that."
        return "What should I remember?"
    return None

def _clean_query(t):
    t = t.lower().strip(" .!?")
    for w in ["show me", "can you", "please", "some", "for me", "a few", "the"]:
        t = re.sub(r"\b" + w + r"\b", " ", t)
    t = re.sub(r"\b(photos|pictures|images|pics) of\b", r"\1", t)
    t = " ".join(t.split())
    return t or "hello"

def search_command(text):
    low = text.lower()
    for k in ("google ", "search for ", "search up "):
        if k in low:
            return _clean_query(text[low.index(k) + len(k):])
    return None

def run_tools(text):
    """Windows volume/timers/open-app commands from the original jarvis_tools.py. None if not a command."""
    try:
        if BASE not in sys.path:
            sys.path.insert(0, BASE)
        from jarvis_tools import try_open
    except Exception:
        return None
    try:
        return try_open(text)
    except Exception as e:
        return "Sorry, that did not work. " + str(e)[:60]

def PENDING_CHECK():
    try:
        if BASE not in sys.path:
            sys.path.insert(0, BASE)
        from jarvis_tools import PENDING_ALERTS
        return bool(PENDING_ALERTS)
    except Exception:
        return False

def pending_alerts():
    try:
        if BASE not in sys.path:
            sys.path.insert(0, BASE)
        from jarvis_tools import PENDING_ALERTS
        out = []
        while PENDING_ALERTS:
            out.append(PENDING_ALERTS.pop(0))
        return out
    except Exception:
        return []

def auto_remember(question):
    """Ask the brain whether the sentence holds a lasting personal fact (same prompt as the original)."""
    try:
        r = _ollama().chat(model=load_config()["brain"], messages=[
            {"role": "system", "content": "You decide if a spoken sentence contains a lasting personal fact about the speaker worth remembering for months, like their name, family, pets, job, preferences or plans. Ordinary questions and small talk are NOT worth remembering. If it is worth remembering, reply with only the fact written as one short sentence about the user. Otherwise reply with only the word NO."},
            {"role": "user", "content": question}], think=False, options=ollama_options())
        out = r["message"]["content"].strip()
    except Exception:
        return None
    if not out or out.upper().startswith("NO") or len(out) > 150:
        return None
    return out

def _auto_remember_bg(question):
    def run():
        BUSY[0] = True
        try:
            fact = auto_remember(question)
            if fact:
                save_memory(fact)
        finally:
            BUSY[0] = False
    threading.Thread(target=run, daemon=True).start()

ACTION_MARK = "\x00"

def chat_stream(text, context=""):
    """Generator of reply text chunks. A final chunk starting with \\x00 carries a JSON UI action."""
    cmd = handle_commands(text)
    if cmd is not None:
        yield cmd
        return
    try:
        import miko_anime
        anime = miko_anime.command(text)
    except Exception:
        anime = None
    if anime:
        yield anime[0]
        yield ACTION_MARK + json.dumps(anime[1])
        return
    q = search_command(text)
    if q:
        yield "Okay, here is what I found for " + q + "."
        yield ACTION_MARK + json.dumps({"action": "search", "q": q})
        return
    tool = run_tools(text)
    if tool:
        yield tool
        return
    cfg = load_config()
    t0 = time.time()
    with _lock:
        HISTORY.append({"role": "user", "content": text})
        del HISTORY[:-cfg["max_history"]]
        msgs = [{"role": "system", "content": build_system(context)}] + list(HISTORY)
    full = ""
    BUSY[0] = True
    try:
        for part in _ollama().chat(model=cfg["brain"], messages=msgs, think=False, stream=True,
                                   options=ollama_options(), keep_alive="60m"):
            piece = part["message"]["content"]
            full += piece
            yield piece
        STATS["ollama_ok"] = True
    except Exception as e:
        STATS["ollama_ok"] = False
        STATS["last_error"] = str(e)[:120]
        yield ("[Miko could not reach Ollama. Is it running, and is the model '%s' installed? (%s)]"
               % (cfg["brain"], str(e)[:80]))
        return
    finally:
        BUSY[0] = False
    STATS["last_latency"] = round(time.time() - t0, 1)
    with _lock:
        HISTORY.append({"role": "assistant", "content": full})
        del HISTORY[:-cfg["max_history"]]
    if cfg.get("auto_remember", True) and not text.lower().startswith("remember"):
        _auto_remember_bg(text)

def answer_once(text):
    """Full reply as (text, action-or-None). Used by the voice loop."""
    out = "".join(chat_stream(text))
    if ACTION_MARK in out:
        out, _, a = out.partition(ACTION_MARK)
        try:
            return out, json.loads(a)
        except Exception:
            return out, None
    return out, None

def clear_session():
    with _lock:
        HISTORY.clear()

def list_models():
    try:
        r = _ollama().list()
        models = r["models"] if isinstance(r, dict) else getattr(r, "models", [])
        names = []
        for m in models:
            n = m.get("model") if isinstance(m, dict) else getattr(m, "model", None)
            if n:
                names.append(n)
        STATS["ollama_ok"] = True
        return sorted(names)
    except Exception as e:
        STATS["ollama_ok"] = False
        STATS["last_error"] = str(e)[:120]
        return []

RESEARCH_SYSTEM = ("You are Miko's research analyst. Use ONLY the numbered sources the user gives you. "
                   "Write a clear report in Markdown with these sections: '## Summary' (2-4 sentences), "
                   "'## Key findings' (bullet points, cite sources like [1] or [2]), "
                   "'## Where sources disagree or are unclear' (say 'Nothing notable' if so), and "
                   "'## Sources' (numbered list of titles). Never invent facts that are not in the sources. "
                   "If the sources do not answer the topic, say so plainly.")

def research_stream(topic, sources):
    """Stream a Markdown report built only from the given sources. No chat history, no memory."""
    topic = (topic or "").strip()
    if not topic:
        yield "[Type a research topic first.]"
        return
    parts = []
    for i, s in enumerate((sources or [])[:10], 1):
        parts.append("[%d] %s (%s)\n%s" % (i, str(s.get("title", ""))[:140], str(s.get("url", ""))[:140],
                                           str(s.get("body", ""))[:700]))
    if not parts:
        yield "[No sources are selected. Run the research first, or switch some sources on.]"
        return
    cfg = load_config()
    msgs = [{"role": "system", "content": RESEARCH_SYSTEM},
            {"role": "user", "content": "Topic: %s\n\nSources:\n%s" % (topic, "\n\n".join(parts))}]
    BUSY[0] = True
    try:
        for part in _ollama().chat(model=cfg["brain"], messages=msgs, think=False, stream=True,
                                   options=ollama_options(), keep_alive="60m"):
            yield part["message"]["content"]
    except Exception as e:
        yield "[Miko could not reach Ollama. Is it running, and is '%s' installed? (%s)]" % (cfg["brain"], str(e)[:80])
    finally:
        BUSY[0] = False
