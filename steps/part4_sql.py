"""Part 4: SQL tokens -> plan -> tree walk."""
import sys; import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import tokenize, Parser
for sql in ["SELECT name FROM users WHERE id = 2","SELECT * FROM users","SELEC name FROM users"]:
    try:
        toks=tokenize(sql); print(sql,'->',toks[:6],'...'); print(' plan:',Parser(toks).parse())
    except Exception as e: print(sql,'ERROR:',e)
