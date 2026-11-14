"""data.big for the CGFS16 menu from a template, in plain Python (no Apt toolchain).

This is the part the CG Server 16 app needs: it only has to put a new data text into the menu's data
movie. The movie's code never changes (datamovie.py writes it once, with placeholder(0..CHUNKS-1) as its
data strings); the text goes in CHUNKS strings of its constant file (1.const), so writing a new data.big is:

  template BIG4 -> 0.apt kept as is, 1.const rebuilt with the placeholders replaced -> BIG4

FIFA 16 crashes when one of the movie's strings is too long (2026-11-14, FIFA Infinity 9: a 74 KB data
string crashed on opening the menu, 52 KB and FIP's 59 KB did not; FIFA's own movies keep 188 KB of
constants, so the limit is per string). pack() keeps every string under CHUNK_BYTES: it cuts the text at
line ends into chunks, a longer line into `KEY+=more|values` continuation lines (the menu appends their
values to KEY's list, never joining them into one string), and writes an image list's shared folder and
extension once (IMGPRE_<KEY>, IMGSUF_<KEY>). unpack() is the reverse, as the menu reads it.

64-bit .const ("Apt1"): 24-byte magic, u64 entry (offset of the movie in 0.apt), u64 count, u64 48 (header
size), then count items of (u64 type, u64 value), then the strings, NUL-terminated, unaligned, each once;
a string item's value is the offset of its text. Text is UTF-8 (as FIFA 16's movies). The result is
byte-identical to what the Apt toolchain writes for the same text (tests/test_datafile.py).

Shared by the cgfs-ingame project (tools/datafile.py, the original) and the CG Server 16 app
(server16_py/ingame_datafile.py, a byte-identical copy: keep them in sync; cgfs-ingame's
tests/test_repo_copies.py checks it). Self-contained: standard library only, Python 3.9+.
"""
import os
import struct

PLACEHOLDER = 'CGFS16_DATA_PLACEHOLDER'
CHUNKS = 16             # strings of data in the movie: 16 x 30 KB, far above any game's lists
CHUNK_BYTES = 30000     # per string (UTF-8 bytes); a 33 KB string is proven fine in FIFA, 74 KB crashes


def placeholder(i):
    return f'{PLACEHOLDER}_{i}'


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
    """data.big bytes: the template with its placeholder strings replaced by pack(text) (ValueError if it
    does not fit)."""
    parts = big_entries(template_big)
    blobs = dict(parts)
    entry, items = read_const(blobs['1'])
    keys = [placeholder(i).encode() for i in range(CHUNKS)]
    for key in keys:
        if sum(1 for t, v in items if t == 1 and v == key) != 1:
            raise ValueError(f'the template does not hold {key.decode()} exactly once')
    if b'\0' in text.encode('utf-8'):
        raise ValueError('data text cannot hold NUL')
    chunks = pack(text)
    new = dict(zip(keys, [c.encode('utf-8') for c in chunks] + [b''] * (CHUNKS - len(chunks))))
    items = [(t, new.get(v, v) if t == 1 else v) for t, v in items]
    return big4([(n, write_const(entry, items) if n == '1' else b) for n, b in parts])


def read_text(data_big):
    """The data text of a data.big written by render (unpack of its chunks, in order)."""
    entry, items = read_const(dict(big_entries(data_big))['1'])
    # render keeps the template's order: the chunks are the strings that replaced the placeholders, which
    # datamovie.source pushes first (items 0..CHUNKS-1)
    return unpack([v.decode('utf-8') for t, v in items[:CHUNKS]])


# --- strings FIFA 16 can hold -------------------------------------------------------------------------

def _size(s):
    return len(s.encode('utf-8'))


def _compact_images(line):
    """IMG_<KEY>=a/b/x.dds|a/b/y.dds -> [IMGPRE_<KEY>=a/b/, IMGSUF_<KEY>=.dds, IMG_<KEY>=x|y] when shorter."""
    key, _, value = line.partition('=')
    values = value.split('|')
    full = [v for v in values if v]
    if len(full) < 2:
        return [line]
    pre = os.path.commonprefix(full)
    pre = pre[:pre.rfind('/') + 1]
    suf = os.path.commonprefix([v[len(pre):][::-1] for v in full])[::-1]
    suf = suf[suf.find('.'):] if '.' in suf else ''
    if not pre and not suf:
        return [line]
    stripped = [v[len(pre):len(v) - len(suf)] if v else '' for v in values]
    if any(v and not s for v, s in zip(values, stripped)):   # a value that would read as "no image"
        return [line]
    name = key[len('IMG_'):]
    out = [f'IMGPRE_{name}={pre}', f'IMGSUF_{name}={suf}', f'{key}=' + '|'.join(stripped)]
    return out if sum(map(_size, out)) < _size(line) else [line]


def _split_line(line):
    """A line over CHUNK_BYTES -> the line and `KEY+=...` continuations, cut between values."""
    if _size(line) <= CHUNK_BYTES:
        return [line]
    key, _, value = line.partition('=')
    out, head, cur, size = [], f'{key}=', [], 0   # size: of head + '|'.join(cur)
    for v in value.split('|'):
        n = _size(v)
        if cur and size + 1 + n > CHUNK_BYTES:
            out.append(head + '|'.join(cur))
            head, cur = f'{key}+=', []
        size = (size + 1 + n) if cur else _size(head) + n
        cur.append(v)
        if size > CHUNK_BYTES:
            raise ValueError(f'{key}: one value is longer than {CHUNK_BYTES} bytes')
    out.append(head + '|'.join(cur))
    return out


def pack(text):
    """The data text as at most CHUNKS strings of at most CHUNK_BYTES each (ValueError if it does not fit)."""
    lines = []
    for line in text.split('\n'):
        for part in (_compact_images(line) if line.startswith('IMG_') else [line]):
            lines += _split_line(part)
    chunks, cur, size = [], [], 0   # size: of '\n'.join(cur)
    for line in lines:
        n = _size(line)
        if cur and size + 1 + n > CHUNK_BYTES:
            chunks.append('\n'.join(cur))
            cur = []
        size = (size + 1 + n) if cur else n
        cur.append(line)
    chunks.append('\n'.join(cur))
    if len(chunks) > CHUNKS:
        raise ValueError(f'data text of {_size(text)} bytes does not fit in {CHUNKS} strings of {CHUNK_BYTES}')
    return chunks


def unpack(chunks):
    """The text pack() was given, from its chunks (empty ones are ignored), read as the menu reads it."""
    lines = []
    for chunk in chunks:
        lines += chunk.split('\n') if chunk else []
    kv, order = {}, []
    for line in lines:
        key, _, value = line.partition('=')
        if key.endswith('+') and key[:-1] in kv:
            kv[key[:-1]].append(value)
            continue
        if key not in kv:
            order.append(key)
        kv[key] = [value]
    out = []
    for key in order:
        if key.startswith(('IMGPRE_', 'IMGSUF_')) and 'IMG_' + key[7:] in kv:
            continue
        value = '|'.join(kv[key])
        name = key[len('IMG_'):]
        if key.startswith('IMG_') and f'IMGPRE_{name}' in kv:
            pre, suf = kv[f'IMGPRE_{name}'][0], kv.get(f'IMGSUF_{name}', [''])[0]
            value = '|'.join(pre + v + suf if v else '' for v in value.split('|'))
        out.append(f'{key}={value}')
    return '\n'.join(out)


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
