"""Part 1: bytes - length-prefixed rows, no comma guessing."""
import struct
def enc(vals):
    o=bytearray([len(vals)])
    for v in vals:
        if isinstance(v,int): o+=b'\x01'+struct.pack('>q',v)
        else:
            b=v.encode(); o+=b'\x02'+struct.pack('>H',len(b))+b
    return bytes(o)
def dec(buf):
    p=0; n=buf[p]; p+=1; out=[]
    for _ in range(n):
        t=buf[p]; p+=1
        if t==1: out.append(struct.unpack('>q',buf[p:p+8])[0]); p+=8
        else: ln=struct.unpack('>H',buf[p:p+2])[0]; p+=2; out.append(buf[p:p+ln].decode()); p+=ln
    return out
if __name__=='__main__':
    for row in [[1,'Ada Lovelace','ada@mail.com'],[2,'Bob'],[2,'Hopper, Grace']]:
        assert dec(enc(row))==row, row
        print(row,'->',len(enc(row)),'bytes ok')
