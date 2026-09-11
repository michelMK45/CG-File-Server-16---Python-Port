from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server16_py.match_string_patcher import (
    MatchStringPatchCoordinator,
    StadiumDbNamePatchCoordinator,
    _decode_printable_text,
    _extract_current_string,
    _find_isolated_occurrences,
    _find_pipe_bounded_occurrences,
    _locate_pipe_record,
    _probe_available_capacity,
    _probe_zero_padded_capacity,
)


class FakeMemory:
    """In-process stand-in for memory_access.Memory's read/write surface.

    Backs a single contiguous buffer at a fixed base address so
    MatchStringPatchCoordinator's candidate discovery/patch logic can be
    exercised without a real FIFA process or ctypes calls.
    """

    def __init__(self, data: bytes, base_address: int = 0x1000) -> None:
        self.buffer = bytearray(data)
        self.base_address = base_address
        self.process_id = 4242
        self.process_handle = object()
        self.kernel32 = SimpleNamespace(
            VirtualProtectEx=lambda *a, **k: 1,
        )

    def is_open(self) -> bool:
        return True

    def read_process_memory(self, address: int, size: int) -> bytes:
        offset = address - self.base_address
        if offset < 0:
            raise AssertionError("read before buffer start")
        return bytes(self.buffer[offset:offset + size])

    def read_process_memory_partial(self, address: int, size: int) -> bytes:
        # Mirrors memory_access.Memory.read_process_memory_partial's "never
        # raises, returns whatever prefix is actually available" contract --
        # Python's own slicing already truncates past the buffer's end
        # instead of raising, so this only needs to guard against reading
        # before the buffer's start (return b"" there instead of raising, to
        # match the real method never raising).
        offset = address - self.base_address
        if offset < 0:
            return b""
        return bytes(self.buffer[offset:offset + size])

    def write_process_memory(self, address: int, payload: bytes) -> None:
        offset = address - self.base_address
        if offset < 0 or offset + len(payload) > len(self.buffer):
            raise AssertionError("write out of bounds")
        self.buffer[offset:offset + len(payload)] = payload


def make_app(memory: FakeMemory, hid: str = "456", aid: str = "123") -> SimpleNamespace:
    app = SimpleNamespace()
    app.memory = memory
    app.HID = hid
    app.AID = aid
    app._closing = False
    app._kickoff_generation = 1
    app.logs: list[str] = []
    app.log = lambda *parts: app.logs.append(" ".join(str(p) for p in parts))
    return app


def build_match_string(hid: str, aid: str, stad_name: str, capacity: int) -> bytes:
    # Mirrors the real field layout this module depends on: field 2 is the
    # stadium name, field 5 is HID, field 8 is AID.
    parts = ["0", "T", stad_name, "C", "C", hid, "C", "C", aid, "extra"]
    text = "|".join(parts).encode("utf-8") + b"\x00"
    assert len(text) <= capacity
    return text + b"\x00" * (capacity - len(text))


class DecodePrintableTextTests(unittest.TestCase):
    def test_accepts_plain_ascii(self) -> None:
        self.assertEqual(_decode_printable_text(b"Waldstadion"), "Waldstadion")

    def test_accepts_cp1252_when_utf8_fails(self) -> None:
        # 0xE9 alone ("é" in cp1252) is not valid standalone UTF-8.
        raw = "Café".encode("cp1252")
        self.assertEqual(_decode_printable_text(raw), "Café")

    def test_rejects_binary_garbage(self) -> None:
        self.assertIsNone(_decode_printable_text(bytes(range(0, 20))))


class DiscoverAndPatchCandidatesTests(unittest.TestCase):
    def test_discovers_and_patches_isolated_match_string(self) -> None:
        capacity = 64
        # _discover_candidates reads 300 bytes back from the pattern match, so
        # the prefix must be at least that long or the read would fall before
        # this fake buffer's own start address.
        prefix = b"\x00" * 300
        record = build_match_string("456", "123", "Waldstadion", capacity)
        data = prefix + record + b"\x00" * 100
        memory = FakeMemory(data, base_address=0x1000)
        app = make_app(memory)
        coordinator = MatchStringPatchCoordinator(app)

        record_addr = memory.base_address + len(prefix)
        original_text_len = record.index(b"\x00")
        pattern_addr = record_addr + record.index(b"|456|")
        discovered = coordinator._discover_candidates([pattern_addr], "456", "123", b"|456|")
        self.assertEqual(len(discovered), 1)
        addr, cap = discovered[0]
        self.assertEqual(addr, record_addr)
        # Discovery bounds capacity to the *existing* string's own length, not
        # the full padded slot -- matches _patch_cached's own truncate-to-fit
        # safety net when a replacement name would run past this.
        self.assertEqual(cap, original_text_len + 1)

        key = coordinator._context_key()
        # "Anfield" is shorter than "Waldstadion" so it fits the discovered
        # capacity without hitting the truncation path (covered separately
        # below by test_truncates_name_that_does_not_fit_capacity).
        valid, patched = coordinator._patch_cached(key, "Anfield", discovered)
        self.assertTrue(patched)
        self.assertEqual(valid, discovered)

        written = memory.read_process_memory(record_addr, cap)
        text = written.split(b"\x00", 1)[0].decode("utf-8")
        parts = text.split("|")
        self.assertEqual(parts[2], "Anfield")
        self.assertEqual(parts[5], "456")
        self.assertEqual(parts[8], "123")

    def test_ignores_candidate_with_wrong_aid(self) -> None:
        capacity = 64
        record = build_match_string("456", "999", "Waldstadion", capacity)
        memory = FakeMemory(record, base_address=0x2000)
        app = make_app(memory, hid="456", aid="123")
        coordinator = MatchStringPatchCoordinator(app)

        pattern_addr = memory.base_address + record.index(b"|456|")
        discovered = coordinator._discover_candidates([pattern_addr], "456", "123", b"|456|")
        self.assertEqual(discovered, [])

    def test_truncates_name_that_does_not_fit_capacity(self) -> None:
        capacity = 40
        record = build_match_string("456", "123", "X", capacity)
        memory = FakeMemory(record, base_address=0x3000)
        app = make_app(memory)
        coordinator = MatchStringPatchCoordinator(app)
        key = coordinator._context_key()

        long_name = "A Very Long Stadium Name That Cannot Possibly Fit"
        valid, patched = coordinator._patch_cached(key, long_name, [(memory.base_address, capacity)])
        self.assertTrue(patched)
        written = memory.read_process_memory(memory.base_address, capacity)
        text = written.split(b"\x00", 1)[0].decode("utf-8")
        self.assertLessEqual(len(text.encode("utf-8")) + 1, capacity)
        parts = text.split("|")
        self.assertTrue(long_name.startswith(parts[2]))
        self.assertEqual(parts[5], "456")
        self.assertEqual(parts[8], "123")

    def test_patch_cached_noops_when_name_already_correct(self) -> None:
        capacity = 64
        record = build_match_string("456", "123", "Sanderson Park", capacity)
        memory = FakeMemory(record, base_address=0x4000)
        app = make_app(memory)
        coordinator = MatchStringPatchCoordinator(app)
        key = coordinator._context_key()

        original = bytes(memory.buffer)
        valid, patched = coordinator._patch_cached(key, "Sanderson Park", [(memory.base_address, capacity)])
        self.assertTrue(patched)
        self.assertEqual(bytes(memory.buffer), original)

    def test_patch_cached_drops_candidate_once_context_is_stale(self) -> None:
        capacity = 64
        record = build_match_string("456", "123", "Waldstadion", capacity)
        memory = FakeMemory(record, base_address=0x5000)
        app = make_app(memory)
        coordinator = MatchStringPatchCoordinator(app)
        key = coordinator._context_key()

        # Simulate a new match (HID changed) between scan and write.
        app.HID = "789"
        valid, patched = coordinator._patch_cached(key, "Sanderson Park", [(memory.base_address, capacity)])
        self.assertEqual(valid, [])
        self.assertFalse(patched)


