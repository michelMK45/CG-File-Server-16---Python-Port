from __future__ import annotations

import unittest

from server16_py.memory_access import Memory, MemoryAccessError


class FakeMemory(Memory):
    """Backs Memory's read/write surface with a plain in-process buffer so
    write_string_safe's capacity-probing logic can be exercised without a
    real process handle. Deliberately skips Memory.__init__ (which opens a
    real process) -- write_string_safe only ever calls read_process_memory/
    write_process_memory, both overridden here."""

    def __init__(self, data: bytes, base_address: int = 0x1000) -> None:
        self.buffer = bytearray(data)
        self.base_address = base_address
        # Memory.__del__ calls close(), which reads process_handle -- Memory's
        # own __init__ is deliberately skipped here (it opens a real
        # process), so this satisfies that attribute without needing it.
        self.process_handle = None

    def read_process_memory(self, address: int, size: int) -> bytes:
        offset = address - self.base_address
        if offset < 0:
            raise MemoryAccessError("read before buffer start")
        return bytes(self.buffer[offset:offset + size])

    def read_process_memory_partial(self, address: int, size: int) -> bytes:
        # Mirrors the real Memory.read_process_memory_partial's "never
        # raises" contract -- Python's own slicing already truncates past
        # the buffer's end instead of raising, so this only needs to guard
        # the before-buffer-start case (return b"" there instead of raising).
        offset = address - self.base_address
        if offset < 0:
            return b""
        return bytes(self.buffer[offset:offset + size])

    def write_process_memory(self, address: int, payload: bytes) -> None:
        offset = address - self.base_address
        if offset < 0 or offset + len(payload) > len(self.buffer):
            raise MemoryAccessError("write out of bounds")
        self.buffer[offset:offset + len(payload)] = payload


