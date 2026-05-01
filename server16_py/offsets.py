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
