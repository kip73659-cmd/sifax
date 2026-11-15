"""Run Miko inside Streamlit:   streamlit run miko_streamlit.py
Starts miko_server.py in the background (once) and shows Miko's interface in this page.
Put this file in the same folder as miko_server.py."""
import os, socket, subprocess, sys
import streamlit as st
import streamlit.components.v1 as components

BASE = os.path.dirname(os.path.abspath(__file__))
MIKO_PORT = 8765

st.set_page_config(page_title="Miko", page_icon="🌸", layout="wide", initial_sidebar_state="collapsed")
st.markdown("<style>header,footer{visibility:hidden;height:0} .block-container{padding:0.4rem 0.6rem 0 0.6rem;max-width:100%}</style>",
            unsafe_allow_html=True)

def miko_running():
    try:
        with socket.create_connection(("127.0.0.1", MIKO_PORT), timeout=0.5):
            return True
    except OSError:
        return False

@st.cache_resource
def start_miko():
    if miko_running():
        return None
    env = dict(os.environ, MIKO_REMOTE="1")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([sys.executable, "miko_server.py", "--no-browser"], cwd=BASE, env=env, creationflags=flags)
    return proc

start_miko()

import time
for _ in range(40):
    if miko_running():
        break
    time.sleep(0.25)
else:
    st.error("Miko's server did not start. Run  python miko_server.py  in the Miko folder and read the message.")
    st.stop()

# Use the same host name the browser used to reach Streamlit, so it works from other devices too.
host = ""
try:
    host = (st.context.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
except Exception:
    pass
if host in ("", "localhost", "::1"):
    host = "127.0.0.1"
url = "http://%s:%d/" % (host, MIKO_PORT)

components.iframe(url, height=900, scrolling=False)
st.caption("If the box above is blank or asks for a key, open %s once directly. "
           "Other devices need the access key from miko_access_key.txt." % url)
