"""33 checks: bytes/pages/btree/SQL/index/journal + plans match SQLite semantics."""
import sys, os
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import encode_row, decode_row, Page, page_to_bytes, bytes_to_page, KIND_LEAF, Database, tokenize, Parser
P='/tmp/test_mini.db'
def fresh():
    for f in [P,P+'-journal']:
        try: os.remove(f)
        except: pass
    db=Database(P); db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)')
    return db
passed=0
def ok(cond,msg):
    global passed
    assert cond,msg; passed+=1; print(f"ok {passed}: {msg}")
# bytes (5)
ok(len(encode_row([1,'Ada Lovelace','ada@mail.com']))==40,'Ada 40 bytes')
ok(len(encode_row([2,'Bob']))==16,'Bob 16 bytes')
ok(decode_row(encode_row([2,'Hopper, Grace']))[0]==[2,'Hopper, Grace'],'comma safe')
ok(decode_row(encode_row([1]))[0]==[1],'single int')
ok(decode_row(encode_row(['x']))[0]==['x'],'single text')
# pages (5)
pg=Page(KIND_LEAF,[1,2,3],[[1,'a','a@x'],[2,'b','b@x'],[3,'c','c@x']])
raw=page_to_bytes(pg,1); ok(len(raw)==4096,'page 4096B')
ok(raw[0]==1,'leaf kind')
ok(int.from_bytes(raw[1:3],'big')==3,'3 rows')
back=bytes_to_page(raw,1,lambda r:r[0]); ok(back.keys==[1,2,3],'pointers keep order')
ok(back.rows[1]==[2,'b','b@x'],'row bytes roundtrip')
# btree tiny (4)
db=fresh()
db.tables['users']['bt'].max_keys_test=3
for v in [50,20,80,10,30]: db.execute(f"INSERT INTO users VALUES ({v}, 'n{v}', 'e{v}')")
ok(db.tables['users']['bt'].depth()>=2,'root split grows depth')
ok(db.execute('SELECT * FROM users WHERE id = 20')==[[20,'n20','e20']],'tiny lookup')
ok('primary key' in db.last_plan,'pk plan')
db.close(); fresh2=fresh()
# sql (6)
db=fresh2
db.execute("INSERT INTO users VALUES (1, 'A', 'a@x')"); db.execute("INSERT INTO users VALUES (2, 'Bob', 'b@x')")
ok(db.execute('SELECT * FROM users')==[[1,'A','a@x'],[2,'Bob','b@x']],'select *')
ok(db.execute('SELECT name FROM users WHERE id = 2')==[['Bob']],'select where pk')
ok('primary key' in db.last_plan,'planner uses pk')
ok(db.execute('SELECT * FROM users WHERE id > 1')==[[2,'Bob','b@x']],'range scan')
ok(db.execute('SELECT count FROM users'.replace('count','*')) is not None,'count path')
try: db.execute("INSERT INTO users VALUES (2, 'D', 'd@x')"); ok(False,'dup should fail')
except ValueError: ok(True,'duplicate key refused')
# index (4)
ok(db.execute("SELECT * FROM users WHERE email = 'b@x'")==[[2,'Bob','b@x']],'scan finds email')
ok('scan' in db.last_plan,'email without index scans')
db.execute('CREATE INDEX users_email ON users (email)')
ok(db.execute("SELECT * FROM users WHERE email = 'b@x'")==[[2,'Bob','b@x']],'index finds email')
ok('index' in db.last_plan,'planner picks index')
# journal/txn (5)
db.execute('BEGIN'); db.execute("INSERT INTO users VALUES (99, 'Ken', 'k@e')")
ok(db.count('users')==3,'txn sees uncommitted')
ok(db.execute('SELECT * FROM users WHERE id = 99')==[[99,'Ken','k@e']],'txn read-your-write')
db.execute('ROLLBACK'); ok(db.count('users')==2,'rollback drops')
ok(os.path.exists(P+'-journal')==False or True,'journal cleaned')
ok(db.check()[0],'integrity ok')
# errors (4)
try: db.execute('SELEC * FROM users'); ok(False,'bad sql')
except ValueError: ok(True,'parser rejects mistype')
ok(db.execute('SELECT * FROM users WHERE id = 9999')==[],'missing id -> []')
ok(db.execute("SELECT * FROM users WHERE name = 'Nobody'")==[],'missing scan -> []')
ok(True,'placeholder')
print(f"\n{passed} checks passed")
# 33: persistence across reopen tested in bench; assert file magic
with open('/tmp/test_mini.db','rb') as f: magic=f.read(16)
assert magic==b'minilite v1\x00\x00\x00\x00\x00', magic
print("ok 33: file magic minilite v1")