class RequestGatingTests(unittest.TestCase):
    def test_request_returns_false_without_hid_or_aid(self) -> None:
        memory = FakeMemory(b"\x00" * 16)
        app = make_app(memory, hid="", aid="")
        coordinator = MatchStringPatchCoordinator(app)
        self.assertFalse(coordinator.request("Anfield"))
        self.assertTrue(any("HID/AID not available" in line for line in app.logs))

    def test_request_returns_false_when_memory_not_open(self) -> None:
        memory = FakeMemory(b"\x00" * 16)
        app = make_app(memory)
        app.memory.is_open = lambda: False
        coordinator = MatchStringPatchCoordinator(app)
        self.assertFalse(coordinator.request("Anfield"))

    def test_request_without_scan_permission_noops_with_empty_cache(self) -> None:
        memory = FakeMemory(b"\x00" * 16)
        app = make_app(memory)
        coordinator = MatchStringPatchCoordinator(app)
        self.assertFalse(coordinator.request("Anfield", allow_scan=False))

    def test_reset_clears_cache_and_pending_state(self) -> None:
        memory = FakeMemory(b"\x00" * 16)
        app = make_app(memory)
        coordinator = MatchStringPatchCoordinator(app)
        key = coordinator._context_key()
        coordinator._cache[key] = [(memory.base_address, 16)]
        coordinator._scan_attempted.add(key)
        coordinator._pending_name[key] = "Anfield"
        coordinator.reset()
        self.assertEqual(coordinator._cache, {})
        self.assertEqual(coordinator._scan_attempted, set())
        self.assertEqual(coordinator._pending_name, {})


def make_db_app(memory: FakeMemory) -> SimpleNamespace:
    app = SimpleNamespace()
    app.memory = memory
    app._closing = False
    app.logs: list[str] = []
    app.log = lambda *parts: app.logs.append(" ".join(str(p) for p in parts))
    return app


def _patched_scan(memory: FakeMemory, pattern: bytes):
    """_scan_memory itself talks to real kernel32/VirtualQueryEx -- not
    something FakeMemory can stand in for. These tests only exercise
    _find_isolated_occurrences' own NUL-boundary validation, so _scan_memory
    is patched to just report every raw occurrence in the fake buffer."""
    addr = memory.base_address
    found = []
    start = 0
    while True:
        idx = memory.buffer.find(pattern, start)
        if idx == -1:
            break
        found.append(addr + idx)
        start = idx + 1
    return patch("server16_py.match_string_patcher._scan_memory", return_value=found)


class FindIsolatedOccurrencesTests(unittest.TestCase):
    def test_finds_nul_isolated_utf16le_string(self) -> None:
        text = "Waldstadion".encode("utf-16-le")
        data = b"\x00" * 32 + text + b"\x00" * 32
        memory = FakeMemory(data, base_address=0x10000)
        app = make_db_app(memory)
        with _patched_scan(memory, text):
            addresses = _find_isolated_occurrences(app, text, term_width=2)
        self.assertEqual(addresses, [memory.base_address + 32])

    def test_rejects_substring_of_a_longer_string(self) -> None:
        # "Waldstadion" embedded with real (non-NUL) text on both sides is
        # not a whole, isolated string -- must not be treated as a match.
        text = "Waldstadion".encode("utf-16-le")
        data = b"\x00" * 32 + "X".encode("utf-16-le") + text + "Y".encode("utf-16-le") + b"\x00" * 32
        memory = FakeMemory(data, base_address=0x10000)
        app = make_db_app(memory)
        with _patched_scan(memory, text):
            addresses = _find_isolated_occurrences(app, text, term_width=2)
        self.assertEqual(addresses, [])

    def test_finds_nul_isolated_utf8_string(self) -> None:
        text = "Waldstadion".encode("utf-8")
        data = b"\x00" * 16 + text + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x2000)
        app = make_db_app(memory)
        with _patched_scan(memory, text):
            addresses = _find_isolated_occurrences(app, text, term_width=1)
        self.assertEqual(addresses, [memory.base_address + 16])

    def test_accepts_utf8_string_preceded_by_nonprintable_tag_byte(self) -> None:
        # Confirmed live 2026-09-10: the actual render-source buffer (first
        # located via Cheat Engine -- see CGFS_DEBUG_SCAN_TARGET's docstring,
        # which documents a live edit there directly changing the pre-match
        # presentation screen) is preceded by a single non-printable
        # tag/type byte (0xCC/0xCD-style), not a NUL. Must be accepted, not
        # rejected as if it were a substring of a longer string.
        text = "Waldstadion".encode("utf-8")
        data = b"\x00" * 16 + b"\xcc" + text + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x50000)
        app = make_db_app(memory)
        with _patched_scan(memory, text):
            addresses = _find_isolated_occurrences(app, text, term_width=1)
        self.assertEqual(addresses, [memory.base_address + 17])

    def test_rejects_utf8_string_preceded_by_printable_text(self) -> None:
        # The genuine "substring of a longer string" case the isolation
        # check exists to catch must still be rejected -- a real preceding
        # *character*, unlike the non-printable tag byte case above.
        text = "Waldstadion".encode("utf-8")
        data = b"\x00" * 16 + b"X" + text + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x51000)
        app = make_db_app(memory)
        with _patched_scan(memory, text):
            addresses = _find_isolated_occurrences(app, text, term_width=1)
        self.assertEqual(addresses, [])


