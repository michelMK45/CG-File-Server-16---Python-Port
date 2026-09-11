from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Offsets:
    ORIPGBASE: int = 58757168
    ORIHTIDBASE: int = 56170408
    ORITOURIDBASE: int = 56170408
    ORISTADIDBASE: int = 55673768
    ORIFRIHTIDBASE: int = 57966104
    ORINETDEPTHBASE: int = 55697872
    STDNAMEBASE: int = 57964392
    GAMESTARTEDBINARYBASE: int = 55490608
    GAMESTATSBASE: int = 56299464
    PG1: list[int] = field(default_factory=lambda: [232, 192, 136, 472, 0])
    HT: list[int] = field(default_factory=lambda: [504, 3544, 1712, 80, 276, 280])
    HT2: list[int] = field(default_factory=lambda: [656, 920, 200, 1504, 552, 556])
    S: list[int] = field(default_factory=lambda: [1552, 80, 3448, 3440, 832, 3068])
    T: list[int] = field(default_factory=lambda: [504, 3544, 1712, 80, 40, 44])
    NTDP: list[int] = field(default_factory=lambda: [648])
    NTCP: list[int] = field(default_factory=lambda: [644])
    NTRI: list[int] = field(default_factory=lambda: [632])
    NTTR: list[int] = field(default_factory=lambda: [624])
    STDNAMEOFFSET176: list[int] = field(default_factory=lambda: [408, 48, 7393])
    STDNAMEOFFSET261: list[int] = field(default_factory=lambda: [296, 48, 13553])
    # Alternate final-leaf offsets for the same two struct chains. The scoreboard
    # stadium-name struct's layout apparently shifts with FIFA build/mod (FIP vs
    # vanilla vs total-conversion mods) -- STDNAMEOFFSET176/261 above are the
    # values confirmed against this project's own reference build, while these
    # "B" variants are the values a downstream contributor (Nono) confirmed
    # working against a different build/mod combination. Writing both leaves on
    # every scoreboardstdname update (see StadiumRuntime.write_active_stad_name)
    # costs nothing on a build where one pair is simply wrong (the pointer chain
    # still resolves to *some* writable address; write_string_with_offsets_safe
    # rejects it if it doesn't look like a short existing string) and fixes the
    # display on a build where the vanilla pair silently misses.
    STDNAMEOFFSET176B: list[int] = field(default_factory=lambda: [296, 48, 16633])
    STDNAMEOFFSET261B: list[int] = field(default_factory=lambda: [296, 48, 28337])
    # A third variant, found 2026-09-11 by directly diffing this project's
    # offsets.py against downstream contributor Nono's own fork
    # (D:\Proyectos\CGFS16_Python_Port\NonoServer\offsets.py). Nono's fork
    # ships STDNAMEOFFSET176B/261B with the exact same values as ours above
    # (already ported in, see the comment on those two) -- but his PRIMARY
    # STDNAMEOFFSET176/261 are [408, 48, 31109] / [296, 48, 40657], entirely
    # different final-leaf offsets from this project's own 7393/13553 (the
    # values `da2700a`, CLAUDE.md §7, tuned specifically for this project's
    # reference "fip" build after a wrong offset there corrupted memory and
    # crashed FIFA for certain teams -- a different bug from the
    # scoreboardstdname saga). That means the live 2026-09 investigation
    # (CLAUDE.md §7 "Part 1") which found writing to all FOUR of
    # 176/176B/261/261B had "zero visible effect" on the fip build never
    # actually tried Nono's own primary values -- only our own 176/261 and
    # his 176B/261B. Nono's build (a separate fork, separate .exe, used with
    # a different total-conversion mod set) reliably shows long custom
    # stadium names via this exact same STDNAMEBASE pointer-chain mechanism,
    # with NO memory scan needed at all (confirmed live 2026-09-11, comparing
    # against his fork's own runtime log) -- strong evidence his primary
    # offsets resolve to the ACTUAL render buffer on whatever memory layout
    # his build/mod produces. Worth trying directly against the fip
    # reference build as a genuinely untested candidate before assuming no
    # static chain reaches it there (CLAUDE.md §7 Part 14's own Cheat Engine
    # pointer-scan came up empty, but a targeted candidate from a build that
    # is KNOWN to work is stronger evidence than a blind, bounded scan).
    #
    # Tested live 2026-09-11 on the fip reference build: FALSIFIED. Both
    # slots were outright rejected -- "no NUL terminator within 256 bytes" --
    # meaning these offsets don't even resolve to a string-shaped buffer on
    # this build, let alone the render source. Confirms Nono's build/mod
    # genuinely has a different memory layout for this struct, not just a
    # different offset into the same one. Left in place (harmless: a
    # rejected write is a no-op, logged and skipped, same as any other slot
    # that doesn't apply to a given build) in case a *different* build/mod
    # combination matches Nono's layout instead of this project's own.
    STDNAMEOFFSET176C: list[int] = field(default_factory=lambda: [408, 48, 31109])
    STDNAMEOFFSET261C: list[int] = field(default_factory=lambda: [296, 48, 40657])
    # Known-safe low-16-bit suffixes for StadiumDbNamePatchCoordinator's
    # NUL-isolated "Waldstadion"/"Sanderson Park" scoreboard-name scan
    # (match_string_patcher.py). A scan for the vanilla name can turn up
    # MULTIPLE simultaneous isolated copies in memory -- confirmed live
    # 2026-09 to include at least one genuine decoy: writing even a few
    # bytes past that decoy's own footprint (into memory the OS reports as
    # "readable") corrupted something the engine reads/frees during match
    # teardown, crashing FIFA on leaving the match -- reproduced twice, with
    # writes of only 4 and 21 bytes past the vanilla name's own length. The
    # ACTUAL render-source buffer is a separate, specific copy: confirmed
    # directly with Cheat Engine (2026-09-10, re-confirmed 2026-09-11) that
    # editing it in place both (a) changes the on-screen pre-match stadium
    # name and (b) survives abandoning the match with no crash, even with a
    # replacement well over 11 characters. Its full address moves with ASLR
    # on every FIFA launch (0x9448989D / 0x944D989D / 0x9450989D / 0x9455989D
    # observed across separate sessions), but the low 16 bits are stable
    # across restarts for a given install/build -- heap segment placement is
    # randomized, but this allocation's offset *within* its segment is
    # deterministic given the same startup allocation sequence. Any isolated
    # occurrence whose address ends in one of these suffixes is treated as
    # confirmed-safe to extend past its own footprint (using
    # _probe_available_capacity's measured readable capacity); every other
    # occurrence is capped hard at its own base_capacity (old_name's length +
    # one terminator) regardless of how much extra the probe reports, since
    # "readable" alone was proven NOT to imply "safe to overwrite" for the
    # decoy(s). Only ever ADD a value here after live-confirming it the same
    # way (edit directly in Cheat Engine, confirm the display changes AND a
    # full match can be abandoned/completed with no crash) -- never guess one
    # in from a single scan log line, since an unconfirmed decoy address
    # looks identical to the real one in every way except this.
    #
    # 0x989D is slot 176's ("Waldstadion") confirmed buffer. 0xBCB5 is slot
    # 261's ("Sanderson Park") equivalent -- confirmed live 2026-09-11 the
    # same way (0x945DBCB5, both display-change and no-crash-on-abandon
    # verified by the user directly). A second slot-261 candidate seen in the
    # same session, 0x9550EEA6 (suffix 0xEEA6), was explicitly tested and
    # ruled out by the user -- deliberately NOT added here; if it resurfaces
    # in a future scan log, it is a known decoy for this slot, not an
    # oversight.
    STDNAME_SAFE_EXTEND_SUFFIXES: list[int] = field(default_factory=lambda: [0x989D, 0xBCB5])
    # Narrow address window(s) to scan FIRST when searching for the buffer
    # above, before falling back to the full (up to 4GB) process scan.
    # Derived from the four full addresses observed live for the 0x989D
    # suffix (0x9448989D / 0x944D989D / 0x9450989D / 0x9455989D) -- all four
    # cluster within about 0xD0000 (~850KB) of each other, consistent with
    # Windows heap-segment ASLR having bounded entropy for this allocation
    # on this install. This range (0x94000000-0x94800000, 8MB) covers all
    # four with generous margin for a future session landing slightly
    # outside the observed cluster. Found needed live 2026-09-11: a session
    # where the buffer only turned up on scan attempt 15/20 of a full scan,
    # ~20+ seconds after the bumper -- the match ended before that attempt's
    # result could even be used. Scanning ~8MB first costs milliseconds
    # versus the ~0.5-1s+ a full scan takes, turning "might get lucky within
    # the time budget" into "nearly instant" for this specific install. If
    # this install's cluster ever moves outside this window (a different
    # FIFA build/mod, a Windows update changing ASLR behavior, etc.), the
    # priority scan simply finds nothing and the code falls back to the
    # ordinary full scan exactly as before -- update this range after a
    # fresh live Cheat Engine confirmation, same rule as
    # STDNAME_SAFE_EXTEND_SUFFIXES above, never guessed in.
    STDNAME_SAFE_EXTEND_PRIORITY_RANGES: list[tuple[int, int]] = field(
        default_factory=lambda: [(0x94000000, 0x94800000)]
    )
    GAMESTARTEDBINARY: list[int] = field(default_factory=lambda: [560, 1592, 88, 16, 4056])
    GAMERANTIME: list[int] = field(default_factory=lambda: [5500])
    GAMEHOMEGOALSCORE: list[int] = field(default_factory=lambda: [5484])
    GAMEAWAYGOALSCORE: list[int] = field(default_factory=lambda: [5488])
    DASHBOARDSECONDSBASE: int = 57966104
    DASHBOARDMINUTESBASE: int = 57964464
    DASHBOARDHOMEIDBASE: int = 56705008
    DASHBOARDAWAYIDBASE: int = 57966104
    DASHBOARDHOMEGOALSBASE: int = 55425024
    DASHBOARDAWAYGOALSBASE: int = 56634592
    DASHBOARDSECONDS: list[int] = field(default_factory=lambda: [648, 536, 72, 3640, 2456, 1296])
    DASHBOARDMINUTES: list[int] = field(default_factory=lambda: [40])
    DASHBOARDHOMEID: list[int] = field(default_factory=lambda: [104, 2112, 16, 24, 3472])
    DASHBOARDAWAYID: list[int] = field(default_factory=lambda: [1004])
    DASHBOARDHOMEGOALS: list[int] = field(default_factory=lambda: [56, 2984, 1092])
    DASHBOARDAWAYGOALS: list[int] = field(default_factory=lambda: [240, 360, 216, 1444])

    # --- Substitution-count hook (see D:\Proyectos\CGFS16_Python_Port\5-sub\
    # fifa16-sustituciones-5-contexto.md for the full reverse-engineering session). SUBHOOKRVA
    # is the ONLY code location confirmed safe to patch — a nearby instruction (+0x4B8998A) was
    # confirmed in testing to crash the game if patched/breakpointed, and to be silently
    # reverted by FIFA's anti-tamper protection otherwise. Never repoint this feature at that or
    # any other unverified address. Do not change these values without re-verifying against a
    # live FIFA16.exe and documenting why (project hard rule, see CLAUDE.md).
    SUBHOOKRVA: int = 0x4B8D3E6  # `mov [r12+r14+0xB03C], eax` (8 bytes) — patched with jmp+3 nop
    SUBREADOFFSET: int = 0xA78C  # struct-relative offset of the "rules" value (= 0xB03C - 0x8B0)
    SUBHOOKORIGBYTES: list[int] = field(
        default_factory=lambda: [0x43, 0x89, 0x84, 0x34, 0x3C, 0xB0, 0x00, 0x00]
    )  # expected original bytes at base_module+SUBHOOKRVA; verified before every install

    @classmethod
    def load(cls) -> "Offsets":
        return cls()

    def is_configured(self) -> bool:
        scalar_values = [
            self.ORIPGBASE,
            self.ORIHTIDBASE,
            self.ORITOURIDBASE,
            self.ORISTADIDBASE,
            self.ORIFRIHTIDBASE,
            self.ORINETDEPTHBASE,
            self.STDNAMEBASE,
            self.GAMESTARTEDBINARYBASE,
            self.GAMESTATSBASE,
            self.DASHBOARDSECONDSBASE,
            self.DASHBOARDMINUTESBASE,
            self.DASHBOARDHOMEIDBASE,
            self.DASHBOARDAWAYIDBASE,
            self.DASHBOARDHOMEGOALSBASE,
            self.DASHBOARDAWAYGOALSBASE,
        ]
        list_values = [
            self.PG1,
            self.HT,
            self.HT2,
            self.S,
            self.T,
            self.NTDP,
            self.NTCP,
            self.NTRI,
            self.NTTR,
            self.STDNAMEOFFSET176,
            self.STDNAMEOFFSET261,
            self.STDNAMEOFFSET176B,
            self.STDNAMEOFFSET261B,
            self.STDNAMEOFFSET176C,
            self.STDNAMEOFFSET261C,
            self.GAMESTARTEDBINARY,
            self.GAMERANTIME,
            self.GAMEHOMEGOALSCORE,
            self.GAMEAWAYGOALSCORE,
            self.DASHBOARDSECONDS,
            self.DASHBOARDMINUTES,
            self.DASHBOARDHOMEID,
            self.DASHBOARDAWAYID,
            self.DASHBOARDHOMEGOALS,
            self.DASHBOARDAWAYGOALS,
        ]
        if any(value != 0 for value in scalar_values):
            return True
        return any(any(item != 0 for item in values) for values in list_values)
