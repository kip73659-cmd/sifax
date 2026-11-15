import os

folder = os.getcwd()

with open('start_jarvis.bat', 'w') as f:
    f.write('@echo off\n')
    f.write('cd /d "' + folder + '"\n')
    f.write('start "" pythonw avatar.py\n')
    f.write('start "" python jarvis_voice2.py\n')

print('Created start_jarvis.bat in', folder)