class FindIsolatedOccurrencesPriorityRangeTests(unittest.TestCase):
    def test_uses_only_the_priority_range_result_when_it_finds_something(self) -> None:
        # Added 2026-09-11: a live session found the known-safe buffer only
        # on scan attempt 15/20 of a full scan, ~20+ seconds after the
        # bumper -- the match ended before that result could be used.
        # Scanning a narrow, known-likely address window FIRST should let a
        # hit there skip the (much more expensive) full scan entirely.
        text = "Waldstadion".encode("utf-8")
        data = b"\x00" * 16 + text + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x94000010)
        app = make_db_app(memory)
        priority_addr = memory.base_address + 16

        def fake_scan(app_arg, pattern, start_addr=0, end_addr=0x7FFFFFFFFFFF):
            if start_addr == 0x94000000 and end_addr == 0x94800000:
                return [priority_addr]
            raise AssertionError("full scan must not run when the priority range already found something")

        with patch("server16_py.match_string_patcher._scan_memory", side_effect=fake_scan):
            addresses = _find_isolated_occurrences(
                app, text, term_width=1, priority_ranges=[(0x94000000, 0x94800000)]
            )
        self.assertEqual(addresses, [priority_addr])
        self.assertTrue(any("priority address range" in line for line in app.logs))

    def test_falls_back_to_the_full_scan_when_the_priority_range_finds_nothing(self) -> None:
        text = "Waldstadion".encode("utf-8")
        data = b"\x00" * 16 + text + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x2000)
        app = make_db_app(memory)
        full_scan_calls = []

        def fake_scan(app_arg, pattern, start_addr=0, end_addr=0x7FFFFFFFFFFF):
            if start_addr == 0x94000000 and end_addr == 0x94800000:
                return []  # nothing in the priority window this time
            full_scan_calls.append((start_addr, end_addr))
            return [memory.base_address + 16]

        with patch("server16_py.match_string_patcher._scan_memory", side_effect=fake_scan):
            addresses = _find_isolated_occurrences(
                app, text, term_width=1, priority_ranges=[(0x94000000, 0x94800000)]
            )
        self.assertEqual(addresses, [memory.base_address + 16])
        self.assertEqual(len(full_scan_calls), 1)  # the ordinary unrestricted scan did run

    def test_no_priority_ranges_goes_straight_to_the_full_scan(self) -> None:
        # priority_ranges=None (the default) must behave exactly as before
        # this feature existed -- no behavior change for every other caller.
        text = "Waldstadion".encode("utf-8")
        data = b"\x00" * 16 + text + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x2000)
        app = make_db_app(memory)
        with _patched_scan(memory, text):
            addresses = _find_isolated_occurrences(app, text, term_width=1)
        self.assertEqual(addresses, [memory.base_address + 16])


class ProbeAvailableCapacityTests(unittest.TestCase):
    def test_extends_capacity_across_trailing_zero_padding(self) -> None:
        # Real case found live 2026-09-09: the isolation check alone only
        # confirms one terminator's worth of NULs; a buffer can have real
        # slack past that a longer replacement could use instead of being
        # truncated.
        text = "Waldstadion".encode("utf-8")
        base_capacity = len(text) + 1
        data = text + b"\x00" * 40
        memory = FakeMemory(data, base_address=0x80000)
        app = make_db_app(memory)
        capacity = _probe_available_capacity(app, memory.base_address, base_capacity, term_width=1)
        # base_capacity already consumes the first of the 40 zero bytes as
        # its own terminator, so only 39 more are there to discover.
        self.assertEqual(capacity, len(data))

    def test_claims_all_readable_bytes_regardless_of_content(self) -> None:
        # Real case found live 2026-09-10 (CLAUDE.md §7 Part 19): the byte
        # right after "Waldstadion"'s own terminator was 0x98 for one live
        # truncation, after an EARLIER live report already falsified an
        # 0xCC/0xCD-only allowlist (Part 18) for the exact same scenario.
        # Byte-value gating kept producing false "no room" readings and never
        # once caught a real case of corrupting something that mattered -- a
        # user directly typing a 19+ character replacement into this exact
        # kind of buffer in Cheat Engine rendered fine with no visible
        # corruption regardless of what was sitting there beforehand. This
        # now simply claims whatever is actually readable, regardless of
        # value.
        text = "Waldstadion".encode("utf-8")
        base_capacity = len(text) + 1
        data = text + b"\x00" + b"\x98\xCD\xCC\x01\xFF" + b"NEXTFIELD"
        memory = FakeMemory(data, base_address=0x81000)
        app = make_db_app(memory)
        capacity = _probe_available_capacity(app, memory.base_address, base_capacity, term_width=1)
        self.assertEqual(capacity, len(data))

    def test_no_extra_room_when_nothing_more_is_readable(self) -> None:
        text = "Waldstadion".encode("utf-8")
        base_capacity = len(text) + 1
        data = text + b"\x00"  # buffer ends exactly at the terminator
        memory = FakeMemory(data, base_address=0x82000)
        app = make_db_app(memory)
        capacity = _probe_available_capacity(app, memory.base_address, base_capacity, term_width=1)
        self.assertEqual(capacity, base_capacity)

    def test_respects_utf16le_term_width_alignment(self) -> None:
        text = "Waldstadion".encode("utf-16-le")
        base_capacity = len(text) + 2
        # 21 more readable bytes -- an odd count that can't hold a full
        # trailing UTF-16LE code unit, so the last lone byte must be dropped.
        data = text + b"\x00" * 2 + b"\xAB" * 21
        memory = FakeMemory(data, base_address=0x83000)
        app = make_db_app(memory)
        capacity = _probe_available_capacity(app, memory.base_address, base_capacity, term_width=2)
        self.assertEqual(capacity, base_capacity + 20)

    def test_unreadable_address_falls_back_to_base_capacity_and_logs(self) -> None:
        text = "Waldstadion".encode("utf-8")
        base_capacity = len(text) + 1
        memory = FakeMemory(text + b"\x00", base_address=0x84000)
        app = make_db_app(memory)

        def flaky_read(address: int, size: int) -> bytes:
            # read_process_memory_partial never raises (see its own
            # docstring) -- it returns b"" on total failure instead.
            return b""

        memory.read_process_memory_partial = flaky_read  # type: ignore[method-assign]
        capacity = _probe_available_capacity(app, memory.base_address, base_capacity, term_width=1)
        self.assertEqual(capacity, base_capacity)
        self.assertTrue(any("no probeable slack" in line for line in app.logs))

    def test_credits_a_partial_read_instead_of_discarding_it(self) -> None:
        # The actual live bug (found 2026-09-10, after the byte-value gating
        # above was already removed): ReadProcessMemory can genuinely
        # PARTIALLY succeed when part of a requested range crosses into
        # unmapped memory -- Windows copies the accessible prefix and reports
        # that byte count while the call still fails overall. The old
        # implementation (read_process_memory raising whenever the Win32 call
        # reported overall failure, regardless of any bytes actually copied)
        # discarded that legitimately-read prefix entirely, so a probe
        # requesting max_extra=512 bytes got credited with ZERO extra room
        # the instant even the very last requested byte fell outside mapped
        # memory -- even though, here, 50 real bytes right after the
        # terminator were genuinely safe. This is exactly the gap between
        # "Cheat Engine could write a longer name here" and CGFS's own probe
        # reporting no room at all.
        text = "Waldstadion".encode("utf-8")
        base_capacity = len(text) + 1
        memory = FakeMemory(text + b"\x00", base_address=0x86000)
        app = make_db_app(memory)

        def partial_read(address: int, size: int) -> bytes:
            self.assertEqual(size, 512)  # the requested max_extra
            return b"\x00" * 50  # only a 50-byte prefix was actually mapped

        memory.read_process_memory_partial = partial_read  # type: ignore[method-assign]
        capacity = _probe_available_capacity(app, memory.base_address, base_capacity, term_width=1)
        self.assertEqual(capacity, base_capacity + 50)


