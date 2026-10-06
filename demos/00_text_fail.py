"""Demo: text DB fails - slow find/update, comma split, crash loses half."""
import time, os
PATH='/tmp/demo_text_users.csv'
open(PATH,'w').close()
def add(u): open(PATH,'a').write(f"{u[0]},{u[1]},{u[2]}\n")
t0=time.time()
for i in range(1,20001): add([i,f'User{i}',f'user{i}@example.com'])
print(f"wrote 20k rows in {time.time()-t0:.2f}s size {os.path.getsize(PATH)/1e6:.1f}MB")
t0=time.time()
found=None
with open(PATH) as f:
    for line in f:
        p=line.strip().split(',')
        if p[0]=='19777': found=p; break
print(f"find 19777: {found} in {(time.time()-t0)*1000:.1f}ms (scans every line before it)")
# comma
add([20001,'Hopper, Grace','hg@x.com'])
with open(PATH) as f: rows=[l.strip().split(',') for l in f if l.startswith('20001')]
print("comma row splits into",len(rows[0]),"values:",rows[0])
# crash: rewrite half then die
with open(PATH) as f: lines=f.readlines()
with open(PATH,'w') as f:
    f.writelines(lines[:len(lines)//2]); f.flush()
print(f"crash mid-rewrite: {len(lines)} -> {len(lines)//2} rows left, half the users gone")
