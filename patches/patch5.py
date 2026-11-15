p = 'avatar.py'
s = open(p, encoding='utf-8').read()
s = s.replace("root.geometry('400x500+100+100')", "root.geometry('400x500')")
s = s.replace("root.mainloop()", "root.eval('tk::PlaceWindow . center')\nroot.lift()\nroot.mainloop()")
open(p, 'w', encoding='utf-8').write(s)
print('Patched!')