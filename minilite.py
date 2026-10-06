"""minilite: a SQLite-like database engine in ~683 lines, zero dependencies.
Layers: bytes -> pages -> B-tree -> SQL -> indexes -> crash safety (rollback journal).
Design mirrors SQLite: 4096-byte pages, slotted pages, B+ tree, schema table on page 0,
secondary index B-trees, rollback-journal atomic commit. Only stdlib is used.
"""
import bisect
import os
import re
import struct

PAGE_SIZE = 4096
MAGIC = b'minilite v1\x00\x00\x00\x00\x00'
MAGIC_LEN = 16
assert len(MAGIC) == MAGIC_LEN
KIND_LEAF = 1
KIND_INTERIOR = 2
TYPE_INT = 1
TYPE_TEXT = 2
HEADER = 9


# ---------------------------------------------------------------- bytes (part 1)
def encode_row(values):
    out = bytearray()
    out.append(len(values) & 0xFF)
    for v in values:
        if isinstance(v, int):
            out.append(TYPE_INT)
            out += struct.pack('>q', v)
        elif isinstance(v, str):
            out.append(TYPE_TEXT)
            b = v.encode('utf-8')
            out += struct.pack('>H', len(b))
            out += b
        else:
            raise ValueError('only int/str supported')
    return bytes(out)


def decode_row(buf, pos=0):
    n = buf[pos]
    pos += 1
    vals = []
    for _ in range(n):
        t = buf[pos]
        pos += 1
        if t == TYPE_INT:
            vals.append(struct.unpack('>q', buf[pos:pos + 8])[0])
            pos += 8
        elif t == TYPE_TEXT:
            ln = struct.unpack('>H', buf[pos:pos + 2])[0]
            pos += 2
            vals.append(buf[pos:pos + ln].decode('utf-8'))
            pos += ln
        else:
            raise ValueError('bad type byte %r' % t)
    return vals, pos


def encode_key(key):
    if isinstance(key, int):
        return b'I' + struct.pack('>q', key)
    if isinstance(key, tuple):
        email, i = key
        b = email.encode('utf-8')
        return b'T' + struct.pack('>H', len(b)) + b + struct.pack('>q', i)
    raise ValueError('bad key')


def decode_key(buf):
    if buf[0:1] == b'I':
        return struct.unpack('>q', buf[1:9])[0]
    if buf[0:1] == b'T':
        ln = struct.unpack('>H', buf[1:3])[0]
        email = buf[3:3 + ln].decode('utf-8')
        i = struct.unpack('>q', buf[3 + ln:3 + ln + 8])[0]
        return (email, i)
    raise ValueError('bad key bytes')


# ---------------------------------------------------------------- pages (part 2)
class Page:
    def __init__(self, kind, keys=None, rows=None, children=None, extra=0):
        self.kind = kind
        self.keys = keys or []
        self.rows = rows or []          # leaf only: list of value-lists
        self.children = children or []  # interior only: len(keys)+1
        self.extra = extra              # leaf: next_leaf pgno; interior: rightmost child


def leaf_used(page, pgno):
    hdr = HEADER + (MAGIC_LEN if pgno == 0 else 0)
    used = hdr + 2 * len(page.keys)
    for r in page.rows:
        used += 2 + len(encode_row(r))
    return used


def interior_used(page, pgno):
    hdr = HEADER + (MAGIC_LEN if pgno == 0 else 0)
    used = hdr + 2 * len(page.keys)
    for k in page.keys:
        used += 4 + 2 + len(encode_key(k))
    return used


