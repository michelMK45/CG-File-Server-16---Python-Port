"""data.big for the CGFS16 menu from a template, in plain Python (no Apt toolchain).

This is the part the CG Server 16 app needs: it only has to put a new data text into the menu's data
movie. The movie's code never changes (datamovie.py writes it once, with PLACEHOLDER as its data
string); the text is one string of its constant file (1.const), so writing a new data.big is:

  template BIG4 -> 0.apt kept as is, 1.const rebuilt with PLACEHOLDER replaced -> BIG4

64-bit .const ("Apt1"): 24-byte magic, u64 entry (offset of the movie in 0.apt), u64 count, u64 48 (header
size), then count items of (u64 type, u64 value), then the strings, NUL-terminated, unaligned, each once;
a string item's value is the offset of its text. Text is UTF-8 (as FIFA 16's movies). The result is
byte-identical to what the Apt toolchain writes for the same text (tests/test_datafile.py).

Shared by the cgfs-ingame project (tools/datafile.py, the original) and the CG Server 16 app
(server16_py/ingame_datafile.py, a byte-identical copy: keep them in sync; cgfs-ingame's
tests/test_repo_copies.py checks it). Self-contained: standard library only, Python 3.9+.
"""
import struct

PLACEHOLDER = 'CGFS16_DATA_PLACEHOLDER'


# --- BIG4 (as FIFA 16's community UI mods: uncompressed, 64-byte aligned, no trailer) -----------------

def big_entries(data):
    """[(name, bytes)] of an uncompressed BIG4/BIGF archive."""
    if data[:4] not in (b'BIG4', b'BIGF'):
        raise ValueError('not a BIG archive')
    count = struct.unpack_from('>I', data, 8)[0]
    p, out = 16, []
    for _ in range(count):
        offset, size = struct.unpack_from('>II', data, p)
        end = data.index(b'\0', p + 8)
        out.append((data[p + 8:end].decode('latin-1'), data[offset:offset + size]))
        p = end + 1
    return out


def big4(files):
    names = b''.join(struct.pack('>II', 0, 0) + n.encode() + b'\0' for n, _ in files)
    header_size = 16 + len(names) + 8
    off = (header_size + 63) // 64 * 64
    table, body, pos = bytearray(), bytearray(), off
    for name, blob in files:
        pad = -len(blob) % 64 if blob else 0
        table += struct.pack('>II', pos, len(blob)) + name.encode() + b'\0'
        body += blob + bytes(pad)
        pos += len(blob) + pad
    head = b'BIG4' + struct.pack('<I', off + len(body)) + struct.pack('>II', len(files), header_size)
    head += bytes(table) + b'L286' + bytes.fromhex('15050000')
    return head + bytes(off - len(head)) + bytes(body)


# --- 64-bit Apt constant file -------------------------------------------------------------------

def read_const(data):
    """(entry, [(type, value)]) with string values as bytes."""
    if data[:4] != b'Apt1':
        raise ValueError('not a 64-bit Apt constant file')
    entry, count, hsize = struct.unpack_from('<QQQ', data, 24)
    if hsize != 48:
        raise ValueError(f'unexpected .const header size {hsize}')
    items = []
    for i in range(count):
        t, v = struct.unpack_from('<QQ', data, 48 + 16 * i)
        if t == 1:
            v = data[v:data.index(b'\0', v)]
        items.append((t, v))
    return entry, items


def write_const(entry, items):
    buf = bytearray(b'Apt1' + bytes(20) + struct.pack('<QQQ', entry, len(items), 48))
    base = len(buf)
    buf += bytes(16 * len(items))
    placed = {}
    for i, (t, v) in enumerate(items):
        if t == 1:
            if v not in placed:
                placed[v] = len(buf)
                buf += v + b'\0'
            v = placed[v]
        struct.pack_into('<QQ', buf, base + 16 * i, t, v)
    return bytes(buf)


def render(template_big, text):
    """data.big bytes: the template with its PLACEHOLDER string replaced by text."""
    parts = big_entries(template_big)
    blobs = dict(parts)
    entry, items = read_const(blobs['1'])
    key = PLACEHOLDER.encode()
    if sum(1 for t, v in items if t == 1 and v == key) != 1:
        raise ValueError('the template does not hold the data placeholder exactly once')
    new = text.encode('utf-8')
    if b'\0' in new:
        raise ValueError('data text cannot hold NUL')
    items = [(t, new if t == 1 and v == key else v) for t, v in items]
    return big4([(n, write_const(entry, items) if n == '1' else b) for n, b in parts])


# --- the data text (same format as model.apply_data_body reads) -----------------------------------

def encode(values, selected=None, source='CG Server 16', stamp='', ack=None):
    """values: {row NAME: [texts]}, selected: {row NAME: index}, ack: the last menu save the app processed
    (the menu keeps its own newer save over the app's selection until the app has seen it)."""
    lines = [f'SOURCE={source}', f'STAMP={stamp}'] + ([f'ACK={int(ack)}'] if ack is not None else [])
    for name, texts in values.items():
        for t in texts:
            if any(c in t for c in '|=\n'):
                raise ValueError(f'{t!r}: values cannot hold | = or a line break')
        lines.append(f'{name}=' + '|'.join(texts))
    for name, index in (selected or {}).items():
        lines.append(f'{name}_SEL={int(index)}')
    for line in lines[:2]:
        if '\n' in line or line.count('=') != 1:
            raise ValueError(f'bad line {line!r}')
    return '\n'.join(lines)
