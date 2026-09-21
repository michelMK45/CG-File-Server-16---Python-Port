from __future__ import annotations

import ctypes
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server16_py import match_string_patcher as msp
from server16_py.match_string_patcher import (
    StadiumDbNamePatchCoordinator,
    _find_isolated_occurrences,
    _scan_memory,
)

MEM_COMMIT = 0x1000
MEM_FREE = 0x10000
PAGE_READWRITE = 0x04


class _FakeFunc:
    """ctypes function pointers accept .restype/.argtypes assignment; a bound
    method does not, so wrap the fake in something that does."""

    def __init__(self, fn) -> None:
        self.fn = fn
        self.restype = None
        self.argtypes = None

    def __call__(self, *args):
        return self.fn(*args)


class FakeKernel32:
    """Just enough VirtualQueryEx/ReadProcessMemory over a list of
    (base, bytes) committed regions, with free gaps in between."""

    def __init__(self, regions: list[tuple[int, bytes]]) -> None:
        self.regions = sorted(regions)
        self.vqe_calls = 0
        self.lock_held_during_walk: list[bool] = []
        self.VirtualQueryEx = _FakeFunc(self._virtual_query_ex)
        self.ReadProcessMemory = self._read_process_memory

    def _virtual_query_ex(self, handle, addr, mbi_ref, size):
        # A real walk must not be holding the module's scan lock (that
        # serialized every scan in the process behind the first one).
        self.lock_held_during_walk.append(msp._SCAN_LOCK.locked())
        self.vqe_calls += 1
        mbi = mbi_ref._obj
        for base, data in self.regions:
            if base <= addr < base + len(data):
                mbi.BaseAddress = base
                mbi.RegionSize = base + len(data) - addr
                mbi.State = MEM_COMMIT
                mbi.Protect = PAGE_READWRITE
                mbi.AllocationProtect = PAGE_READWRITE
                return ctypes.sizeof(mbi)
        # Free gap up to the next region (or a large tail).
        next_base = min((b for b, _ in self.regions if b > addr), default=None)
        if next_base is None:
            return 0
        mbi.BaseAddress = addr
        mbi.RegionSize = next_base - addr
        mbi.State = MEM_FREE
        mbi.Protect = 0
        mbi.AllocationProtect = 0
        return ctypes.sizeof(mbi)

    def _read_process_memory(self, handle, addr_ptr, buf, size, read_ref):
        addr = addr_ptr.value
        for base, data in self.regions:
            if base <= addr < base + len(data):
                chunk = data[addr - base: addr - base + size]
                ctypes.memmove(buf, chunk, len(chunk))
                read_ref._obj.value = len(chunk)
                return 1
        return 0


def make_scan_app(regions) -> SimpleNamespace:
    app = SimpleNamespace()
    app.memory = SimpleNamespace(kernel32=FakeKernel32(regions), process_handle=object())
    app.logs = []
    app.log = lambda *parts: app.logs.append(" ".join(str(p) for p in parts))
    return app


