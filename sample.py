from os import path

#here = path.abspath(path.dirname(__file__))
#print here # C:\Users\P2714823\PycharmProjects\mapscas
base = path.dirname(path.dirname(__file__))
joined = base + '/mapscas'
print joined
second = path.dirname(base)
#print second

rel = path.relpath('../Documents')
#print rel