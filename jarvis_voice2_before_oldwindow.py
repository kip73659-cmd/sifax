import time as _t
import asyncio
import time
import os
import sounddevice as sd
import edge_tts
import ollama
from jarvis_tools import try_open, PENDING_ALERTS
from faster_whisper import WhisperModel

BRAIN = 'qwen3.5:4b'
VOICE = 'en-US-AvaNeural'

import threading, time, subprocess

GAME_MODE = [False]
BUSY = [False]
GPU_ON_PERCENT = 50
GPU_CMD = ('(Get-Counter "\\GPU Engine(*engtype_3D)\\Utilization Percentage")'
           '.CounterSamples | Measure-Object CookedValue -Sum | '
           'Select-Object -ExpandProperty Sum')

def gpu_load():
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-Command', GPU_CMD],
                             capture_output=True, text=True, timeout=10, creationflags=0x08000000).stdout.strip()
        return float(out.replace(',', '.'))
    except Exception:
        return 0.0

def game_watcher():
    high = 0
    low = 0
    while True:
        time.sleep(3)
        if BUSY[0]:
            continue
        load = gpu_load()
        if load > GPU_ON_PERCENT:
            high += 1
            low = 0
        else:
            low += 1
            high = 0
        if not GAME_MODE[0] and high >= 4:
            GAME_MODE[0] = True
            try:
                ollama.generate(model=BRAIN, prompt='', keep_alive=0)
            except Exception:
                pass
            print('Game mode ON (CPU only)')
        elif GAME_MODE[0] and low >= 7:
            GAME_MODE[0] = False
            try:
                ollama.generate(model=BRAIN, prompt='', keep_alive=0)
            except Exception:
                pass
            print('Game mode OFF (GPU)')

def ollama_options():
    return {'num_gpu': 0} if GAME_MODE[0] else {}


threading.Thread(target=game_watcher, daemon=True).start()

print('Loading ears, please wait...')
ears = WhisperModel('small.en', device='cpu', compute_type='int8')
ears_big = WhisperModel('distil-large-v3', device='cpu', compute_type='int8', cpu_threads=6)

def set_state(name):
    open('state.txt', 'w').write(name)

def wait_for_wake_word():  # NEW_WAKE
    import numpy as np
    set_state('idle')
    print('Waiting for wake word: Miko...')
    WAKE_WORDS = ['miko', 'mico', 'mica', 'meeko', 'mikko', 'nico', 'micro', 'jarvis']
    rate = 16000
    window = np.zeros(rate * 2, dtype='float32')
    new_samples = 0
    with sd.InputStream(samplerate=rate, channels=1, dtype='float32', device=1) as stream:
        while True:
            while PENDING_ALERTS:
                set_state('speaking')
                asyncio.run(speak(PENDING_ALERTS.pop(0)))
                set_state('idle')
            data, _ = stream.read(8000)
            data = data.flatten()
            window = np.concatenate([window[len(data):], data])
            new_samples += len(data)
            if new_samples < rate:
                continue
            new_samples = 0
            if float(np.abs(window).mean()) < 0.004:
                continue
            segs, _ = ears.transcribe(window, language='en', initial_prompt='Miko, Jarvis')
            heard = ' '.join(x.text for x in segs).lower()
            if any(w in heard for w in WAKE_WORDS):
                return

def listen():
    import numpy as np
    set_state('listening')
    print('Listening... speak now')
    chunk = 1600
    threshold = 0.01
    silence_limit = 12
    max_chunks = 300
    frames = []
    started = False
    quiet = 0
    with sd.InputStream(samplerate=16000, channels=1, dtype='float32', device=1) as stream:
        for _ in range(max_chunks):
            data, _ = stream.read(chunk)
            if PENDING_ALERTS and not started:  # LISTEN_ALERTS
                break
            loud = float(np.abs(data).mean()) > threshold
            if loud:
                started = True
                quiet = 0
            elif started:
                quiet += 1
            if started:
                frames.append(data)
            if started and quiet >= silence_limit:
                break
    if not frames:
        return ''
    audio = np.concatenate(frames).flatten()
    _t0 = _t.time()
    segments, info = ears_big.transcribe(audio, language='en', initial_prompt='Miko, Jarvis', beam_size=1, vad_filter=True, condition_on_previous_text=False)
    _txt = ' '.join(x.text for x in segments).strip()
    print('EARS took', round(_t.time() - _t0, 1), 'sec')
    return _txt