class ScanMemoryTests(unittest.TestCase):
    def test_does_not_hold_the_scan_lock_during_the_walk(self) -> None:
        # Found live 2026-09-21: MatchStringPatchCoordinator's 3-second
        # full-process scan (which has never found anything in any captured
        # log) held this lock for its whole walk, so the scan that actually
        # matters waited behind it and the name patch landed too late.
        data = b"\x00" * 16 + b"Waldstadion" + b"\x00" * 16
        app = make_scan_app([(0x1000, data)])
        _scan_memory(app, b"Waldstadion")
        self.assertTrue(app.memory.kernel32.lock_held_during_walk)
        self.assertFalse(any(app.memory.kernel32.lock_held_during_walk))

    def test_two_scans_can_overlap(self) -> None:
        # A scan that is mid-walk must not block another scan from starting.
        gate = threading.Event()
        released = threading.Event()
        data = b"\x00" * 8 + b"Waldstadion" + b"\x00" * 8
        slow_app = make_scan_app([(0x1000, data)])
        real_vqe = slow_app.memory.kernel32._virtual_query_ex

        def slow_vqe(handle, addr, mbi_ref, size):
            gate.set()
            released.wait(timeout=5)
            return real_vqe(handle, addr, mbi_ref, size)

        slow_app.memory.kernel32.VirtualQueryEx = _FakeFunc(slow_vqe)
        fast_app = make_scan_app([(0x1000, data)])

        results = {}
        t = threading.Thread(target=lambda: results.setdefault("slow", _scan_memory(slow_app, b"Waldstadion")))
        t.start()
        self.assertTrue(gate.wait(timeout=5))
        # The slow scan is now parked inside its walk. A second scan must
        # still complete promptly rather than queueing behind it.
        started = time.monotonic()
        fast = _scan_memory(fast_app, b"Waldstadion")
        elapsed = time.monotonic() - started
        released.set()
        t.join(timeout=5)
        self.assertEqual(fast, [0x1000 + 8])
        self.assertLess(elapsed, 2.0)
        self.assertEqual(results["slow"], [0x1000 + 8])

    def test_quiet_suppresses_the_summary_unless_something_was_found(self) -> None:
        app = make_scan_app([(0x1000, b"\x00" * 64)])
        _scan_memory(app, b"Waldstadion", quiet=True)
        self.assertEqual(app.logs, [])

        hit_app = make_scan_app([(0x1000, b"\x00" * 8 + b"Waldstadion" + b"\x00" * 8)])
        _scan_memory(hit_app, b"Waldstadion", quiet=True)
        self.assertTrue(any("Memory scan" in line for line in hit_app.logs))

    def test_default_scan_still_logs_its_summary(self) -> None:
        app = make_scan_app([(0x1000, b"\x00" * 64)])
        _scan_memory(app, b"Waldstadion")
        self.assertTrue(any("Memory scan" in line for line in app.logs))

    def test_max_scan_clips_an_oversized_region(self) -> None:
        # The name sits well past the cap inside a single big region -- a
        # bounded probe must not read that far.
        big = b"\x00" * 4096 + b"Waldstadion" + b"\x00" * 16
        app = make_scan_app([(0x1000, big)])
        self.assertEqual(_scan_memory(app, b"Waldstadion", max_scan=1024), [])
        self.assertEqual(_scan_memory(app, b"Waldstadion"), [0x1000 + 4096])

    def test_range_bounds_the_walk(self) -> None:
        # Nothing is allocated inside the window yet (the state right before
        # FIFA allocates the buffer): no hits, and the walk terminates.
        elsewhere = b"\x00" * 8 + b"Waldstadion" + b"\x00" * 8
        app = make_scan_app([(0x10000000, elsewhere)])
        self.assertEqual(_scan_memory(app, b"Waldstadion", start_addr=0x94000000, end_addr=0x94800000), [])


