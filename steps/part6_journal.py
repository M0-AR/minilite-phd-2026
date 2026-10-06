"""Part 6: rollback journal - old bytes first, delete = commit."""
import sys; import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import Database
import os
p='/tmp/step6.db'
for f in [p,p+'-journal']:
    try: os.remove(f)
    except: pass
db=Database(p); db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
for i in range(1,4): db.execute(f"INSERT INTO users VALUES ({i}, 'n{i}', 'e{i}')")
db.execute('BEGIN'); db.execute("INSERT INTO users VALUES (99, 'Ken', 'k@e')")
print('in txn count:',db.count('users'), db.execute("SELECT * FROM users WHERE id = 99"))
db.execute('ROLLBACK'); print('after rollback:',db.count('users'))
db.close()