class ProbeZeroPaddedCapacityTests(unittest.TestCase):
    """The safe, install-independent default (added 2026-09-11) used for
    every address that isn't in offsets.STDNAME_SAFE_EXTEND_SUFFIXES -- see
    [[live_memory_write_safety_protocol]] for why _probe_available_capacity's
    any-readable-byte extension is unsafe as a default."""

    def test_extends_across_genuinely_zero_padding(self) -> None:
        text = "Waldstadion".encode("utf-8")
        base_capacity = len(text) + 1
        data = text + b"\x00" * 40
        memory = FakeMemory(data, base_address=0x87000)
        app = make_db_app(memory)
        capacity = _probe_zero_padded_capacity(app, memory.base_address, base_capacity, term_width=1)
        self.assertEqual(capacity, len(data))

    def test_stops_at_the_first_non_zero_byte(self) -> None:
        # This is the exact scenario that caused two live crashes when
        # _probe_available_capacity's any-readable-byte behavior was used
        # instead: non-zero bytes right after the terminator are a
        # neighboring live object's own data, not free padding.
        text = "Waldstadion".encode("utf-8")
        base_capacity = len(text) + 1
        data = text + b"\x00" + b"\x00" * 20 + b"\x41" + b"\x00" * 20
        memory = FakeMemory(data, base_address=0x88000)
        app = make_db_app(memory)
        capacity = _probe_zero_padded_capacity(app, memory.base_address, base_capacity, term_width=1)
        self.assertEqual(capacity, base_capacity + 20)  # stops right before the 0x41

    def test_no_extra_room_when_the_very_next_byte_is_non_zero(self) -> None:
        text = "Waldstadion".encode("utf-8")
        base_capacity = len(text) + 1
        data = text + b"\x00" + b"\x98\xCD\xCC\x01\xFF"
        memory = FakeMemory(data, base_address=0x89000)
        app = make_db_app(memory)
        capacity = _probe_zero_padded_capacity(app, memory.base_address, base_capacity, term_width=1)
        self.assertEqual(capacity, base_capacity)

    def test_respects_utf16le_term_width_alignment(self) -> None:
        text = "Waldstadion".encode("utf-16-le")
        base_capacity = len(text) + 2
        # 21 more zero bytes -- an odd count that can't hold a full trailing
        # UTF-16LE code unit, so the last lone byte must be dropped.
        data = text + b"\x00" * 2 + b"\x00" * 20 + b"\xAB"
        memory = FakeMemory(data, base_address=0x8A000)
        app = make_db_app(memory)
        capacity = _probe_zero_padded_capacity(app, memory.base_address, base_capacity, term_width=2)
        self.assertEqual(capacity, base_capacity + 20)


class ExtractCurrentStringTests(unittest.TestCase):
    def test_extracts_utf8_string_ignoring_extended_padding(self) -> None:
        raw = "Waldstadion".encode("utf-8") + b"\x00" * 40
        self.assertEqual(_extract_current_string(raw, term_width=1, encoding="utf-8"), "Waldstadion")

    def test_extracts_utf16le_string_ignoring_extended_padding(self) -> None:
        raw = "Waldstadion".encode("utf-16-le") + b"\x00" * 40
        self.assertEqual(_extract_current_string(raw, term_width=2, encoding="utf-16-le"), "Waldstadion")

    def test_exact_capacity_matches_old_chop_last_terminator_behavior(self) -> None:
        raw = "Anfield".encode("utf-16-le") + b"\x00\x00"
        self.assertEqual(_extract_current_string(raw, term_width=2, encoding="utf-16-le"), "Anfield")


class FindPipeBoundedOccurrencesTests(unittest.TestCase):
    def test_finds_field_bounded_by_pipes(self) -> None:
        # The exact shape confirmed live 2026-09-09 (CLAUDE.md §7 Part 11):
        # the pre-match presentation screen's competition-type/stadium/team
        # text, as one pipe-delimited record.
        record = b"AC|-1|ATH|-1|-2|Waldstadion|0|0|0|4|"
        data = b"\x00" * 16 + record + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x40000)
        app = make_db_app(memory)
        pattern = b"Waldstadion"
        expected_addr = memory.base_address + 16 + record.index(pattern)
        with _patched_scan(memory, pattern):
            addresses = _find_pipe_bounded_occurrences(app, pattern)
        self.assertEqual(addresses, [expected_addr])

    def test_rejects_standalone_nul_bounded_occurrence(self) -> None:
        # A plain NUL-terminated string (no pipes around it) is exactly what
        # _find_isolated_occurrences already handles -- this function must
        # NOT also claim it.
        data = b"\x00" * 16 + b"Waldstadion" + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x41000)
        app = make_db_app(memory)
        pattern = b"Waldstadion"
        with _patched_scan(memory, pattern):
            addresses = _find_pipe_bounded_occurrences(app, pattern)
        self.assertEqual(addresses, [])


class LocatePipeRecordTests(unittest.TestCase):
    def test_locates_full_nul_bounded_record_around_the_field(self) -> None:
        record = b"AC|-1|ATH|-1|-2|Waldstadion|0|0|0|4|"
        # _locate_pipe_record's default window (512) reads that far back from
        # the field's address -- a real process address is always far larger
        # than that, but this fake buffer needs an equally large prefix or
        # the read would fall before its own start.
        data = b"\x00" * 16 + record + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x42000)
        app = make_db_app(memory)
        pattern = b"Waldstadion"
        field_addr = memory.base_address + 16 + record.index(pattern)
        result = _locate_pipe_record(app, field_addr, len(pattern), window=16)
        self.assertIsNotNone(result)
        record_addr, record_len = result
        self.assertEqual(record_addr, memory.base_address + 16)
        self.assertEqual(record_len, len(record))

    def test_returns_none_when_record_is_not_nul_terminated_nearby(self) -> None:
        # No NUL within reach after the field -- can't safely bound a record.
        record = b"AC|-1|ATH|-1|-2|Waldstadion|0|0|0|4|"
        memory = FakeMemory(b"\x00" * 16 + record, base_address=0x43000)
        app = make_db_app(memory)
        pattern = b"Waldstadion"
        field_addr = memory.base_address + 16 + record.index(pattern)
        result = _locate_pipe_record(app, field_addr, len(pattern), window=8)
        self.assertIsNone(result)


