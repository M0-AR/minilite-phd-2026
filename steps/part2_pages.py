"""Part 2: pages - 4096B slotted pages, pointers + binary search."""
import sys; import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__),'..')); sys.path.insert(0,'/work'); sys.path.insert(0,'/home/md/src/minilite-phd-2026')
from minilite import Page, page_to_bytes, bytes_to_page, KIND_LEAF
import bisect
if __name__=='__main__':
    rows=[[i,f'U{i}',f'u{i}@e.com'] for i in [3,1,2]]
    keys=[r[0] for r in rows]
    paired=sorted(zip(keys,rows)); keys=[k for k,_ in paired]; rows=[r for _,r in paired]
    pg=Page(KIND_LEAF,keys,rows); raw=page_to_bytes(pg,1)
    print('header:',raw[0],int.from_bytes(raw[1:3],'big'),'rows begin',int.from_bytes(raw[3:5],'big'))
    back=bytes_to_page(raw,1,lambda r:r[0]); print('roundtrip keys',back.keys)
    print('bisect 2 ->',bisect.bisect_left(back.keys,2))
