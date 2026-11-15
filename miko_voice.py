"""Voice engine for Miko Stitch.
Reuses the original jarvis_voice2.py logic (faster-whisper ears, wake word 'Miko', edge-tts voice, pygame playback)
but runs as a background thread inside the app, so the UI can switch it on/off, trigger it from a mic button,
and show what was heard / said.  Models load only when voice is switched on.  Original state.txt is still written
so the old avatar window keeps working."""
import asyncio, collections, itertools, os, threading, time

import miko_chat

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "state.txt")
REPLY_FILE = os.path.join(BASE, "reply.mp3")
WAKE_WORDS = ["miko", "mico", "mica", "meeko", "mikko", "nico", "micro", "jarvis"]
STOP_WORDS = ["stop", "go to sleep", "goodbye", "turn off"]

class Engine:
    def __init__(self):
        self.thread = None
        self.stop_evt = threading.Event()
        self.state = "off"            # off | loading | idle | listening | thinking | speaking | error
        self.error = ""
        self.events = collections.deque(maxlen=200)
        self._ids = itertools.count(1)
        self.ears = None
        self.ears_big = None
        self.wake_now = False
        self.last_poll = 0.0
        self.last_heard = ""
        self.last_reply = ""
        self.ui_url = "http://127.0.0.1:8765/"

    # ----- helpers -----
    def emit(self, typ, **kw):
        ev = {"id": next(self._ids), "t": time.time(), "type": typ}
        ev.update(kw)
        self.events.append(ev)
        return ev

    def set_state(self, name):
        self.state = name
        try:
            # the old avatar window understands: idle / listening / thinking / speaking
            with open(STATE_FILE, "w") as f:
                f.write(name if name in ("idle", "listening", "thinking", "speaking") else "idle")
        except Exception:
            pass
        self.emit("state", state=name)

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def status(self):
        return {"state": self.state, "running": self.running(), "error": self.error,
                "heard": self.last_heard, "reply": self.last_reply,
                "game_mode": miko_chat.GAME_MODE[0]}

    def events_since(self, since):
        self.last_poll = time.time()
        return [e for e in list(self.events) if e["id"] > since]

    # ----- lifecycle -----
    def start(self):
        if self.running():
            return True
        self.stop_evt.clear()
        self.error = ""
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.stop_evt.set()

    def wake(self):
        """Skip the wake word: start listening right now (mic button)."""
        if not self.running():
            self.start()
        self.wake_now = True

    # ----- internals -----
    def _cfg(self):
        return miko_chat.load_config()

    def _load_models(self):
        from faster_whisper import WhisperModel
        self.ears = WhisperModel("small.en", device="cpu", compute_type="int8")
        self.ears_big = WhisperModel("distil-large-v3", device="cpu", compute_type="int8", cpu_threads=6)

    def _mic(self):
        d = self._cfg().get("mic_device", 1)
        return None if d in (None, "", "default") else int(d)

    def _loop(self):
        try:
            self.set_state("loading")
            if self.ears is None:
                self._load_models()
        except Exception as e:
            self.error = "Could not load the speech models: " + str(e)[:140]
            self.set_state("error")
            return
        try:
            while not self.stop_evt.is_set():
                if not self._wait_wake():
                    break
                self._conversation()
        except Exception as e:
            self.error = "Voice stopped: " + str(e)[:140]
            self.set_state("error")
            return
        self.set_state("off")

    def _speak_alerts(self):
        for msg in miko_chat.pending_alerts():
            self.set_state("speaking")
            self._speak(msg)
            self.set_state("idle")

    def _wait_wake(self):
        import numpy as np
        import sounddevice as sd
        self.set_state("idle")
        rate = 16000
        window = np.zeros(rate * 2, dtype="float32")
        new_samples = 0
        with sd.InputStream(samplerate=rate, channels=1, dtype="float32", device=self._mic()) as stream:
            while not self.stop_evt.is_set():
                self._speak_alerts()
                if self.wake_now:
                    self.wake_now = False
                    return True
                data, _ = stream.read(8000)
                data = data.flatten()
                window = np.concatenate([window[len(data):], data])
                new_samples += len(data)
                if new_samples < rate:
                    continue
                new_samples = 0
                if float(np.abs(window).mean()) < 0.004:
                    continue
                segs, _ = self.ears.transcribe(window, language="en", initial_prompt="Miko, Jarvis")
                heard = " ".join(x.text for x in segs).lower()
                if any(w in heard for w in WAKE_WORDS):
                    return True
        return False

    def _listen(self):
        import numpy as np
        import sounddevice as sd
        self.set_state("listening")
        chunk, threshold, silence_limit, max_chunks = 1600, 0.01, 12, 300
        frames, started, quiet = [], False, 0
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32", device=self._mic()) as stream:
            for _ in range(max_chunks):
                if self.stop_evt.is_set():
                    return ""
                data, _ = stream.read(chunk)
                if miko_chat.PENDING_CHECK() and not started:
                    break
                loud = float(np.abs(data).mean()) > threshold
                if loud:
                    started, quiet = True, 0
                elif started:
                    quiet += 1
                if started:
                    frames.append(data)
                if started and quiet >= silence_limit:
                    break
        if not frames:
            return ""
        audio = np.concatenate(frames).flatten()
        segments, _info = self.ears_big.transcribe(audio, language="en", initial_prompt="Miko, Jarvis", beam_size=1,
                                                   vad_filter=True, condition_on_previous_text=False)
        return " ".join(x.text for x in segments).strip()

    def _conversation(self):
        while not self.stop_evt.is_set():
            question = self._listen()
            self._speak_alerts()
            if not question:
                continue
            self.last_heard = question
            self.emit("heard", text=question)
            if any(w in question.lower() for w in STOP_WORDS):
                self.set_state("speaking")
                self._speak("Okay, going to sleep.")
                miko_chat.clear_session()
                self.set_state("idle")
                return
            self.set_state("thinking")
            try:
                answer, action = miko_chat.answer_once(question)
            except Exception as e:
                answer, action = "Sorry, something went wrong: " + str(e)[:60], None
            self.last_reply = answer
            self.emit("reply", text=answer)
            if action:
                self.emit("action", **action)
                self._open_ui_if_needed(action)
            self.set_state("speaking")
            self._speak(answer)

    def _open_ui_if_needed(self, action):
        """If no Miko window is polling for events, open one so a spoken 'search for X' still shows results."""
        if action.get("action") == "search" and time.time() - self.last_poll > 6:
            import webbrowser
            from urllib.parse import quote
            webbrowser.open(self.ui_url + "?q=" + quote(action.get("q", "")) + "#web-search")
        elif action.get("action") == "anime" and time.time() - self.last_poll > 6:
            import webbrowser
            webbrowser.open(self.ui_url + "#anime-room")

    # ----- speaking (same as the original speak()) -----
    def _speak(self, text):
        try:
            asyncio.run(self._tts_play(text))
        except Exception as e:
            self.emit("error", text="Speaking failed: " + str(e)[:100])

    async def _tts_play(self, text):
        import edge_tts
        cfg = self._cfg()
        await edge_tts.Communicate(text, cfg["voice"], pitch="%+dHz" % int(cfg["voice_pitch"]),
                                   rate="%+d%%" % int(cfg["voice_rate"])).save(REPLY_FILE)
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(REPLY_FILE)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if self.stop_evt.is_set():
                pygame.mixer.music.stop()
                break
            await asyncio.sleep(0.1)
        pygame.mixer.music.unload()
        pygame.mixer.quit()

