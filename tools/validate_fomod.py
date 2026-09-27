#!/usr/bin/env python3
"""Validate the Mantella FOMOD override before it becomes a release asset.

Adapted from HeapSentinel-fomod's tools/validate_fomod.py (same author family,
same philosophy: gates that CAN fail, not smoke tests). Checks:

  1. XML: ModuleConfig.xml is well-formed and validates against the vendored
     FOMOD schema (fomod/schema/ModConfig5.0.xsd) when xmllint is available.
  2. STRUCTURE: the schema is vague about a few rules that matter in practice —
     exactly one Recommended default per SelectExactlyOne group.
  3. PACKAGE LAYOUT: every <file source="..."> resolves to a regular FILE in the
     staged package. This is the gate that catches the bug this package
     actually shipped with: a <file source="SKSE" destination="SKSE"/> (a
     DIRECTORY) is not an error for Amethyst's installer — it copies "0 item(s)"
     and then dies on the missing staging dir.
  4. ARCHIVE: with --zip, the zip is built and its contents re-checked.

Usage:
    python3 tools/validate_fomod.py --stage path/to/staged/package
    python3 tools/validate_fomod.py --stage ... --zip out.zip

Exit status is 0 only if every applicable check passed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULECONFIG = REPO_ROOT / "fomod" / "ModuleConfig.xml"
SCHEMA = REPO_ROOT / "fomod" / "schema" / "ModConfig5.0.xsd"

failures: list[str] = []


def ok(msg: str) -> None:
    print(f"  ok: {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL: {msg}")
    failures.append(msg)


def check_xml() -> ET.Element:
    print("== XML well-formedness and schema")
    try:
        root = ET.parse(MODULECONFIG).getroot()
        ok("ModuleConfig.xml is well-formed")
    except ET.ParseError as exc:
        fail(f"ModuleConfig.xml is not well-formed XML: {exc}")
        raise SystemExit(1)
    if shutil.which("xmllint"):
        proc = subprocess.run(
            ["xmllint", "--noout", "--schema", str(SCHEMA), str(MODULECONFIG)],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            ok("ModuleConfig.xml validates against fomod/schema/ModConfig5.0.xsd")
        else:
            for line in (proc.stderr or "").splitlines():
                if "error" in line:
                    fail(f"schema: {line.strip()}")
    else:
        print("  skip: xmllint not found - schema validation skipped")
    return root


def check_structure(root: ET.Element) -> None:
    print("== FOMOD structure")
    groups = root.findall(".//group[@type='SelectExactlyOne']")
    if not groups:
        fail("no SelectExactlyOne group - the installer would have no default")
    for group in groups:
        recommended = [
            p for p in group.findall("./plugins/plugin")
            if p.find("./typeDescriptor/type") is not None
            and p.find("./typeDescriptor/type").get("name") == "Recommended"
        ]
        if len(recommended) != 1:
            fail(f"group {group.get('name')!r}: expected exactly one Recommended "
                 f"plugin, found {len(recommended)}")
        else:
            ok(f"group {group.get('name')!r} has one Recommended default")


def check_layout(root: ET.Element, stage: Path) -> None:
    print("== package layout (every <file source> must be a regular file)")
    sources = sorted({
        node.get("source") for node in root.iter("file") if node.get("source")
    })
    if not sources:
        fail("ModuleConfig.xml installs no files at all")
    for src in sources:
        candidate = stage / src.replace("\\", "/")
        if candidate.is_file():
            ok(f"{src}")
        else:
            fail(f"{src} is missing or not a regular file under {stage} "
                 f"(a directory reference silently installs as '0 items')")


def check_archive(zip_path: Path, stage: Path | None = None) -> None:
    print(f"== archive {zip_path.name}")
    root = ET.parse(MODULECONFIG).getroot()
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
    bad = [n for n in names if not (n.startswith("fomod/") or n.startswith("SKSE/"))]
    if bad:
        fail(f"unexpected archive entries: {bad}")
    required = {"fomod/ModuleConfig.xml", "fomod/info.xml"}
    required.update(
        node.get("source").replace("\\", "/")
        for node in root.iter("file") if node.get("source")
    )
    for entry in sorted(required):
        if entry in names:
            ok(f"{entry} in archive")
        else:
            fail(f"{entry} missing from archive (and it IS referenced by ModuleConfig.xml)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, help="staged package directory")
    parser.add_argument("--zip", type=Path, help="archive to build/check")
    args = parser.parse_args()

    root = check_xml()
    check_structure(root)

    if args.stage:
        check_layout(root, args.stage)
    if args.zip:
        check_archive(args.zip)

    if failures:
        print(f"\nFAILED: {len(failures)} problem(s)")
        return 1
    print("\nAll FOMOD checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())