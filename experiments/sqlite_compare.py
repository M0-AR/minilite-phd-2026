"""Compare minilite file vs sqlite3 stdlib on same data (10k sample for speed)."""
import sys, os, sqlite3, time
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import Database
N=10000
mp='/tmp/cmp_mini.db'; sp='/tmp/cmp_lite.db'
for f in [mp,mp+'-journal',sp]:
    try: os.remove(f)
    except: pass
db=Database(mp); db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
db.pager.begin()
for i in range(1,N+1): db.insert('users',[i,f'User{i}',f'user{i}@example.com'])
db.pager.commit()
print(f"minilite pages={db.pager.npages} size={os.path.getsize(mp)}")
db.close()
con=sqlite3.connect(sp); cur=con.cursor()
cur.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
cur.executemany('INSERT INTO users VALUES (?,?,?)',[(i,f'User{i}',f'user{i}@example.com') for i in range(1,N+1)])
con.commit()
cur.execute('EXPLAIN QUERY PLAN SELECT * FROM users WHERE id=7777'); print('sqlite pk plan:',cur.fetchall())
cur.execute("EXPLAIN QUERY PLAN SELECT * FROM users WHERE email='user7777@example.com'"); print('sqlite email plan:',cur.fetchall())
cur.execute('CREATE INDEX users_email ON users(email)')
cur.execute("EXPLAIN QUERY PLAN SELECT * FROM users WHERE email='user7777@example.com'"); print('sqlite email indexed:',cur.fetchall())
import subprocess
print(f"sqlite pages={os.path.getsize(sp)//4096} size={os.path.getsize(sp)}")
con.close()
