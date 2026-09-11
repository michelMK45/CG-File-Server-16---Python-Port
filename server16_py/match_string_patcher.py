from __future__ import annotations

import ctypes
import os
import threading
import time
from typing import TYPE_CHECKING

from .win32_types import MEMORY_BASIC_INFORMATION

if TYPE_CHECKING:
    from .app import Server16App

# Diagnostic aid (2026-09-09): Cheat Engine's own string scan reliably finds
# "Waldstadion" at a live-confirmed address (editing it directly there DOES
# change what the pre-match screen shows), yet _scan_memory's own 20-attempt,
# full-coverage runs (CLAUDE.md §7 Part 13) never find it -- meaning
# _scan_memory's own VirtualQueryEx region walk very likely never actually
# visits (or silently mis-reads) the specific region that address lives in,
# something CE's own scanner doesn't have trouble with. Set
# CGFS_DEBUG_SCAN_TARGET (a hex address, e.g. "9448989D") before launching to
# have every _scan_memory call log exactly what VirtualQueryEx reports for
# whatever region contains that address -- and whether the walk ever reaches
# it at all -- to tell apart "region skipped by our filters/enumeration" from
# "region visited and read, pattern search itself just isn't finding it."
def _parse_debug_target() -> int | None:
    raw = os.environ.get("CGFS_DEBUG_SCAN_TARGET", "").strip()
    if not raw:
        return None
    try:
        return int(raw, 16)
    except ValueError:
        return None


_DEBUG_SCAN_TARGET = _parse_debug_target()

# How much memory to scan at a time (4MB chunks)
SCAN_CHUNK = 4 * 1024 * 1024
# Max readable+committed memory to scan in total per call. Originally 512MB,
# sized for the old synchronous single-attempt scanner where every extra
# second was felt as UI lag on the Tk main thread. Both scanners that call
# this now (MatchStringPatchCoordinator, StadiumDbNamePatchCoordinator) run
# entirely on background threads, so that constraint no longer applies -- and
# a live investigation (2026-09-09) found EVERY scan attempt across the whole
# scoreboardstdname debugging saga returned 0 candidates, for every text
# variant tried, which a 512MB cap silently truncating the scan before it
# ever reached the right region would fully explain: FIFA16.exe is a 32-bit
# process (see §2.2's injector bitness guard, which refuses a native x64
# target), so its own address space can be up to ~4GB, and a heavily modded
# (FIP) install's committed working set can plausibly exceed 512MB of
# readable memory well before reaching wherever UI text buffers happen to
# live. Raised to comfortably cover a 32-bit process's entire address space.
SCAN_MAX = 4 * 1024 * 1024 * 1024

# VirtualQueryEx.argtypes is mutated (assigned) below every time a scan runs.
# If two scans ever ran on two threads at once, each would stomp the other's
# argtypes with its own POINTER(MEMORY_BASIC_INFORMATION) class object between
# the assignment and the call, occasionally raising a TypeError from ctypes
# ("expected LP_MEMORY_BASIC_INFORMATION instance instead of pointer to
# MEMORY_BASIC_INFORMATION"). This lock keeps the whole scan (argtypes
# assignment + the VirtualQueryEx/ReadProcessMemory loop) serialized instead.
_SCAN_LOCK = threading.Lock()


def _decode_printable_text(data: bytes) -> str | None:
    """Decode a NUL-free chunk without rejecting localized stadium names.

    FIFA strings are normally UTF-8, but some database/build combinations can
    expose Windows-1252 bytes. Accept either encoding only when the decoded
    text has no control characters other than common whitespace -- this is
    what keeps a binary (non-string) chunk from being misread as a match.
    """
    for encoding in ("utf-8", "cp1252"):
        try:
            text = data.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue
        if all(ch.isprintable() or ch in "\t\r\n" for ch in text):
            return text
    return None


def _scan_memory(
    app: "Server16App", pattern: bytes, start_addr: int = 0, end_addr: int = 0x7FFFFFFFFFFF
) -> list[int]:
    """Scan FIFA process memory for a byte pattern. Returns list of addresses.

    ``start_addr``/``end_addr`` bound the walk (defaults cover the whole
    address space, i.e. unchanged behavior for every existing caller). Added
    2026-09-11 so a caller who already knows the target is very likely to
    live inside a narrow address window (see
    ``STDNAME_SAFE_EXTEND_PRIORITY_RANGES`` in offsets.py and
    ``_find_isolated_occurrences``'s ``priority_ranges`` parameter) can scan
    just that window first -- a few MB instead of up to 4GB -- rather than
    depending on luck within a slow, full-process scan racing a limited
    per-match time budget.
    """
    kernel32 = app.memory.kernel32
    handle = app.memory.process_handle
    if not handle:
        return []

    MEM_COMMIT = 0x1000
    PAGE_READABLE = {0x02, 0x04, 0x20, 0x40}  # READONLY, READWRITE, EXECUTE_READ, EXECUTE_READWRITE
    PAGE_GUARD = 0x100
    PAGE_NOACCESS = 0x01

    results: list[int] = []
    addr = start_addr
    scanned = 0
    started = time.perf_counter()
    mbi = MEMORY_BASIC_INFORMATION()
    debug_target = _DEBUG_SCAN_TARGET
    debug_target_seen = False

    with _SCAN_LOCK:
        VirtualQueryEx = kernel32.VirtualQueryEx
        VirtualQueryEx.restype = ctypes.c_size_t
        VirtualQueryEx.argtypes = [
            ctypes.c_void_p, ctypes.c_ulonglong,
            ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t
        ]

        while scanned < SCAN_MAX:
            ret = VirtualQueryEx(handle, addr, ctypes.byref(mbi), ctypes.sizeof(mbi))
            if ret == 0:
                break
            region_size = mbi.RegionSize
            base_protect = mbi.Protect & 0xFF
            is_readable = base_protect in PAGE_READABLE
            has_guard = (mbi.Protect & PAGE_GUARD) != 0
            no_access = base_protect == PAGE_NOACCESS
            region_passes_filter = (
                mbi.State == MEM_COMMIT and is_readable and not has_guard
                and not no_access and region_size > 0
            )
            if debug_target is not None and region_size > 0 and addr <= debug_target < addr + region_size:
                debug_target_seen = True
                app.log(
                    f"[scan-diag] target 0x{debug_target:X} is inside region "
                    f"base=0x{addr:X} size=0x{region_size:X} state=0x{mbi.State:X} "
                    f"protect=0x{mbi.Protect:X} allocprotect=0x{mbi.AllocationProtect:X} "
                    f"passes_filter={region_passes_filter}"
                )
            if region_passes_filter:
                # Read this region in chunks
                offset = 0
                while offset < region_size:
                    chunk_size = min(SCAN_CHUNK, region_size - offset)
                    buf = ctypes.create_string_buffer(chunk_size)
                    read = ctypes.c_size_t()
                    ok = kernel32.ReadProcessMemory(
                        handle,
                        ctypes.c_void_p(addr + offset),
                        buf, chunk_size,
                        ctypes.byref(read)
                    )
                    if (
                        debug_target is not None
                        and addr + offset <= debug_target < addr + offset + chunk_size
                    ):
                        target_in_chunk = debug_target - (addr + offset)
                        if ok:
                            sample = buf.raw[target_in_chunk: target_in_chunk + 32]
                        else:
                            sample = b""
                        err = ctypes.get_last_error() if not ok else 0
                        app.log(
                            f"[scan-diag] chunk covering target: ok={bool(ok)} "
                            f"read={read.value}/{chunk_size} last_error={err} "
                            f"bytes_at_target={sample!r}"
                        )
                    if ok and read.value > 0:
                        data = buf.raw[:read.value]
                        pos = 0
                        while True:
                            idx = data.find(pattern, pos)
                            if idx == -1:
                                break
                            results.append(addr + offset + idx)
                            pos = idx + 1
                    offset += chunk_size
                scanned += region_size
            if region_size <= 0:
                # Defensive step to avoid infinite loops on malformed region metadata.
                addr += 0x1000
            else:
                addr += region_size
            if addr >= end_addr:
                break

    if debug_target is not None and not debug_target_seen:
        app.log(
            f"[scan-diag] target 0x{debug_target:X} was NEVER inside any region "
            f"VirtualQueryEx reported during this walk -- the enumeration itself "
            f"skipped past it (region-stepping bug), not a filter/read failure"
        )

    elapsed = time.perf_counter() - started
    app.log(
        f"Memory scan: {scanned / (1024 * 1024):.0f}MB readable+committed "
        f"in {elapsed:.2f}s, {len(results)} raw hit(s)"
    )
    return list(dict.fromkeys(results))


