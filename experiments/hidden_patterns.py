"""Hidden patterns: sequential fill-factor waste, fanout scaling, index write price."""
import sys; import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import Database
import os, random, time
def build(order,N):
    p=f'/tmp/pat_{order}_{N}.db'
    for f in [p,p+'-journal']:
        try: os.remove(f)
        except: pass
    db=Database(p); db.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
    ids=list(range(1,N+1))
    if order=='random': random.seed(0); random.shuffle(ids)
    db.pager.begin()
    for i in ids: db.insert('t',[i,f'U{i}',f'u{i}@e.com'])
    db.pager.commit()
    pages=db.pager.npages; depth=db.tables['t']['bt'].depth()
    # occupancy: avg rows per leaf
    leaves=db.tables['t']['bt']._ordered_leaves()
    avg=sum(len(lp.rows) for _,lp in leaves)/max(1,len(leaves))
    db.close(); return pages,depth,avg,len(leaves)
for N in [20000]:
    s=build('sequential',N); r=build('random',N)
    print(f"N={N} sequential pages={s[0]} depth={s[1]} avg_rows/leaf={s[2]:.1f} leaves={s[3]}")
    print(f"N={N} random     pages={r[0]} depth={r[1]} avg_rows/leaf={r[2]:.1f} leaves={r[3]}")
    print(f"waste: sequential uses {s[0]/r[0]:.2f}x pages of random? (naive 50/50 split leaves left half-empty)")
    print("fanout estimate: interior keys per page ~250-300 => depth 2 holds ~20k, depth 3 holds ~6M, depth 4 holds ~1B")