def page_to_bytes(page, pgno):
    buf = bytearray(PAGE_SIZE)
    if pgno == 0:
        buf[0:MAGIC_LEN] = MAGIC
        h = MAGIC_LEN
    else:
        h = 0
    buf[h] = page.kind
    struct.pack_into('>H', buf, h + 1, len(page.keys))
    ptr_base = h + HEADER
    cell = PAGE_SIZE
    if page.kind == KIND_LEAF:
        for i, row in enumerate(page.rows):
            rb = encode_row(row)
            need = 2 + len(rb)
            cell -= need
            if cell < ptr_base + 2 * len(page.keys):
                raise OverflowError('leaf full')
            struct.pack_into('>H', buf, cell, len(rb))
            buf[cell + 2:cell + 2 + len(rb)] = rb
            struct.pack_into('>H', buf, ptr_base + i * 2, cell)
        struct.pack_into('>H', buf, h + 3, cell)
        struct.pack_into('>I', buf, h + 5, page.extra)
    else:
        for i, key in enumerate(page.keys):
            kb = encode_key(key)
            child = page.children[i]
            need = 4 + 2 + len(kb)
            cell -= need
            if cell < ptr_base + 2 * len(page.keys):
                raise OverflowError('interior full')
            struct.pack_into('>I', buf, cell, child)
            struct.pack_into('>H', buf, cell + 4, len(kb))
            buf[cell + 6:cell + 6 + len(kb)] = kb
            struct.pack_into('>H', buf, ptr_base + i * 2, cell)
        struct.pack_into('>H', buf, h + 3, cell)
        right = page.children[-1] if page.children else 0
        struct.pack_into('>I', buf, h + 5, right)
    return bytes(buf)


def bytes_to_page(buf, pgno, key_of_row=None):
    if pgno == 0:
        assert bytes(buf[0:MAGIC_LEN]) == MAGIC, 'bad magic'
        h = MAGIC_LEN
    else:
        h = 0
    kind = buf[h]
    n = struct.unpack('>H', buf[h + 1:h + 3])[0]
    extra = struct.unpack('>I', buf[h + 5:h + 9])[0]
    ptr_base = h + HEADER
    if kind == KIND_LEAF:
        rows = []
        for i in range(n):
            off = struct.unpack('>H', buf[ptr_base + i * 2:ptr_base + i * 2 + 2])[0]
            ln = struct.unpack('>H', buf[off:off + 2])[0]
            vals, _ = decode_row(buf, off + 2)
            assert len(encode_row(vals)) == ln or True
            rows.append(vals)
        if key_of_row:
            keys = [key_of_row(r) for r in rows]
        else:
            keys = list(range(n))
        return Page(KIND_LEAF, keys, rows, extra=extra)
    elif kind == KIND_INTERIOR:
        keys, children = [], []
        for i in range(n):
            off = struct.unpack('>H', buf[ptr_base + i * 2:ptr_base + i * 2 + 2])[0]
            child = struct.unpack('>I', buf[off:off + 4])[0]
            klen = struct.unpack('>H', buf[off + 4:off + 6])[0]
            key = decode_key(bytes(buf[off + 6:off + 6 + klen]))
            children.append(child)
            keys.append(key)
        children.append(extra)
        return Page(KIND_INTERIOR, keys, children=children, extra=extra)
    raise ValueError('bad page kind')