class WriteStringSafeTests(unittest.TestCase):
    def test_uses_max_bytes_when_no_extra_room_exists(self) -> None:
        # Tightly packed: right after the old string's own NUL comes
        # non-zero data belonging to something else -- must not touch it.
        data = b"Anfield\x00" + b"\xAB" * 64
        memory = FakeMemory(data)
        written, _addr = memory.write_string_safe(memory.base_address, "Old Trafford", max_bytes=8)
        self.assertEqual(written, "Old Traf")  # truncated to the 8-byte floor
        self.assertEqual(memory.buffer[9], 0xAB)  # untouched marker byte

    def test_extends_past_max_bytes_using_measured_zero_padding(self) -> None:
        # A short old string, but plenty of real zero padding after it --
        # reported live 2026-09-10: editing this kind of buffer directly in
        # Cheat Engine showed no practical limit, unlike the old fixed
        # max_bytes=63 default this function used to enforce unconditionally.
        data = b"Anfield\x00" + b"\x00" * 100
        memory = FakeMemory(data)
        long_name = "A Very Long Custom Stadium Display Name"
        written, _addr = memory.write_string_safe(memory.base_address, long_name, max_bytes=8)
        self.assertEqual(written, long_name)  # not truncated to the 8-byte floor

    def test_reuses_old_strings_own_footprint_even_with_zero_extra_padding(self) -> None:
        # The old string was already longer than max_bytes -- everything up
        # to and including its own NUL is provably safe to overwrite,
        # regardless of what (if anything) comes right after it.
        old = "Waldstadion (a longish vanilla name)"
        data = old.encode("utf-8") + b"\x00" + b"\xCD" * 32
        memory = FakeMemory(data)
        written, _addr = memory.write_string_safe(memory.base_address, "Also Fairly Long Name", max_bytes=8)
        self.assertEqual(written, "Also Fairly Long Name")

    def test_probes_further_when_initial_read_window_is_entirely_zero(self) -> None:
        # validation_size bounds only the *initial* read; if that whole
        # window comes back zero, a follow-up probe read extends the
        # measured capacity further rather than assuming the padding stops
        # exactly at the initial window's edge.
        data = b"Anfield\x00" + b"\x00" * 32  # entirely zero within validation_size below
        extra = b"\x00" * 200  # more real zero padding beyond the initial read window
        memory = FakeMemory(data + extra)
        long_name = "X" * 150
        written, _addr = memory.write_string_safe(
            memory.base_address, long_name, max_bytes=8, validation_size=40
        )
        self.assertEqual(written, long_name)

    def test_probe_read_failure_caps_capacity_at_the_initial_reads_own_findings(self) -> None:
        # If the follow-up probe read comes back completely empty (e.g.
        # crossing into an unmapped page from the very first probed byte),
        # the measured capacity must fall back to only what the *initial*
        # read already proved is zero -- never silently assume more room
        # exists just because the probe couldn't confirm it.
        data = b"Anfield\x00" + b"\x00" * 8  # null_index=7, 8 known-zero bytes after it
        memory = FakeMemory(data)

        def empty_probe(address: int, size: int) -> bytes:
            return b""  # read_process_memory_partial never raises; total failure is b""

        memory.read_process_memory_partial = empty_probe  # type: ignore[method-assign]
        long_name = "X" * 30
        written, _addr = memory.write_string_safe(
            memory.base_address, long_name, max_bytes=8, validation_size=16
        )
        self.assertEqual(len(written), 15)  # null_index(7) + zero_run(8), no more

    def test_probe_credits_a_partial_read_past_the_initial_window(self) -> None:
        # Real bug found live 2026-09-10: ReadProcessMemory can genuinely
        # PARTIALLY succeed when part of the requested range crosses into
        # unmapped memory -- Windows copies the accessible prefix and reports
        # that byte count while the call still fails overall. The old
        # implementation (a plain try/except around read_process_memory,
        # which raises on ANY overall failure regardless of bytes actually
        # copied) discarded that legitimately-read prefix entirely, so this
        # probe got credited with ZERO extra room the instant even the very
        # last requested byte fell outside mapped memory -- exactly the gap
        # between a user's own longer Cheat Engine edit working fine and
        # CGFS's own write truncating the same buffer.
        data = b"Anfield\x00" + b"\x00" * 8  # null_index=7, 8 known-zero bytes in the initial window
        # The backing buffer needs real room for the write this measured
        # capacity will actually use -- only the *probe* (below) is faked to
        # simulate a partial ReadProcessMemory result short of the full
        # requested size; the bytes it claims are readable must genuinely
        # exist for the write itself to succeed.
        memory = FakeMemory(data + b"\x00" * 40)

        def partial_probe(address: int, size: int) -> bytes:
            return b"\x00" * 40  # only a 40-byte prefix of the request was actually mapped

        memory.read_process_memory_partial = partial_probe  # type: ignore[method-assign]
        long_name = "X" * 60
        written, _addr = memory.write_string_safe(
            memory.base_address, long_name, max_bytes=8, validation_size=16
        )
        self.assertEqual(len(written), 55)  # null_index(7) + zero_run(8 + 40)

    def test_never_writes_past_the_measured_capacity(self) -> None:
        data = b"Anfield\x00" + b"\x00" * 10 + b"\xAB" * 20
        memory = FakeMemory(data)
        long_name = "X" * 100
        written, _addr = memory.write_string_safe(memory.base_address, long_name, max_bytes=8)
        # zero_run is exactly 10 (bytes after the NUL up to the 0xAB marker),
        # so effective_max_bytes = null_index(7) + zero_run(10) = 17.
        self.assertEqual(len(written), 17)
        self.assertEqual(memory.buffer[8 + 10:], b"\xAB" * 20)  # marker region untouched

    def test_rejects_address_with_no_nul_within_the_read_window(self) -> None:
        data = b"\xAB" * 300
        memory = FakeMemory(data)
        with self.assertRaises(MemoryAccessError):
            memory.write_string_safe(memory.base_address, "Anfield", max_bytes=8)

    def test_offsets_variant_forwards_max_extra_capacity(self) -> None:
        class ResolvingMemory(FakeMemory):
            def resolve_pointer(self, static_ptr: int, offsets: list) -> int:
                return self.base_address

        data = b"Anfield\x00" + b"\x00" * 100
        memory = ResolvingMemory(data)
        long_name = "A Very Long Custom Stadium Display Name"
        written, _addr = memory.write_string_with_offsets_safe(0, [0], long_name, max_bytes=8)
        self.assertEqual(written, long_name)


if __name__ == "__main__":
    unittest.main()
