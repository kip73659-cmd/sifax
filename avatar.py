import tkinter as tk
import os

STATES = {
    'idle': ('#2b2b3d', 'Idle'),
    'listening': ('#2d6a4f', 'Listening...'),
    'thinking': ('#b5651d', 'Thinking...'),
    'speaking': ('#4361ee', 'Speaking...'),
}

root = tk.Tk()
root.title('Jarvis')
root.geometry('400x500+1950+100')
root.attributes('-topmost', True)

label = tk.Label(root, text='Idle', font=('Segoe UI', 28), fg='white', bg='#2b2b3d')
label.pack(fill='both', expand=True)

last = None

def poll():
    global last
    try:
        state = open('state.txt').read().strip()
    except Exception:
        state = 'idle'
    if state != last and state in STATES:
        color, text = STATES[state]
        label.config(bg=color, text=text)
        last = state
    root.after(200, poll)

poll()
root.eval('tk::PlaceWindow . center')
root.lift()
root.mainloop()