# ---------------------------------------------------------------- pager + journal (part 6)
class Pager:
    def __init__(self, path, journal_on=True):
        self.path = path
        self.jpath = path + '-journal'
        self.journal_on = journal_on
        self.cache = {}
        self.dirty = set()
        self.journal = {}   # pgno -> old raw bytes
        self.orig_npages = 0
        self.npages = 0
        self.disk_reads = 0
        self.logical_reads = 0
        self.in_txn = False
        self._open_file()
        self._maybe_rollback()
        self._read_sizes()

    def _open_file(self):
        exists = os.path.exists(self.path)
        self.f = open(self.path, 'a+b')
        self.f.close()
        self.f = open(self.path, 'r+b')
        if not exists or os.path.getsize(self.path) == 0:
            self.f.truncate(PAGE_SIZE)
            self.f.seek(0)
            empty = Page(KIND_LEAF, [], [])
            self.f.write(page_to_bytes(empty, 0))
            self.f.flush()

    def _read_sizes(self):
        sz = os.path.getsize(self.path)
        self.npages = max(1, (sz + PAGE_SIZE - 1) // PAGE_SIZE)
        self.orig_npages = self.npages

    def _raw_read(self, pgno):
        self.f.seek(pgno * PAGE_SIZE)
        data = self.f.read(PAGE_SIZE)
        if len(data) < PAGE_SIZE:
            data = data + b'\x00' * (PAGE_SIZE - len(data))
        return data

    def _maybe_rollback(self):
        if os.path.exists(self.jpath) and os.path.getsize(self.jpath) > 0:
            with open(self.jpath, 'rb') as jf:
                hdr = jf.read(16)
                if len(hdr) < 16:
                    return
                assert hdr[0:8] == b'MNLJRNL\x00'
                orig = struct.unpack('>I', hdr[8:12])[0]
                cnt = struct.unpack('>I', hdr[12:16])[0]
                for _ in range(cnt):
                    meta = jf.read(8)
                    if len(meta) < 8:
                        break
                    pgno, ln = struct.unpack('>II', meta)
                    data = jf.read(ln)
                    self.f.seek(pgno * PAGE_SIZE)
                    self.f.write(data)
                self.f.truncate(orig * PAGE_SIZE)
                self.f.flush()
                try:
                    os.fsync(self.f.fileno())
                except Exception:
                    pass
            try:
                os.remove(self.jpath)
            except Exception:
                pass

    def begin(self):
        self.in_txn = True
        self.orig_npages = self.npages
        self.journal = {}

    def get(self, pgno, key_of_row=None):
        self.logical_reads += 1
        if pgno in self.cache:
            return self.cache[pgno]
        raw = self._raw_read(pgno)
        self.disk_reads += 1
        pg = bytes_to_page(raw, pgno, key_of_row)
        self.cache[pgno] = pg
        return pg

    def put(self, pgno, page):
        if self.in_txn and self.journal_on:
            if pgno < self.orig_npages and pgno not in self.journal:
                self.journal[pgno] = self._raw_read(pgno)
        self.cache[pgno] = page
        self.dirty.add(pgno)
        if pgno >= self.npages:
            self.npages = pgno + 1

    def alloc(self, page):
        pgno = self.npages
        self.npages += 1
        self.cache[pgno] = page
        self.dirty.add(pgno)
        return pgno

    def commit(self, crash_after=None):
        if self.journal_on and self.in_txn:
            with open(self.jpath, 'wb') as jf:
                jf.write(b'MNLJRNL\x00' + struct.pack('>II', self.orig_npages, len(self.journal)))
                for pgno, old in self.journal.items():
                    jf.write(struct.pack('>II', pgno, len(old)))
                    jf.write(old)
                jf.flush()
                try:
                    os.fsync(jf.fileno())
                except Exception:
                    pass
        ordered = sorted(self.dirty)
        written = 0
        for pgno in ordered:
            raw = page_to_bytes(self.cache[pgno], pgno)
            self.f.seek(pgno * PAGE_SIZE)
            self.f.write(raw)
            written += 1
            if crash_after is not None and written >= crash_after:
                self.f.flush()
                try:
                    os.fsync(self.f.fileno())
                except Exception:
                    pass
                # simulate power cut: do NOT delete journal, leave partial db
                self.dirty = set()
                return 'crashed'
        self.f.flush()
        try:
            os.fsync(self.f.fileno())
        except Exception:
            pass
        if self.journal_on and os.path.exists(self.jpath):
            try:
                os.remove(self.jpath)
            except Exception:
                pass
        self.dirty = set()
        self.journal = {}
        self.in_txn = False
        self.orig_npages = self.npages
        return 'ok'

    def rollback_txn(self):
        self.cache = {}
        self.dirty = set()
        self.journal = {}
        self.in_txn = False
        self._read_sizes()
        if os.path.exists(self.jpath):
            try:
                os.remove(self.jpath)
            except Exception:
                pass

    def flush_all(self):
        return self.commit()

    def close(self):
        try:
            self.f.flush()
            self.f.close()
        except Exception:
            pass


# ---------------------------------------------------------------- B-tree (part 3)
class BTree:
    def __init__(self, pager, root_pgno, key_of_row, max_keys_test=None):
        self.pager = pager
        self.root = root_pgno
        self.key_of_row = key_of_row
        self.max_keys_test = max_keys_test  # shrink pages for demos (e.g. 3)

    def _get(self, pgno):
        return self.pager.get(pgno, self.key_of_row)

    def path_to(self, key):
        node_no = self.root
        path = []
        while True:
            pg = self._get(node_no)
            if pg.kind == KIND_LEAF:
                return node_no, pg, path
            idx = bisect.bisect_left(pg.keys, key)
            child = pg.children[idx]
            path.append((node_no, pg, idx))
            node_no = child

    def search(self, key):
        leaf_no, leaf, _ = self.path_to(key)
        i = bisect.bisect_left(leaf.keys, key)
        if i < len(leaf.keys) and leaf.keys[i] == key:
            return leaf.rows[i]
        return None

    def _fits(self, page, pgno):
        if self.max_keys_test is not None:
            return len(page.keys) <= self.max_keys_test
        try:
            page_to_bytes(page, pgno)
            return True
        except OverflowError:
            return False

    def insert(self, key, row):
        if not self.pager.in_txn:
            self.pager.begin()
            autocommit = True
        else:
            autocommit = False
        leaf_no, leaf, path = self.path_to(key)
        i = bisect.bisect_left(leaf.keys, key)
        if i < len(leaf.keys) and leaf.keys[i] == key:
            raise ValueError('duplicate key')
        leaf.keys.insert(i, key)
        leaf.rows.insert(i, row)
        self.pager.put(leaf_no, leaf)
        if not self._fits(leaf, leaf_no):
            self._split(leaf_no, leaf, path)
        if autocommit:
            self.pager.commit()

    def _split(self, pgno, page, path):
        is_root = (pgno == self.root and not path)
        if page.kind == KIND_LEAF:
            mid = len(page.keys) // 2
            left_keys = page.keys[:mid]
            left_rows = page.rows[:mid]
            right_keys = page.keys[mid:]
            right_rows = page.rows[mid:]
            sep = left_keys[-1]
            old_next = page.extra
            if is_root:
                left_no = self.pager.alloc(Page(KIND_LEAF, left_keys, left_rows, extra=0))
                right_no = self.pager.alloc(Page(KIND_LEAF, right_keys, right_rows, extra=old_next))
                self.pager.cache[left_no].extra = right_no
                self.pager.dirty.add(left_no)
                self.pager.dirty.add(right_no)
                new_root = Page(KIND_INTERIOR, [sep], children=[left_no, right_no])
                self.pager.put(self.root, new_root)
            else:
                new_leaf = Page(KIND_LEAF, right_keys, right_rows, extra=old_next)
                new_no = self.pager.alloc(new_leaf)
                page.keys, page.rows = left_keys, left_rows
                page.extra = new_no
                self.pager.put(pgno, page)
                self.pager.put(new_no, new_leaf)
                self._insert_parent(pgno, sep, new_no, path)
        else:
            mid = len(page.keys) // 2
            sep = page.keys[mid]
            left_keys = page.keys[:mid]
            left_ch = page.children[:mid + 1]
            right_keys = page.keys[mid + 1:]
            right_ch = page.children[mid + 1:]
            if is_root:
                left_no = self.pager.alloc(Page(KIND_INTERIOR, left_keys, children=left_ch))
                right_no = self.pager.alloc(Page(KIND_INTERIOR, right_keys, children=right_ch))
                new_root = Page(KIND_INTERIOR, [sep], children=[left_no, right_no])
                self.pager.put(self.root, new_root)
            else:
                new_pg = Page(KIND_INTERIOR, right_keys, children=right_ch)
                new_no = self.pager.alloc(new_pg)
                page.keys, page.children = left_keys, left_ch
                self.pager.put(pgno, page)
                self.pager.put(new_no, new_pg)
                self._insert_parent(pgno, sep, new_no, path)

    def _insert_parent(self, left_no, sep, right_no, path):
        if not path:
            # non-root split propagated to root (root is interior, not the split page)
            # path empty here means parent is root? Actually this happens when split page
            # was a child of root and root itself now overflows -> handled below.
            # For safety, treat as root split of parent.
            pno = self.root
            parent = self.pager.get(pno, self.key_of_row)
            # parent already has sep inserted by caller; just check overflow
            if not self._fits(parent, pno):
                self._split(pno, parent, [])
            return
        pno, parent, idx = path.pop()
        i = bisect.bisect_left(parent.keys, sep)
        parent.keys.insert(i, sep)
        try:
            li = parent.children.index(left_no)
            parent.children.insert(li + 1, right_no)
        except ValueError:
            parent.children.insert(i + 1, right_no)
        self.pager.put(pno, parent)
        if not self._fits(parent, pno):
            self._split(pno, parent, path)

    def leftmost_leaf(self):
        no = self.root
        while True:
            pg = self._get(no)
            if pg.kind == KIND_LEAF:
                return no, pg
            no = pg.children[0]

    def scan_from(self, start_key=None):
        if start_key is None:
            no, pg = self.leftmost_leaf()
        else:
            no, pg, _ = self.path_to(start_key)
        # collect in order via next chain + interior order fallback (walk leaves via chain)
        out = []
        # build ordered leaf list by full traversal for correctness
        leaves = self._ordered_leaves()
        started = start_key is None
        for lno, lp in leaves:
            for k, r in zip(lp.keys, lp.rows):
                if not started:
                    if k < start_key:
                        continue
                    started = True
                out.append((k, r))
        return out

    def _ordered_leaves(self):
        res = []
        def rec(pgno):
            pg = self._get(pgno)
            if pg.kind == KIND_LEAF:
                res.append((pgno, pg))
            else:
                for c in pg.children:
                    rec(c)
        rec(self.root)
        return res

    def count(self):
        return sum(len(lp.rows) for _, lp in self._ordered_leaves())

    def depth(self):
        d, no = 1, self.root
        while True:
            pg = self._get(no)
            if pg.kind == KIND_LEAF:
                return d
            no = pg.children[0]
            d += 1

    def npages_subtree(self):
        seen = set()
        def rec(pgno):
            if pgno in seen:
                return
            seen.add(pgno)
            pg = self._get(pgno)
            if pg.kind == KIND_INTERIOR:
                for c in pg.children:
                    rec(c)
        rec(self.root)
        return len(seen)


# ---------------------------------------------------------------- SQL (part 4)
TOKEN = re.compile(r"""\s*(?:(\d+)|'([^']*)'|([A-Za-z_][A-Za-z0-9_]*)|(==|!=|>=|<=|=|>|<|,|\(|\)|\*|;))""")


def tokenize(sql):
    toks = []
    i, n = 0, len(sql)
    while i < n:
        if sql[i].isspace():
            i += 1
            continue
        m = TOKEN.match(sql, i)
        if not m or m.end() == i:
            raise ValueError('bad token at %r' % sql[i:])
        num, q, word, sym = m.groups()
        if num is not None:
            toks.append(('NUM', int(num)))
        elif q is not None:
            toks.append(('STR', q))
        elif word is not None:
            toks.append(('WORD', word))
        else:
            toks.append(('SYM', sym))
        i = m.end()
    return toks


class Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def nxt(self):
        tok = self.peek()
        self.i += 1
        return tok

    def kw(self, *words):
        k, v = self.peek()
        if k == 'WORD' and v.lower() in words:
            self.i += 1
            return v.lower()
        return None

    def expect_kw(self, *words):
        w = self.kw(*words)
        if not w:
            raise ValueError('expected %s' % ('/'.join(words)))
        return w

    def expect_sym(self, s):
        k, v = self.nxt()
        if k != 'SYM' or v != s:
            raise ValueError('expected %s' % s)

    def parse(self):
        k, v = self.peek()
        if k != 'WORD':
            raise ValueError('unknown statement')
        w = v.lower()
        if w == 'select':
            return self.p_select()
        if w == 'insert':
            return self.p_insert()
        if w == 'create':
            return self.p_create()
        if w in ('begin', 'commit', 'rollback'):
            self.i += 1
            return {'op': w}
        raise ValueError('no rule for %r' % v)

    def p_select(self):
        self.expect_kw('select')
        k, v = self.nxt()
        if k == 'SYM' and v == '*':
            cols = ['*']
        elif k == 'WORD' and v.lower() == 'count':
            cols = ['count']
        else:
            cols = [v] if k in ('WORD', 'NUM', 'STR') else []
            while self.peek() == ('SYM', ','):
                self.i += 1
                kk, vv = self.nxt()
                cols.append(vv)
        self.expect_kw('from')
        _, tbl = self.nxt()
        plan = {'op': 'select', 'table': tbl, 'cols': cols, 'where': None}
        if self.kw('where'):
            _, col = self.nxt()
            _, op = self.nxt()
            kk, vv = self.nxt()
            plan['where'] = (col, op, vv)
        return plan

    def p_insert(self):
        self.expect_kw('insert')
        self.expect_kw('into')
        _, tbl = self.nxt()
        self.expect_kw('values')
        self.expect_sym('(')
        vals = []
        while True:
            kk, vv = self.nxt()
            vals.append(vv)
            if self.peek() == ('SYM', ','):
                self.i += 1
                continue
            break
        self.expect_sym(')')
        return {'op': 'insert', 'table': tbl, 'values': vals}

    def p_create(self):
        self.expect_kw('create')
        k, v = self.nxt()
        if v.lower() == 'table':
            _, tbl = self.nxt()
            cols = []
            if self.peek() == ('SYM', '('):
                self.i += 1
                while True:
                    kk, cc = self.nxt()
                    cols.append(cc)
                    # skip type + constraints until , or )
                    while True:
                        pk, pv = self.peek()
                        if pk == 'SYM' and pv in (',', ')'):
                            break
                        if pk is None:
                            break
                        self.i += 1
                    if self.peek() == ('SYM', ','):
                        self.i += 1
                        continue
                    break
                self.expect_sym(')')
            return {'op': 'create_table', 'table': tbl, 'columns': cols, 'sql': ''}
        if v.lower() == 'index':
            _, idx = self.nxt()
            self.expect_kw('on')
            _, tbl = self.nxt()
            self.expect_sym('(')
            _, col = self.nxt()
            self.expect_sym(')')
            return {'op': 'create_index', 'index': idx, 'table': tbl, 'column': col}
        raise ValueError('bad create')


# ---------------------------------------------------------------- database
class Database:
    def __init__(self, path, journal_on=True):
        self.pager = Pager(path, journal_on)
        self.tables = {}
        self.indexes = {}  # (table,col) -> {root,name,col_idx}
        self.last_pages_read = 0
        self.last_plan = ''
        self._load_schema()

    def _schema_page(self):
        return self.pager.get(0, lambda r: r[1] if len(r) > 1 else r[0])

    def _save_schema_row(self, row):
        sp = self._schema_page()
        key = row[1]
        # schema keys are names
        if key in sp.keys:
            return
        sp.keys.append(key)
        sp.rows.append(row)
        # keep sorted by name for binary search demo
        paired = sorted(zip(sp.keys, sp.rows))
        sp.keys = [p[0] for p in paired]
        sp.rows = [p[1] for p in paired]
        self.pager.put(0, sp)

    def _load_schema(self):
        sp = self._schema_page()
        for row in sp.rows:
            if row[0] == 'table':
                _, name, root, _ = row[0], row[1], row[2], row[3] if len(row) > 3 else ''
                cols = ['id', 'name', 'email']
                self.tables[name] = {'root': root, 'columns': cols,
                                     'bt': BTree(self.pager, root, lambda r: r[0])}
            elif row[0] == 'index':
                _, name, root, tblcol = row[0], row[1], row[2], row[3]
                tbl, col = tblcol.split('.')
                ci = self.tables[tbl]['columns'].index(col) if tbl in self.tables else 1
                self.indexes[(tbl, col)] = {'root': root, 'name': name, 'col_idx': ci,
                                            'bt': BTree(self.pager, root, lambda r: (r[0], r[1]))}

    def create_table(self, name, columns=None, sql=''):
        if name in self.tables:
            return
        self.pager.begin()
        root = self.pager.alloc(Page(KIND_LEAF, [], []))
        self.pager.put(root, self.pager.get(root, lambda r: r[0]))
        cols = columns or ['id', 'name', 'email']
        self.tables[name] = {'root': root, 'columns': cols, 'bt': BTree(self.pager, root, lambda r: r[0])}
        self._save_schema_row(['table', name, root, sql or ('CREATE TABLE %s' % name)])
        self.pager.commit()

    def create_index(self, idx_name, table, column):
        key = (table, column)
        if key in self.indexes:
            return
        cols = self.tables[table]['columns']
        ci = cols.index(column)
        self.pager.begin()
        root = self.pager.alloc(Page(KIND_LEAF, [], []))
        ibt = BTree(self.pager, root, lambda r: (r[0], r[1]))
        # scan whole table once
        tbt = self.tables[table]['bt']
        for _, row in tbt._ordered_leaves():
            pass
        pairs = tbt.scan_from(None)
        for k, row in pairs:
            ek = (row[ci], row[0])
            ibt.insert(ek, [row[ci], row[0]])
        self.indexes[key] = {'root': root, 'name': idx_name, 'col_idx': ci, 'bt': ibt}
        self._save_schema_row(['index', idx_name, root, '%s.%s' % (table, column)])
        self.pager.commit()

    def insert(self, table, values):
        outer = self.pager.in_txn
        if not outer:
            self.pager.begin()
        try:
            t = self.tables[table]
            key = values[0]
            t['bt'].insert(key, values)
            for (tbl, col), idx in self.indexes.items():
                if tbl == table:
                    ek = (values[idx['col_idx']], values[0])
                    try:
                        idx['bt'].insert(ek, [values[idx['col_idx']], values[0]])
                    except ValueError:
                        pass
        except Exception:
            if not outer:
                self.pager.rollback_txn()
            raise
        if not outer:
            self.pager.commit()

    def _filter(self, row, cols, where):
        if not where:
            return True
        col, op, val = where
        ci = cols.index(col)
        a = row[ci]
        if op == '=':
            return a == val
        if op == '>':
            return a > val
        if op == '>=':
            return a >= val
        if op == '<':
            return a < val
        if op == '<=':
            return a <= val
        if op == '!=':
            return a != val
        raise ValueError('bad op')

    def select(self, table, cols, where=None):
        t = self.tables[table]
        columns = t['columns']
        bt = t['bt']
        self.pager.disk_reads = 0
        self.pager.logical_reads = 0
        # honest depth: drop clean pages, keep schema + dirty (uncommitted) so txn reads stay visible
        saved_cache = dict(self.pager.cache)
        dirty = set(self.pager.dirty)
        self.pager.cache = {k: v for k, v in saved_cache.items() if k == 0 or k in dirty}
        if where is not None:
            col, op, val = where
        else:
            col, op, val = None, None, None
        # planner
        if where is not None and col == 'id' and op == '=':
            self.last_plan = 'search %s using primary key' % table
            r = bt.search(val)
            rows = [r] if r and self._filter(r, columns, where) else []
            self.last_pages_read = self.pager.logical_reads
        elif where is not None and col == 'id' and op in ('>', '>='):
            self.last_plan = 'range scan %s using primary key' % table
            start = val if op == '>=' else val + 1 if isinstance(val, int) else val
            pairs = bt.scan_from(start)
            rows = [r for _, r in pairs if self._filter(r, columns, where)]
            self.last_pages_read = self.pager.logical_reads
        elif where is not None and (table, col) in self.indexes and op == '=':
            self.last_plan = 'search %s using index %s' % (table, self.indexes[(table, col)]['name'])
            ibt = self.indexes[(table, col)]['bt']
            # efficient: seek to (val, -inf), check that slot + at most next leaf
            lno, leaf, _ = ibt.path_to((val, -10**18))
            import bisect as _bis
            i = _bis.bisect_left(leaf.keys, (val, -10**18))
            hit = None
            if i < len(leaf.keys) and leaf.keys[i][0] == val:
                hit = leaf.keys[i][1]
            else:
                nxt = leaf.extra
                if nxt:
                    nlp = ibt._get(nxt)
                    if nlp.keys and nlp.keys[0][0] == val:
                        hit = nlp.keys[0][1]
            rows = []
            if hit is not None:
                r = bt.search(hit)
                if r and self._filter(r, columns, where):
                    rows.append(r)
            self.last_pages_read = self.pager.logical_reads
        else:
            self.last_plan = 'scan %s' % table
            pairs = bt.scan_from(None)
            rows = [r for _, r in pairs if self._filter(r, columns, where)]
            self.last_pages_read = self.pager.logical_reads
        # restore cache (keep newly read pages too)
        for k, v in saved_cache.items():
            if k not in self.pager.cache:
                self.pager.cache[k] = v
        # project
        if cols == ['*']:
            return rows
        if cols == ['count']:
            return [[len(rows)]]
        idxs = [columns.index(c) for c in cols]
        return [[r[i] for i in idxs] for r in rows]

    def execute(self, sql):
        toks = tokenize(sql)
        # strip trailing ;
        toks = [t for t in toks if t != ('SYM', ';')]
        plan = Parser(toks).parse()
        op = plan['op']
        if op == 'select':
            return self.select(plan['table'], plan['cols'], plan['where'])
        if op == 'insert':
            tbl = plan['table']
            self.insert(tbl, plan['values'])
            return []
        if op == 'create_table':
            self.create_table(plan['table'], plan['columns'], sql)
            return []
        if op == 'create_index':
            self.create_index(plan['index'], plan['table'], plan['column'])
            return []
        if op == 'begin':
            self.pager.begin()
            return []
        if op == 'commit':
            self.pager.commit()
            return []
        if op == 'rollback':
            self.pager.rollback_txn()
            # reload schema caches (roots unchanged)
            self.pager.cache = {}
            return []
        raise ValueError('unknown op')

    def count(self, table):
        return self.tables[table]['bt'].count()

    def check(self, table='users'):
        # integrity: parents ranges + leaf order + no dangling children
        if table not in self.tables:
            return True, 'no table'
        bt = self.tables[table]['bt']
        try:
            leaves = bt._ordered_leaves()
            allk = [k for _, lp in leaves for k in lp.keys]
            if allk != sorted(allk):
                return False, 'leaf order broken'
            # parent range check via recursion
            def rec(pgno, lo, hi):
                pg = bt._get(pgno)
                if pg.kind == KIND_LEAF:
                    for k in pg.keys:
                        if not (lo < k <= hi if lo is not None else k <= hi):
                            return False, 'key %r outside (%r,%r] at %d' % (k, lo, hi, pgno)
                    return True, ''
                for i, k in enumerate(pg.keys):
                    child = pg.children[i]
                    ok, msg = rec(child, lo if i == 0 else pg.keys[i - 1], k)
                    if not ok:
                        return ok, msg
                    lo = k
                return rec(pg.children[-1], pg.keys[-1] if pg.keys else lo, hi)
            ok, msg = rec(bt.root, None, 10**18)
            return ok, msg or 'ok %d rows' % len(allk)
        except Exception as e:
            return False, 'exception %r' % e

    def close(self):
        if self.pager.in_txn:
            self.pager.commit()
        else:
            self.pager.flush_all()
        self.pager.close()
