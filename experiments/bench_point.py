"""Benchmark: point/range/scan pages + latency. Usage: python3 bench_point.py [N]"""
import sys; import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import Database
import os, time, random
N=int(sys.argv[1]) if len(sys.argv)>1 else 100000
P=f'/tmp/bench_{N}.db'
for f in [P,P+'-journal']:
    try: os.remove(f)
    except: pass
db=Database(P)
db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
t0=time.time()
db.pager.begin()
for i in range(1,N+1):
    db.insert('users',[i,f'User{i}',f'user{i}@example.com'])
db.pager.commit()
print(f"load {N} rows {time.time()-t0:.1f}s pages={db.pager.npages} depth={db.tables['users']['bt'].depth()} bytes={os.path.getsize(P)}")
target=min(777777,N)
for q,args in [('id point',(f'SELECT * FROM users WHERE id = {target}',)),('email scan',(f"SELECT * FROM users WHERE email = 'user{target}@example.com'",))]:
    t0=time.time(); r=db.execute(args[0]); dt=(time.time()-t0)*1000
    print(f"{q}: rows={len(r)} plan='{db.last_plan}' pages={db.last_pages_read}/{db.pager.npages} {dt:.2f}ms")
db.execute('CREATE INDEX users_email ON users (email)')
print(f"after index pages={db.pager.npages}")
t0=time.time(); r=db.execute(f"SELECT * FROM users WHERE email = 'user{target}@example.com'")
print(f"email indexed: rows={len(r)} plan='{db.last_plan}' pages={db.last_pages_read} {(time.time()-t0)*1000:.2f}ms")
t0=time.time(); r=db.execute(f"SELECT * FROM users WHERE id = {target}")
print(f"id point (cold logical): plan='{db.last_plan}' pages={db.last_pages_read} {(time.time()-t0)*1000:.2f}ms")
print('check',db.check())
db.close()
