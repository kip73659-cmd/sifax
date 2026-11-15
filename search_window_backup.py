import sys
import tkinter as tk
from ddgs import DDGS

import requests
def tavily_search(q):
    key = open('tavily_key.txt').read().strip()
    r = requests.post('https://api.tavily.com/search', json={'api_key': key, 'query': q, 'max_results': 6}, timeout=20)
    r.raise_for_status()
    return [{'title': x.get('title', ''), 'body': x.get('content', ''), 'href': x.get('url', '')} for x in r.json().get('results', [])]

query = ' '.join(sys.argv[1:]) or 'hello'

root = tk.Tk()
root.title('Miko Search')
root.geometry('620x520+200+80')
root.attributes('-topmost', True)
root.configure(bg='#1e1e2e')

tk.Label(root, text=query, font=('Segoe UI', 16, 'bold'), fg='white', bg='#1e1e2e', wraplength=580, justify='left').pack(anchor='w', padx=14, pady=(14, 6))

box = tk.Text(root, wrap='word', font=('Segoe UI', 11), fg='#e6e6e6', bg='#2a2a3d', bd=0, padx=12, pady=10)
box.pack(fill='both', expand=True, padx=14, pady=(0, 14))

try:
    results = tavily_search(query)
except Exception as e:
    results = []
    box.insert('end', 'Search failed: ' + str(e))

for r in results:
    box.insert('end', r.get('title', '') + '\n')
    box.insert('end', r.get('body', '') + '\n')
    box.insert('end', r.get('href', '') + '\n\n')

box.config(state='disabled')

state = {'left': 20}

def tick():
    if state['left'] <= 0:
        root.destroy()
        return
    state['left'] -= 1
    root.after(1000, tick)

def keep_open(event=None):
    state['left'] = 20

root.bind('<Motion>', keep_open)
root.bind('<Button-1>', keep_open)
root.bind('<MouseWheel>', keep_open)
tick()
root.mainloop()