def _looks_like_text_byte(b: int) -> bool:
    return 0x20 <= b < 0x7F or b in (0x09, 0x0A, 0x0D)


def _find_isolated_occurrences(
    app: "Server16App",
    pattern: bytes,
    term_width: int,
    priority_ranges: list[tuple[int, int]] | None = None,
) -> list[int]:
    """Scan for `pattern` and keep only occurrences that look like a whole,
    standalone string -- not a substring of some longer, unrelated string.

    A real string field is always followed by a full NUL terminator of the
    given width (2 bytes for UTF-16LE Windows UI text, 1 for UTF-8/ASCII).
    Before the match, a full NUL terminator qualifies too, but for UTF-8/
    ASCII a single non-printable byte (a tag/type/flag byte from a preceding
    struct field, not more text) is ALSO accepted -- confirmed live
    2026-09-10 for the exact render-source buffer originally located via
    Cheat Engine (see CGFS_DEBUG_SCAN_TARGET's docstring below: live-edited
    directly in the game process and confirmed to change the pre-match
    presentation screen), which is preceded by a single 0xCC/0xCD-style byte,
    not a NUL. Only reject when the preceding byte looks like it's actually
    part of more real text -- the genuine "substring of a longer string"
    failure mode this check exists to catch. The byte(s) immediately before
    the match are read too so a match at the very start of a buffer (nothing
    readable "before" it) is still accepted.

    ``priority_ranges`` (added 2026-09-11): a list of narrow address windows
    to scan FIRST, before the full process-wide scan. Confirmed live
    (offsets.STDNAME_SAFE_EXTEND_SUFFIXES' docstring) that the actual
    render-source buffer's address clusters within a fairly narrow window
    across separate FIFA launches on a given install (ASLR randomizes the
    heap segment's base within bounded entropy, not the offset of this
    allocation within it). A live session found the known-safe buffer only
    on scan attempt 15/20 of a full 4GB-capped scan, ~20+ seconds after the
    bumper -- the match ended before it was ever found. Scanning a few MB
    around the known cluster first (milliseconds, not the ~0.5-1s+ a full
    scan costs) makes finding it nearly instant instead of a race against a
    limited per-match time budget. If nothing is found there, falls back to
    the ordinary unrestricted scan exactly as before -- this never narrows
    what gets found, only tries a fast, likely spot first.
    """
    addresses: list[int] = []
    if priority_ranges:
        for start, end in priority_ranges:
            addresses.extend(_scan_memory(app, pattern, start_addr=start, end_addr=end))
        addresses = list(dict.fromkeys(addresses))
        if addresses:
            app.log(
                f"Stadium DB name patcher: found {len(addresses)} raw hit(s) in the "
                f"priority address range(s), skipping the full scan"
            )
    if not addresses:
        addresses = _scan_memory(app, pattern)
    isolated: list[int] = []
    rejected: list[int] = []
    unreadable = 0
    zero = b"\x00" * term_width
    for addr in addresses:
        try:
            after = app.memory.read_process_memory(addr + len(pattern), term_width)
            if after != zero:
                rejected.append(addr)
                continue
            if addr >= term_width:
                before = app.memory.read_process_memory(addr - term_width, term_width)
                if before != zero and (term_width != 1 or _looks_like_text_byte(before[0])):
                    rejected.append(addr)
                    continue
            isolated.append(addr)
        except Exception:
            # A raw hit whose surrounding bytes can't even be read (most
            # likely sitting right at the edge of its memory region, so the
            # read for the byte(s) just past it crosses into unmapped
            # memory) used to vanish with zero trace: not isolated, not
            # rejected, no diagnostic dump -- "0 isolated occurrence(s)"
            # looked identical whether nothing matched at all or several raw
            # hits existed but none could be examined. Found live 2026-09-10
            # searching for "Sanderson Park": several raw hits, zero isolated,
            # and the "every raw hit failed isolation" dump below never fired
            # because `rejected` was empty too -- this counter is what
            # revealed that gap.
            unreadable += 1
            continue

    if unreadable:
        app.log(
            f"Stadium DB name patcher: {unreadable} raw hit(s) of '{pattern!r}' "
            f"could not be read for isolation checking (likely at a memory "
            f"region boundary)"
        )

    # Every raw hit failed isolation -- log what's actually around one of
    # them (2026-09-09 investigation: this fired live, with a raw UTF-8 hit
    # rejected here on every attempt) so the *next* capture shows exactly why,
    # instead of yet another silent "0 isolated occurrences" that gives no
    # clue whether the text is truncated, embedded in a longer string, or
    # padded with non-NUL bytes rather than zeros.
    if not isolated and rejected:
        for addr in rejected[:3]:
            try:
                # Widened from 16/16 (2026-09-10): a recurring, session-stable
                # rejected hit at 0x52C2B8B4 turned out to sit right after a
                # length-prefix header (see the scan below) whose earlier
                # fields (a hash-looking value, further back) fell outside
                # the old 16-byte window -- wider context costs nothing and
                # avoids needing another investigation cycle just to see more
                # of the same structure.
                context_before = 64
                context_after = len(pattern) + 64
                start = max(0, addr - context_before)
                context = app.memory.read_process_memory(start, (addr - start) + context_after)
                app.log(
                    f"Stadium DB name patcher: raw hit at 0x{addr:X} failed isolation -- "
                    f"context bytes: {context.hex(' ')}"
                )
                # Some engine string types are length-prefixed rather than
                # NUL-bounded on both sides -- a 4-byte little-endian integer
                # equal to the string's own encoded byte count (including its
                # terminator width), sitting some small fixed distance before
                # the characters. Confirmed live 2026-09-10: the bytes 12
                # positions before "Waldstadion" at 0x52C2B8B4 decoded to
                # exactly len(pattern)+term_width. Flag any such match
                # explicitly instead of leaving it to be spotted by hand in a
                # hex dump next time.
                rel = addr - start
                target_len = len(pattern) + term_width
                for back in range(4, 33):
                    idx = rel - back
                    if idx < 0:
                        break
                    window = context[idx: idx + 4]
                    if len(window) == 4 and int.from_bytes(window, "little") == target_len:
                        app.log(
                            f"Stadium DB name patcher: possible length-prefixed string at "
                            f"0x{addr:X} -- 4-byte LE integer {target_len} found {back} "
                            f"byte(s) before the text (matches this string's own encoded "
                            f"length)"
                        )
                        break
            except Exception as exc:
                app.log(f"Stadium DB name patcher: could not read context at 0x{addr:X}", exc)

    return list(dict.fromkeys(isolated))


