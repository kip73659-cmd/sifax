import os

folder = os.getcwd()

with open('start_jarvis.bat', 'w') as f:
    f.write('@echo off\n')
    f.write('cd /d "' + folder + '"\n')
    f.write('start "" pythonw avatar.py\n')
    f.write('start "" pythonw jarvis_voice2.py\n')

print('Updated start_jarvis.bat')