import subprocess
import os

import os
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
    'overwatch': 'Overwatch\u00ae.url',
    'rocket league': 'Rocket League\u00ae.url',
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

def try_open_app(q):
	q = q.lower()
	if 'open ' not in q:
		return None
	name = q.split('open ', 1)[1].strip(' .!?')
	link = find_game_link(name)
	if link:
		os.startfile(link)
		return 'Opening ' + name
	if not name:
		return None
	cmd = 'Get-StartApps | Where-Object Name -like *' + name + '* | Select-Object -First 1 -ExpandProperty AppID'
	r = subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, text=True)
	app = r.stdout.strip()
	if not app:
		return None
	os.startfile('shell:AppsFolder' + chr(92) + app)
	return 'Opening ' + name


SKILLS_INSTALLED = True
import re as _re
import threading as _threading
import time as _time

PENDING_ALERTS = []

def _volume_iface():
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    speakers = AudioUtilities.GetSpeakers()
    try:
        interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    except AttributeError:
        interface = speakers._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))

def _get_vol():
    return int(round(_volume_iface().GetMasterVolumeLevelScalar() * 100))

def _set_vol(p):
    p = max(0, min(100, int(p)))
    _volume_iface().SetMasterVolumeLevelScalar(p / 100.0, None)
    return p

def _words_to_number(text):
    small = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
             'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11,
             'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
             'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
             'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60,
             'seventy': 70, 'eighty': 80, 'ninety': 90, 'half': 0.5, 'a': 1, 'an': 1}
    m = _re.search(r'\d+(?:\.\d+)?', text)
    if m:
        return float(m.group())
    total = 0
    found = False
    for w in text.replace('-', ' ').split():
        if w in small:
            total += small[w]
            found = True
        elif w == 'hundred' and found:
            total *= 100
    return total if found else None

def _timer_done(seconds, label):
    _time.sleep(seconds)
    PENDING_ALERTS.append("Ding ding! Your " + label + " timer is all done!")

def try_skills(q):
    low = q.lower().strip(' .!?')
    try:
        if 'mute' in low and 'unmute' not in low:
            _volume_iface().SetMute(1, None)
            return 'Shhh. Muted.'
        if 'unmute' in low:
            _volume_iface().SetMute(0, None)
            return 'Sound is back on.'
        if 'volume' in low:
            if _re.search(r'(set|to|at|put).*(volume|\d)', low) and (_re.search(r'\d', low) or 'percent' in low):
                num = _words_to_number(low.split('volume', 1)[1]) if not _re.search(r'\d', low) else float(_re.search(r'\d+', low).group())
                if num is not None:
                    return 'Volume set to ' + str(_set_vol(num)) + ' percent.'
            if 'up' in low or 'louder' in low or 'increase' in low:
                return 'Volume up to ' + str(_set_vol(_get_vol() + 10)) + ' percent.'
            if 'down' in low or 'lower' in low or 'quieter' in low or 'decrease' in low:
                return 'Volume down to ' + str(_set_vol(_get_vol() - 10)) + ' percent.'
            m = _re.search(r'\d+', low)
            if m:
                return 'Volume set to ' + str(_set_vol(int(m.group()))) + ' percent.'
            return 'The volume is at ' + str(_get_vol()) + ' percent.'
        if 'timer' in low and ('set' in low or 'start' in low or 'for' in low):
            after = low.split('for', 1)[1] if ' for ' in low else low
            num = _words_to_number(after)
            if num is None or num <= 0:
                return 'For how long should I set the timer?'
            if 'hour' in after:
                secs = num * 3600
                label = str(num).rstrip('0').rstrip('.') + ' hour'
            elif 'second' in after:
                secs = num
                label = str(int(num)) + ' second'
            else:
                secs = num * 60
                label = str(num).rstrip('0').rstrip('.') + ' minute'
            _threading.Thread(target=_timer_done, args=(secs, label), daemon=True).start()
            return 'Okay, a ' + label + ' timer, starting now.'
    except Exception as e:
        return 'Sorry, that did not work. ' + str(e)[:60]
    return None


def try_open(q):
    r = try_skills(q)
    if r:
        return r
    return try_open_app(q)