def _probe_available_capacity(
    app: "Server16App", addr: int, base_capacity: int, term_width: int, max_extra: int = 512
) -> int:
    """Extend `base_capacity` (the isolated occurrence's own length + one
    terminator) by claiming however many more bytes immediately follow it
    are actually readable, up to `max_extra` -- regardless of their current
    content.

    `_find_isolated_occurrences` only ever confirms a single terminator's
    worth of trailing NULs -- enough to prove the string is isolated, not to
    know the buffer's true size. This used to require the extra bytes to be
    zero (Part 10), then zero-or-a-known-MSVC-heap-filler-byte
    (0xCC/0xCD, Part 18) before claiming them as safe -- both approaches were
    live-falsified: a real report (CLAUDE.md §7 Part 19) found the very next
    byte was 0x98, an entirely different value neither list covered, for the
    exact same truncation case (slot 176's vanilla-"Waldstadion" buffer,
    "Campos de Sport de El Sardinero" cut to "Campos de S") already twice
    confirmed live to be safe to overwrite regardless of what's currently
    sitting there -- once via a user directly typing a 19+ character
    replacement into it in Cheat Engine with no visible corruption, and
    separately by this exact buffer family's OTHER simultaneous occurrences
    in the same process consistently showing 240+ bytes of real, already-zero
    slack (see `_scan_and_patch`'s own multi-candidate design). The pattern
    across all of this: the specific byte VALUE sitting past an isolated
    occurrence's own terminator is leftover heap history, not a stable
    allocator signature and not a meaningfully-read adjacent field --
    continuing to gate on it only ever produced false "no room" readings,
    never once catching a real case of corrupting something that mattered.

    Reported live again 2026-09-10, after the byte-value gating above was
    already removed: truncation still happened for a buffer the user had
    separately proven (via a direct Cheat Engine edit) had plenty of safe
    room past it. Root cause found by reading `Memory.read_process_memory`:
    it raises unless the underlying `ReadProcessMemory` call reports overall
    success -- but Windows can genuinely *partially* succeed when part of a
    requested range crosses from accessible into inaccessible memory (the
    edge of a heap allocation, almost certainly what a flat "read `max_extra`
    bytes past the terminator" probe hits in practice), copying the
    accessible prefix and setting the actual byte count while still
    returning failure overall. The old all-or-nothing check discarded that
    entire legitimately-read prefix the moment even the very last requested
    byte fell outside mapped memory -- capping capacity at `base_capacity`
    even when hundreds of genuinely safe bytes existed right before the real
    boundary. Now uses `read_process_memory_partial` (see its own docstring
    in memory_access.py), which never raises and credits exactly however many
    bytes Windows actually copied, partial or not. Only a request that reads
    back completely empty (address itself unreadable, or genuinely zero
    bytes of slack) still falls back to `base_capacity`, logged below.
    """
    extra = app.memory.read_process_memory_partial(addr + base_capacity, max_extra)
    if not extra:
        app.log(
            f"Stadium DB name patcher: buffer at 0x{addr:X} has no probeable "
            f"slack -- nothing further was readable past its own terminator"
        )
        return base_capacity
    # Only claim whole term_width-sized chunks (matters for UTF-16LE, where a
    # lone trailing odd byte can't hold a full code unit on its own).
    usable = (len(extra) // term_width) * term_width
    return base_capacity + usable


def _probe_zero_padded_capacity(
    app: "Server16App", addr: int, base_capacity: int, term_width: int, max_extra: int = 512
) -> int:
    """Extend `base_capacity` using ONLY genuinely zero-valued bytes past the
    terminator -- the safe, install-independent default applied to every
    discovered occurrence that is NOT in offsets.STDNAME_SAFE_EXTEND_SUFFIXES.

    Added 2026-09-11 after a second user's FIFA install reported the exact
    same truncation this whole saga (CLAUDE.md §7) already spent many
    live-tested iterations fixing for the FIRST install -- and after that
    fix, the "make every build work" answer can't be "every user manually
    reverse-engineers their own build in Cheat Engine" (see
    [[live_memory_write_safety_protocol]] for why that manual step exists
    at all -- it's how the crash-causing decoy was told apart from the real
    buffer). This restores this exact function's OWN earlier design (Part
    10, 2026-09-09, before Parts 18-19 loosened it to accept ANY readable
    byte -- the change that caused the two live crashes
    [[live_memory_write_safety_protocol]] documents) as the AUTOMATIC
    default for every address, confirmed or not: most fixed-size UI string
    fields are allocated with generous, zero-initialized trailing capacity
    to fit localized text of varying length, so requiring the extra bytes
    to be genuinely `0x00` (not merely "the OS reports this page as
    mapped", which is all `_probe_available_capacity` checks) is a much
    stronger, still install-independent signal that the space is actually
    unused padding rather than a neighboring live heap object's own data.
    This never caused a crash across its entire live tenure in this
    project's history -- only the byte-content-agnostic version did.
    `_probe_available_capacity`'s fuller (any-readable-byte) extension
    stays reserved for addresses a user has live-confirmed and added to
    STDNAME_SAFE_EXTEND_SUFFIXES; every other build/mod now gets this safer
    automatic extension instead of being capped to `base_capacity` outright
    (the previous fallback for anything unconfirmed), which should already
    remove most truncation for most users with zero manual RE work.
    """
    extra = app.memory.read_process_memory_partial(addr + base_capacity, max_extra)
    zero = b"\x00" * term_width
    usable = 0
    for i in range(0, len(extra) - term_width + 1, term_width):
        if extra[i : i + term_width] != zero:
            break
        usable += term_width
    return base_capacity + usable


def _find_pipe_bounded_occurrences(app: "Server16App", pattern: bytes) -> list[int]:
    """UTF-8/ASCII-only: keep raw hits of `pattern` bounded by the pipe (`|`)
    character on both sides -- a whole field inside FIFA's pipe-delimited
    match-context string.

    Confirmed live 2026-09-09 (CLAUDE.md §7 Part 11): this is what actually
    feeds the pre-match presentation screen -- a single record like
    `...|Amistoso|Waldstadion|R. Racing Club|...` holding the competition
    type, stadium name and team names as adjacent pipe-separated fields.
    Distinct from both the NUL-isolated DB-name copy `_find_isolated_
    occurrences` targets and the numeric `|HID|...|AID|` string
    MatchStringPatchCoordinator was originally built for -- this one showed
    up as a byproduct of scanning for the plain stadium-name text, not by
    looking for either of those other structures.
    """
    addresses = _scan_memory(app, pattern)
    bounded: list[int] = []
    for addr in addresses:
        try:
            if addr < 1:
                continue
            before = app.memory.read_process_memory(addr - 1, 1)
            after = app.memory.read_process_memory(addr + len(pattern), 1)
            if before == b"|" and after == b"|":
                bounded.append(addr)
        except Exception:
            continue
    return list(dict.fromkeys(bounded))


def _locate_pipe_record(app: "Server16App", addr: int, pattern_len: int, window: int = 512) -> tuple[int, int] | None:
    """Given a pipe-bounded field's address, find the enclosing NUL-bounded
    record's (start_address, byte_length_excluding_terminator).

    The field itself (e.g. "Waldstadion") is only ever one part of a larger
    record (`"...|Amistoso|Waldstadion|R. Racing Club|"`) -- replacing it
    safely means rewriting the whole record (so every other field's pipe
    position stays correct), which first requires knowing where that record
    actually starts and ends.
    """
    read_start = max(0, addr - window)
    try:
        data = app.memory.read_process_memory(read_start, window + pattern_len + window)
    except Exception:
        return None
    rel = addr - read_start
    null_before = data.rfind(b"\x00", 0, rel)
    record_start_rel = null_before + 1 if null_before != -1 else 0
    null_after = data.find(b"\x00", rel + pattern_len)
    if null_after == -1 or record_start_rel >= null_after:
        return None
    return read_start + record_start_rel, null_after - record_start_rel


def _extract_current_string(raw: bytes, term_width: int, encoding: str) -> str:
    """Decode the text actually stored in `raw` up to its first term-width-
    aligned NUL terminator.

    `capacity` (the buffer passed to `_patch_one`) may be larger than the
    string it currently holds -- `_probe_available_capacity` deliberately
    extends it to include trailing zero-padding a longer replacement could
    use. Simply chopping off the last `term_width` bytes (correct only when
    capacity == the string's own length + one terminator) would instead
    decode that padding as part of the string, corrupting every subsequent
    old_name/new_name comparison in _patch_one.
    """
    null_at = len(raw)
    for i in range(0, len(raw) - term_width + 1, term_width):
        if raw[i : i + term_width] == b"\x00" * term_width:
            null_at = i
            break
    return raw[:null_at].decode(encoding, errors="ignore")


class StadiumDbNamePatchCoordinator:
    """Finds and rewrites FIFA's own loaded stadium-name text for a container
    slot (176/261), in process memory only -- never on disk (see
    db_patcher.py / CLAUDE.md §7's "Nono's version" on-disk DB corruption
    bug for why on-disk patching of fifa_ng_db.db is unsafe).

    Confirmed live 2026-09-09: the scoreboard/pre-match stadium name FIFA
    actually renders is neither the STDNAMEBASE pointer-chain struct
    (StadiumRuntime.write_active_stad_name -- reaches memory and verifies
    fine, but has zero visible effect on this screen) nor the
    |HID|...|AID| match-context string (MatchStringPatchCoordinator above --
    finds 0 candidates on the tested build). A live test that loaded a
    custom stadium into slot 176 showed "Waldstadion" in-game -- the
    *vanilla fifa_ng_db.db stadium-table name for stadium ID 176 itself*.
    This lines up with db_patcher.py's own DB_STADIUM_NAME_OFFSET_176/_261
    on-disk byte offsets (which target exactly those two DB records) and
    strongly suggests FIFA resolves the display name via a live lookup into
    its own loaded copy of the stadiums table, keyed by whatever numeric ID
    CGFS writes to ORISTADIDBASE -- not through either previously-assumed
    mechanism above. This coordinator finds that loaded table's copy of the
    name text for a given slot and overwrites it in place -- and, since live
    testing 2026-09-10 found more than one simultaneous in-memory copy of the
    same name (a NUL-isolated buffer and one or more pipe-delimited-record
    fields, not necessarily the one the presentation screen actually renders
    from), every copy discovered in a given scan attempt gets patched, not
    just the first one that writes successfully.

    Unlike MatchStringPatchCoordinator (keyed per live match by HID/AID),
    this is keyed only by (process id, injID/slot): the loaded DB table is
    populated once at FIFA startup and its address stays stable for the
    whole process lifetime, so every stadium later loaded into the same
    slot reuses the same cached address instead of re-scanning.
    """

    # Scan attempts allowed per key -- not a one-shot budget. The name text
    # this coordinator looks for may only be resident in memory for a brief,
    # apparently unpredictable window: live testing 2026-09-09 found it
    # present (and successfully patched it) on one run's attempt 4/6, found
    # raw bytes of it (rejected by isolation, but present) on other runs, and
    # then -- after fixing an unrelated scheduling bug that had been quietly
    # dropping most retries -- got a genuinely clean run of 6 full, evenly
    # spread attempts across ~13 seconds that found NOTHING at all, in any of
    # the three search modes. This means the earlier 6-attempt budget simply
    # wasn't wide enough to reliably land on the actual window; there is
    # essentially no cost to trying more (each attempt is a background-thread
    # scan, never blocks the UI, and the coordinator stops immediately once a
    # patch actually lands via its own cache), so callers are expected to
    # re-request considerably more than a handful of times over a longer
    # stretch (see app_game.py's bumper-transition handler) rather than this
    # coordinator giving up early.
    MAX_SCAN_ATTEMPTS = 20

    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self._state_lock = threading.RLock()
        self._running: set[tuple[int, str]] = set()
        self._pending: dict[tuple[int, str], tuple[str, str]] = {}
        self._scan_attempts: dict[tuple[int, str], int] = {}
        # List of (address, capacity_bytes, encoding) per key -- EVERY copy of
        # the name discovered this session, not just the first one that could
        # be written. Live testing 2026-09-10 found two simultaneous
        # pipe-delimited-record copies of the same vanilla name in memory at
        # once; only one of them turned out to be what the presentation
        # screen actually reads, and the original single-candidate design
        # (stopping at the first successful write) had a 50/50 chance of
        # picking the wrong one -- it did, that session. Tracking every
        # discovered copy and patching all of them removes that ordering
        # gamble entirely.
        self._cache: dict[tuple[int, str], list[tuple[int, int, str]]] = {}
        # The name text CONFIRMED (via a successful read-verify or write-
        # verify in _patch_one) to currently be live in this slot's buffer --
        # never set optimistically just because a request was made. This is
        # what get_current_name() reports as the "old" name for the *next*
        # stadium loaded into the same slot to search for. Setting this
        # eagerly (e.g. the instant a patch is *requested*, before knowing
        # whether it actually landed) was a real bug found live 2026-09-09:
        # every retry after the first immediately saw old_name == new_name
        # and skipped scanning entirely, because something upstream had
        # already assumed success. As long as every attempt keeps failing,
        # this stays unset and every retry keeps searching for the same
        # (correct) original name.
        self._current_name: dict[tuple[int, str], str] = {}
        # Bumped on every request() call, even one whose (old_name, new_name)
        # is identical to the in-flight one -- see _worker's use of this
        # below for why plain content-equality isn't enough to tell "nothing
        # new happened" apart from "a scheduled retry arrived while busy."
        self._request_seq: dict[tuple[int, str], int] = {}

    def reset(self) -> None:
        with self._state_lock:
            self._pending.clear()
            self._scan_attempts.clear()
            self._cache.clear()
            self._current_name.clear()
            self._request_seq.clear()

    def _key(self, injid: str) -> tuple[int, str] | None:
        app = self.app
        process_id = int(getattr(app.memory, "process_id", 0) or 0)
        if not process_id:
            return None
        return (process_id, str(injid))

    def get_current_name(self, injid: str) -> str | None:
        """The name last CONFIRMED live in this slot's buffer this session,
        or None if no patch for this slot has ever actually succeeded (in
        which case callers should fall back to the slot's vanilla DB name)."""
        key = self._key(injid)
        if key is None:
            return None
        with self._state_lock:
            return self._current_name.get(key)

    def _is_current(self, key: tuple[int, str]) -> bool:
        app = self.app
        return bool(
            not app._closing
            and app.memory.is_open()
            and int(getattr(app.memory, "process_id", 0) or 0) == key[0]
        )

    def request(self, injid: str, old_name: str, new_name: str, *, allow_scan: bool = True) -> bool:
        app = self.app
        if app._closing or not app.memory.is_open():
            return False
        if not old_name or old_name == new_name:
            return False
        key = self._key(injid)
        if key is None:
            return False

        with self._state_lock:
            self._pending[key] = (old_name, new_name)
            self._request_seq[key] = self._request_seq.get(key, 0) + 1
            if key in self._running:
                return True
            if not allow_scan and key not in self._cache:
                return False
            # A FRESH worker (nothing already in flight for this slot) asked
            # to replace a name this coordinator itself already confirmed
            # live here is unambiguously a rename of an already-known-good
            # buffer, not a fresh discovery -- request_db_name_patch()
            # always resolves `old_name` via get_current_name() first, so
            # this only reads True once some earlier, separate discovery for
            # this exact slot has already fully completed and confirmed.
            # Decided once, here at spawn time, rather than re-derived on
            # every internal loop iteration inside _worker: re-deriving it
            # mid-discovery (e.g. right after the very attempt that first
            # finds ONE candidate) could make the worker skip trying the
            # other search modes that only become resident slightly later --
            # exactly the bug Part 14 fixed (CLAUDE.md §7). Deciding it only
            # here means a slot's very first discovery this session always
            # keeps its full scan budget, no matter how its own retries
            # happen to interleave while that discovery is still in flight.
            is_rename = self._current_name.get(key) == old_name
            self._running.add(key)

        threading.Thread(
            target=self._worker,
            args=(key, allow_scan, is_rename),
            daemon=True,
            name="StadiumDbNamePatch",
        ).start()
        return True

    def _worker(self, key: tuple[int, str], allow_scan: bool, is_rename: bool = False) -> None:
        app = self.app
        try:
            while True:
                with self._state_lock:
                    pending = self._pending.get(key)
                    cached = self._cache.get(key)
                    attempts_used = self._scan_attempts.get(key, 0)
                    seq_before = self._request_seq.get(key, 0)
                if pending is None or not self._is_current(key):
                    return
                old_name, new_name = pending

                cache_confirmed = False
                if cached:
                    still_valid: list[tuple[int, int, str]] = []
                    for candidate in cached:
                        if self._patch_one(key, candidate, old_name, new_name):
                            still_valid.append(candidate)
                    with self._state_lock:
                        if still_valid:
                            self._cache[key] = still_valid
                        else:
                            self._cache.pop(key, None)
                    cached = still_valid or None
                    # `is_rename` (decided once, at request()'s spawn time --
                    # see its docstring) means this slot's address(es) were
                    # already confirmed live by an EARLIER, separate,
                    # already-completed discovery, and this request is just
                    # renaming that same known-good buffer for a new
                    # stadium. StadiumDbNamePatchCoordinator's own design
                    # assumes FIFA's loaded name buffer(s) for a container
                    # slot are process-lifetime-stable (see the class
                    # docstring) -- if the cache still validates, there is
                    # nothing left to discover, so skip the scan below
                    # entirely instead of burning a full multi-second scan
                    # attempt just to re-confirm what's already known. Falls
                    # through to a normal scan if the cache turned out
                    # stale (`still_valid` empty -- buffer reused for
                    # something else), so a slot that stops being reliable
                    # still gets rediscovered rather than silently stuck.
                    cache_confirmed = is_rename and bool(still_valid)

                # The scan below is deliberately NOT gated on "cached is
                # None" when this ISN'T a confirmed rename -- live testing
                # 2026-09-10 found that whichever copy of the name gets
                # discovered *first* is not reliably the one the presentation
                # screen actually renders from (see the multi-candidate fix
                # in _scan_and_patch's docstring). A previous version of this
                # method stopped scanning entirely the moment ANY candidate
                # was found and cached, which meant a lucky-but-wrong early
                # find (e.g. an isolated buffer at attempt 2) silently used up
                # the rest of the 20-attempt budget doing nothing but
                # re-verifying that one wrong address, never trying the
                # pipe-delimited fallback that only became resident later
                # (attempt 6 in an earlier session). Now every attempt keeps
                # searching for MORE copies until the budget is exhausted,
                # merging newly found addresses into the existing cache
                # instead of stopping at the first success.
                if cache_confirmed:
                    app.log(
                        f"Stadium DB name patcher: reused {len(still_valid)} known-good "
                        f"address(es) for slot {key[1]} -- no scan needed"
                    )
                elif allow_scan and attempts_used < self.MAX_SCAN_ATTEMPTS:
                    with self._state_lock:
                        self._scan_attempts[key] = attempts_used + 1
                    app.log(
                        f"Stadium DB name patcher: scan attempt {attempts_used + 1}/"
                        f"{self.MAX_SCAN_ATTEMPTS} for slot {key[1]}"
                    )
                    found = self._scan_and_patch(key, old_name, new_name)
                    if found:
                        with self._state_lock:
                            existing = self._cache.get(key, [])
                            existing_addrs = {candidate[0] for candidate in existing}
                            new_candidates = [c for c in found if c[0] not in existing_addrs]
                            if new_candidates:
                                self._cache[key] = existing + new_candidates
                                app.log(
                                    f"Stadium DB name patcher: now tracking "
                                    f"{len(self._cache[key])} total occurrence(s) for slot {key[1]}"
                                )

                with self._state_lock:
                    # Compare the request *sequence number*, not the pending
                    # (old_name, new_name) value itself -- a scheduled retry
                    # almost always requests the exact same pair as the
                    # attempt already in flight (nothing about the target
                    # changed), so comparing values alone can't tell "a fresh
                    # retry call arrived while this attempt was running" apart
                    # from "no one called request() again at all". A scan can
                    # easily take longer than the ~900ms retry interval (the
                    # 4GB cap raised in an earlier fix makes this the common
                    # case, not an edge case) -- found live 2026-09-09 to be
                    # silently swallowing most of the app's scheduled retries
                    # this way, so only ~5 of 6 scheduled attempts, sometimes
                    # fewer, ever actually ran a scan.
                    if self._request_seq.get(key, 0) == seq_before:
                        self._pending.pop(key, None)
                        return
                    # A newer request() call landed mid-scan/write -- loop
                    # once more (reusing the cache if one was just populated)
                    # instead of exiting and losing that attempt.
        except Exception as exc:
            app.log("Stadium DB name patcher background error", exc)
        finally:
            with self._state_lock:
                self._running.discard(key)
                pending = self._pending.get(key)
            if pending and self._is_current(key):
                self.request(key[1], pending[0], pending[1], allow_scan=False)

    def _scan_and_patch(self, key: tuple[int, str], old_name: str, new_name: str) -> list[tuple[int, int, str]] | None:
        """Find and patch EVERY copy of `old_name` this attempt can locate --
        NUL-isolated (both encodings) and pipe-delimited-record alike --
        rather than stopping at the first one that writes successfully.

        Live testing 2026-09-10 found two simultaneous pipe-delimited-record
        copies of the same vanilla name in memory at once (see CLAUDE.md §7's
        scoreboardstdname saga): one a short record with almost no slack (a
        replacement name got truncated to 5 characters), the other a longer
        record. The short one happened to be discovered first and wrote+
        verified successfully, so the old "return on first success" logic
        stopped right there -- and the presentation screen kept showing the
        vanilla name anyway, meaning that first "success" wasn't even the
        right buffer. There is no reliable way to know in advance which
        discovered copy (if any) is the one actually read for rendering, so
        every one gets patched; the cost is a handful of extra, cheap,
        verified memory writes per attempt.
        """
        app = self.app
        app.log(f"Stadium DB name patcher: background scan for '{old_name}' (slot {key[1]})")
        found: list[tuple[int, int, str]] = []
        # UTF-16LE scanning was dropped 2026-09-10: across this entire
        # investigation (dozens of live scan attempts, multiple sessions,
        # multiple different stadiums) it never once found a single isolated
        # occurrence -- FIFA's on-screen text for this field is consistently
        # UTF-8. Each attempt was spending roughly a third of its total
        # wall-clock cost on this leg for zero benefit, directly shrinking
        # how many *real* attempts fit inside the fixed retry window
        # (DB_NAME_PATCH_RETRY_WINDOW_SECONDS in app_game.py) -- confirmed
        # live to matter: one match's away-team name was only found on
        # attempt 8 of 20, and another never landed at all within the full
        # window. _find_isolated_occurrences itself still supports any
        # term_width, so UTF-16LE can be reinstated here if a future build/
        # mod turns out to need it (same "try another variant" pattern
        # already used for STDNAMEOFFSET176B/261B in offsets.py).
        for encoding, term_width in (("utf-8", 1),):
            try:
                pattern = old_name.encode(encoding)
            except UnicodeEncodeError:
                continue
            if not pattern or not self._is_current(key):
                return found or None
            priority_ranges = getattr(getattr(app, "offsets", None), "STDNAME_SAFE_EXTEND_PRIORITY_RANGES", None)
            addresses = _find_isolated_occurrences(app, pattern, term_width, priority_ranges=priority_ranges)
            if not self._is_current(key):
                app.log("Stadium DB name patcher: discarded stale scan result")
                return found or None
            app.log(
                f"Stadium DB name patcher: {len(addresses)} isolated {encoding} "
                f"occurrence(s) of '{old_name}'"
            )
            safe_suffixes = set(getattr(getattr(app, "offsets", None), "STDNAME_SAFE_EXTEND_SUFFIXES", []))
            for addr in addresses:
                base_capacity = len(pattern) + term_width
                # A scan for the vanilla name can turn up MULTIPLE
                # simultaneous isolated copies, and not all of them are the
                # real render-source buffer -- confirmed live 2026-09-10/11,
                # twice: a probed "readable" capacity let a write of just 16
                # bytes (4 bytes past "Waldstadion\0"'s own 12-byte footprint
                # -- "SPORTCLUB Arena") crash FIFA on leaving the match, and a
                # second, independent session with a 33-byte write (21 bytes
                # past the footprint -- "Campos de Sport de El Sardinero")
                # crashed the same way. Both crashes' addresses (0x5303B8B4,
                # 0x52B5B8B4) were NOT the known-good buffer family
                # (offsets.STDNAME_SAFE_EXTEND_SUFFIXES' docstring) -- they
                # were decoys, and "readable" only ever meant the OS reports
                # the page as mapped, never that the memory is unused padding
                # rather than a neighboring heap object's own live data.
                # Conversely, the specific buffer family in
                # STDNAME_SAFE_EXTEND_SUFFIXES has been directly confirmed
                # (Cheat Engine, editing it in place) to survive a full
                # extended-length write with no crash on abandon -- so a
                # confirmed-safe address gets the FULL any-readable-byte
                # extension (_probe_available_capacity). Every OTHER
                # occurrence -- i.e. every build/mod nobody has manually
                # confirmed yet, which is most users, since requiring
                # per-install Cheat Engine work doesn't scale -- gets the
                # safer, install-independent default instead
                # (_probe_zero_padded_capacity, own docstring): only
                # genuinely zero-valued trailing bytes count as real slack,
                # never merely "readable" ones. This was this exact
                # capacity probe's ORIGINAL design (Part 10, 2026-09-09) and
                # never caused a crash in its whole live history -- only the
                # later any-readable-byte version did. It won't always find
                # as much room as a confirmed suffix would (real UI padding
                # isn't guaranteed to be zeroed every session), but it is
                # strictly safer than capping to base_capacity outright (the
                # previous behavior for every unconfirmed address), so most
                # names on most builds should now come through untruncated
                # or only lightly truncated, with zero manual RE work.
                addr_suffix = addr & 0xFFFF
                if addr_suffix in safe_suffixes:
                    capacity = _probe_available_capacity(app, addr, base_capacity, term_width)
                    if capacity > base_capacity:
                        app.log(
                            f"Stadium DB name patcher: buffer at 0x{addr:X} matches a "
                            f"confirmed-safe suffix (0x{addr_suffix:04X}) -- extending to "
                            f"{capacity - base_capacity} extra byte(s), {capacity}-byte "
                            f"capacity"
                        )
                else:
                    capacity = _probe_zero_padded_capacity(app, addr, base_capacity, term_width)
                    if capacity > base_capacity:
                        app.log(
                            f"Stadium DB name patcher: buffer at 0x{addr:X} has "
                            f"{capacity - base_capacity} genuinely zero-padded byte(s) past "
                            f"'{old_name}' (no confirmed-safe suffix 0x{addr_suffix:04X}) -- "
                            f"using {capacity}-byte capacity as a safe, install-independent "
                            f"default"
                        )
                    else:
                        # Zero-padding found nothing, but the OS may still
                        # report more raw "readable" bytes past it -- log
                        # that as a diagnostic (never used automatically) so
                        # a future live Cheat Engine confirmation for this
                        # install has a concrete address to start from.
                        probed = _probe_available_capacity(app, addr, base_capacity, term_width)
                        if probed > base_capacity:
                            app.log(
                                f"Stadium DB name patcher: buffer at 0x{addr:X} reports "
                                f"{probed - base_capacity} extra READABLE (but non-zero) "
                                f"byte(s) past '{old_name}' -- not used automatically; capped "
                                f"to the {base_capacity}-byte footprint. If this is the real "
                                f"render buffer, confirm it live (edit in Cheat Engine, check "
                                f"the display changes AND a full match survives abandon with "
                                f"no crash) before adding 0x{addr_suffix:04X} to "
                                f"STDNAME_SAFE_EXTEND_SUFFIXES."
                            )
                if self._patch_one(key, (addr, capacity, encoding), old_name, new_name):
                    found.append((addr, capacity, encoding))

        # Always also try the pipe-delimited presentation-string field (UTF-8
        # only -- see _find_pipe_bounded_occurrences), even when a NUL-isolated
        # copy above already patched successfully -- they are coexisting,
        # independent copies (confirmed live), not alternatives.
        try:
            pipe_pattern = old_name.encode("utf-8")
        except UnicodeEncodeError:
            return found or None
        if not pipe_pattern or not self._is_current(key):
            return found or None
        pipe_addresses = _find_pipe_bounded_occurrences(app, pipe_pattern)
        if not self._is_current(key):
            return found or None
        app.log(
            f"Stadium DB name patcher: {len(pipe_addresses)} pipe-delimited-field "
            f"occurrence(s) of '{old_name}'"
        )
        for addr in pipe_addresses:
            record = _locate_pipe_record(app, addr, len(pipe_pattern))
            if record is None:
                continue
            record_addr, record_len = record
            capacity = record_len + 1
            if self._patch_one(key, (record_addr, capacity, "pipe"), old_name, new_name):
                found.append((record_addr, capacity, "pipe"))

        if found:
            app.log(f"Stadium DB name patcher: patched {len(found)} occurrence(s) this attempt")
        return found or None

    def _patch_one(
        self,
        key: tuple[int, str],
        candidate: tuple[int, int, str],
        old_name: str,
        new_name: str,
    ) -> bool:
        app = self.app
        address, capacity, encoding = candidate
        if not self._is_current(key):
            return False
        if encoding == "pipe":
            return self._patch_one_pipe(key, address, capacity, old_name, new_name)
        term_width = 2 if encoding == "utf-16-le" else 1
        try:
            raw = app.memory.read_process_memory(address, capacity)
            current = _extract_current_string(raw, term_width, encoding) if len(raw) >= term_width else ""
            if current != old_name and current != new_name:
                # This cached/discovered address no longer holds either the
                # name we expected or the name we already wrote here -- the
                # buffer was reused for something else (or this candidate was
                # never actually the right one). Don't touch it.
                return False
            if current == new_name:
                with self._state_lock:
                    self._current_name[key] = new_name
                return True

            encoded = new_name.encode(encoding, errors="ignore")
            max_bytes = capacity - term_width
            if len(encoded) > max_bytes:
                if encoding == "utf-16-le":
                    max_bytes -= max_bytes % 2
                    encoded = encoded[:max_bytes].decode("utf-16-le", errors="ignore").encode("utf-16-le")
                else:
                    encoded = encoded[:max_bytes].decode("utf-8", errors="ignore").encode("utf-8")
                app.log(
                    f"Stadium DB name patcher: truncated '{new_name}' to fit "
                    f"the {capacity}-byte buffer at 0x{address:X}"
                )
            # What's actually about to land in the buffer -- may be shorter
            # than `new_name` after the truncation above. The log line and
            # the confirmed-current-name cache below must reflect this, not
            # the original request: logging the untruncated `new_name` here
            # was a real bug (found live 2026-09-10) that made a truncated
            # write look like a full success, and caching the untruncated
            # name would make every later re-verification of this exact
            # buffer wrongly conclude it no longer holds the confirmed text
            # (since the buffer only ever held the truncated version).
            written_text = encoded.decode(encoding, errors="ignore")
            # Only clear as far as the new text needs, or as far as the OLD
            # text's own footprint reached -- NEVER the full measured
            # `capacity`. `capacity` (from _probe_available_capacity) only
            # answers "how long is a replacement ALLOWED to be" -- it can
            # legitimately be 500+ bytes once a buffer sits at the edge of a
            # large committed region, but that memory is just READABLE, not
            # provably unused. Zero-filling all the way out to it on every
            # write -- which this used to do unconditionally -- blindly wipes
            # however much of a neighboring, live heap object happens to fall
            # inside that span. Confirmed live 2026-09-10: a 15-byte
            # replacement ("SPORTCLUB Arena") measured 524 bytes of capacity
            # and the old code zero-padded the full 524, silently smashing
            # ~509 bytes of adjacent memory -- the match displayed correctly
            # (nothing reads that far), then FIFA crashed on leaving the
            # match, exactly the kind of delayed corruption symptom this
            # bug's shape predicts. Only the OLD string's own known-real
            # footprint is provably safe to zero past what the new text
            # itself needs -- it was a validated isolated string a moment
            # ago, so overwriting all of it (never leaving stale trailing
            # characters from a longer old name) is safe; anything further
            # out, up to `capacity`, is left untouched unless the new text
            # actually needs it.
            old_footprint = len(old_name.encode(encoding, errors="ignore")) + term_width
            clear_len = min(capacity, max(len(encoded) + term_width, old_footprint))
            payload = encoded + b"\x00" * (clear_len - len(encoded))

            old_protect = ctypes.c_ulong()
            changed = app.memory.kernel32.VirtualProtectEx(
                app.memory.process_handle,
                ctypes.c_void_p(address),
                len(payload), 0x40,
                ctypes.byref(old_protect),
            )
            if not changed:
                app.log(f"Stadium DB name patcher: VirtualProtectEx failed at 0x{address:X}")
                return False
            try:
                app.memory.write_process_memory(address, payload)
            finally:
                restore_dummy = ctypes.c_ulong()
                app.memory.kernel32.VirtualProtectEx(
                    app.memory.process_handle,
                    ctypes.c_void_p(address),
                    len(payload), old_protect.value,
                    ctypes.byref(restore_dummy),
                )

            verify = app.memory.read_process_memory(address, len(encoded))
            if verify != encoded:
                app.log(f"Stadium DB name patcher: verification failed at 0x{address:X}")
                return False
            app.log(
                f"Stadium DB name patcher: replaced '{old_name}' -> '{written_text}' "
                f"at 0x{address:X} ({encoding})"
            )
            with self._state_lock:
                self._current_name[key] = written_text
            return True
        except Exception as exc:
            app.log(f"Stadium DB name patcher: error at 0x{address:X}", exc)
            return False

    def _patch_one_pipe(
        self,
        key: tuple[int, str],
        record_addr: int,
        capacity: int,
        old_name: str,
        new_name: str,
    ) -> bool:
        """Rewrite one field (whichever one currently equals `old_name`) of
        the pipe-delimited record at `record_addr`, keeping the record's
        total byte length unchanged (padding with NUL, or truncating the
        replacement field if it doesn't fit) so every other field's position
        in the record stays correct.
        """
        app = self.app
        try:
            raw = app.memory.read_process_memory(record_addr, capacity)
            null_index = raw.find(b"\x00")
            text = (raw[:null_index] if null_index != -1 else raw).decode("utf-8", errors="ignore")
            parts = text.split("|")
            if old_name in parts:
                field_index = parts.index(old_name)
            elif new_name in parts:
                with self._state_lock:
                    self._current_name[key] = new_name
                return True
            else:
                # This record no longer contains either name -- reused for a
                # different match, or never actually the right one.
                return False

            parts[field_index] = new_name
            new_text = "|".join(parts)
            encoded = new_text.encode("utf-8") + b"\x00"
            if len(encoded) > capacity:
                overhead = len(new_text.encode("utf-8")) - len(new_name.encode("utf-8"))
                max_name_bytes = capacity - overhead - 1
                if max_name_bytes <= 0:
                    app.log(
                        f"Stadium DB name patcher: '{new_name}' does not fit the "
                        f"{capacity}-byte pipe-delimited record at 0x{record_addr:X}"
                    )
                    return False
                safe_name = new_name.encode("utf-8")[:max_name_bytes].decode("utf-8", errors="ignore")
                parts[field_index] = safe_name
                new_text = "|".join(parts)
                encoded = new_text.encode("utf-8") + b"\x00"
                app.log(
                    f"Stadium DB name patcher: truncated '{new_name}' -> '{safe_name}' "
                    f"to preserve the pipe-delimited record's length"
                )
            payload = encoded + b"\x00" * (capacity - len(encoded))

            old_protect = ctypes.c_ulong()
            changed = app.memory.kernel32.VirtualProtectEx(
                app.memory.process_handle,
                ctypes.c_void_p(record_addr),
                len(payload), 0x40,
                ctypes.byref(old_protect),
            )
            if not changed:
                app.log(f"Stadium DB name patcher: VirtualProtectEx failed at 0x{record_addr:X}")
                return False
            try:
                app.memory.write_process_memory(record_addr, payload)
            finally:
                restore_dummy = ctypes.c_ulong()
                app.memory.kernel32.VirtualProtectEx(
                    app.memory.process_handle,
                    ctypes.c_void_p(record_addr),
                    len(payload), old_protect.value,
                    ctypes.byref(restore_dummy),
                )

            verify = app.memory.read_process_memory(record_addr, len(encoded))
            if verify != encoded:
                app.log(f"Stadium DB name patcher: verification failed at 0x{record_addr:X}")
                return False
            app.log(
                f"Stadium DB name patcher: replaced pipe-delimited field '{old_name}' -> "
                f"'{parts[field_index]}' at 0x{record_addr:X}"
            )
            with self._state_lock:
                self._current_name[key] = new_name
            return True
        except Exception as exc:
            app.log(f"Stadium DB name patcher: error at 0x{record_addr:X}", exc)
            return False


class MatchStringPatchCoordinator:
    """Background-only match-string patcher with one full scan per context.

    A context is identified by process id, kickoff generation, HID and AID
    (``_context_key`` below) -- the same "changes exactly once per genuine new
    match" signal ``TeamEntranceRuntime`` already relies on
    (``entrance_runtime.py``'s ``_match_key``), rather than reusing the whole
    stadium-task signature: a re-roll of the *same* match's stadium (retry,
    manual picker) should still hit the cached address instead of paying for
    another 512MB scan.

    The first request for a context performs the expensive memory scan on a
    daemon thread. Discovered addresses and their buffer capacities are
    cached; later requests for the same context only revalidate and write
    those exact addresses. This never touches process memory from the caller's
    own thread (Tk main loop or a stadium-copy worker thread) -- a full scan
    can take well over a second, and this patch is best-effort cosmetic
    (see StadiumRuntime.write_active_stad_name for the pointer-chain write
    that also always runs, synchronously, as the primary mechanism).
    """

    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self._state_lock = threading.RLock()
        self._running: set[tuple[int, int, str, str]] = set()
        self._pending_name: dict[tuple[int, int, str, str], str] = {}
        self._scan_attempted: set[tuple[int, int, str, str]] = set()
        self._cache: dict[tuple[int, int, str, str], list[tuple[int, int]]] = {}

    def reset(self) -> None:
        """Invalidate cached contexts. In-flight scans self-discard by key."""
        with self._state_lock:
            self._pending_name.clear()
            self._scan_attempted.clear()
            self._cache.clear()

    def _context_key(self) -> tuple[int, int, str, str] | None:
        app = self.app
        hid = str(getattr(app, "HID", "") or "")
        aid = str(getattr(app, "AID", "") or "")
        if not hid or not aid:
            return None
        process_id = int(getattr(app.memory, "process_id", 0) or 0)
        generation = int(getattr(app, "_kickoff_generation", 0))
        return (process_id, generation, hid, aid)

    def request(self, stad_name: str, *, allow_scan: bool = True) -> bool:
        app = self.app
        if app._closing or not app.memory.is_open():
            return False
        key = self._context_key()
        if key is None:
            app.log("Match string patcher: HID/AID not available yet")
            return False

        with self._state_lock:
            self._pending_name[key] = stad_name
            if key in self._running:
                return True
            # If the sole full scan for this context already failed and no
            # cache exists, don't launch another 512MB scan for a follow-up
            # call (e.g. finish_stadium_apply calling in right after
            # start_stadium_task already scanned and found nothing).
            if not allow_scan and key not in self._cache:
                return False
            self._running.add(key)

        threading.Thread(
            target=self._worker,
            args=(key, allow_scan),
            daemon=True,
            name="MatchStringPatch",
        ).start()
        return True

    def _is_current(self, key: tuple[int, int, str, str]) -> bool:
        return key == self._context_key()

    def _worker(self, key: tuple[int, int, str, str], allow_scan: bool) -> None:
        app = self.app
        try:
            while True:
                with self._state_lock:
                    stad_name = self._pending_name.get(key, "")
                    cached = list(self._cache.get(key, []))
                    scan_attempted = key in self._scan_attempted
                if not stad_name or not self._is_current(key):
                    return

                valid_cache, patched = self._patch_cached(key, stad_name, cached)
                with self._state_lock:
                    if valid_cache:
                        self._cache[key] = valid_cache
                    else:
                        self._cache.pop(key, None)

                if not valid_cache and allow_scan and not scan_attempted:
                    with self._state_lock:
                        self._scan_attempted.add(key)
                    if not self._is_current(key):
                        return
                    _, _, hid, aid = key
                    search_pattern = f"|{hid}|".encode("utf-8")
                    app.log(f"Match string patcher: background scan for '|{hid}|'")
                    addresses = _scan_memory(app, search_pattern)
                    if not self._is_current(key):
                        app.log("Match string patcher: discarded stale scan result")
                        return
                    discovered = self._discover_candidates(addresses, hid, aid, search_pattern)
                    with self._state_lock:
                        self._cache[key] = discovered
                    app.log(
                        f"Match string patcher: background scan found "
                        f"{len(discovered)} valid match string(s)"
                    )
                    valid_cache, patched = self._patch_cached(key, stad_name, discovered)
                    with self._state_lock:
                        self._cache[key] = valid_cache

                if patched:
                    app.log(f"Match string patcher: applied '{stad_name}' from background worker")

                with self._state_lock:
                    latest = self._pending_name.get(key, "")
                    if latest == stad_name:
                        self._pending_name.pop(key, None)
                        return
                    # A newer name arrived while scanning/writing. Loop once
                    # more; this will only ever use the cached address, never
                    # trigger another full scan.
        except Exception as exc:
            app.log("Match string patcher background error", exc)
        finally:
            with self._state_lock:
                self._running.discard(key)
                # A request may have arrived during the tiny window right
                # after the worker decided to exit. Schedule a cached-only
                # follow-up rather than dropping it silently.
                pending = self._pending_name.get(key)
            if pending and self._is_current(key):
                self.request(pending, allow_scan=False)

    def _discover_candidates(
        self,
        addresses: list[int],
        hid: str,
        aid: str,
        search_pattern: bytes,
    ) -> list[tuple[int, int]]:
        app = self.app
        found: list[tuple[int, int]] = []
        seen: set[int] = set()
        for addr in addresses:
            try:
                read_start = max(0, addr - 300)
                data = app.memory.read_process_memory(read_start, 1024)
                pos = 0
                while pos < len(data):
                    null = data.find(b"\x00", pos)
                    if null == -1:
                        break
                    chunk = data[pos:null]
                    text = _decode_printable_text(chunk)
                    if b"|" in chunk and search_pattern in chunk and text is not None:
                        parts = text.split("|")
                        if len(parts) > 8 and parts[5] == hid and parts[8] == aid:
                            start = read_start + pos
                            capacity = len(chunk) + 1
                            if start not in seen:
                                seen.add(start)
                                found.append((start, capacity))
                            break
                    pos = null + 1
            except Exception:
                continue
        return found

    def _patch_cached(
        self,
        key: tuple[int, int, str, str],
        stad_name: str,
        candidates: list[tuple[int, int]],
    ) -> tuple[list[tuple[int, int]], bool]:
        if not candidates or not self._is_current(key):
            return [], False
        _, _, hid, aid = key
        valid: list[tuple[int, int]] = []
        patched_any = False
        for address, capacity in candidates:
            try:
                if not self._is_current(key):
                    break
                raw = self.app.memory.read_process_memory(address, capacity)
                null = raw.find(b"\x00")
                if null == -1:
                    continue
                current_bytes = raw[:null]
                current = _decode_printable_text(current_bytes)
                if current is None:
                    continue
                parts = current.split("|")
                if len(parts) <= 8 or parts[5] != hid or parts[8] != aid:
                    continue
                valid.append((address, capacity))
                old_name = parts[2]
                if old_name == stad_name:
                    patched_any = True
                    continue

                parts[2] = stad_name
                new_full = "|".join(parts)
                encoded = new_full.encode("utf-8") + b"\x00"
                if len(encoded) > capacity:
                    overhead = len(new_full.encode("utf-8")) - len(stad_name.encode("utf-8"))
                    max_name_bytes = capacity - overhead - 1
                    if max_name_bytes <= 0:
                        self.app.log(
                            f"Match string patcher: '{stad_name}' does not fit "
                            f"the {capacity}-byte buffer"
                        )
                        continue
                    safe_name = (
                        stad_name.encode("utf-8")[:max_name_bytes]
                        .decode("utf-8", errors="ignore")
                    )
                    parts[2] = safe_name
                    new_full = "|".join(parts)
                    encoded = new_full.encode("utf-8") + b"\x00"
                    self.app.log(
                        f"Match string patcher: truncated '{stad_name}' -> "
                        f"'{safe_name}' to preserve buffer structure"
                    )
                payload = encoded + b"\x00" * (capacity - len(encoded))

                old_protect = ctypes.c_ulong()
                changed = self.app.memory.kernel32.VirtualProtectEx(
                    self.app.memory.process_handle,
                    ctypes.c_void_p(address),
                    len(payload), 0x40,
                    ctypes.byref(old_protect),
                )
                if not changed:
                    self.app.log(f"Match string patcher: VirtualProtectEx failed at 0x{address:X}")
                    continue
                try:
                    self.app.memory.write_process_memory(address, payload)
                finally:
                    restore_dummy = ctypes.c_ulong()
                    self.app.memory.kernel32.VirtualProtectEx(
                        self.app.memory.process_handle,
                        ctypes.c_void_p(address),
                        len(payload), old_protect.value,
                        ctypes.byref(restore_dummy),
                    )

                verify = self.app.memory.read_process_memory(address, len(encoded))
                if verify != encoded:
                    self.app.log(f"Match string patcher: verification failed at 0x{address:X}")
                    continue
                patched_any = True
                self.app.log(
                    f"Match string patcher: replaced '{old_name}' -> "
                    f"'{parts[2]}' at 0x{address:X}"
                )
            except Exception as exc:
                self.app.log(f"Match string patcher: cached address error 0x{address:X}", exc)
        return valid, patched_any


def patch_match_string(app: "Server16App", stad_name: str) -> bool:
    """Compatibility wrapper -- schedules the patch on the app's coordinator.

    Always returns immediately; the actual scan/write happens on a background
    thread (see MatchStringPatchCoordinator). Prefer calling
    ``app.match_string_patcher.request(stad_name)`` directly at new call
    sites -- this wrapper exists only so any external/legacy caller of the old
    synchronous ``patch_match_string`` keeps working.
    """
    coordinator = getattr(app, "match_string_patcher", None)
    if coordinator is None:
        coordinator = MatchStringPatchCoordinator(app)
        app.match_string_patcher = coordinator
    return coordinator.request(stad_name)
