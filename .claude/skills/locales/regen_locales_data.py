"""Regenerate server16_py/locales_data.py from server16_py/locales/{en,es,pt}.json.

Byte-identical to the checked-in file when the JSONs are unchanged (CRLF, utf-8), so a diff after
running it shows only the keys you added.

Usage:
  python .claude/skills/locales/regen_locales_data.py           # regenerate
  python .claude/skills/locales/regen_locales_data.py --check   # exit 1 if locales_data.py is stale
  python .claude/skills/locales/regen_locales_data.py --hook    # PostToolUse hook: reads the hook JSON
                                                                # on stdin, acts only for locales/*.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PKG = REPO / "server16_py"
LANGS = ("en", "es", "pt")


def render() -> bytes:
    out = ["from __future__ import annotations", "", "LOCALE_CATALOGS = {"]
    for lang in LANGS:
        cat = json.loads((PKG / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        out.append(f"    {lang!r}: {cat!r},")
    out.append("}")
    return ("\r\n".join(out) + "\r\n").encode("utf-8")


def missing_keys() -> dict[str, list[str]]:
    cats = {
        lang: json.loads((PKG / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        for lang in LANGS
    }
    en = set(cats["en"])
    return {lang: sorted(en - set(cats[lang])) for lang in LANGS if lang != "en"}


def main(argv: list[str]) -> int:
    target = PKG / "locales_data.py"
    if "--hook" in argv:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            return 0
        path = str((payload.get("tool_input") or {}).get("file_path", "")).replace("\\", "/").lower()
        if "/server16_py/locales/" not in path or not path.endswith(".json"):
            return 0
    try:
        data = render()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"locales_data.py NOT regenerated: {exc}", file=sys.stderr)
        return 2  # surfaces the error to Claude in hook mode
    current = target.read_bytes() if target.exists() else b""
    if "--check" in argv:
        if current != data:
            print("locales_data.py is stale; run regen_locales_data.py", file=sys.stderr)
            return 1
        print("locales_data.py is up to date")
        return 0
    if current != data:
        target.write_bytes(data)
        print("locales_data.py regenerated")
    else:
        print("locales_data.py already up to date")
    if "--hook" not in argv:
        for lang, keys in missing_keys().items():
            if keys:
                print(f"{lang}.json lacks {len(keys)} en key(s) (falls back to en)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
