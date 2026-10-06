"""Demo: kill after 3 pages without journal -> corrupt; with journal -> rollback."""
import sys; import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import Database
import os
for journal_on in [False, True]:
    p='/tmp/demo_crash_%s.db'%journal_on
    for f in [p,p+'-journal']:
        try: os.remove(f)
        except: pass
    db=Database(p,journal_on=journal_on)
    db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
    db.pager.begin()
    for i in range(1,2001): db.insert('users',[i,f'U{i}',f'u{i}@e.com'])
    db.pager.commit()
    db.pager.begin()
    for i in range(2001,4001): db.tables['users']['bt'].insert(i,[i,f'U{i}',f'u{i}@e.com'])
    db.pager.commit(crash_after=3)
    try: db.pager.close()
    except: pass
    try:
        db2=Database(p,journal_on=journal_on)
        c=db2.count('users'); chk=db2.check()
        print(f"journal_on={journal_on} count={c} check={chk}")
        db2.close()
    except Exception as e:
        print(f"journal_on={journal_on} CORRUPT as expected: {type(e).__name__}: {e}")
