---
paths:
  - "server16_py/stadium_runtime.py"
  - "server16_py/file_tools.py"
  - "server16_py/asset_runtime.py"
  - "server16_py/net_mesh.py"
  - "tests/test_stadium_runtime.py"
  - "tests/test_file_tools.py"
---
Stadium / asset file installation. Read `docs/stadium-slots.md`; goalposts/nets `docs/bugs-goalpost.md`.
- Only two engine slots, `176`/`261`, ping-ponged by `file_tools.inc_count`/`set_inj_id`. Write
  `ORISTADIDBASE` only after the copy is verified. Idle slot is restored to vanilla, never emptied.
- FIFA never re-reads a path it already resolved in a session: per-stadium variants are installed under
  slot-specific `specific*_0_{injid}` names (net color, goalpost packs, net mesh). Reuse that pattern
  before considering any memory patch.
- Copy/clear pairs go through `file_tools.py` manifest helpers so cleanup stays symmetric; no raw `shutil`.
- Archives extract into `runtime/` temp folders and are always removed afterwards.
- One stadium load per match preparation (KickOffHub revisits don't re-apply) — see `stadium-slots.md`.
