"""Install / uninstall the CGFS16 in-game menu's files in a FIFA 16 install, and the release package.

Standard library only: the CG Server 16 carries a byte-identical copy (server16_py/ingame_modinstall.py)
and installs the menu from a release package (resources/ingame/mod) without this project's toolchain.

  GameFiles(root)      a FIFA 16 install: its .big index (read_packed, read) and .bh name hashes
  install(game, files, patches, info)
                       files: rel -> bytes, or a function(original bytes) -> bytes | None (a changed copy of
                       one of the game's files; None = leave it alone). patches: rel -> (patch, unpatch) of
                       text files other mods also edit. Everything is computed and checked before anything
                       is written. A file the game had is backed up and put back by uninstall; a loose
                       file the game did not have gets its name hash zeroed in the .bh files (as FIP's
                       regenerator does) and uninstall puts the hash back.
  uninstall(game, patches)
  write_package(folder, info, files, variants) / load_package(folder)
                       the release package: prebuilt files plus, for a game file we change (the KickOffHub
                       movie), one prebuilt copy per known original (keyed by the original's sha1)
Bookkeeping: <game>/_cgfs16_ingame/manifest.json (backups next to it), shared by every installer.
"""
import hashlib
import json
import os
import shutil
import struct
import subprocess
import zlib

STATE_DIR = '_cgfs16_ingame'
BH_BACKUP = '_bh_original'  # same folder FIP's regenerator and the Decomp tools use
PACKAGE_INFO = 'package.json'


# --- .big archives ---------------------------------------------------------------------------------

def big_entries(data):
    """(offset, size, name) of every entry of a BIG4/BIGF header."""
    if data[:4] not in (b'BIG4', b'BIGF'):
        raise ValueError(f'not a BIG archive ({data[:4]!r})')
    count = struct.unpack_from('>I', data, 8)[0]
    p = 16
    for _ in range(count):
        offset, size = struct.unpack_from('>II', data, p)
        p += 8
        end = data.index(b'\0', p)
        yield offset, size, data[p:end].decode('latin-1')
        p = end + 1


def unchunk(data):
    """A chunkzip entry decompressed (stored and deflate chunks: the PC files); anything else as is."""
    if data[:8] not in (b'chunkzip', b'chunklzx'):
        return data
    _version, usize, _chunk_size, count, align = struct.unpack_from('>5I', data, 8)
    p = 28
    out = bytearray()
    for _ in range(count):
        p = (p + 8 + align - 1) // align * align if align else p + 8
        clen, ctype = struct.unpack_from('>II', data, p - 8)
        chunk = data[p:p + clen]
        p += clen
        if ctype == 1:
            out += zlib.decompressobj(-15).decompress(chunk)
        elif ctype == 0:
            out += chunk
        else:
            raise ValueError(f'chunkzip: chunk type {ctype}')
    if len(out) != usize:
        raise ValueError(f'chunkzip: {len(out)} bytes, expected {usize}')
    return bytes(out)


def read_header(f):
    """Only the entry table: the main .big files are up to 1.8 GB."""
    head = f.read(16)
    f.seek(0)
    return f.read(16 + struct.unpack_from('>I', head, 12)[0])


