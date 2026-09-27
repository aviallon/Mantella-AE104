# Mantella — SKSE Plugins (AE 1.7.104)

The four SKSE plugin DLLs of [Mantella](https://www.nexusmods.com/skyrimspecialedition/mods/98631)
rebuilt from their upstream C++ sources against **CommonLibSSE-NG 6.8.0**, for
the Skyrim SE/AE runtime **1.7.104** — packaged as a clean **FOMOD override** of
the base mod.

## Why

The DLLs shipped with Mantella-Spell (Nexus 98631) were built against a
2022-era CommonLibSSE-NG (the `colorglass` vcpkg registry the upstream projects
pin is frozen at 3.6/3.7). That address-library reader cannot parse the **V5**
bins shipped with runtime 1.7.104 (`versionlib-1-7-104-0.bin`), so the plugins
fail at load with *"Unsupported address library format"* / *"incompatible with
the address library available for this version of the game"*. Nothing else is
runtime-specific in them: `RuntimeCompatibility = AddressLibrary` all the way.

## What is in the package

| DLL | upstream source (pinned) | fixups |
|---|---|---|
| `SKSE_HTTP.dll` | [Leidtier/SKSE_HTTP](https://github.com/Leidtier/SKSE_HTTP) | `patches/SKSE_HTTP-*` |
| `MantellaDialogue.dll` | [mikastamm/mantella-vanilla-dialogue](https://github.com/mikastamm/mantella-vanilla-dialogue) | — |
| `MantellaLauncher.dll` | [art-from-the-machine/Mantella-SKSE-Launcher](https://github.com/art-from-the-machine/Mantella-SKSE-Launcher) | — |
| `MantellaSubtitles.dll` | [swwu/Mantella-Subtitles-Plugin-NG](https://github.com/swwu/Mantella-Subtitles-Plugin-NG) | `patches/Mantella-Subtitles-Plugin-NG-*` |

## Install

1. Install the **base Mantella mod** (Nexus 98631) — keep it enabled, it ships
   `Mantella.esp`, the Papyrus scripts and `MantellaSoftware/`.
2. Install this package **after** it (MO2 / Amethyst / any manager, FOMOD or
   plain unzip — the payload sits at the archive root either way).
3. The four plugins must then load without any "address library" complaint in
   the SKSE log (`…/Documents/My Games/Skyrim Special Edition/SKSE/skse64.log`).

## Build

CI builds on `windows-latest` with MSVC + vcpkg (`.github/workflows/build.yml`),
fetches the pinned upstream sources, applies `patches/`, builds against the
overlay port `ports/commonlibsse-ng` (CLNG 6.8.0 from source), verifies each PE
(`tools/verify-dll.py`), and packages the FOMOD (`tools/package.py`).

Locally (Linux, no MSVC/Wine) the same pipeline runs through clang-cl + an xwin
sysroot: `tools/build.sh <plugin-src-dir>`. See `research/notes.md` for the
diagnosis and the portability pitfalls.

## Verification

`tools/verify-dll.py` parses the `SKSEPlugin_Version` export (name, version,
`StructCompatibility`, `RuntimeCompatibility = AddressLibrary`) and asserts the
Address Library **V5 reader** strings are present. `tools/package.py` refuses to
package when a FOMOD `source=` is not a regular file in the archive (a directory
reference installs as "0 items" and fails silently in Amethyst).
