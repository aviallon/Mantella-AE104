#!/usr/bin/env python3
"""Package the rebuilt SKSE plugin DLLs as a FOMOD override zip.

Installable AFTER the base Mantella mod in MO2 / Amethyst (or any manager that
extracts a plain zip: the payload sits at the archive root either way).

    tools/package.py               # -> ~/Téléchargements/Mantella-AE1.7.104-...zip
    OUTDIR=... VERSION=... WORK=... tools/package.py

Python stdlib on purpose: the same script packages on a workstation and in CI,
and the guards below are the reason it exists as a script at all.

Guards (learned the hard way):
  * every FOMOD `source=` must be a regular FILE in the archive — a directory
    reference is not an error for Amethyst's installer, it silently copies
    "0 item(s)" and then dies on the missing staging dir;
  * every archive entry must sit under `fomod/` or `SKSE/`.
"""

import hashlib
import os
import re
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get("WORK", "/tmp/mantella-build"))
OUTDIR = Path(os.environ.get("OUTDIR", Path.home() / "Téléchargements"))
VERSION = os.environ.get("VERSION", date.today().strftime("%Y%m%d"))
NAME = os.environ.get("PKGNAME", "Mantella-AE1.7.104-SKSE-Plugins-fixed")

DLLS = ["SKSE_HTTP", "MantellaDialogue", "MantellaLauncher", "MantellaSubtitles"]


def main() -> int:
    out = OUTDIR / f"{NAME}.zip"
    OUTDIR.mkdir(parents=True, exist_ok=True)

    files: dict[str, Path] = {}
    for xml in ("fomod/ModuleConfig.xml", "fomod/info.xml"):
        p = REPO / xml
        if p.exists():
            files[xml] = p
    for dll in DLLS:
        built = WORK / "out" / f"{dll}.dll"
        if not built.is_file():
            print(f"FATAL: {dll}.dll not built (run tools/build.sh first)", file=sys.stderr)
            return 1
        files[f"SKSE/Plugins/{dll}.dll"] = built

    # Guard 1: every FOMOD source must be a file we are actually shipping.
    config = (REPO / "fomod/ModuleConfig.xml").read_text(encoding="utf-8")
    for src in sorted(set(re.findall(r'source="([^"]+)"', config))):
        if src not in files:
            print(f"FATAL: fomod source is missing or not a regular file: {src}", file=sys.stderr)
            return 1

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, path in sorted(files.items()):
            z.write(path, name)

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        # Guard 2: the layout itself.
        bad = [n for n in names if not (n.startswith("fomod/") or n.startswith("SKSE/"))]
        if bad:
            print(f"FATAL: unexpected archive entries: {bad}", file=sys.stderr)
            return 1

    report = [f"# {NAME}", f"Built: {datetime.now().isoformat(timespec='seconds')}", "",
              "| file | sha256 |", "|---|---|"]
    for name, path in sorted(files.items()):
        if name.endswith(".dll"):
            report.append(f"| {name} | {hashlib.sha256(path.read_bytes()).hexdigest()} |")
    report += ["", f"zip: {hashlib.sha256(out.read_bytes()).hexdigest()}  ({out})", ""]
    with (REPO / "research" / "shipping.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(report))

    print(f"OK: {out}")
    for n in sorted(files):
        print(f"  {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