class FindIsolatedPriorityOnlyTests(unittest.TestCase):
    def _app(self, data: bytes, base: int):
        memory = SimpleNamespace(
            read_process_memory=lambda address, size: bytes(data[address - base: address - base + size]),
        )
        app = SimpleNamespace(memory=memory, logs=[])
        app.log = lambda *parts: app.logs.append(" ".join(str(p) for p in parts))
        return app

    def test_priority_only_never_falls_back_to_the_full_scan(self) -> None:
        app = self._app(b"\x00" * 32, 0x94000000)
        calls = []

        def fake_scan(app_arg, pattern, start_addr=0, end_addr=0x7FFFFFFFFFFF, **kwargs):
            calls.append((start_addr, end_addr))
            return []

        with patch("server16_py.match_string_patcher._scan_memory", side_effect=fake_scan):
            result = _find_isolated_occurrences(
                app, b"Waldstadion", 1, priority_ranges=[(0x94000000, 0x94800000)], priority_only=True
            )
        self.assertEqual(result, [])
        self.assertEqual(calls, [(0x94000000, 0x94800000)])  # no unrestricted scan

    def test_quiet_and_max_scan_are_forwarded_and_silence_the_logs(self) -> None:
        text = b"Waldstadion"
        data = b"\x00" * 16 + text + b"\x00" * 16
        app = self._app(data, 0x94000000)
        seen = {}

        def fake_scan(app_arg, pattern, start_addr=0, end_addr=0x7FFFFFFFFFFF, **kwargs):
            seen.update(kwargs)
            return [0x94000000 + 16]

        with patch("server16_py.match_string_patcher._scan_memory", side_effect=fake_scan):
            result = _find_isolated_occurrences(
                app, text, 1, priority_ranges=[(0x94000000, 0x94800000)],
                priority_only=True, quiet=True, max_scan=1234,
            )
        self.assertEqual(result, [0x94000000 + 16])
        self.assertEqual(seen, {"quiet": True, "max_scan": 1234})
        self.assertEqual(app.logs, [])

    def test_default_call_forwards_no_extra_kwargs(self) -> None:
        # Existing callers/tests patch _scan_memory with the old signature.
        text = b"Waldstadion"
        data = b"\x00" * 16 + text + b"\x00" * 16
        app = self._app(data, 0x94000000)
        seen = {}

        def fake_scan(app_arg, pattern, start_addr=0, end_addr=0x7FFFFFFFFFFF, **kwargs):
            seen.update(kwargs)
            return [0x94000000 + 16]

        with patch("server16_py.match_string_patcher._scan_memory", side_effect=fake_scan):
            _find_isolated_occurrences(app, text, 1, priority_ranges=[(0x94000000, 0x94800000)])
        self.assertEqual(seen, {})


class FakeProcessMemory:
    """A single mutable buffer standing in for FIFA's name buffer, with the
    read/write surface the coordinator's patch path needs."""

    def __init__(self, base: int, size: int = 0x400) -> None:
        self.base_address = base
        self.buffer = bytearray(size)
        self.process_id = 4242
        self.process_handle = object()
        self.kernel32 = SimpleNamespace(VirtualProtectEx=lambda *a, **k: 1)

    def is_open(self) -> bool:
        return True

    def put(self, offset: int, text: bytes) -> None:
        self.buffer[offset:offset + len(text)] = text

    def read_process_memory(self, address: int, size: int) -> bytes:
        off = address - self.base_address
        if off < 0:
            raise AssertionError("read before buffer")
        return bytes(self.buffer[off:off + size])

    def read_process_memory_partial(self, address: int, size: int) -> bytes:
        off = address - self.base_address
        return b"" if off < 0 else bytes(self.buffer[off:off + size])

    def write_process_memory(self, address: int, payload: bytes) -> None:
        off = address - self.base_address
        self.buffer[off:off + len(payload)] = payload


def make_coordinator(memory, ranges=None):
    app = SimpleNamespace()
    app.memory = memory
    app._closing = False
    app.offsets = SimpleNamespace(
        STDNAME_SAFE_EXTEND_PRIORITY_RANGES=[(0x94000000, 0x94800000)] if ranges is None else ranges,
        STDNAME_SAFE_EXTEND_SUFFIXES=[],
    )
    app.logs = []
    app.log = lambda *parts: app.logs.append(" ".join(str(p) for p in parts))
    return app, StadiumDbNamePatchCoordinator(app)