class GameFiles:
    """A FIFA 16 install. rel paths are like 'data/ui/nav/mainfeflow.nav' (any case)."""

    def __init__(self, root):
        self.root = str(root)
        if not os.path.exists(os.path.join(self.root, 'fifa16.exe')):
            raise FileNotFoundError(f'{self.root} is not a FIFA 16 install (no fifa16.exe)')
        self._index = None

    def path(self, rel):
        return os.path.join(self.root, *rel.split('/'))

    def bigs(self):
        """Archives with a .bh index, data_patch.big first (it overrides the others)."""
        names = sorted(n for n in os.listdir(self.root)
                       if n.lower().endswith('.big') and os.path.exists(os.path.join(self.root, n[:-4] + '.bh')))
        names.sort(key=lambda n: n.lower() != 'data_patch.big')
        return names

    def index(self):
        """lower-case entry name -> [(big, offset, size)] in priority order."""
        if self._index is None:
            self._index = {}
            for big in self.bigs():
                with open(os.path.join(self.root, big), 'rb') as f:
                    for o, s, n in big_entries(read_header(f)):
                        self._index.setdefault(n.lower(), []).append((big, o, s))
        return self._index

    def in_big(self, rel):
        return bool(self.index().get(rel.lower()))

    def read_packed(self, rel):
        """The entry as stored in the game's .big files (not the loose file), decompressed."""
        hits = self.index().get(rel.lower())
        if not hits:
            raise KeyError(f'{rel} is not in any .big of {self.root}')
        big, o, s = hits[0]
        with open(os.path.join(self.root, big), 'rb') as f:
            f.seek(o)
            return unchunk(f.read(s))

    def read(self, rel):
        """What the game loads: the loose file if there is one, else the .big entry."""
        p = self.path(rel)
        if os.path.exists(p):
            with open(p, 'rb') as f:
                return f.read()
        return self.read_packed(rel)

    # .bh name hashes ---------------------------------------------------------------
    def _bh_slots(self, rel):
        """[(bh file, entry index)] of every .big entry named rel."""
        out = []
        for big in self.bigs():
            with open(os.path.join(self.root, big), 'rb') as f:
                for i, (_o, _s, n) in enumerate(big_entries(read_header(f))):
                    if n.lower() == rel.lower():
                        out.append((big[:-4] + '.bh', i))
        return out

    def hash_zeroed(self, rel):
        """True if every .bh slot of rel is zero (the game then reads the loose file)."""
        for bh, i in self._bh_slots(rel):
            with open(os.path.join(self.root, bh), 'rb') as f:
                f.seek(16 + i * 20 + 12)
                if f.read(8) != bytes(8):
                    return False
        return True

    def zero_hash(self, rel):
        """Zeroes rel's name hash in every .bh (backing up each .bh once). Returns the slots changed."""
        changed = []
        for bh, i in self._bh_slots(rel):
            path = os.path.join(self.root, bh)
            with open(path, 'rb') as f:
                data = bytearray(f.read())
            if data[:4] != b'ViV4':
                raise ValueError(f'{path}: not a ViV4 index')
            at = 16 + i * 20 + 12
            if data[at:at + 8] == bytes(8):
                continue
            backup = os.path.join(self.root, BH_BACKUP)
            os.makedirs(backup, exist_ok=True)
            if not os.path.exists(os.path.join(backup, bh)):
                with open(os.path.join(backup, bh), 'wb') as f:
                    f.write(data)
            changed.append({'bh': bh, 'index': i, 'hash': data[at:at + 8].hex()})
            data[at:at + 8] = bytes(8)
            with open(path, 'wb') as f:
                f.write(data)
        return changed

    def restore_hash(self, slot):
        """Undoes one zero_hash slot (only if it is still zero)."""
        path = os.path.join(self.root, slot['bh'])
        with open(path, 'rb') as f:
            data = bytearray(f.read())
        at = 16 + slot['index'] * 20 + 12
        if data[at:at + 8] == bytes(8):
            data[at:at + 8] = bytes.fromhex(slot['hash'])
            with open(path, 'wb') as f:
                f.write(data)


def game_running():
    """True if fifa16.exe is running (install and uninstall need it closed)."""
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq fifa16.exe'], capture_output=True, text=True,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    except OSError:
        return False
    return 'fifa16.exe' in out.lower()


# --- install / uninstall ---------------------------------------------------------------------------

def manifest_path(game):
    return os.path.join(game.root, STATE_DIR, 'manifest.json')


def load_manifest(game):
    p = manifest_path(game)
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    return None


def save_manifest(game, man):
    p = manifest_path(game)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(man, f, indent=2, ensure_ascii=False)


def _backup_path(game, rel):
    return os.path.join(game.root, STATE_DIR, 'backup', *rel.split('/'))


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def original(game, rel):
    """The game's own copy of a file we replace with a changed one: our backup once installed (the
    file in the game is then ours), else what the game loads now."""
    man = load_manifest(game)
    if man and rel in man['created']:
        if not man['created'][rel].get('had_file'):
            return game.read_packed(rel)  # there was no loose file: the game's is in its .big
        with open(_backup_path(game, rel), 'rb') as f:
            return f.read()
    return game.read(rel)


def _remove_created(game, man, rel, log):
    """Deletes a file install created (or puts back the one it replaced)."""
    info = man['created'].pop(rel)
    dst = game.path(rel)
    saved = _backup_path(game, rel)
    if info.get('had_file') and os.path.exists(saved):
        shutil.copy2(saved, dst)
    elif os.path.exists(dst):
        os.remove(dst)
    for slot in [s for s in man['hashes'] if s.get('rel') == rel]:
        if not info.get('had_file'):
            game.restore_hash(slot)
        man['hashes'].remove(slot)
    d = os.path.dirname(dst)  # empty folders we made
    while d.startswith(os.path.join(game.root, 'data', 'ui')) and os.path.isdir(d) and not os.listdir(d):
        os.rmdir(d)
        d = os.path.dirname(d)
    log(f'- {rel}')


def _zero_hash(game, man, rel):
    if game.in_big(rel) and not game.hash_zeroed(rel):
        man['hashes'] += [dict(slot, rel=rel) for slot in game.zero_hash(rel)]