HISTORY = []
MAX_HISTORY = 10
MEMORY_FILE = r'C:\Users\sissi\Desktop\jarvis_memory.txt'

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def save_memory(fact):
    with open(MEMORY_FILE, 'a', encoding='utf-8') as f:
        f.write(fact.strip() + '\n')

def forget_last():
    facts = load_memory()
    if not facts:
        return False
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        for fact in facts[:-1]:
            f.write(fact + '\n')
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
            options=ollama_options(),
        )
        out = r['message']['content'].strip()
    except Exception:
        return None
    if not out or out.upper().startswith('NO') or len(out) > 150:
        return None
    return out

def _clean_query(t):
    import re
    t = t.lower().strip(' .!?')
    for w in ['show me', 'can you', 'please', 'some', 'for me', 'a few', 'the']:
        t = re.sub(r'\b' + w + r'\b', ' ', t)
    t = re.sub(r'\b(photos|pictures|images|pics) of\b', r'\1', t)
    t = ' '.join(t.split())
    return t or 'hello'

def think(question):
    HISTORY.append({'role': 'user', 'content': question})
    del HISTORY[:-MAX_HISTORY]
    facts = load_memory()
    system = ('You are a warm, relaxed, friendly voice assistant who talks like a kind friend. Answer in one or two short, natural sentences. Do not start with disclaimers like '
              '"As an AI" and do not lecture. Do not end with offers of more help or follow-up questions. '
              'If the user directly asks whether you are a person or an AI, answer honestly in a light, friendly way.')
    if facts:
        system += (' Background facts about the user, to use ONLY when they clearly help answer the '
                   'current question. Never mention them otherwise, and never mention the user name unless asked: ' + ' '.join(facts))
    reply = ollama.chat(
        model=BRAIN,
        messages=[
            {'role': 'system', 'content': system},
        ] + HISTORY,
        think=False,
        options=ollama_options(),
        keep_alive='60m',
    )
    answer = reply['message']['content']
    HISTORY.append({'role': 'assistant', 'content': answer})
    del HISTORY[:-MAX_HISTORY]
    return answer

async def speak(text):
    _m0 = _t.time()
    await edge_tts.Communicate(text, VOICE, pitch='+6Hz', rate='+5%').save('reply.mp3')
    print('MAKE took', round(_t.time() - _m0, 1), 'sec')
    _p0 = _t.time()
    import pygame
    pygame.mixer.init()
    pygame.mixer.music.load('reply.mp3')
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.1)
    pygame.mixer.music.unload()
    pygame.mixer.quit()
    print('PLAY took', round(_t.time() - _p0, 1), 'sec')

STOP_WORDS = ['stop', 'go to sleep', 'goodbye', 'turn off']

def wants_to_stop(q):
    q = q.lower()
    return any(w in q for w in STOP_WORDS)

while True:
    wait_for_wake_word()
    while True:
        question = listen()
        while PENDING_ALERTS:  # LISTEN_ALERTS2
            set_state('speaking')
            asyncio.run(speak(PENDING_ALERTS.pop(0)))
            set_state('idle')
        print('You said:', question)
        if not question:
            continue
        if wants_to_stop(question):
            set_state('speaking')
            asyncio.run(speak('Okay, going to sleep.'))
            HISTORY.clear()
            set_state('idle')
            break
        low = question.lower().strip(' .!?')
        check_memory = False
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
            BUSY[0] = True
            _t1 = _t.time()
            _ql = question.lower()
        _gq = None
        for _k in ('google ', 'search for ', 'search up '):
            if _k in _ql:
                _gq = _clean_query(question[_ql.index(_k) + len(_k):])
                break
        if _gq:
            import subprocess, sys
            subprocess.Popen([sys.executable, 'search_window.py', _gq])
            answer = 'Okay, here is what I found for ' + _gq + '.'
        else:
            answer = try_open(question) or think(question)
            print('BRAIN took', round(_t.time() - _t1, 1), 'sec')
            BUSY[0] = False
            check_memory = True
        print('Jarvis:', answer)
        set_state('speaking')
        _t2 = _t.time()
        asyncio.run(speak(answer))
        print('VOICE took', round(_t.time() - _t2, 1), 'sec')
        if check_memory:
            fact = auto_remember(question)
            if fact:
                save_memory(fact)