class ScanAndPatchPipeFallbackTests(unittest.TestCase):
    def test_falls_back_to_pipe_record_when_no_nul_isolated_copy_exists(self) -> None:
        # The name exists ONLY inside the pipe-delimited record -- no
        # standalone NUL-terminated copy anywhere -- exactly the live
        # 2026-09-09 finding that motivated this fallback.
        record = b"AC|-1|ATH|-1|-2|Waldstadion|0|0|0|4|"
        # _locate_pipe_record (called with its default 512-byte window by
        # _scan_and_patch) reads that far back from the field -- give it a
        # matching prefix so that read doesn't fall before this fake buffer's
        # own start (a real process address never has this problem).
        prefix = b"\x00" * 600
        data = prefix + record + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x44000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        def scan_side_effect(app_arg, pattern):
            if pattern == b"Waldstadion":
                addr = memory.base_address + len(prefix) + record.index(b"Waldstadion")
                return [addr]
            return []

        with patch("server16_py.match_string_patcher._scan_memory", side_effect=scan_side_effect):
            result = coordinator._scan_and_patch(key, "Waldstadion", "Anfield")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        addr, capacity, mode = result[0]
        self.assertEqual(mode, "pipe")
        self.assertEqual(capacity, len(record) + 1)  # +1 for the NUL terminator

        written = memory.read_process_memory(addr, capacity)
        text = written[: written.find(b"\x00")].decode("utf-8") if b"\x00" in written else written.decode("utf-8")
        self.assertEqual(text, "AC|-1|ATH|-1|-2|Anfield|0|0|0|4|")
        self.assertEqual(coordinator.get_current_name("176"), "Anfield")

    def test_patches_every_discovered_pipe_record_not_just_the_first(self) -> None:
        # Real bug found live 2026-09-10 (CLAUDE.md §7 scoreboardstdname
        # saga): two independent pipe-delimited copies of the same vanilla
        # name coexisted in memory at once -- one a short record with almost
        # no slack, one longer. The old "return on first successful write"
        # design patched whichever was discovered first (that session, the
        # short one) and the presentation screen never changed, because it
        # wasn't the copy actually read for rendering. Every discovered copy
        # must be patched, not just the first that writes successfully.
        record1 = b"R#|-1|Waldstadion|"
        record2 = b"AC|-1|ATH|-1|-2|Waldstadion|0|0|0|4|"
        prefix1 = b"\x00" * 600
        gap = b"\x00" * 600
        data = prefix1 + record1 + b"\x00" + gap + record2 + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x48000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        record1_addr = memory.base_address + len(prefix1)
        record2_addr = record1_addr + len(record1) + 1 + len(gap)
        addr1 = record1_addr + record1.index(b"Waldstadion")
        addr2 = record2_addr + record2.index(b"Waldstadion")

        def scan_side_effect(app_arg, pattern):
            if pattern == b"Waldstadion":
                return [addr1, addr2]
            return []

        with patch("server16_py.match_string_patcher._scan_memory", side_effect=scan_side_effect):
            result = coordinator._scan_and_patch(key, "Waldstadion", "Anfield")

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)

        text1 = memory.read_process_memory(record1_addr, len(record1) + 1).split(b"\x00", 1)[0].decode("utf-8")
        text2 = memory.read_process_memory(record2_addr, len(record2) + 1).split(b"\x00", 1)[0].decode("utf-8")
        self.assertIn("Anfield", text1)
        self.assertIn("Anfield", text2)

    def test_truncates_replacement_field_to_preserve_record_length(self) -> None:
        record = b"AC|-1|ATH|-1|-2|Waldstadion|0|0|0|4|"
        data = b"\x00" * 16 + record + b"\x00" * 16
        memory = FakeMemory(data, base_address=0x45000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        field_addr = memory.base_address + 16 + record.index(b"Waldstadion")
        record_addr = memory.base_address + 16

        ok = coordinator._patch_one_pipe(key, record_addr, len(record), "Waldstadion", "A Very Long Stadium Name Indeed")
        self.assertTrue(ok)
        written = memory.read_process_memory(record_addr, len(record))
        self.assertEqual(len(written), len(record))
        self.assertTrue(any("truncated" in line.lower() for line in app.logs))

    def test_already_correct_field_is_a_noop(self) -> None:
        record = b"AC|-1|ATH|-1|-2|Anfield|0|0|0|4|"
        data = record + b"\x00" * 8
        memory = FakeMemory(data, base_address=0x46000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        original = bytes(memory.buffer)

        ok = coordinator._patch_one_pipe(key, memory.base_address, len(record), "Waldstadion", "Anfield")
        self.assertTrue(ok)
        self.assertEqual(bytes(memory.buffer), original)
        self.assertEqual(coordinator.get_current_name("176"), "Anfield")

    def test_neither_name_present_fails(self) -> None:
        record = b"AC|-1|ATH|-1|-2|SomeOtherStadium|0|0|0|4|"
        data = record + b"\x00" * 8
        memory = FakeMemory(data, base_address=0x47000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        ok = coordinator._patch_one_pipe(key, memory.base_address, len(record), "Waldstadion", "Anfield")
        self.assertFalse(ok)
        self.assertIsNone(coordinator.get_current_name("176"))


class StadiumDbNamePatchCoordinatorPaddingTests(unittest.TestCase):
    def test_scan_and_patch_never_extends_into_non_zero_unconfirmed_memory(self) -> None:
        # Reworked 2026-09-11 (see [[live_memory_write_safety_protocol]]):
        # extending into merely-"readable" memory for an unconfirmed address
        # caused two separate live crashes (CLAUDE.md §7) -- a write of only
        # 4-21 bytes past "Waldstadion\0"'s own 12-byte footprint, into
        # memory the probe reported as "512 extra readable byte(s)",
        # corrupted something the engine reads/frees during match teardown.
        # "Readable" only proves the OS considers the page mapped, not that
        # the bytes are unused padding rather than a neighboring heap
        # object's own live data (simulated here with a non-zero 0x41
        # filler, standing in for that live data). An UNCONFIRMED address
        # (no matching STDNAME_SAFE_EXTEND_SUFFIXES entry) must still cap to
        # its own base_capacity when the padding isn't genuinely zero --
        # see the next test for the case where it IS zero, which now
        # extends automatically as a safe, install-independent default.
        old_text = "Waldstadion".encode("utf-8")
        # A real occurrence always has readable bytes before it too (this is
        # a live process's address space, not a buffer starting at 0) --
        # give the isolation check's "before" read something real to see.
        data = b"\x00" * 16 + old_text + b"\x00" + b"\x41" * 40
        memory = FakeMemory(data, base_address=0x90000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        long_new_name = "Campos de Sport de El Sardinero"
        with _patched_scan(memory, old_text):
            result = coordinator._scan_and_patch(key, "Waldstadion", long_new_name)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        addr, capacity, encoding = result[0]
        self.assertEqual(encoding, "utf-8")
        base_capacity = len(old_text) + 1
        self.assertEqual(capacity, base_capacity)  # never extended past the real footprint

        written = memory.read_process_memory(addr, capacity)
        decoded = written.split(b"\x00", 1)[0].decode("utf-8")
        self.assertTrue(long_new_name.startswith(decoded))
        self.assertLess(len(decoded), len(long_new_name))  # truncated, not extended
        self.assertTrue(any("truncated" in line.lower() for line in app.logs))
        # The 40 non-zero filler bytes past the string (standing in for a
        # neighboring live object) must be completely untouched -- proof
        # nothing was written beyond base_capacity. (prefix=16 bytes, then
        # base_capacity=12 bytes get written; everything from offset 28
        # onward is the original 0x41 filler.)
        untouched_offset = 16 + base_capacity
        self.assertEqual(bytes(memory.buffer[untouched_offset:]), b"\x41" * 40)

    def test_scan_and_patch_extends_into_genuinely_zero_padded_unconfirmed_memory(self) -> None:
        # The safe, install-independent default added 2026-09-11: an
        # UNCONFIRMED address (no STDNAME_SAFE_EXTEND_SUFFIXES match) still
        # gets extended automatically when the padding past it is
        # genuinely all-zero -- the same signal Part 10 originally used,
        # restored as the default so most builds/mods get untruncated names
        # without any manual Cheat Engine confirmation. Only non-zero
        # padding (the previous test) stays capped.
        old_text = "Waldstadion".encode("utf-8")
        data = b"\x00" * 16 + old_text + b"\x00" * 40
        memory = FakeMemory(data, base_address=0x91000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        long_new_name = "Campos de Sport de El Sardinero"
        with _patched_scan(memory, old_text):
            result = coordinator._scan_and_patch(key, "Waldstadion", long_new_name)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        addr, capacity, encoding = result[0]
        base_capacity = len(old_text) + 1
        self.assertGreater(capacity, base_capacity)

        written = memory.read_process_memory(addr, capacity)
        decoded = written.split(b"\x00", 1)[0].decode("utf-8")
        self.assertEqual(decoded, long_new_name)  # not truncated
        self.assertTrue(any("genuinely zero-padded" in line for line in app.logs))

    def test_scan_and_patch_extends_capacity_only_for_a_confirmed_safe_suffix(self) -> None:
        # Follow-up fix, 2026-09-11: the crash above was caused by extending
        # a DECOY copy of the vanilla name, not the real render-source
        # buffer -- the user directly confirmed with Cheat Engine that a
        # specific buffer family (identified by its low-16-bit address
        # suffix, stable across FIFA restarts despite ASLR moving the rest
        # of the address -- see offsets.STDNAME_SAFE_EXTEND_SUFFIXES) IS safe
        # to extend: it renders correctly AND survives abandoning the match.
        # An isolated occurrence whose address matches one of those confirmed
        # suffixes must still get the extended, unprobed-content capacity;
        # only occurrences that DON'T match stay capped to base_capacity.
        old_text = "Waldstadion".encode("utf-8")
        prefix = b"\x00" * 16
        data = prefix + old_text + b"\x00" * 40
        base_address = 0x92000
        memory = FakeMemory(data, base_address=base_address)
        app = make_db_app(memory)
        addr = base_address + len(prefix)
        app.offsets = SimpleNamespace(STDNAME_SAFE_EXTEND_SUFFIXES=[addr & 0xFFFF])
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        long_new_name = "Campos de Sport de El Sardinero"
        with _patched_scan(memory, old_text):
            result = coordinator._scan_and_patch(key, "Waldstadion", long_new_name)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        found_addr, capacity, encoding = result[0]
        self.assertEqual(found_addr, addr)
        self.assertGreater(capacity, len(old_text) + 1)  # extended past base_capacity

        written = memory.read_process_memory(found_addr, capacity)
        decoded = written.split(b"\x00", 1)[0].decode("utf-8")
        self.assertEqual(decoded, long_new_name)  # not truncated for the confirmed-safe suffix
        self.assertTrue(any("confirmed-safe suffix" in line for line in app.logs))


class StadiumDbNamePatchCoordinatorTests(unittest.TestCase):
    def test_scan_and_patch_no_longer_tries_utf16le(self) -> None:
        # UTF-16LE scanning was intentionally dropped from _scan_and_patch
        # (2026-09-10) -- across the whole live investigation it never once
        # found anything, and was costing roughly a third of each attempt's
        # wall-clock time for zero benefit, directly shrinking how many real
        # attempts fit inside the retry window. _find_isolated_occurrences
        # itself still supports UTF-16LE (see FindIsolatedOccurrencesTests),
        # so this locks in that _scan_and_patch deliberately no longer calls
        # it, rather than that support having silently regressed.
        old_text = "Waldstadion".encode("utf-16-le")
        data = b"\x00" * 32 + old_text + b"\x00" * 32
        memory = FakeMemory(data, base_address=0x30000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        with _patched_scan(memory, old_text):
            result = coordinator._scan_and_patch(key, "Waldstadion", "Anfield")
        self.assertIsNone(result)
        self.assertIsNone(coordinator.get_current_name("176"))

    def test_get_current_name_is_none_before_any_confirmed_success(self) -> None:
        memory = FakeMemory(b"\x00" * 16, base_address=0x31000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        self.assertIsNone(coordinator.get_current_name("176"))

    def test_patch_one_records_current_name_on_already_correct_noop(self) -> None:
        # _patch_one's "already the new name" branch (test_patch_one_noops_
        # when_already_the_new_name above) must also record the confirmed
        # name -- it's a real confirmation the buffer holds it, just one that
        # didn't require a write.
        text = "Anfield".encode("utf-16-le")
        capacity = len(text) + 2
        memory = FakeMemory(text + b"\x00\x00", base_address=0x32000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        coordinator._patch_one(key, (memory.base_address, capacity, "utf-16-le"), "Waldstadion", "Anfield")
        self.assertEqual(coordinator.get_current_name("176"), "Anfield")

    def test_patch_one_caches_truncated_text_not_the_full_request(self) -> None:
        # Real bug found live 2026-09-10: a truncated write used to log and
        # cache the FULL requested name, not what was actually written --
        # making the log claim success for text that was never fully there,
        # and poisoning get_current_name() so the *next* stadium loaded into
        # this slot would search for a name that was never actually
        # resident (since the buffer only ever held the truncated version).
        text = "Waldstadion".encode("utf-8")
        capacity = len(text) + 1  # exactly the vanilla name's own length -- no slack
        memory = FakeMemory(text + b"\x00", base_address=0x53000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        long_name = "A Very Long Stadium Name That Cannot Possibly Fit"
        ok = coordinator._patch_one(key, (memory.base_address, capacity, "utf-8"), "Waldstadion", long_name)
        self.assertTrue(ok)

        written = memory.read_process_memory(memory.base_address, capacity)
        decoded = written.split(b"\x00", 1)[0].decode("utf-8")
        self.assertTrue(long_name.startswith(decoded))
        self.assertLess(len(decoded), len(long_name))

        # get_current_name must report what's actually in the buffer, not
        # the untruncated request.
        self.assertEqual(coordinator.get_current_name("176"), decoded)
        self.assertTrue(any(f"-> '{decoded}'" in line for line in app.logs))
        self.assertFalse(any(f"-> '{long_name}'" in line for line in app.logs))

    def test_patch_one_does_not_wipe_memory_beyond_what_the_write_needs(self) -> None:
        # Real crash found live 2026-09-10: _probe_available_capacity can
        # legitimately measure hundreds of bytes of readable "slack" past a
        # short vanilla name (CLAUDE.md §7 Part 19) -- readable does not
        # mean unused, just readable. The old code always zero-padded the
        # FULL measured capacity regardless of how short the actual
        # replacement was, so a 15-byte name ("SPORTCLUB Arena") measured
        # against 524 bytes of capacity blindly wiped ~509 bytes of whatever
        # memory happened to sit past the string with NUL bytes -- FIFA
        # crashed on leaving the match shortly after, consistent with
        # delayed corruption of a neighboring live heap object that only
        # gets touched again during match teardown. Only as much as the new
        # text (or the old text's own footprint, whichever is larger)
        # actually needs must ever be touched -- `capacity` is only a
        # ceiling on how long a replacement is ALLOWED to be, not a
        # standing instruction to always clear out to it.
        old_text = b"Waldstadion"
        old_footprint = len(old_text) + 1  # text + its own NUL terminator
        marker = b"\xAB" * 500  # simulates unrelated, live memory past the string
        data = old_text + b"\x00" + marker
        capacity = len(data)  # a large measured "slack" capacity
        memory = FakeMemory(data, base_address=0x91000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        new_name = "SPORTCLUB Arena"
        ok = coordinator._patch_one(key, (memory.base_address, capacity, "utf-8"), "Waldstadion", new_name)
        self.assertTrue(ok)

        new_footprint = len(new_name.encode("utf-8")) + 1
        self.assertEqual(
            bytes(memory.buffer[:new_footprint]),
            new_name.encode("utf-8") + b"\x00",
        )
        # Everything past the new text's own footprint must be exactly the
        # original marker bytes, untouched -- not zeroed out.
        self.assertEqual(
            bytes(memory.buffer[new_footprint:]),
            marker[new_footprint - old_footprint:],
        )

    def test_patch_one_does_not_record_current_name_on_failure(self) -> None:
        text = "Some Other Field".encode("utf-16-le")
        capacity = len(text) + 2
        memory = FakeMemory(text + b"\x00\x00", base_address=0x33000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        coordinator._patch_one(key, (memory.base_address, capacity, "utf-16-le"), "Waldstadion", "Anfield")
        self.assertIsNone(coordinator.get_current_name("176"))

    def test_reset_clears_current_name(self) -> None:
        memory = FakeMemory(b"\x00" * 16, base_address=0x34000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        coordinator._current_name[key] = "Anfield"
        coordinator.reset()
        self.assertIsNone(coordinator.get_current_name("176"))

    def test_patch_one_noops_when_already_the_new_name(self) -> None:
        text = "Anfield".encode("utf-16-le")
        capacity = len(text) + 2
        memory = FakeMemory(text + b"\x00\x00", base_address=0x40000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        original = bytes(memory.buffer)

        ok = coordinator._patch_one(key, (memory.base_address, capacity, "utf-16-le"), "Waldstadion", "Anfield")
        self.assertTrue(ok)
        self.assertEqual(bytes(memory.buffer), original)

    def test_patch_one_refuses_buffer_that_was_reused_for_something_else(self) -> None:
        text = "Some Other Field".encode("utf-16-le")
        capacity = len(text) + 2
        memory = FakeMemory(text + b"\x00\x00", base_address=0x50000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        original = bytes(memory.buffer)

        ok = coordinator._patch_one(key, (memory.base_address, capacity, "utf-16-le"), "Waldstadion", "Anfield")
        self.assertFalse(ok)
        self.assertEqual(bytes(memory.buffer), original)

    def test_worker_retries_scan_across_calls_up_to_max_attempts(self) -> None:
        # The text may not be resident yet on the first call (fired as early
        # as the "TV/bumper" transition) -- app_game.py re-requests a few
        # times over the next few seconds, and each such call should trigger
        # a fresh scan (not silently no-op after the very first miss) until
        # MAX_SCAN_ATTEMPTS is reached.
        memory = FakeMemory(b"\x00" * 16, base_address=0x70000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        scan_calls = []
        with patch.object(coordinator, "_scan_and_patch", side_effect=lambda *a: scan_calls.append(a) or None):
            for _ in range(StadiumDbNamePatchCoordinator.MAX_SCAN_ATTEMPTS + 3):
                coordinator._pending[key] = ("Waldstadion", "Anfield")
                coordinator._running.add(key)
                coordinator._worker(key, allow_scan=True)
        self.assertEqual(len(scan_calls), StadiumDbNamePatchCoordinator.MAX_SCAN_ATTEMPTS)
        self.assertEqual(coordinator._scan_attempts[key], StadiumDbNamePatchCoordinator.MAX_SCAN_ATTEMPTS)

    def test_worker_loops_again_when_a_retry_arrives_mid_scan_even_with_identical_content(self) -> None:
        # Real bug found live 2026-09-09: a scan can take 1-2.5s+ (the 4GB
        # cap raise made this the common case), longer than app_game.py's
        # ~900ms retry interval. A retry firing while the previous scan is
        # still running always requests the exact same (old_name, new_name)
        # pair -- nothing about the target changed -- so comparing pending
        # *values* alone can't tell "a fresh retry call landed mid-scan" apart
        # from "no one called request() again". That swallowed most scheduled
        # retries silently (only ~5 of 6 scheduled attempts, sometimes fewer,
        # ever ran a real scan). The fix compares a request sequence number
        # instead, bumped on every request() call regardless of content.
        memory = FakeMemory(b"\x00" * 16, base_address=0x71000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        scan_calls = []

        def fake_scan_and_patch(k, old_name, new_name):
            scan_calls.append((old_name, new_name))
            if len(scan_calls) == 1:
                # Simulate app_game.py's retry timer firing a *second*
                # request() call (identical content) while this "scan" is
                # still in progress.
                coordinator.request("176", old_name, new_name)
            return None

        # Drive _worker directly (as the other tests in this class do) rather
        # than through request(), which would spawn a real background thread
        # and make this test's assertions race against it.
        coordinator._pending[key] = ("Waldstadion", "Anfield")
        coordinator._running.add(key)
        coordinator._request_seq[key] = 1
        with patch.object(coordinator, "_scan_and_patch", side_effect=fake_scan_and_patch):
            coordinator._worker(key, allow_scan=True)

        # Without the sequence-number fix, the worker would see the pending
        # tuple unchanged after the first scan, pop it, and exit after a
        # single attempt -- silently dropping the retry that arrived mid-scan.
        self.assertEqual(len(scan_calls), 2)
        self.assertEqual(coordinator._scan_attempts[key], 2)

    def test_worker_keeps_scanning_after_early_find_and_merges_new_candidates(self) -> None:
        # Real bug found live 2026-09-10: a candidate found on an early
        # attempt (e.g. attempt 2/20) used to make the worker stop scanning
        # entirely for the rest of the 20-attempt budget -- it just kept
        # re-verifying that one already-cached address. That candidate turned
        # out not to be the one the presentation screen renders from, and the
        # pipe-delimited record that WAS found (and worked, in a different
        # sense) in an earlier session only became resident later (attempt
        # 6) -- with the old behavior, that later discovery would never have
        # been attempted at all. Scanning must continue every attempt, adding
        # newly found addresses to what's already cached rather than treating
        # any find as "done".
        memory = FakeMemory(b"\x00" * 16, base_address=0x72000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        scan_calls: list[tuple[str, str]] = []

        def fake_scan_and_patch(k, old_name, new_name):
            scan_calls.append((old_name, new_name))
            if len(scan_calls) == 1:
                return [(0x1000, 16, "utf-8")]
            if len(scan_calls) == 3:
                return [(0x2000, 32, "pipe")]
            return None

        with patch.object(coordinator, "_scan_and_patch", side_effect=fake_scan_and_patch), \
                patch.object(coordinator, "_patch_one", return_value=True):
            for _ in range(5):
                coordinator._pending[key] = ("Waldstadion", "Anfield")
                coordinator._running.add(key)
                coordinator._worker(key, allow_scan=True)

        self.assertEqual(len(scan_calls), 5)
        self.assertEqual(coordinator._cache[key], [(0x1000, 16, "utf-8"), (0x2000, 32, "pipe")])

    def test_worker_skips_scan_when_renaming_an_already_confirmed_slot(self) -> None:
        # Once a slot's address has already been CONFIRMED live by an
        # earlier, separate rename, loading a *different* stadium into the
        # same slot should just rewrite that known-good address directly --
        # not pay for another multi-second memory scan. FIFA's loaded name
        # buffer for a container slot is assumed process-lifetime-stable
        # (this class's own design, CLAUDE.md §7 Part 3/14).
        text = "Anfield".encode("utf-8")
        capacity = len(text) + 32
        memory = FakeMemory(text + b"\x00" * 32, base_address=0x73000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        coordinator._cache[key] = [(memory.base_address, capacity, "utf-8")]
        coordinator._current_name[key] = "Anfield"
        coordinator._pending[key] = ("Anfield", "Old Trafford")
        coordinator._running.add(key)

        with patch.object(coordinator, "_scan_and_patch") as mock_scan:
            coordinator._worker(key, allow_scan=True, is_rename=True)

        mock_scan.assert_not_called()
        new_bytes = "Old Trafford".encode("utf-8")
        self.assertEqual(memory.read_process_memory(memory.base_address, len(new_bytes)), new_bytes)
        self.assertEqual(coordinator.get_current_name("176"), "Old Trafford")

    def test_worker_falls_back_to_scan_when_renamed_cache_no_longer_valid(self) -> None:
        # The rename shortcut must not get stuck if the cached address turns
        # out to no longer hold either the expected old or new name (the
        # buffer was reused for something else) -- fall back to a real scan
        # to rediscover it rather than silently doing nothing forever.
        text = "Some Other Field".encode("utf-8")
        capacity = len(text) + 8
        memory = FakeMemory(text + b"\x00" * 8, base_address=0x74000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        coordinator._cache[key] = [(memory.base_address, capacity, "utf-8")]
        coordinator._current_name[key] = "Anfield"
        coordinator._pending[key] = ("Anfield", "Old Trafford")
        coordinator._running.add(key)

        with patch.object(coordinator, "_scan_and_patch", return_value=None) as mock_scan:
            coordinator._worker(key, allow_scan=True, is_rename=True)

        mock_scan.assert_called_once()

    def test_worker_still_scans_first_discovery_even_with_is_rename_unset(self) -> None:
        # is_rename defaults to False -- a slot's very first discovery this
        # session (nothing confirmed yet) must always keep its full scan
        # budget, never shortcut based on a merely-populated cache.
        memory = FakeMemory(b"\x00" * 16, base_address=0x77000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        coordinator._pending[key] = ("Waldstadion", "Anfield")
        coordinator._running.add(key)

        with patch.object(coordinator, "_scan_and_patch", return_value=None) as mock_scan:
            coordinator._worker(key, allow_scan=True)

        mock_scan.assert_called_once()

    def test_request_marks_is_rename_when_old_name_matches_confirmed_current_name(self) -> None:
        memory = FakeMemory(b"\x00" * 16, base_address=0x61000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        coordinator._current_name[key] = "Anfield"

        with patch("server16_py.match_string_patcher.threading.Thread") as mock_thread:
            coordinator.request("176", "Anfield", "Old Trafford")

        _, kwargs = mock_thread.call_args
        self.assertEqual(kwargs["args"], (key, True, True))

    def test_request_does_not_mark_is_rename_for_first_time_discovery(self) -> None:
        memory = FakeMemory(b"\x00" * 16, base_address=0x62000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")

        with patch("server16_py.match_string_patcher.threading.Thread") as mock_thread:
            coordinator.request("176", "Waldstadion", "Anfield")

        _, kwargs = mock_thread.call_args
        self.assertEqual(kwargs["args"], (key, True, False))

    def test_request_returns_false_when_old_equals_new(self) -> None:
        memory = FakeMemory(b"\x00" * 16, base_address=0x60000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        self.assertFalse(coordinator.request("176", "Anfield", "Anfield"))

    def test_request_returns_false_when_memory_not_open(self) -> None:
        memory = FakeMemory(b"\x00" * 16, base_address=0x60000)
        app = make_db_app(memory)
        app.memory.is_open = lambda: False
        coordinator = StadiumDbNamePatchCoordinator(app)
        self.assertFalse(coordinator.request("176", "Waldstadion", "Anfield"))

    def test_reset_clears_cache_and_pending_state(self) -> None:
        memory = FakeMemory(b"\x00" * 16, base_address=0x60000)
        app = make_db_app(memory)
        coordinator = StadiumDbNamePatchCoordinator(app)
        key = coordinator._key("176")
        coordinator._cache[key] = [(memory.base_address, 16, "utf-16-le")]
        coordinator._scan_attempts[key] = 1
        coordinator._pending[key] = ("Waldstadion", "Anfield")
        coordinator.reset()
        self.assertEqual(coordinator._cache, {})
        self.assertEqual(coordinator._scan_attempts, {})
        self.assertEqual(coordinator._pending, {})


if __name__ == "__main__":
    unittest.main()
