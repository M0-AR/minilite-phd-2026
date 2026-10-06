"""Part 3: B-tree with 3-key pages - watch splits and root growth."""
import sys; import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import Database
import os
p='/tmp/step3.db'
for f in [p,p+'-journal']:
    try: os.remove(f)
    except: pass
db=Database(p); db.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
# force tiny pages via max_keys_test
db.tables['t']['bt'].max_keys_test=3
for v in [50,20,80,10,30,40,70,90,60,25,35,45,15,85,95,55,65,75]:
    db.execute(f"INSERT INTO t VALUES ({v}, 'n{v}', 'e{v}')")
print('depth',db.tables['t']['bt'].depth(),'npages',db.pager.npages)
print('lookup 65:',db.execute('SELECT * FROM t WHERE id = 65'),db.last_plan,db.last_pages_read)
db.close()