def install(game, files, patches, info, check=None, log=print):
    """Installs (or updates an older install of) the files and patches; returns the manifest.
    check(rel, text) raises ValueError when a patched text lacks something. FIFA 16 must be closed."""
    man = load_manifest(game) or {'created': {}, 'patched': {}, 'hashes': []}
    contents, skipped = {}, []
    for rel, data in files.items():
        if callable(data):
            data = data(original(game, rel))
            if data is None:
                skipped.append(rel)
                continue
        contents[rel] = data
    changed = {}
    for rel, (patch, unpatch) in patches.items():  # every text checked before writing anything
        after = patch(unpatch(game.read(rel).decode('latin-1')))  # re-patch: an older install is replaced
        if check:
            check(rel, after)
        changed[rel] = after
    for rel in [r for r in man['created'] if r not in contents]:  # left by an older install, or skipped now
        _remove_created(game, man, rel, log)
    for rel, data in contents.items():
        dst = game.path(rel)
        if rel not in man['created']:
            had = os.path.exists(dst)
            if had:  # not ours: keep it to put back on uninstall
                _write(_backup_path(game, rel), open(dst, 'rb').read())
            man['created'][rel] = {'had_file': had}
        _write(dst, data)
        _zero_hash(game, man, rel)
        log(f'+ {rel}')
    for rel, after in changed.items():
        dst = game.path(rel)
        if rel not in man['patched']:
            loose = os.path.exists(dst)
            if loose:  # safety copy only: uninstall removes our block instead of restoring this
                _write(_backup_path(game, rel), open(dst, 'rb').read())
            man['patched'][rel] = {'had_loose': loose}
        _write(dst, after.encode('latin-1'))
        _zero_hash(game, man, rel)
        log(f'~ {rel}')
    for rel in skipped:
        log(f'! {rel}: not a copy this package knows, left as it is')
    man.update(info, skipped=skipped)
    save_manifest(game, man)
    return man


def uninstall(game, patches, log=print):
    """Removes exactly what install added. False if nothing was installed."""
    man = load_manifest(game)
    if not man:
        return False
    for rel in list(man['created']):
        _remove_created(game, man, rel, log)
    for rel in man['patched']:
        dst = game.path(rel)
        if not os.path.exists(dst) or rel not in patches:
            continue
        _patch, unpatch = patches[rel]
        text = unpatch(game.read(rel).decode('latin-1'))
        info = man['patched'][rel]
        if not info.get('had_loose') and game.in_big(rel) and text.encode('latin-1') == game.read_packed(rel):
            os.remove(dst)  # identical to the game's own: no loose file, as before
        else:
            _write(dst, text.encode('latin-1'))
        log(f'~ {rel} (sin el bloque CGFS16)')
    for slot in man.get('hashes', []):  # those of the patched files
        game.restore_hash(slot)
    os.remove(manifest_path(game))
    shutil.rmtree(os.path.join(game.root, STATE_DIR, 'backup'), ignore_errors=True)
    try:
        os.rmdir(os.path.join(game.root, STATE_DIR))
    except OSError:
        pass
    return True


# --- release package -------------------------------------------------------------------------------

def sha1(data):
    return hashlib.sha1(data).hexdigest()


def write_package(folder, info, files, variants):
    """files: rel -> bytes; variants: rel -> {sha1 of the game's original: our copy}. Replaces the folder
    (only one that is empty or holds a package)."""
    if os.path.isdir(folder) and os.listdir(folder) and not os.path.exists(os.path.join(folder, PACKAGE_INFO)):
        raise ValueError(f'{folder} is not empty and holds no {PACKAGE_INFO}: not replaced')
    shutil.rmtree(folder, ignore_errors=True)
    index = dict(info, files=sorted(files), variants={})
    for rel, data in files.items():
        _write(os.path.join(folder, 'files', *rel.split('/')), data)
    for rel, copies in variants.items():
        index['variants'][rel] = {}
        for key, data in copies.items():
            name = f'variants/{key}.big'
            _write(os.path.join(folder, *name.split('/')), data)
            index['variants'][rel][key] = name
    with open(os.path.join(folder, PACKAGE_INFO), 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    return index


def load_package(folder):
    """(info, files) for install(): a variant file is a function picking the copy for the game's original."""
    with open(os.path.join(folder, PACKAGE_INFO), encoding='utf-8') as f:
        index = json.load(f)
    files = {}
    for rel in index['files']:
        with open(os.path.join(folder, 'files', *rel.split('/')), 'rb') as f:
            files[rel] = f.read()
    for rel, copies in index['variants'].items():
        def pick(orig, copies=copies):
            name = copies.get(sha1(orig))
            if name is None:
                return None
            with open(os.path.join(folder, *name.split('/')), 'rb') as f:
                return f.read()
        files[rel] = pick
    info = {k: v for k, v in index.items() if k not in ('files', 'variants')}
    return info, files
