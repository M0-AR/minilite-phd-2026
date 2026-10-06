"""Part 5: secondary index (email,id) -> id -> row."""
import sys; import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import Database
import os
p='/tmp/step5.db'
for f in [p,p+'-journal']:
    try: os.remove(f)
    except: pass
db=Database(p); db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
for i in range(1,500): db.insert('users',[i,f'U{i}',f'u{i}@e.com'])
print('scan plan:',db.execute("SELECT * FROM users WHERE email = 'u77@e.com'"),db.last_plan,db.last_pages_read)
db.execute('CREATE INDEX users_email ON users (email)')
print('index plan:',db.execute("SELECT * FROM users WHERE email = 'u77@e.com'"),db.last_plan,db.last_pages_read)
db.close()