def wait_for(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class FastWatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.memory = FakeProcessMemory(0x94000000)
        self.app, self.coordinator = make_coordinator(self.memory)
        # Keep the tests fast without changing the logic under test.
        self.coordinator.FAST_WATCH_INTERVAL_SECONDS = 0.01
        self.coordinator.FAST_WATCH_GRACE_INTERVAL_SECONDS = 0.01
        self.coordinator.FAST_WATCH_GRACE_SECONDS = 0.1

    def _fake_scan(self, appear_after_probes: int):
        """_scan_memory stand-in: empty for the first N probes (the buffer is
        not allocated yet), then reports the text's real location."""
        probes = {"n": 0}
        pattern_offsets = {}

        def scan(app_arg, pattern, start_addr=0, end_addr=0x7FFFFFFFFFFF, **kwargs):
            probes["n"] += 1
            if probes["n"] <= appear_after_probes:
                return []
            idx = self.memory.buffer.find(pattern)
            return [self.memory.base_address + idx] if idx != -1 else []

        scan.probes = probes
        return scan

    def test_patches_as_soon_as_the_buffer_appears_without_using_scan_budget(self) -> None:
        scan = self._fake_scan(appear_after_probes=3)
        with patch("server16_py.match_string_patcher._scan_memory", side_effect=scan):
            self.assertTrue(self.coordinator.fast_watch("261", "Sanderson Park", "Coliseum Alfonso Perez"))
            # The buffer only shows up later, like FIFA allocating it at load.
            time.sleep(0.02)
            self.memory.put(0x20, b"Sanderson Park\x00")
            self.assertTrue(wait_for(lambda: self.coordinator.get_current_name("261") == "Coliseum Alfonso Perez"))
        written = bytes(self.memory.buffer[0x20:0x20 + 23])
        self.assertTrue(written.startswith(b"Coliseum Alfonso Perez\x00"))
        # Probes must not consume the per-slot scan budget.
        self.assertEqual(self.coordinator._scan_attempts, {})
        self.assertTrue(wait_for(lambda: not self.coordinator._fast_watching))

    def test_caches_the_patched_address_for_later_reuse(self) -> None:
        self.memory.put(0x20, b"Sanderson Park\x00")
        scan = self._fake_scan(appear_after_probes=0)
        with patch("server16_py.match_string_patcher._scan_memory", side_effect=scan):
            self.coordinator.fast_watch("261", "Sanderson Park", "Coliseum Alfonso Perez")
            self.assertTrue(wait_for(lambda: self.coordinator._cache.get((4242, "261"))))
        cached = self.coordinator._cache[(4242, "261")]
        self.assertEqual(cached[0][0], 0x94000000 + 0x20)

    def test_stops_at_its_deadline_when_nothing_ever_appears(self) -> None:
        scan = self._fake_scan(appear_after_probes=10 ** 9)
        with patch("server16_py.match_string_patcher._scan_memory", side_effect=scan):
            self.coordinator.fast_watch("261", "Sanderson Park", "X", max_seconds=0.15)
            self.assertTrue(wait_for(lambda: not self.coordinator._fast_watching, timeout=5))
        self.assertIsNone(self.coordinator.get_current_name("261"))

    def test_second_call_does_not_spawn_a_second_worker(self) -> None:
        scan = self._fake_scan(appear_after_probes=10 ** 9)
        with patch("server16_py.match_string_patcher._scan_memory", side_effect=scan):
            with patch("server16_py.match_string_patcher.threading.Thread") as thread_cls:
                self.assertTrue(self.coordinator.fast_watch("261", "Sanderson Park", "X"))
                self.assertTrue(self.coordinator.fast_watch("261", "Sanderson Park", "X"))
        self.assertEqual(thread_cls.call_count, 1)

    def test_noop_when_old_equals_new(self) -> None:
        self.assertFalse(self.coordinator.fast_watch("261", "Same", "Same"))
        self.assertFalse(self.coordinator._fast_watching)

    def test_noop_without_any_priority_window(self) -> None:
        # An install with no configured window and nothing learned yet keeps
        # relying on the slow attempts exactly as before.
        app, coordinator = make_coordinator(self.memory, ranges=[])
        self.assertFalse(coordinator.fast_watch("261", "Sanderson Park", "X"))

    def test_noop_when_the_process_is_gone(self) -> None:
        self.app._closing = True
        self.assertFalse(self.coordinator.fast_watch("261", "Sanderson Park", "X"))

    def test_probes_only_the_priority_window_never_a_full_scan(self) -> None:
        calls = []

        def scan(app_arg, pattern, start_addr=0, end_addr=0x7FFFFFFFFFFF, **kwargs):
            calls.append((start_addr, end_addr, kwargs))
            return []

        with patch("server16_py.match_string_patcher._scan_memory", side_effect=scan):
            self.coordinator.fast_watch("261", "Sanderson Park", "X", max_seconds=0.1)
            self.assertTrue(wait_for(lambda: not self.coordinator._fast_watching, timeout=5))
        self.assertTrue(calls)
        for start, end, kwargs in calls:
            self.assertEqual((start, end), (0x94000000, 0x94800000))
            self.assertTrue(kwargs.get("quiet"))
            self.assertEqual(kwargs.get("max_scan"), StadiumDbNamePatchCoordinator.FAST_WATCH_MAX_SCAN_BYTES)

    def test_probing_is_silent_until_something_is_found(self) -> None:
        scan = self._fake_scan(appear_after_probes=10 ** 9)
        with patch("server16_py.match_string_patcher._scan_memory", side_effect=scan):
            self.coordinator.fast_watch("261", "Sanderson Park", "X", max_seconds=0.1)
            self.assertTrue(wait_for(lambda: not self.coordinator._fast_watching, timeout=5))
        self.assertEqual(self.app.logs, [])


class LearnedRangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.memory = FakeProcessMemory(0x10000000)
        self.app, self.coordinator = make_coordinator(self.memory, ranges=[])

    def test_a_successful_patch_teaches_a_window_used_by_later_scans(self) -> None:
        self.assertEqual(self.coordinator._priority_ranges(4242), [])
        self.coordinator._learn_range(4242, 0x10000020)
        ranges = self.coordinator._priority_ranges(4242)
        self.assertEqual(len(ranges), 1)
        start, end = ranges[0]
        self.assertLessEqual(start, 0x10000020)
        self.assertGreater(end, 0x10000020)

    def test_an_address_already_covered_learns_nothing_new(self) -> None:
        self.coordinator._learn_range(4242, 0x10000020)
        self.coordinator._learn_range(4242, 0x10000900)
        self.assertEqual(len(self.coordinator._priority_ranges(4242)), 1)

    def test_configured_windows_also_count_as_covering(self) -> None:
        app, coordinator = make_coordinator(self.memory, ranges=[(0x10000000, 0x11000000)])
        coordinator._learn_range(4242, 0x10000020)
        self.assertEqual(coordinator._priority_ranges(4242), [(0x10000000, 0x11000000)])

    def test_windows_are_per_process(self) -> None:
        self.coordinator._learn_range(4242, 0x10000020)
        self.assertEqual(self.coordinator._priority_ranges(9999), [])

    def test_reset_forgets_learned_windows(self) -> None:
        self.coordinator._learn_range(4242, 0x10000020)
        self.coordinator.reset()
        self.assertEqual(self.coordinator._priority_ranges(4242), [])

    def test_a_real_patch_learns_its_own_neighborhood(self) -> None:
        # End to end through the shared patch path: slot A's slow discovery
        # teaches a window that makes slot B's fast watch possible on an
        # install with no configured window at all.
        self.memory.put(0x20, b"Waldstadion\x00")
        key = self.coordinator._key("176")
        addr = self.memory.base_address + 0x20
        found = self.coordinator._patch_isolated_addresses(
            key, [addr], b"Waldstadion", 1, "utf-8", "Waldstadion", "Anfield"
        )
        self.assertEqual(len(found), 1)
        self.assertTrue(self.coordinator._priority_ranges(4242))
        self.assertTrue(self.coordinator.fast_watch("261", "Sanderson Park", "X", max_seconds=0.05))
        self.assertTrue(wait_for(lambda: not self.coordinator._fast_watching, timeout=5))


if __name__ == "__main__":
    unittest.main()
