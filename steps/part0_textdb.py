"""Part 0: the most obvious database - one line per user, commas. Watch it fail."""
import os
PATH='/tmp/part0.txt'
def insert(uid,name,email):
    with open(PATH,'a') as f: f.write(f"{uid},{name},{email}\n")
def find(uid):
    with open(PATH) as f:
        for line in f:
            parts=line.rstrip('\n').split(',')
            if parts[0]==str(uid): return parts
    return None
def update(uid,name,email):
    rows=[]
    with open(PATH) as f:
        for line in f:
            p=line.rstrip('\n').split(',')
            rows.append([str(uid),name,email] if p[0]==str(uid) else p)
    with open(PATH,'w') as f:
        for r in rows: f.write(','.join(r)+'\n')
if __name__=='__main__':
    try: os.remove(PATH)
    except: pass
    insert(1,'Ada Lovelace','ada@mail.com'); insert(2,'Grace Hopper','grace@mail.com'); insert(3,'Linus T','linus@mail.com')
    print('find 2:',find(2))
    update(2,'Grace Hopper','grace@new.com'); print('after update:',find(2))
    insert(4,'Hopper, Grace','hg@mail.com'); print('comma row:',find(4),'-> 4 values, broken!')
