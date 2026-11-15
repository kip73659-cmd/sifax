import sys
import os
import json
import tkinter as tk
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def tavily_search(q):
    key_path = os.path.join(BASE_DIR, 'tavily_key.txt')

    with open(key_path, 'r', encoding='utf-8') as f:
        key = f.read().strip()

    r = requests.post(
        'https://api.tavily.com/search',
        json={
            'api_key': key,
            'query': q,
            'max_results': 6
        },
        timeout=25
    )
    r.raise_for_status()

    return [
        {
            'title': x.get('title', ''),
            'body': x.get('content', ''),
            'href': x.get('url', '')
        }
        for x in r.json().get('results', [])
    ]

query = ' '.join(sys.argv[1:-1]) if len(sys.argv) > 2 else (
    ' '.join(sys.argv[1:]) or 'hello'
)

output_path = sys.argv[-1] if len(sys.argv) > 2 else os.path.join(
    BASE_DIR, 'miko_search_results.json'
)

root = tk.Tk()
root.title('Miko Search')
root.geometry('700x560+200+80')
root.attributes('-topmost', True)
root.configure(bg='#1e1e2e')

tk.Label(
    root,
    text='MIKO SEARCH',
    font=('Segoe UI', 11, 'bold'),
    fg='#a6adc8',
    bg='#1e1e2e'
).pack(anchor='w', padx=14, pady=(12, 2))

tk.Label(
    root,
    text=query,
    font=('Segoe UI', 16, 'bold'),
    fg='white',
    bg='#1e1e2e',
    wraplength=650,
    justify='left'
).pack(anchor='w', padx=14, pady=(4, 10))

box = tk.Text(
    root,
    wrap='word',
    font=('Segoe UI', 11),
    fg='#e6e6e6',
    bg='#2a2a3d',
    bd=0,
    padx=12,
    pady=10
)
box.pack(fill='both', expand=True, padx=14, pady=(0, 14))

results = []
error = None

try:
    box.insert('end', 'Searching the web with Tavily...\n\n')
    root.update()
    results = tavily_search(query)

except Exception as e:
    error = str(e)

payload = {
    'query': query,
    'results': results,
    'error': error
}

try:
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
except Exception as e:
    error = 'Could not save search results: ' + str(e)

box.delete('1.0', 'end')

if error:
    box.insert('end', 'Search failed:\n' + error + '\n\n')

if not results and not error:
    box.insert('end', 'No results were found.')

for r in results:
    box.insert('end', r.get('title', '') + '\n', 'title')
    box.insert('end', r.get('body', '') + '\n')
    box.insert('end', r.get('href', '') + '\n\n', 'link')

box.tag_config('title', foreground='#89b4fa', font=('Segoe UI', 12, 'bold'))
box.tag_config('link', foreground='#a6e3a1')
box.config(state='disabled')

root.mainloop()
