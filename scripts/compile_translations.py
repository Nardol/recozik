"""Compile gettext catalogs (PO -> MO) for recozik."""

from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

try:  # pragma: no cover - optional dependency
    import polib  # type: ignore
except ImportError:  # pragma: no cover - fallback path
    polib = None

ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = ROOT / "packages" / "recozik-core" / "src" / "recozik_core" / "locales"


def _parse_po(path: Path) -> dict[str, str]:
    messages: dict[str, str] = {}
    msgid_parts: list[str] = []
    msgstr_parts: list[str] = []
    state: str | None = None
    fuzzy = False

    def _flush() -> None:
        nonlocal msgid_parts, msgstr_parts, fuzzy
        if msgid_parts and not fuzzy:
            raw_id = "".join(msgid_parts)
            raw_str = "".join(msgstr_parts)
            msgid = bytes(raw_id, "utf-8").decode("unicode_escape")
            msgstr = bytes(raw_str, "utf-8").decode("unicode_escape")
            messages[msgid] = msgstr
        msgid_parts = []
        msgstr_parts = []
        fuzzy = False

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
                continue
            if line.startswith("#"):
                continue
            if line.startswith("msgid "):
                _flush()
                state = "msgid"
                msgid_parts = [line[6:].strip().strip('"')]
                continue
            if line.startswith("msgstr "):
                state = "msgstr"
                msgstr_parts = [line[7:].strip().strip('"')]
                continue
            if line == "":
                _flush()
                state = None
                continue
            if line.startswith('"'):
                fragment = line.strip('"')
                if state == "msgid":
                    msgid_parts.append(fragment)
                elif state == "msgstr":
                    msgstr_parts.append(fragment)
    _flush()
    return messages


def _compile_to_mo(po_file: Path, mo_file: Path) -> None:
    msgfmt = shutil.which("msgfmt")
    if msgfmt:
        subprocess.run([msgfmt, "-o", str(mo_file), str(po_file)], check=True)  # noqa: S603
        return
    if polib is not None:
        polib.pofile(str(po_file)).save_as_mofile(str(mo_file))
        return

    catalog = _parse_po(po_file)
    keys = sorted(catalog)
    key_data = b""
    val_data = b""
    key_entries: list[tuple[int, int]] = []
    val_entries: list[tuple[int, int]] = []

    for key in keys:
        encoded = key.encode("utf-8") + b"\0"
        key_entries.append((len(encoded), len(key_data)))
        key_data += encoded

    for key in keys:
        encoded = catalog[key].encode("utf-8") + b"\0"
        val_entries.append((len(encoded), len(val_data)))
        val_data += encoded

    keystart = 7 * 4
    key_table = []
    val_table = []
    for length, offset in key_entries:
        key_table.append(struct.pack("II", length, keystart + 16 * len(keys) + offset))
    value_base = keystart + 16 * len(keys) + len(key_data)
    for length, offset in val_entries:
        val_table.append(struct.pack("II", length, value_base + offset))

    header = struct.pack("IIIIII", 0x950412DE, 0, len(keys), keystart, keystart + len(keys) * 8, 0)

    with mo_file.open("wb") as handle:
        handle.write(header)
        handle.write(b"".join(key_table))
        handle.write(b"".join(val_table))
        handle.write(key_data)
        handle.write(val_data)


def compile_locales() -> None:
    """Compile every available gettext catalogue into its binary `.mo` file."""
    for po_file in LOCALES_DIR.rglob("*.po"):
        mo_file = po_file.with_suffix(".mo")
        _compile_to_mo(po_file, mo_file)
        print(f"Compiled {mo_file.relative_to(ROOT)}")


if __name__ == "__main__":  # pragma: no cover - CLI helper
    compile_locales()
