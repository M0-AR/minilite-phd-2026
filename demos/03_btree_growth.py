"""Demo: B-tree growth with 3-key pages (transcript numbers)."""
import sys; import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import Database
import os
p='/tmp/demo_btree.db'
for f in [p,p+'-journal']:
    try: os.remove(f)
    except: pass
db=Database(p); db.execute('CREATE TABLE u (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
db.tables['u']['bt'].max_keys_test=3
for v in [50,20,80,10,30,40,70,90,60,25,35,45,15,85,95,55,65,75]:
    db.execute(f"INSERT INTO u VALUES ({v}, 'n{v}', 'e{v}')")
print('12 pages in transcript; ours pages:',db.pager.npages,'depth:',db.tables['u']['bt'].depth())
print('lookup 65:',db.execute('SELECT * FROM u WHERE id = 65'),db.last_plan,'pages',db.last_pages_read)
db.close()