ENGINE = Engine()

# ----- text to speech for the browser (voice sample, Read Aloud): returns mp3 bytes -----
def tts_bytes(text, voice=None, rate=None, pitch=None):
    import edge_tts
    cfg = miko_chat.load_config()
    voice = voice or cfg["voice"]
    rate = cfg["voice_rate"] if rate is None else int(rate)
    pitch = cfg["voice_pitch"] if pitch is None else int(pitch)
    async def run():
        buf = b""
        comm = edge_tts.Communicate(text[:1500], voice, pitch="%+dHz" % pitch, rate="%+d%%" % rate)
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf += chunk["data"]
        return buf
    return asyncio.run(run())

def list_voices():
    import edge_tts
    vs = asyncio.run(edge_tts.list_voices())
    keep = ("en-", "fr-", "ar-", "ja-", "es-", "de-")
    out = [{"name": v["ShortName"], "gender": v.get("Gender", ""), "locale": v.get("Locale", "")}
           for v in vs if v["ShortName"].startswith(keep)]
    return sorted(out, key=lambda v: (v["locale"], v["name"]))

STATIC_VOICES = [{"name": n, "gender": g, "locale": n[:5]} for n, g in (
    ("en-US-AvaNeural", "Female"), ("en-US-AriaNeural", "Female"), ("en-US-JennyNeural", "Female"),
    ("en-US-AndrewNeural", "Male"), ("en-GB-SoniaNeural", "Female"), ("en-AU-NatashaNeural", "Female"),
    ("fr-FR-DeniseNeural", "Female"), ("ar-DZ-AminaNeural", "Female"), ("ja-JP-NanamiNeural", "Female"))]

def list_mics():
    import sounddevice as sd
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) > 0:
            out.append({"index": i, "name": d["name"]})
    return out
