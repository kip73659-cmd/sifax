import json
import ollama

MODEL = 'qwen3.5:9b'

TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'web_search',
            'description': 'Search the web and show results. Use clean keywords, not the full sentence. If the user describes an animal or thing, work out what it is and search for its name.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'short search keywords'},
                    'images': {'type': 'boolean', 'description': 'true if the user wants pictures'},
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'set_timer',
            'description': 'Set a countdown timer.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'seconds': {'type': 'integer', 'description': 'length in seconds'},
                    'label': {'type': 'string', 'description': 'what the timer is for'},
                },
                'required': ['seconds'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'open_app',
            'description': 'Open an app or game on the computer.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string', 'description': 'app or game name'},
                },
                'required': ['name'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'set_volume',
            'description': 'Change the computer volume.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'level': {'type': 'integer', 'description': 'volume from 0 to 100'},
                },
                'required': ['level'],
            },
        },
    },
]

SYSTEM = (
    'You are Miko, a friendly voice assistant. Keep spoken answers to one or two short sentences. '
    'Use a tool whenever the user wants something done. '
    'Never say you searched, opened or set anything unless you really called the tool. Always call the tool first. '
    'If the user describes something without naming it, such as an animal, object, person, place or game, work out its name yourself and search for that name instead of the description. '
    'If you are not sure what the user means, ask one short question instead of guessing.'
)


def fake_run(name, args):
    # Test version: only pretends. Later we connect these to jarvis_tools.py
    print('   TOOL CHOSEN:', name, json.dumps(args))
    return 'done'


messages = [{'role': 'system', 'content': SYSTEM}]

while True:
    text = input('\nYou: ').strip()
    if text.lower() in ('quit', 'exit'):
        break
    messages.append({'role': 'user', 'content': text})
    reply = ollama.chat(model=MODEL, messages=messages, tools=TOOLS, think=False, keep_alive='60m')
    msg = reply['message']
    messages.append(msg)
    if msg.get('tool_calls'):
        for call in msg['tool_calls']:
            result = fake_run(call['function']['name'], dict(call['function']['arguments']))
            messages.append({'role': 'tool', 'tool_name': call['function']['name'], 'content': result})
        final = ollama.chat(model=MODEL, messages=messages, think=False, keep_alive='60m')
        print('Miko:', final['message']['content'])
        messages.append(final['message'])
    else:
        print('Miko:', msg['content'])